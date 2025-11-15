"""OHLC Technical Analysis Module for MarketPulse
Provides comprehensive candlestick pattern analysis and trend detection
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from loguru import logger


class OHLCAnalyzer:
    """Comprehensive OHLC technical analysis"""

    def __init__(self):
        self.timeframes = {
            '4h': {'period': '7d', 'interval': '1h', 'limit': 168},  # 7 days of hourly candles
            '1d': {'period': '1mo', 'interval': '1d', 'limit': 30},   # 30 days
            '7d': {'period': '3mo', 'interval': '1d', 'limit': 90},  # ~12 weeks of daily candles
            '30d': {'period': '1y', 'interval': '1d', 'limit': 365}  # 1 year of daily candles
        }

    def analyze_symbol(self, data: Dict[str, Any], symbol: str) -> Dict[str, Any]:
        """Analyze a symbol across multiple timeframes"""
        try:
            analysis = {
                'symbol': symbol,
                'timestamp': datetime.now().isoformat(),
                'timeframes': {},
                'overall_trend': 'NEUTRAL',
                'overall_strength': 0,
                'key_levels': {},
                'patterns': [],
                'signals': []
            }

            timeframe_results = []

            for tf_name, tf_config in self.timeframes.items():
                try:
                    # Extract OHLC data for this timeframe
                    ohlc_data = self._extract_ohlc_data(data, tf_name, symbol)
                    if ohlc_data is None or len(ohlc_data) < 10:
                        logger.warning(f"Insufficient data for {symbol} {tf_name} timeframe")
                        continue

                    # Perform analysis for this timeframe
                    tf_analysis = self._analyze_timeframe(ohlc_data, tf_name)
                    analysis['timeframes'][tf_name] = tf_analysis
                    timeframe_results.append(tf_analysis)

                except Exception as e:
                    logger.warning(f"Error analyzing {symbol} {tf_name}: {e}")
                    continue

            # Aggregate results
            if timeframe_results:
                analysis['overall_trend'] = self._determine_overall_trend(timeframe_results)
                analysis['overall_strength'] = self._calculate_overall_strength(timeframe_results)
                analysis['key_levels'] = self._identify_key_levels(timeframe_results)
                analysis['patterns'] = self._aggregate_patterns(timeframe_results)
                analysis['signals'] = self._generate_signals(analysis)

            return analysis

        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}")
            return {'symbol': symbol, 'error': str(e), 'timestamp': datetime.now().isoformat()}

    def _extract_ohlc_data(self, data: Dict[str, Any], timeframe: str, symbol: str) -> Optional[pd.DataFrame]:
        """Extract OHLC data for a specific timeframe"""
        try:
            # Try different data sources
            raw_data = []

            if 'historical_data' in data and timeframe in data['historical_data']:
                # New format: {'historical_data': {'4h': {'symbol': symbol, 'data': [...]}}}
                timeframe_data = data['historical_data'][timeframe]
                if isinstance(timeframe_data, dict) and 'data' in timeframe_data:
                    raw_data = timeframe_data['data']
                elif isinstance(timeframe_data, list):
                    raw_data = timeframe_data
            elif 'candles' in data and timeframe in data['candles']:
                # Alternative format: {'candles': {'4h': [{}]}}
                raw_data = data['candles'][timeframe]
            else:
                # No real data available - return None instead of mock data
                logger.warning(f"No real OHLC data available for {symbol} {timeframe} - refusing to use mock data")
                return None

            if not raw_data:
                logger.warning(f"No raw data found for {symbol} {timeframe}")
                return None

            # Convert to DataFrame
            df = pd.DataFrame(raw_data)
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)

            # Ensure proper column names
            column_mapping = {
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'close': 'close',
                'volume': 'volume'
            }

            df = df.rename(columns={k: v for k, v in column_mapping.items() if k in df.columns})

            # Ensure we have required columns
            required_cols = ['open', 'high', 'low', 'close']
            if not all(col in df.columns for col in required_cols):
                logger.warning(f"Missing required columns for {symbol} {timeframe}. Available: {list(df.columns)}")
                return None

            logger.info(f"Successfully extracted {len(df)} data points for {symbol} {timeframe}")
            return df.sort_index()

        except Exception as e:
            logger.error(f"Error extracting OHLC data for {symbol} {timeframe}: {e}")
            return None

    def _generate_sample_data(self, symbol: str, timeframe: str) -> List[Dict]:
        """Generate realistic sample OHLC data for testing"""
        np.random.seed(hash(symbol + timeframe) % 1000)

        base_price = {
            'SPY': 450.0,
            'QQQ': 380.0,
            'BTC': 45000.0,
            'ETH': 2400.0,
            'VIX': 16.0
        }.get(symbol, 100.0)

        limit = self.timeframes[timeframe]['limit']
        data = []
        current_price = base_price

        for i in range(limit):
            # Generate realistic price movement
            change_pct = np.random.normal(0, 0.02)  # 2% daily volatility
            volume = np.random.randint(1000000, 10000000)

            high = current_price * (1 + abs(np.random.normal(0, 0.01)))
            low = current_price * (1 - abs(np.random.normal(0, 0.01)))
            close = current_price * (1 + change_pct)
            open_price = current_price

            # Ensure OHLC relationships
            high = max(high, open_price, close)
            low = min(low, open_price, close)

            data.append({
                'timestamp': (datetime.now() - timedelta(hours=i*4)).isoformat(),
                'open': round(open_price, 2),
                'high': round(high, 2),
                'low': round(low, 2),
                'close': round(close, 2),
                'volume': volume
            })

            current_price = close

        return list(reversed(data))

    def _analyze_timeframe(self, df: pd.DataFrame, timeframe: str) -> Dict[str, Any]:
        """Analyze OHLC data for a single timeframe"""
        try:
            if len(df) < 10:
                return {'error': 'Insufficient data'}

            # Basic price metrics
            current_price = df['close'].iloc[-1]
            price_change = df['close'].iloc[-1] - df['close'].iloc[-2]
            price_change_pct = (price_change / df['close'].iloc[-2]) * 100

            # Trend analysis
            trend = self._analyze_trend(df)

            # Technical indicators
            sma_20 = self._calculate_sma(df['close'], 20)
            sma_50 = self._calculate_sma(df['close'], 50)
            ema_12 = self._calculate_ema(df['close'], 12)
            ema_26 = self._calculate_ema(df['close'], 26)

            # ATR calculation
            atr = self._calculate_atr(df, 14)

            # Support and resistance levels
            support_levels = self._find_support_levels(df)
            resistance_levels = self._find_resistance_levels(df)

            # Candlestick patterns
            patterns = self._identify_candlestick_patterns(df)

            # Volume analysis
            volume_analysis = self._analyze_volume(df)

            # Volatility analysis
            volatility = self._analyze_volatility(df)

            # Convert numpy types to native Python types for JSON serialization
            def convert_numpy_types(obj):
                if hasattr(obj, 'item'):  # numpy scalar
                    return obj.item()
                elif isinstance(obj, dict):
                    return {k: convert_numpy_types(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_numpy_types(x) for x in obj]
                elif hasattr(obj, '__iter__') and not isinstance(obj, (str, bytes)):
                    return [convert_numpy_types(x) for x in obj]
                return obj

            return convert_numpy_types({
                'timeframe': timeframe,
                'current_price': float(current_price),
                'price_change': float(price_change),
                'price_change_pct': float(price_change_pct),
                'trend': trend,
                'indicators': {
                    'sma_20': float(sma_20) if sma_20 is not None else None,
                    'sma_50': float(sma_50) if sma_50 is not None else None,
                    'ema_12': float(ema_12) if ema_12 is not None else None,
                    'ema_26': float(ema_26) if ema_26 is not None else None,
                    'atr': float(atr) if atr is not None else None
                },
                'support_levels': support_levels,
                'resistance_levels': resistance_levels,
                'patterns': patterns,
                'volume_analysis': volume_analysis,
                'volatility': volatility,
                'data_points': int(len(df))
            })

        except Exception as e:
            logger.error(f"Error analyzing timeframe {timeframe}: {e}")
            return {'timeframe': timeframe, 'error': str(e)}

    def _analyze_trend(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze price trend"""
        try:
            closes = df['close']

            # Linear regression trend
            x = np.arange(len(closes))
            slope, intercept = np.polyfit(x, closes, 1)

            # Trend strength based on R-squared
            y_pred = slope * x + intercept
            ss_res = ((closes - y_pred) ** 2).sum()
            ss_tot = ((closes - closes.mean()) ** 2).sum()
            r_squared = 1 - (ss_res / ss_tot)

            # Determine trend direction
            if slope > 0.01:
                direction = 'BULLISH'
            elif slope < -0.01:
                direction = 'BEARISH'
            else:
                direction = 'NEUTRAL'

            # Trend strength
            if r_squared > 0.7:
                strength = 'STRONG'
            elif r_squared > 0.4:
                strength = 'MODERATE'
            else:
                strength = 'WEAK'

            # Recent momentum
            momentum = (closes.iloc[-5:].mean() - closes.iloc[-10:].mean()) / closes.iloc[-10:].mean()

            return {
                'direction': direction,
                'strength': strength,
                'slope': slope,
                'r_squared': r_squared,
                'momentum_5d': momentum,
                'trendline': {
                    'slope': slope,
                    'intercept': intercept,
                    'current_value': slope * (len(closes) - 1) + intercept
                }
            }

        except Exception as e:
            logger.error(f"Error analyzing trend: {e}")
            return {'direction': 'NEUTRAL', 'strength': 'UNKNOWN', 'error': str(e)}

    def _calculate_sma(self, prices: pd.Series, period: int) -> Optional[float]:
        """Calculate Simple Moving Average"""
        if len(prices) < period:
            return None
        return prices.rolling(window=period).mean().iloc[-1]

    def _calculate_ema(self, prices: pd.Series, period: int) -> Optional[float]:
        """Calculate Exponential Moving Average"""
        if len(prices) < period:
            return None
        return prices.ewm(span=period).mean().iloc[-1]

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> Optional[float]:
        """Calculate Average True Range"""
        try:
            high = df['high']
            low = df['low']
            close = df['close']

            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())

            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window=period).mean()

            return atr.iloc[-1] if not pd.isna(atr.iloc[-1]) else None

        except Exception as e:
            logger.error(f"Error calculating ATR: {e}")
            return None

    def _find_support_levels(self, df: pd.DataFrame) -> List[Dict[str, float]]:
        """Find key support levels"""
        try:
            lows = df['low']
            levels = []

            # Find recent swing lows
            for i in range(2, len(lows) - 2):
                if (lows.iloc[i] < lows.iloc[i-1] and lows.iloc[i] < lows.iloc[i-2] and
                    lows.iloc[i] < lows.iloc[i+1] and lows.iloc[i] < lows.iloc[i+2]):

                    levels.append({
                        'price': lows.iloc[i],
                        'strength': self._calculate_level_strength(df, lows.iloc[i], 'support'),
                        'date': df.index[i].isoformat()
                    })

            # Sort by strength and return top 3
            levels.sort(key=lambda x: x['strength'], reverse=True)
            return levels[:3]

        except Exception as e:
            logger.error(f"Error finding support levels: {e}")
            return []

    def _find_resistance_levels(self, df: pd.DataFrame) -> List[Dict[str, float]]:
        """Find key resistance levels"""
        try:
            highs = df['high']
            levels = []

            # Find recent swing highs
            for i in range(2, len(highs) - 2):
                if (highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i-2] and
                    highs.iloc[i] > highs.iloc[i+1] and highs.iloc[i] > highs.iloc[i+2]):

                    levels.append({
                        'price': highs.iloc[i],
                        'strength': self._calculate_level_strength(df, highs.iloc[i], 'resistance'),
                        'date': df.index[i].isoformat()
                    })

            # Sort by strength and return top 3
            levels.sort(key=lambda x: x['strength'], reverse=True)
            return levels[:3]

        except Exception as e:
            logger.error(f"Error finding resistance levels: {e}")
            return []

    def _calculate_level_strength(self, df: pd.DataFrame, level: float, level_type: str) -> float:
        """Calculate strength of a support/resistance level"""
        try:
            touches = 0
            tolerance = 0.02  # 2% tolerance

            if level_type == 'support':
                touches = ((df['low'] >= level * (1 - tolerance)) &
                          (df['low'] <= level * (1 + tolerance))).sum()
            else:
                touches = ((df['high'] >= level * (1 - tolerance)) &
                          (df['high'] <= level * (1 + tolerance))).sum()

            return touches

        except Exception as e:
            logger.error(f"Error calculating level strength: {e}")
            return 0

    def _identify_candlestick_patterns(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Identify common candlestick patterns"""
        try:
            patterns = []

            if len(df) < 3:
                return patterns

            # Get last few candles
            recent = df.tail(5)

            # Doji pattern
            if len(recent) >= 1:
                last_candle = recent.iloc[-1]
                body_size = abs(last_candle['close'] - last_candle['open'])
                range_size = last_candle['high'] - last_candle['low']

                if range_size > 0 and body_size / range_size < 0.1:
                    patterns.append({
                        'name': 'Doji',
                        'signal': 'INDECISION',
                        'strength': 'MODERATE',
                        'date': df.index[-1].isoformat()
                    })

            # Hammer pattern (last 3 candles)
            if len(recent) >= 3:
                hammer = recent.iloc[-3]
                body_size = abs(hammer['close'] - hammer['open'])
                lower_shadow = min(hammer['close'], hammer['open']) - hammer['low']
                upper_shadow = hammer['high'] - max(hammer['close'], hammer['open'])

                if (lower_shadow > 2 * body_size and upper_shadow < 0.5 * body_size and
                    body_size / (hammer['high'] - hammer['low']) < 0.3):
                    patterns.append({
                        'name': 'Hammer',
                        'signal': 'BULLISH_REVERSAL',
                        'strength': 'MODERATE',
                        'date': recent.index[-3].isoformat()
                    })

            # Engulfing pattern (last 2 candles)
            if len(recent) >= 2:
                first = recent.iloc[-2]
                second = recent.iloc[-1]

                # Bullish engulfing
                if (first['close'] < first['open'] and  # First is red
                    second['close'] > second['open'] and  # Second is green
                    second['open'] < first['close'] and  # Second opens below first close
                    second['close'] > first['open']):   # Second closes above first open

                    patterns.append({
                        'name': 'Bullish Engulfing',
                        'signal': 'BULLISH_REVERSAL',
                        'strength': 'STRONG',
                        'date': df.index[-1].isoformat()
                    })

                # Bearish engulfing
                elif (first['close'] > first['open'] and  # First is green
                      second['close'] < second['open'] and  # Second is red
                      second['open'] > first['close'] and  # Second opens above first close
                      second['close'] < first['open']):   # Second closes below first open

                    patterns.append({
                        'name': 'Bearish Engulfing',
                        'signal': 'BEARISH_REVERSAL',
                        'strength': 'STRONG',
                        'date': df.index[-1].isoformat()
                    })

            return patterns

        except Exception as e:
            logger.error(f"Error identifying candlestick patterns: {e}")
            return []

    def _analyze_volume(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze volume patterns"""
        try:
            if 'volume' not in df.columns:
                return {'error': 'No volume data'}

            volume = df['volume']
            current_volume = volume.iloc[-1]
            avg_volume = volume.tail(20).mean()
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1

            # Volume trend
            volume_trend = 'NEUTRAL'
            if len(volume) >= 10:
                recent_avg = volume.tail(5).mean()
                older_avg = volume.tail(10).head(5).mean()
                if recent_avg > older_avg * 1.2:
                    volume_trend = 'INCREASING'
                elif recent_avg < older_avg * 0.8:
                    volume_trend = 'DECREASING'

            return {
                'current_volume': current_volume,
                'average_volume_20d': avg_volume,
                'volume_ratio': volume_ratio,
                'trend': volume_trend,
                'anomaly': volume_ratio > 2.0 or volume_ratio < 0.5
            }

        except Exception as e:
            logger.error(f"Error analyzing volume: {e}")
            return {'error': str(e)}

    def _analyze_volatility(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze volatility patterns"""
        try:
            returns = df['close'].pct_change().dropna()

            if len(returns) < 10:
                return {'error': 'Insufficient data'}

            # Calculate volatility metrics
            volatility_10d = returns.tail(10).std() * np.sqrt(252)  # Annualized
            volatility_20d = returns.tail(20).std() * np.sqrt(252)

            # Current vs historical volatility
            current_vol = volatility_10d
            historical_vol = returns.std() * np.sqrt(252)

            # Volatility regime
            if current_vol > historical_vol * 1.5:
                regime = 'HIGH'
            elif current_vol < historical_vol * 0.5:
                regime = 'LOW'
            else:
                regime = 'NORMAL'

            return {
                'volatility_10d': current_vol,
                'volatility_20d': volatility_20d,
                'historical_volatility': historical_vol,
                'regime': regime,
                'expansion': current_vol > historical_vol * 1.2
            }

        except Exception as e:
            logger.error(f"Error analyzing volatility: {e}")
            return {'error': str(e)}

    def _determine_overall_trend(self, timeframe_results: List[Dict]) -> str:
        """Determine overall trend from multiple timeframes"""
        try:
            if not timeframe_results:
                return 'NEUTRAL'

            # Weight longer timeframes more heavily
            weights = {'4h': 1, '1d': 2, '7d': 3, '30d': 4}

            bullish_score = 0
            bearish_score = 0

            for result in timeframe_results:
                if 'trend' in result and 'direction' in result['trend']:
                    tf = result['timeframe']
                    weight = weights.get(tf, 1)

                    if result['trend']['direction'] == 'BULLISH':
                        bullish_score += weight
                    elif result['trend']['direction'] == 'BEARISH':
                        bearish_score += weight

            if bullish_score > bearish_score * 1.5:
                return 'STRONGLY_BULLISH'
            elif bullish_score > bearish_score:
                return 'BULLISH'
            elif bearish_score > bullish_score * 1.5:
                return 'STRONGLY_BEARISH'
            elif bearish_score > bullish_score:
                return 'BEARISH'
            else:
                return 'NEUTRAL'

        except Exception as e:
            logger.error(f"Error determining overall trend: {e}")
            return 'NEUTRAL'

    def _calculate_overall_strength(self, timeframe_results: List[Dict]) -> float:
        """Calculate overall trend strength"""
        try:
            if not timeframe_results:
                return 0.0

            total_strength = 0
            count = 0

            for result in timeframe_results:
                if 'trend' in result and 'r_squared' in result['trend']:
                    total_strength += result['trend']['r_squared']
                    count += 1

            return total_strength / count if count > 0 else 0.0

        except Exception as e:
            logger.error(f"Error calculating overall strength: {e}")
            return 0.0

    def _identify_key_levels(self, timeframe_results: List[Dict]) -> Dict[str, List[Dict]]:
        """Aggregate key support/resistance levels"""
        try:
            all_support = []
            all_resistance = []

            for result in timeframe_results:
                if 'support_levels' in result:
                    all_support.extend(result['support_levels'])
                if 'resistance_levels' in result:
                    all_resistance.extend(result['resistance_levels'])

            # Find consensus levels (similar prices across timeframes)
            consensus_support = self._find_consensus_levels(all_support)
            consensus_resistance = self._find_consensus_levels(all_resistance)

            return {
                'support': consensus_support[:3],  # Top 3
                'resistance': consensus_resistance[:3]  # Top 3
            }

        except Exception as e:
            logger.error(f"Error identifying key levels: {e}")
            return {'support': [], 'resistance': []}

    def _find_consensus_levels(self, levels: List[Dict], tolerance: float = 0.02) -> List[Dict]:
        """Find levels that appear across multiple timeframes"""
        try:
            if not levels:
                return []

            # Group levels by price (within tolerance)
            groups = []
            for level in levels:
                price = level['price']
                added = False

                for group in groups:
                    if abs(price - group[0]['price']) / group[0]['price'] < tolerance:
                        group.append(level)
                        added = True
                        break

                if not added:
                    groups.append([level])

            # Calculate consensus strength
            consensus = []
            for group in groups:
                avg_price = sum(l['price'] for l in group) / len(group)
                total_strength = sum(l['strength'] for l in group)

                consensus.append({
                    'price': avg_price,
                    'strength': total_strength,
                    'timeframes': len(group),
                    'confirmations': len(group)
                })

            # Sort by strength
            consensus.sort(key=lambda x: x['strength'], reverse=True)
            return consensus

        except Exception as e:
            logger.error(f"Error finding consensus levels: {e}")
            return []

    def _aggregate_patterns(self, timeframe_results: List[Dict]) -> List[Dict]:
        """Aggregate candlestick patterns from all timeframes"""
        try:
            all_patterns = []

            for result in timeframe_results:
                if 'patterns' in result:
                    for pattern in result['patterns']:
                        pattern['timeframe'] = result['timeframe']
                        all_patterns.append(pattern)

            # Sort by strength and recency
            strength_order = {'STRONG': 3, 'MODERATE': 2, 'WEAK': 1}
            all_patterns.sort(key=lambda x: (strength_order.get(x['strength'], 0), x['date']), reverse=True)

            return all_patterns[:10]  # Top 10 patterns

        except Exception as e:
            logger.error(f"Error aggregating patterns: {e}")
            return []

    def _generate_signals(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate trading signals based on analysis"""
        try:
            signals = []

            # Trend signals
            if analysis['overall_trend'] in ['BULLISH', 'STRONGLY_BULLISH']:
                signals.append({
                    'type': 'TREND',
                    'direction': 'BULLISH',
                    'strength': 'STRONG' if 'STRONGLY' in analysis['overall_trend'] else 'MODERATE',
                    'reasoning': f"Overall trend is {analysis['overall_trend']}",
                    'confidence': min(analysis['overall_strength'] * 100, 95)
                })
            elif analysis['overall_trend'] in ['BEARISH', 'STRONGLY_BEARISH']:
                signals.append({
                    'type': 'TREND',
                    'direction': 'BEARISH',
                    'strength': 'STRONG' if 'STRONGLY' in analysis['overall_trend'] else 'MODERATE',
                    'reasoning': f"Overall trend is {analysis['overall_trend']}",
                    'confidence': min(analysis['overall_strength'] * 100, 95)
                })

            # Pattern signals
            for pattern in analysis['patterns'][:3]:  # Top 3 patterns
                if 'REVERSAL' in pattern['signal']:
                    direction = 'BULLISH' if 'BULLISH' in pattern['signal'] else 'BEARISH'
                    signals.append({
                        'type': 'PATTERN',
                        'direction': direction,
                        'strength': pattern['strength'],
                        'reasoning': f"{pattern['name']} pattern detected on {pattern['timeframe']}",
                        'confidence': 70 if pattern['strength'] == 'STRONG' else 50
                    })

            # Level breakout/breakdown signals
            current_price = None
            for tf_name, tf_data in analysis['timeframes'].items():
                if 'current_price' in tf_data:
                    current_price = tf_data['current_price']
                    break

            if current_price and analysis['key_levels']:
                # Check for nearby resistance
                for resistance in analysis['key_levels']['resistance'][:2]:
                    if abs(current_price - resistance['price']) / current_price < 0.02:
                        signals.append({
                            'type': 'RESISTANCE',
                            'direction': 'NEUTRAL',
                            'strength': 'MODERATE',
                            'reasoning': f"Approaching key resistance at ${resistance['price']:.2f}",
                            'confidence': min(resistance['strength'] * 20, 80)
                        })

                # Check for nearby support
                for support in analysis['key_levels']['support'][:2]:
                    if abs(current_price - support['price']) / current_price < 0.02:
                        signals.append({
                            'type': 'SUPPORT',
                            'direction': 'NEUTRAL',
                            'strength': 'MODERATE',
                            'reasoning': f"Approaching key support at ${support['price']:.2f}",
                            'confidence': min(support['strength'] * 20, 80)
                        })

            return signals

        except Exception as e:
            logger.error(f"Error generating signals: {e}")
            return []