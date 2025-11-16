"""
AI Trading Analyst powered by Massive.com MCP + Claude 4

Combines institutional-grade market data from Massive.com with Claude 4's
reasoning capabilities and MarketPulse's technical analysis systems.

Features:
- Natural language queries for market analysis
- Real-time and historical data from Massive.com
- Integration with divergence detection, ICT analysis, risk management
- AI-powered trade recommendations with risk validation
"""

import os
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass

from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.mcp import MCPServerStdio
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from loguru import logger

# Import our existing analysis systems
from src.analysis.divergence_detector import scan_for_divergences
from src.analysis.ict_analyzer import ICTAnalyzer
from src.analysis.risk_manager import RiskManager
from src.analysis.technical_indicators import TechnicalIndicators, identify_trends


console = Console()


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
    AI Trading Analyst using Massive.com data + Claude 4

    Combines:
    - Massive.com's institutional-grade market data (via MCP server)
    - Claude 4's advanced reasoning
    - MarketPulse's technical analysis (divergences, ICT, risk management)
    """

    def __init__(
        self,
        massive_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None
    ):
        """
        Initialize AI analyst

        Args:
            massive_api_key: Massive.com API key (or from env MASSIVE_API_KEY)
            anthropic_api_key: Anthropic API key (or from env ANTHROPIC_API_KEY)
        """
        self.massive_api_key = massive_api_key or os.getenv('MASSIVE_API_KEY')
        self.anthropic_api_key = anthropic_api_key or os.getenv('ANTHROPIC_API_KEY')

        if not self.massive_api_key:
            logger.warning("No Massive.com API key found - MCP server features disabled")

        if not self.anthropic_api_key:
            raise ValueError("Anthropic API key required (set ANTHROPIC_API_KEY)")

        # Initialize our technical analysis systems
        self.risk_manager = RiskManager()
        self.ict_analyzer = ICTAnalyzer()

        # Message history for conversation context
        self.message_history = []

        # Initialize agent (will be set in create_agent)
        self.agent = None

        logger.info("MassiveAIAnalyst initialized")

    def create_massive_mcp_server(self) -> Optional[MCPServerStdio]:
        """
        Create Massive.com MCP server connection

        Returns:
            MCP server instance or None if API key missing
        """
        if not self.massive_api_key:
            return None

        # Environment for MCP server
        env = os.environ.copy()
        env['MASSIVE_API_KEY'] = self.massive_api_key

        logger.info("Creating Massive.com MCP server connection")

        return MCPServerStdio(
            command="uvx",
            args=[
                "--from",
                "git+https://github.com/massive-com/mcp_massive@v0.4.0",
                "mcp_massive"
            ],
            env=env
        )

    async def create_agent(self) -> Agent:
        """
        Create Pydantic AI agent with Claude 4 + Massive.com tools

        Returns:
            Configured AI agent
        """
        # Create MCP server if we have API key
        mcp_servers = []
        server = self.create_massive_mcp_server()
        if server:
            mcp_servers.append(server)
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
            model="anthropic:claude-sonnet-4-20250514",  # Claude 4 Sonnet
            mcp_servers=mcp_servers,
            system_prompt=system_prompt
        )

        logger.info("AI agent created with Claude 4")
        return self.agent

    async def analyze_with_marketpulse(
        self,
        symbol: str,
        context: TradingContext
    ) -> Dict[str, Any]:
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
            # Get historical data (using yfinance for now, will be replaced by Massive.com)
            from src.api.yahoo_client import YahooFinanceClient
            client = YahooFinanceClient()
            df = client.get_historical_data(symbol, period=context.period, interval=context.timeframe)

            if df.empty:
                return {"error": f"No data found for {symbol}"}

            # 1. Divergence Detection
            divergences = scan_for_divergences(df, min_strength=70.0)

            # 2. Technical Indicators & Trends
            df_with_indicators = TechnicalIndicators.calculate_all(df)
            trends = identify_trends(df_with_indicators)

            # 3. ICT Analysis
            ict_analysis = {
                'fvgs': self.ict_analyzer.detect_fair_value_gaps(df),
                'order_blocks': self.ict_analyzer.detect_order_blocks(df),
                'liquidity': self.ict_analyzer.detect_liquidity_pools(df)
            }

            # 4. Current price and key levels
            current_price = float(df['close'].iloc[-1])
            recent_high = float(df['high'].iloc[-20:].max())
            recent_low = float(df['low'].iloc[-20:].min())

            # 5. Combine into analysis
            analysis = {
                'symbol': symbol,
                'current_price': current_price,
                'timeframe': context.timeframe,
                'period': context.period,
                'divergences': {
                    'total': divergences['total_divergences'],
                    'signal': divergences['signal'],
                    'by_type': divergences['by_type'],
                    'strongest': divergences['strongest'],
                    'list': divergences['divergences'][:3]  # Top 3
                },
                'trends': trends,
                'ict': {
                    'bullish_fvgs': len(ict_analysis['fvgs']['bullish']),
                    'bearish_fvgs': len(ict_analysis['fvgs']['bearish']),
                    'order_blocks': len(ict_analysis['order_blocks']),
                    'liquidity_pools': len(ict_analysis['liquidity'])
                },
                'key_levels': {
                    'current': current_price,
                    'recent_high': recent_high,
                    'recent_low': recent_low,
                    'range': recent_high - recent_low
                }
            }

            logger.info(f"MarketPulse analysis complete for {symbol}")
            return analysis

        except Exception as e:
            logger.error(f"Error in MarketPulse analysis: {e}")
            return {"error": str(e)}

    async def validate_trade(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        direction: str,
        contracts: int = 1
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
            contracts=contracts
        )

        return {
            'approved': validation.approved,
            'reason': validation.reason,
            'risk_amount': validation.risk_amount,
            'reward_amount': validation.reward_amount,
            'risk_reward_ratio': validation.risk_reward_ratio,
            'position_size': validation.position_size,
            'details': validation.details
        }

    async def query(
        self,
        question: str,
        context: Optional[TradingContext] = None,
        include_technical_analysis: bool = True
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
            # Try to extract symbol
            import re
            symbols = re.findall(r'\b[A-Z]{1,5}\b', question.upper())
            if symbols:
                context = TradingContext(symbol=symbols[0])

        # Get technical analysis if requested and we have context
        tech_analysis = None
        if include_technical_analysis and context:
            tech_analysis = await self.analyze_with_marketpulse(context.symbol, context)

            # Add technical analysis to question
            if 'error' not in tech_analysis:
                question += f"\n\nMarketPulse Technical Analysis for {context.symbol}:\n"
                question += f"- Current Price: ${tech_analysis['current_price']:.2f}\n"
                question += f"- Divergence Signal: {tech_analysis['divergences']['signal']}\n"
                question += f"- Total Divergences: {tech_analysis['divergences']['total']}\n"

                if tech_analysis['divergences']['strongest']:
                    strongest = tech_analysis['divergences']['strongest']
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
            response = await self.agent.run(
                question,
                message_history=self.message_history
            )

            # Update message history
            self.message_history.append({
                'role': 'user',
                'content': question
            })
            self.message_history.append({
                'role': 'assistant',
                'content': response.data
            })

            # Keep only last 10 messages
            if len(self.message_history) > 10:
                self.message_history = self.message_history[-10:]

            return response.data

        except Exception as e:
            logger.error(f"Error querying AI analyst: {e}")
            return f"Error: {str(e)}"

    async def get_trade_recommendation(
        self,
        symbol: str,
        context: Optional[TradingContext] = None
    ) -> Dict[str, Any]:
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

        return {
            'symbol': symbol,
            'recommendation': response,
            'timestamp': datetime.now().isoformat()
        }

    def display_response(self, response: str, title: str = "AI Trading Analyst"):
        """Display AI response with rich formatting"""
        console.print(Panel(
            Markdown(response),
            title=f"[bold cyan]{title}[/bold cyan]",
            border_style="cyan"
        ))

    async def interactive_session(self):
        """Run interactive Q&A session"""
        console.print(Panel(
            "[bold green]AI Trading Analyst[/bold green]\n\n"
            "Powered by Massive.com + Claude 4 + MarketPulse\n\n"
            "Ask questions about markets, get trade recommendations, or analyze symbols.\n"
            "Type 'exit' to quit.",
            border_style="green"
        ))

        # Create agent
        await self.create_agent()

        while True:
            # Get user input
            console.print()
            question = console.input("[bold yellow]You:[/bold yellow] ")

            if question.lower() in ['exit', 'quit', 'q']:
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


if __name__ == '__main__':
    asyncio.run(main())
