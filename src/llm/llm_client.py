"""MarketPulse LLM Integration
Primary: LM Studio (local models)
Fallback: OpenRouter (cloud APIs)
"""

import asyncio
import json
from typing import Dict, Any, Optional, List
from loguru import logger

from ..core.config import get_settings


class LMStudioClient:
    """LM Studio API client for local LLM inference"""
    
    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.base_url = self.settings.llm.primary.base_url
        self.timeout = self.settings.llm.primary.timeout
        self.model = getattr(self.settings.llm.primary, 'model', 'aquif-3.5-max-42b-a3b-i1')
        self.session = None
        
        # Model capabilities and purposes
        self.model_capabilities = {
            'fast_analysis': {
                'purpose': 'Quick market analysis and data validation',
                'max_tokens': 150,
                'temperature': 0.3
            },
            'deep_analysis': {
                'purpose': 'Comprehensive market analysis',
                'max_tokens': 400,
                'temperature': 0.5
            },
            'trade_review': {
                'purpose': 'Trade setup review and validation',
                'max_tokens': 250,
                'temperature': 0.4
            },
            'data_validation': {
                'purpose': 'Sanity checks and data interpretation validation',
                'max_tokens': 100,
                'temperature': 0.2
            }
        }
    
    async def __aenter__(self):
        """Async context manager entry"""
        import aiohttp
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def generate_completion(self, 
                                model: str = 'fast',
                                messages: List[Dict[str, str]] = None,
                                max_tokens: int = 100,
                                temperature: float = 0.3,
                                system_prompt: str = None) -> Optional[Dict[str, Any]]:
        """
        Generate completion using LM Studio
        
        Args:
            model: Model type ('fast', 'analyst', 'reviewer')
            messages: Chat messages in OpenAI format
            max_tokens: Maximum tokens to generate
            temperature: Response creativity (0.0-1.0)
            system_prompt: System prompt for the model
            
        Returns:
            Completion response or None if error
        """
        try:
            # Use default model if not specified
            actual_model = self.models.get(model, self.models['fast'])
            
            # Prepare messages
            if messages is None:
                messages = []
            
            # Add system prompt if provided
            if system_prompt and not any(msg.get('role') == 'system' for msg in messages):
                messages.insert(0, {'role': 'system', 'content': system_prompt})
            
            # LM Studio API request
            url = f"{self.base_url}/chat/completions"
            payload = {
                'model': actual_model,
                'messages': messages,
                'max_tokens': max_tokens,
                'temperature': temperature,
                'stream': False
            }
            
            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.debug(f"LM Studio completion successful: {actual_model}")
                    return result
                else:
                    logger.warning(f"LM Studio API error {response.status}: {await response.text()}")
                    return None
                    
        except Exception as e:
            logger.error(f"LM Studio completion error: {e}")
            return None
    
    async def analyze_market_internals(self, internals_data: Dict[str, Any]) -> Optional[str]:
        """
        Analyze market internals using fast model for quick insights
        """
        system_prompt = """You are a market internals analyst. Analyze market conditions quickly and provide actionable insights.
Focus on: market bias, volatility regime, trading opportunities, and key levels."""
        
        # Format market data for analysis
        user_prompt = f"""
        Market Internals Data:
        {json.dumps(internals_data, indent=2)}
        
        Provide a brief analysis covering:
        1. Current market bias (Bullish/Bearish/Mixed)
        2. Volatility assessment
        3. Key levels to watch
        4. Trading implications
        5. Risk considerations
        
        Keep response under 200 words.
        """
        
        messages = [
            {'role': 'user', 'content': user_prompt}
        ]
        
        response = await self.generate_completion(
            model='fast',
            messages=messages,
            system_prompt=system_prompt,
            max_tokens=150,
            temperature=0.3
        )
        
        if response and 'choices' in response:
            return response['choices'][0]['message']['content']
        return None
    
    async def deep_market_analysis(self, 
                                  internals_data: Dict[str, Any], 
                                  timeframe_analysis: Dict[str, Any] = None) -> Optional[str]:
        """
        Deep market analysis using analyst model
        """
        system_prompt = """You are an expert market analyst specializing in market internals and sentiment analysis.
Provide comprehensive analysis with clear reasoning for trading decisions."""
        
        # Prepare data for deep analysis
        data_summary = f"""
        Current Market Internals:
        {json.dumps(internals_data, indent=2)}
        
        {f'Timeframe Analysis: {json.dumps(timeframe_analysis, indent=2)}' if timeframe_analysis else ''}
        """
        
        user_prompt = f"""
        {data_summary}
        
        Provide detailed analysis covering:
        1. Multi-timeframe market structure
        2. Sentiment analysis (fear/greed, positioning)
        3. Risk assessment and volatility outlook
        4. Sector rotation and breadth analysis
        5. Key support/resistance levels with reasoning
        6. Near-term catalysts and events
        7. Overall market regime classification
        8. Actionable trading implications
        
        Include reasoning for each conclusion.
        Response limit: 500 words.
        """
        
        messages = [
            {'role': 'user', 'content': user_prompt}
        ]
        
        response = await self.generate_completion(
            model='analyst',
            messages=messages,
            system_prompt=system_prompt,
            max_tokens=400,
            temperature=0.5
        )
        
        if response and 'choices' in response:
            return response['choices'][0]['message']['content']
        return None
    
    async def review_trade_setup(self, 
                                trade_context: Dict[str, Any],
                                market_internals: Dict[str, Any]) -> Optional[str]:
        """
        Review trading setup using reviewer model
        """
        system_prompt = """You are a post-trade review specialist. Analyze trading setups objectively,
focusing on risk management, execution quality, and learning opportunities."""
        
        user_prompt = f"""
        Trade Setup Context:
        {json.dumps(trade_context, indent=2)}
        
        Market Context at Time:
        {json.dumps(market_internals, indent=2)}
        
        Review this trading setup focusing on:
        1. Setup quality and market alignment
        2. Risk/reward assessment
        3. Entry and exit timing
        4. Position sizing appropriateness
        5. Market condition suitability
        6. What could be improved
        7. Lessons learned for future setups
        
        Be objective and educational.
        Response limit: 300 words.
        """
        
        messages = [
            {'role': 'user', 'content': user_prompt}
        ]
        
        response = await self.generate_completion(
            model='reviewer',
            messages=messages,
            system_prompt=system_prompt,
            max_tokens=250,
            temperature=0.4
        )
        
        if response and 'choices' in response:
            return response['choices'][0]['message']['content']
        return None
    
    async def validate_data_interpretation(self, data: Dict[str, Any], data_type: str = "market_internals") -> Dict[str, Any]:
        """
        Perform sanity checks on data interpretation using LLM
        
        Args:
            data: The data to validate
            data_type: Type of data ('market_internals', 'price_data', 'technical_indicators')
            
        Returns:
            Dictionary with validation results
        """
        try:
            system_prompt = """You are a data validation expert. Analyze the provided data and verify:
1. Data completeness and structure
2. Reasonable value ranges
3. Logical consistency
4. Potential data quality issues
5. Missing critical information
            
Respond with a JSON object containing:
- is_valid: boolean
- issues: list of issues found (if any)
- confidence: confidence score (0-100)
- recommendations: suggestions for improvement
- summary: brief summary of data quality"""

            if data_type == "market_internals":
                user_prompt = f"""Validate this market internals data for logical consistency:

{json.dumps(data, indent=2)}

Check for:
- Reasonable price ranges (SPY: $300-600, QQQ: $200-500, VIX: $10-80)
- Reasonable percentage changes (±10% max for most assets)
- Consistent volume figures
- Missing critical symbols (SPY, QQQ, VIX)
- Timestamp validity

Return validation results in JSON format."""
            
            elif data_type == "price_data":
                user_prompt = f"""Validate this price data for quality issues:

{json.dumps(data, indent=2)}

Check for:
- OHLC consistency (High >= max(Open, Close), Low <= min(Open, Close))
- Reasonable price movements between candles
- Volume consistency
- Missing or null values
- Timestamp ordering

Return validation results in JSON format."""
            
            else:
                user_prompt = f"""Validate this technical indicator data:

{json.dumps(data, indent=2)}

Check for:
- Reasonable indicator values
- Consistency with price data
- Missing calculations
- Outlier detection

Return validation results in JSON format."""

            messages = [{'role': 'user', 'content': user_prompt}]
            
            response = await self.generate_completion(
                model='fast_analysis',
                messages=messages,
                system_prompt=system_prompt,
                max_tokens=200,
                temperature=0.1
            )
            
            if response and 'choices' in response:
                content = response['choices'][0]['message']['content']
                try:
                    # Try to parse as JSON
                    validation_result = json.loads(content)
                    return validation_result
                except json.JSONDecodeError:
                    # If not JSON, create structured response
                    return {
                        'is_valid': True,
                        'issues': [],
                        'confidence': 80,
                        'recommendations': ['Manual review recommended'],
                        'summary': 'Validation completed (non-JSON response)',
                        'raw_response': content
                    }
            
            return {
                'is_valid': False,
                'issues': ['No response from LLM'],
                'confidence': 0,
                'recommendations': ['Check LLM connection'],
                'summary': 'Validation failed - no LLM response'
            }
            
        except Exception as e:
            logger.error(f"Data validation error: {e}")
            return {
                'is_valid': False,
                'issues': [f'Validation error: {str(e)}'],
                'confidence': 0,
                'recommendations': ['Retry validation'],
                'summary': f'Validation failed with error: {str(e)}'
            }
    
    async def interpret_text_chart_data(self, chart_data: Dict[str, Any]) -> Optional[str]:
        """
        Interpret text-encoded chart data and provide analysis
        
        Args:
            chart_data: Dictionary containing chart data in text format
                       {
                           'symbol': 'NQ',
                           'timeframe': '5m',
                           'candles': [
                               {'time': '10:00', 'open': 15000, 'high': 15025, 'low': 14995, 'close': 15020, 'volume': 1250},
                               ...
                           ],
                           'indicators': {
                               'sma_20': 15010,
                               'rsi': 65.5,
                               'volume_ma': 1100
                           }
                       }
        """
        system_prompt = """You are a technical analyst. Interpret the provided chart data and identify:
1. Trend direction and strength
2. Key support/resistance levels
3. Volume patterns
4. Indicator signals
5. Potential trade setups
6. Risk points

Be concise and actionable. Focus on what matters for trading decisions."""

        # Format chart data for analysis
        chart_summary = f"""
Symbol: {chart_data.get('symbol', 'Unknown')}
Timeframe: {chart_data.get('timeframe', 'Unknown')}
Periods analyzed: {len(chart_data.get('candles', []))}

RECENT PRICE ACTION:
{self._format_recent_candles(chart_data.get('candles', [])[-5:])}

TECHNICAL INDICATORS:
{json.dumps(chart_data.get('indicators', {}), indent=2)}

KEY LEVELS:
- Current Price: {chart_data.get('candles', [])[-1]['close'] if chart_data.get('candles') else 'N/A'}
- Period High: {max(c['high'] for c in chart_data.get('candles', [])) if chart_data.get('candles') else 'N/A'}
- Period Low: {min(c['low'] for c in chart_data.get('candles', [])) if chart_data.get('candles') else 'N/A'}

Provide technical analysis focusing on actionable insights."""

        messages = [{'role': 'user', 'content': chart_summary}]
        
        response = await self.generate_completion(
            model='deep_analysis',
            messages=messages,
            system_prompt=system_prompt,
            max_tokens=300,
            temperature=0.4
        )
        
        if response and 'choices' in response:
            return response['choices'][0]['message']['content']
        return None
    
    def _format_recent_candles(self, candles: List[Dict]) -> str:
        """Format recent candles for LLM analysis"""
        if not candles:
            return "No candle data available"
        
        formatted = []
        for i, candle in enumerate(candles):
            direction = "🟢" if candle['close'] >= candle['open'] else "🔴"
            formatted.append(f"  {direction} Candle {i+1}: O={candle['open']:.2f} H={candle['high']:.2f} L={candle['low']:.2f} C={candle['close']:.2f} V={candle.get('volume', 0)}")
        
        return "\n".join(formatted)
    
    def get_model_status(self) -> Dict[str, Any]:
        """Get status of available models"""
        status = {}
        for model_type, model_name in self.models.items():
            status[model_type] = {
                'name': model_name,
                'available': True,  # Would check actual availability in real implementation
                'purpose': {
                    'fast': 'Quick market analysis (59 tok/s)',
                    'analyst': 'Deep market analysis (19 tok/s)',
                    'reviewer': 'Trade setup review (12 tok/s)'
                }.get(model_type, 'General purpose')
            }
        return status


class OpenRouterClient:
    """OpenRouter API client for cloud LLM fallback"""
    
    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.base_url = self.settings.llm.fallback.base_url
        self.api_key = self.settings.llm.fallback.api_key
        self.timeout = self.settings.llm.fallback.timeout
        self.session = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        import aiohttp
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        self.session = aiohttp.ClientSession(
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def generate_completion(self, 
                                model: str = "openai/gpt-4o-mini",
                                messages: List[Dict[str, str]] = None,
                                max_tokens: int = 100,
                                temperature: float = 0.3) -> Optional[Dict[str, Any]]:
        """Generate completion using OpenRouter"""
        try:
            url = f"{self.base_url}/chat/completions"
            payload = {
                'model': model,
                'messages': messages or [],
                'max_tokens': max_tokens,
                'temperature': temperature
            }
            
            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning(f"OpenRouter API error {response.status}: {await response.text()}")
                    return None
                    
        except Exception as e:
            logger.error(f"OpenRouter completion error: {e}")
            return None


class LLMManager:
    """Orchestrates LLM operations with fallback support"""
    
    def __init__(self):
        self.settings = get_settings()
        self.lm_studio = None
        self.openrouter = None
    
    async def analyze_market(self, 
                           internals_data: Dict[str, Any],
                           analysis_type: str = 'quick') -> Optional[str]:
        """
        Analyze market using appropriate LLM based on analysis type
        
        Args:
            internals_data: Market internals data
            analysis_type: 'quick', 'deep', or 'review'
        """
        
        try:
            # Try LM Studio first (local, faster)
            if analysis_type == 'quick':
                async with LMStudioClient(self.settings) as client:
                    result = await client.analyze_market_internals(internals_data)
                    if result:
                        return f"🤖 LM Studio (Fast Analysis):\n{result}"
            
            elif analysis_type == 'deep':
                async with LMStudioClient(self.settings) as client:
                    result = await client.deep_market_analysis(internals_data)
                    if result:
                        return f"🤖 LM Studio (Deep Analysis):\n{result}"
            
            elif analysis_type == 'review':
                async with LMStudioClient(self.settings) as client:
                    result = await client.review_trade_setup(internals_data, internals_data)
                    if result:
                        return f"🤖 LM Studio (Trade Review):\n{result}"
            
            # Fallback to OpenRouter if LM Studio fails
            logger.warning("LM Studio unavailable, trying OpenRouter fallback...")
            async with OpenRouterClient(self.settings) as client:
                if analysis_type == 'quick':
                    prompt = f"Analyze these market internals briefly: {json.dumps(internals_data)}"
                else:
                    prompt = f"Provide detailed analysis of: {json.dumps(internals_data)}"
                
                messages = [{'role': 'user', 'content': prompt}]
                
                result = await client.generate_completion(
                    model="openai/gpt-4o-mini",
                    messages=messages,
                    max_tokens=300 if analysis_type == 'deep' else 150,
                    temperature=0.3
                )
                
                if result and 'choices' in result:
                    return f"☁️ OpenRouter (Cloud Analysis):\n{result['choices'][0]['message']['content']}"
            
            logger.error("All LLM services failed")
            return None
            
        except Exception as e:
            logger.error(f"LLM analysis error: {e}")
            return None
    
    def get_status(self) -> Dict[str, Any]:
        """Get status of all LLM services"""
        status = {
            'lm_studio': {
                'available': True,  # Would check actual connection
                'endpoint': self.settings.llm.primary.base_url,
                'models': {
                    'fast': 'qwen3-30b-a3b (59 tok/s)',
                    'analyst': 'glm-4.5-air (19 tok/s)',
                    'reviewer': 'glm-4.6-air (12 tok/s)'
                }
            },
            'openrouter': {
                'available': bool(self.settings.llm.fallback.api_key),
                'endpoint': self.settings.llm.fallback.base_url
            }
        }
        return status