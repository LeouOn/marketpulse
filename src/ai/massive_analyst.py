"""
AI Trading Analyst powered by Massive.com MCP + the app's configured LLM

Combines institutional-grade market data from Massive.com with the reasoning
capability of whichever provider the app is configured to use (MiniMax by
default) and MarketPulse's technical analysis systems.

Features:
- Natural language queries for market analysis
- Real-time and historical data from Massive.com
- Integration with divergence detection, ICT analysis, risk management
- AI-powered trade recommendations with risk validation
"""

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from fastmcp.client.transports import StdioTransport
from loguru import logger
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

# Import our existing analysis systems
from src.analysis.divergence_detector import scan_for_divergences
from src.analysis.ict_concepts import ICTAnalyzer
from src.analysis.risk_manager import RiskManager
from src.analysis.technical_indicators import TechnicalIndicators, identify_trends
from src.core.keys import _usable

console = Console()


def _flatten_yahoo_bars(df):
    """Drop yfinance's ticker column level. Empty in, empty out."""
    if df is None or getattr(df, "empty", True):
        return df
    out = df
    columns = out.columns
    if getattr(columns, "nlevels", 1) > 1:
        out = out.copy()
        out.columns = [col[0] if isinstance(col, tuple) else col for col in out.columns]
        columns = out.columns
    if columns.duplicated().any():
        out = out.loc[:, ~columns.duplicated()]
    return out


@dataclass(frozen=True)
class ProviderSpec:
    """The LLM the analyst should talk to, resolved from app configuration."""

    name: str
    base_url: str
    api_key: str
    model: str
    env_var: str


# OpenRouter's config block has no model field, so mirror the default the rest of
# the app already uses for that provider.
_OPENROUTER_DEFAULT_MODEL = "openai/gpt-4o-mini"


def _select_provider(settings) -> ProviderSpec:
    """Map the configured provider name to its connection details.

    No key validation happens here: this is the reporting path (e.g.
    ``/api/ai/status``), which must be able to name the provider even when the
    key is missing or an unresolved placeholder.
    """
    llm = settings.llm
    name = (llm.model_routing.primary_provider or "").strip().lower()

    if name == "minimax":
        cfg = llm.minimax
        return ProviderSpec(name, cfg.base_url, cfg.api_key, cfg.model, "MINIMAX_API_KEY")
    if name == "deepseek":
        cfg = llm.deepseek
        return ProviderSpec(name, cfg.base_url, cfg.api_key, cfg.model_pro, "DEEPSEEK_API_KEY")
    if name == "openrouter":
        cfg = llm.fallback
        return ProviderSpec(name, cfg.base_url, cfg.api_key, _OPENROUTER_DEFAULT_MODEL, "OPENROUTER_API_KEY")
    if name in ("lm_studio", "local", "primary"):
        cfg = llm.primary
        return ProviderSpec(name, cfg.base_url, cfg.api_key, cfg.model, "(no key needed for a local model)")
    raise ValueError(
        f"Unsupported llm.model_routing.primary_provider={name!r}; "
        f"expected one of: minimax, deepseek, openrouter, lm_studio"
    )


def _usable_provider_key(key: str | None) -> bool:
    """True iff the key is a real key, not empty or a placeholder.

    Mirrors ``src/core/keys.py::_usable`` (same helper): only keys that START
    with a placeholder marker (``your_...``) or an unresolved settings
    interpolation token (``${api_keys:...}``) are rejected. A key that merely
    contains ``your_`` mid-string is usable.
    """
    return _usable(key) is not None


def _resolve_provider(settings) -> ProviderSpec:
    """Pick the LLM the analyst uses: whatever the app is configured to use.

    Every provider the app supports speaks the OpenAI chat-completions API, so
    they differ only in host, key and model id. Reading the choice from
    ``llm.model_routing.primary_provider`` is what keeps the analyst from
    drifting back to a hard-coded vendor when the app's default changes.

    Raises ``ValueError`` when the configured key is unusable, so the query
    path fails up front with a clear message instead of sending a placeholder
    to the provider and surfacing its 401.
    """
    spec = _select_provider(settings)

    if not _usable_provider_key(spec.api_key):
        raise ValueError(
            f"{spec.name} API key required (set {spec.env_var}) -- the configured value is empty "
            f"or an unresolved placeholder such as '${{api_keys:{spec.name}:api_key}}'; the "
            f"analyst uses the app's configured LLM provider instead of a hard-coded Anthropic model"
        )
    if not (spec.model or "").strip():
        raise ValueError(
            f"No model id configured for provider {spec.name!r}; set the matching llm.<provider>.model value"
        )

    return spec


def _build_model(spec: ProviderSpec) -> OpenAIChatModel:
    """A pydantic-ai model bound to this provider's host and key."""
    return OpenAIChatModel(
        spec.model,
        provider=OpenAIProvider(base_url=spec.base_url, api_key=spec.api_key),
    )


def _to_model_messages(history: list[dict[str, str]]) -> list[ModelMessage]:
    """
    Rebuild pydantic-ai messages from the stored conversation history.

    pydantic-ai validates every history entry as a ModelMessage, so the plain
    dicts we keep between calls must be converted before being replayed.
    """
    messages: list[ModelMessage] = []
    for entry in history:
        role = entry["role"]
        content = entry["content"]
        if role == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content)]))
        elif role == "assistant":
            messages.append(ModelResponse(parts=[TextPart(content)]))
        else:
            # Never guess: a system or tool entry replayed as the wrong kind of
            # turn desyncs provider-side validation in ways that are hard to trace.
            raise ValueError(f"unexpected role in conversation history: {role!r}")
    return messages


@dataclass
class TradingContext:
    """Context for trading decisions"""

    symbol: str
    timeframe: str = "1d"
    period: str = "3mo"
    risk_per_trade: float = 0.02  # 2% risk
    account_size: float = 10000.0


class MassiveAIAnalyst:
    """
    AI Trading Analyst using Massive.com data + the configured LLM provider

    Combines:
    - Massive.com's institutional-grade market data (via MCP server)
    - the configured provider's reasoning (MiniMax by default)
    - MarketPulse's technical analysis (divergences, ICT, risk management)
    """

    def __init__(
        self,
        massive_api_key: Optional[str] = None,
        settings: Optional[Any] = None,
        provider: Optional[ProviderSpec] = None,
    ):
        """
        Initialize AI analyst

        Args:
            massive_api_key: Massive.com API key (or from env MASSIVE_API_KEY)
            settings: App settings; read from get_settings() when omitted
            provider: Override the resolved provider (mainly for tests)
        """
        from src.core.config import get_settings

        self.settings = settings or get_settings()

        # Follow the app's configured provider instead of demanding an Anthropic key.
        self.provider = provider or _resolve_provider(self.settings)
        self.model = _build_model(self.provider)

        self.massive_api_key = massive_api_key or os.getenv("MASSIVE_API_KEY")

        if not self.massive_api_key:
            logger.warning("No Massive.com API key found - MCP server features disabled")

        logger.info(f"AI analyst using {self.provider.name}/{self.provider.model}")

        # Initialize our technical analysis systems
        self.risk_manager = RiskManager()
        self.ict_analyzer = ICTAnalyzer()

        # Message history for conversation context
        self.message_history = []

        # Initialize agent (will be set in create_agent)
        self.agent = None

        logger.info("MassiveAIAnalyst initialized")

    def create_massive_mcp_server(self) -> Optional[MCPToolset]:
        """
        Create Massive.com MCP server connection

        Returns:
            MCP toolset instance or None if API key missing
        """
        if not self.massive_api_key:
            return None

        # Environment for MCP server
        env = os.environ.copy()
        env["MASSIVE_API_KEY"] = self.massive_api_key

        logger.info("Creating Massive.com MCP server connection")

        return MCPToolset(
            StdioTransport(
                command="uvx",
                args=["--from", "git+https://github.com/massive-com/mcp_massive@v0.4.0", "mcp_massive"],
                env=env,
            )
        )

    async def create_agent(self) -> Agent:
        """
        Create Pydantic AI agent with Claude 4 + Massive.com tools

        Returns:
            Configured AI agent
        """
        # Create MCP toolset if we have API key
        toolsets = []
        server = self.create_massive_mcp_server()
        if server:
            toolsets.append(server)
            logger.info("Massive.com MCP server enabled")
        else:
            logger.warning("Massive.com MCP server disabled (no API key)")

        # System prompt for trading analyst
        system_prompt = """
        You are an expert AI trading analyst with access to institutional-grade market data.

        Your capabilities:
        - Real-time and historical market data from Massive.com (via MCP tools)
        - Technical analysis: divergences, ICT concepts, indicators
        - Risk management validation
        - Trade recommendations with clear entry/exit/stop levels

        Guidelines:
        1. Always use the latest data available
        2. For dates, use the 'get_today_date' tool
        3. Prices from Massive are already split-adjusted
        4. Double-check all calculations
        5. Break complex queries into logical subtasks
        6. Be specific with entry, stop loss, and take profit levels
        7. Always validate trades against risk management rules
        8. Combine technical analysis (divergences, ICT) with market data
        9. Provide clear, actionable recommendations
        10. Explain your reasoning step-by-step

        Risk Management Rules:
        - Maximum 2% risk per trade
        - Minimum 1.5:1 reward-to-risk ratio
        - Maximum 3 consecutive losses before pause
        - Maximum daily loss: $500
        - Maximum portfolio heat: 6%

        When analyzing trades:
        1. Check for divergences (reversal signals)
        2. Identify ICT concepts (FVG, Order Blocks, Liquidity)
        3. Validate with risk management
        4. Provide specific price levels and position sizing

        Be precise, professional, and risk-conscious.
        """

        # Create agent
        self.agent = Agent(
            model=self.model,
            toolsets=toolsets,
            # `instructions=` is the pydantic-ai 2.x parameter. The legacy
            # `system_prompt=` still reaches the model, but as a separate
            # SystemPromptPart that bypasses instruction ids and caching.
            instructions=system_prompt,
        )

        logger.info(f"AI agent created on {self.provider.name}/{self.provider.model}")
        return self.agent

    async def analyze_with_marketpulse(self, symbol: str, context: TradingContext) -> Dict[str, Any]:
        """
        Run MarketPulse technical analysis

        Args:
            symbol: Stock symbol
            context: Trading context

        Returns:
            Technical analysis results
        """
        logger.info(f"Running MarketPulse analysis for {symbol}")

        try:
            # Yahoo bars. get_bars keeps a ticker level on the columns; flatten
            # it so close/high/low are Series. There is no get_historical_data.
            from src.api.yahoo_client import YahooFinanceClient

            client = YahooFinanceClient()
            df = _flatten_yahoo_bars(client.get_bars(symbol, period=context.period, interval=context.timeframe))

            if df is None or df.empty:
                return {"error": f"No data found for {symbol}"}

            # 1. Divergence Detection
            divergences = scan_for_divergences(df, min_strength=70.0)

            # 2. Technical Indicators & Trends
            df_with_indicators = TechnicalIndicators.calculate_all(df)
            trends = identify_trends(df_with_indicators)

            # 3. ICT Analysis
            ict_analysis = {
                "fvgs": self.ict_analyzer.detect_fair_value_gaps(df),
                "order_blocks": self.ict_analyzer.detect_order_blocks(df),
                "liquidity": self.ict_analyzer.detect_liquidity_pools(df),
            }

            # 4. Current price and key levels
            current_price = float(df["close"].iloc[-1])
            recent_high = float(df["high"].iloc[-20:].max())
            recent_low = float(df["low"].iloc[-20:].min())

            # 5. Combine into analysis
            analysis = {
                "symbol": symbol,
                "current_price": current_price,
                "timeframe": context.timeframe,
                "period": context.period,
                "divergences": {
                    "total": divergences["total_divergences"],
                    "signal": divergences["signal"],
                    "by_type": divergences["by_type"],
                    "strongest": divergences["strongest"],
                    "list": divergences["divergences"][:3],  # Top 3
                },
                "trends": trends,
                "ict": {
                    "bullish_fvgs": len(ict_analysis["fvgs"]["bullish"]),
                    "bearish_fvgs": len(ict_analysis["fvgs"]["bearish"]),
                    "order_blocks": len(ict_analysis["order_blocks"]),
                    "liquidity_pools": len(ict_analysis["liquidity"]),
                },
                "key_levels": {
                    "current": current_price,
                    "recent_high": recent_high,
                    "recent_low": recent_low,
                    "range": recent_high - recent_low,
                },
            }

            logger.info(f"MarketPulse analysis complete for {symbol}")
            return analysis

        except Exception as e:
            logger.error(f"Error in MarketPulse analysis: {e}")
            return {"error": str(e)}

    async def validate_trade(
        self, symbol: str, entry_price: float, stop_loss: float, take_profit: float, direction: str, contracts: int = 1
    ) -> Dict[str, Any]:
        """
        Validate trade with risk management

        Args:
            symbol: Symbol
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            direction: LONG or SHORT
            contracts: Number of contracts

        Returns:
            Validation result
        """
        logger.info(f"Validating {direction} trade for {symbol}")

        validation = self.risk_manager.validate_trade(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            direction=direction,
            contracts=contracts,
        )

        return {
            "approved": validation.approved,
            "reason": validation.reason,
            "warnings": validation.warnings,
            "risk_metrics": validation.risk_metrics,
            "suggested_contracts": validation.suggested_contracts,
        }

    async def query(
        self, question: str, context: Optional[TradingContext] = None, include_technical_analysis: bool = True
    ) -> str:
        """
        Query the AI analyst with natural language

        Args:
            question: Natural language question
            context: Trading context (optional)
            include_technical_analysis: Include MarketPulse analysis

        Returns:
            AI response
        """
        # Create agent if not exists
        if not self.agent:
            await self.create_agent()

        # Extract symbol from question if context not provided
        if not context and include_technical_analysis:
            import re

            STOPWORDS = {
                "I",
                "A",
                "AN",
                "THE",
                "IS",
                "IT",
                "IN",
                "ON",
                "AT",
                "TO",
                "OF",
                "AND",
                "OR",
                "FOR",
                "BUT",
                "NOT",
                "BE",
                "AS",
                "IF",
                "SO",
                "DO",
                "BY",
                "UP",
                "NO",
                "MY",
                "ME",
                "WE",
                "HE",
                "SHE",
                "AM",
                "ARE",
                "WAS",
                "HAS",
                "HAD",
                "HIS",
                "HER",
                "ITS",
                "OUR",
                "ALL",
                "ANY",
                "CAN",
                "GET",
                "GOT",
                "HOW",
                "OUT",
                "OWN",
                "SAY",
                "WHO",
                "DID",
                "DOES",
                "WHAT",
                "WHEN",
                "WITH",
                "FROM",
                "THAT",
                "THIS",
                "WILL",
                "HAVE",
                "BEEN",
                "EACH",
                "MAKE",
                "LIKE",
                "THAN",
                "INTO",
                "SOME",
                "COULD",
                "THEM",
                "THESE",
                "THOSE",
                "WOULD",
                "SHOULD",
                "ABOUT",
                "WHICH",
                "THEIR",
                "THERE",
                "WHERE",
                "AFTER",
                "BEFORE",
                "BETWEEN",
                "THROUGH",
                "DURING",
                "ABOVE",
                "BELOW",
                "MUCH",
                "MANY",
                "MORE",
                "MOST",
                "VERY",
                "JUST",
                "ALSO",
                "STILL",
                "EVEN",
                "ONLY",
                "THEN",
                "NOW",
                "HERE",
                "WHY",
                "ASK",
                "ANALYZE",
                "ANALYSIS",
                "ANALYZING",
                "GIVE",
                "SHOW",
                "TELL",
                "THINK",
                "KNOW",
                "TAKE",
                "COME",
                "GO",
                "BUY",
                "SELL",
                "LONG",
                "SHORT",
                "TRADE",
                "TRADING",
                "STOCK",
                "MARKET",
                "PRICE",
                "TARGET",
                "STOP",
                "LOSS",
                "PROFIT",
                "RISK",
                "POSITION",
                "RECOMMEND",
                "RECOMMENDATION",
                "PLEASE",
            }
            symbols = [s for s in re.findall(r"\b[A-Z]{1,5}\b", question.upper()) if s not in STOPWORDS]
            if symbols:
                context = TradingContext(symbol=symbols[0])

        # Get technical analysis if requested and we have context
        tech_analysis = None
        if include_technical_analysis and context:
            tech_analysis = await self.analyze_with_marketpulse(context.symbol, context)

            # Add technical analysis to question
            if "error" not in tech_analysis:
                question += f"\n\nMarketPulse Technical Analysis for {context.symbol}:\n"
                question += f"- Current Price: ${tech_analysis['current_price']:.2f}\n"
                question += f"- Divergence Signal: {tech_analysis['divergences']['signal']}\n"
                question += f"- Total Divergences: {tech_analysis['divergences']['total']}\n"

                if tech_analysis["divergences"]["strongest"]:
                    strongest = tech_analysis["divergences"]["strongest"]
                    question += f"- Strongest Divergence: {strongest['indicator'].upper()} "
                    question += f"{strongest['type'].replace('_', ' ').title()} "
                    question += f"(strength: {strongest['strength']:.0f})\n"

                question += f"- Trend (SMA): {tech_analysis['trends'].get('sma_trend', 'N/A')}\n"
                question += f"- Trend (MACD): {tech_analysis['trends'].get('macd_signal', 'N/A')}\n"
                question += f"- Recent High: ${tech_analysis['key_levels']['recent_high']:.2f}\n"
                question += f"- Recent Low: ${tech_analysis['key_levels']['recent_low']:.2f}\n"
                question += f"- Bullish FVGs: {tech_analysis['ict']['bullish_fvgs']}\n"
                question += f"- Bearish FVGs: {tech_analysis['ict']['bearish_fvgs']}\n"

        logger.info(f"Querying AI analyst: {question[:100]}...")

        try:
            # Run agent
            response = await self.agent.run(question, message_history=_to_model_messages(self.message_history))

            # Update message history
            self.message_history.append({"role": "user", "content": question})
            self.message_history.append({"role": "assistant", "content": response.output})

            # Keep only last 10 messages
            if len(self.message_history) > 10:
                self.message_history = self.message_history[-10:]

            return response.output

        except Exception as e:
            logger.error(f"Error querying AI analyst: {e}")
            return f"Error: {str(e)}"

    async def get_trade_recommendation(self, symbol: str, context: Optional[TradingContext] = None) -> Dict[str, Any]:
        """
        Get comprehensive trade recommendation

        Args:
            symbol: Stock symbol
            context: Trading context

        Returns:
            Trade recommendation with entry, stop, target, and risk validation
        """
        if not context:
            context = TradingContext(symbol=symbol)

        logger.info(f"Getting trade recommendation for {symbol}")

        # Build query
        query = f"""
        Analyze {symbol} and provide a complete trade recommendation.

        Include:
        1. Current market conditions and trend
        2. Key support/resistance levels
        3. Entry price (specific)
        4. Stop loss price (specific)
        5. Take profit target (specific)
        6. Direction (LONG or SHORT)
        7. Position size (number of contracts for futures or shares for stocks)
        8. Risk-reward ratio
        9. Timeframe for the trade
        10. Key factors supporting this trade
        11. Risks and what could invalidate the trade

        Be specific with exact prices. Consider the technical analysis provided.
        """

        # Get AI recommendation
        response = await self.query(query, context=context, include_technical_analysis=True)

        return {"symbol": symbol, "recommendation": response, "timestamp": datetime.now().isoformat()}

    def display_response(self, response: str, title: str = "AI Trading Analyst"):
        """Display AI response with rich formatting"""
        console.print(Panel(Markdown(response), title=f"[bold cyan]{title}[/bold cyan]", border_style="cyan"))

    async def interactive_session(self):
        """Run interactive Q&A session"""
        console.print(
            Panel(
                "[bold green]AI Trading Analyst[/bold green]\n\n"
                f"Powered by Massive.com + {self.provider.name} + MarketPulse\n\n"
                "Ask questions about markets, get trade recommendations, or analyze symbols.\n"
                "Type 'exit' to quit.",
                border_style="green",
            )
        )

        # Create agent
        await self.create_agent()

        while True:
            # Get user input
            console.print()
            question = console.input("[bold yellow]You:[/bold yellow] ")

            if question.lower() in ["exit", "quit", "q"]:
                console.print("[green]Goodbye![/green]")
                break

            if not question.strip():
                continue

            # Process query
            console.print()
            with console.status("[cyan]Thinking...[/cyan]"):
                response = await self.query(question)

            # Display response
            self.display_response(response)


async def main():
    """Main entry point for interactive session"""
    analyst = MassiveAIAnalyst()
    await analyst.interactive_session()


if __name__ == "__main__":
    asyncio.run(main())
