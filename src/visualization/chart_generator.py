"""
Interactive Chart Generator using Plotly

Creates beautiful, interactive charts with:
- Candlestick charts
- Technical indicators overlays
- ICT concepts (FVG, Order Blocks, Liquidity)
- Volume analysis
- Market heatmaps
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from loguru import logger

from src.analysis.technical_indicators import TechnicalIndicators


class ChartGenerator:
    """
    Generate interactive Plotly charts

    Creates professional-looking charts with full interactivity,
    zoom, pan, hover details, and beautiful styling.
    """

    # Color scheme
    COLORS = {
        'bullish': '#26a69a',  # Teal green
        'bearish': '#ef5350',  # Red
        'neutral': '#78909c',  # Blue grey
        'volume_up': 'rgba(38, 166, 154, 0.5)',
        'volume_down': 'rgba(239, 83, 80, 0.5)',
        'fvg_bullish': 'rgba(76, 175, 80, 0.2)',  # Light green
        'fvg_bearish': 'rgba(244, 67, 54, 0.2)',  # Light red
        'order_block': 'rgba(33, 150, 243, 0.3)',  # Light blue
        'liquidity': 'rgba(255, 193, 7, 0.4)',  # Amber
        'background': '#1e1e1e',
        'grid': '#2d2d2d',
        'text': '#e0e0e0'
    }

    def __init__(self, theme: str = 'dark'):
        """
        Initialize chart generator

        Args:
            theme: 'dark' or 'light'
        """
        self.theme = theme

    def create_candlestick_chart(
        self,
        df: pd.DataFrame,
        title: str = "Price Chart",
        indicators: Optional[List[str]] = None,
        show_volume: bool = True,
        height: int = 800
    ) -> go.Figure:
        """
        Create candlestick chart with indicators

        Args:
            df: DataFrame with OHLCV data
            title: Chart title
            indicators: List of indicators to overlay
            show_volume: Show volume subplot
            height: Chart height in pixels

        Returns:
            Plotly Figure
        """
        # Determine subplot layout
        rows = 2 if show_volume else 1
        row_heights = [0.7, 0.3] if show_volume else [1.0]

        # Create subplots
        fig = make_subplots(
            rows=rows,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=row_heights,
            subplot_titles=(title, 'Volume') if show_volume else (title,)
        )

        # Add candlesticks
        fig.add_trace(
            go.Candlestick(
                x=df.index,
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='Price',
                increasing_line_color=self.COLORS['bullish'],
                decreasing_line_color=self.COLORS['bearish']
            ),
            row=1, col=1
        )

        # Add indicators if specified
        if indicators:
            df_with_indicators = TechnicalIndicators.calculate_all(df, indicators)

            # Moving averages
            for ma in ['sma_20', 'sma_50', 'sma_200', 'ema_9', 'ema_21', 'ema_50']:
                if ma in indicators and ma in df_with_indicators.columns:
                    fig.add_trace(
                        go.Scatter(
                            x=df_with_indicators.index,
                            y=df_with_indicators[ma],
                            name=ma.upper(),
                            line=dict(width=1.5),
                            opacity=0.7
                        ),
                        row=1, col=1
                    )

            # Bollinger Bands
            if 'bollinger' in indicators and 'bb_upper' in df_with_indicators.columns:
                # Upper band
                fig.add_trace(
                    go.Scatter(
                        x=df_with_indicators.index,
                        y=df_with_indicators['bb_upper'],
                        name='BB Upper',
                        line=dict(width=1, dash='dash', color='rgba(128,128,128,0.5)'),
                        showlegend=True
                    ),
                    row=1, col=1
                )

                # Lower band
                fig.add_trace(
                    go.Scatter(
                        x=df_with_indicators.index,
                        y=df_with_indicators['bb_lower'],
                        name='BB Lower',
                        line=dict(width=1, dash='dash', color='rgba(128,128,128,0.5)'),
                        fill='tonexty',
                        fillcolor='rgba(128,128,128,0.1)',
                        showlegend=True
                    ),
                    row=1, col=1
                )

                # Middle band
                fig.add_trace(
                    go.Scatter(
                        x=df_with_indicators.index,
                        y=df_with_indicators['bb_middle'],
                        name='BB Middle',
                        line=dict(width=1, color='rgba(128,128,128,0.7)'),
                        showlegend=True
                    ),
                    row=1, col=1
                )

            # VWAP
            if 'vwap' in indicators and 'vwap' in df_with_indicators.columns:
                fig.add_trace(
                    go.Scatter(
                        x=df_with_indicators.index,
                        y=df_with_indicators['vwap'],
                        name='VWAP',
                        line=dict(width=2, color='orange'),
                        opacity=0.8
                    ),
                    row=1, col=1
                )

            # Supertrend
            if 'supertrend' in indicators and 'supertrend' in df_with_indicators.columns:
                # Color based on direction
                colors = ['green' if d == 1 else 'red'
                         for d in df_with_indicators['supertrend_direction']]

                fig.add_trace(
                    go.Scatter(
                        x=df_with_indicators.index,
                        y=df_with_indicators['supertrend'],
                        name='Supertrend',
                        line=dict(width=2),
                        marker=dict(color=colors),
                        mode='lines'
                    ),
                    row=1, col=1
                )

        # Add volume bars
        if show_volume:
            colors = [self.COLORS['volume_up'] if df['close'].iloc[i] >= df['open'].iloc[i]
                     else self.COLORS['volume_down'] for i in range(len(df))]

            fig.add_trace(
                go.Bar(
                    x=df.index,
                    y=df['volume'],
                    name='Volume',
                    marker_color=colors,
                    showlegend=False
                ),
                row=2, col=1
            )

        # Update layout
        fig.update_layout(
            height=height,
            template='plotly_dark' if self.theme == 'dark' else 'plotly_white',
            xaxis_rangeslider_visible=False,
            hovermode='x unified',
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )

        # Update axes
        fig.update_xaxes(
            gridcolor=self.COLORS['grid'],
            showgrid=True,
            title_text="Date",
            row=rows, col=1
        )

        fig.update_yaxes(
            gridcolor=self.COLORS['grid'],
            showgrid=True,
            title_text="Price",
            row=1, col=1
        )

        if show_volume:
            fig.update_yaxes(
                gridcolor=self.COLORS['grid'],
                showgrid=True,
                title_text="Volume",
                row=2, col=1
            )

        return fig

    def create_indicator_panel(
        self,
        df: pd.DataFrame,
        title: str = "Technical Indicators"
    ) -> go.Figure:
        """
        Create multi-panel indicator chart

        Shows RSI, MACD, Stochastic in separate subplots

        Args:
            df: DataFrame with OHLCV data
            title: Chart title

        Returns:
            Plotly Figure
        """
        # Calculate indicators
        df_indicators = TechnicalIndicators.calculate_all(
            df,
            ['rsi', 'macd', 'stochastic']
        )

        # Create subplots
        fig = make_subplots(
            rows=3,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            subplot_titles=('RSI', 'MACD', 'Stochastic'),
            row_heights=[0.33, 0.33, 0.34]
        )

        # RSI
        fig.add_trace(
            go.Scatter(
                x=df_indicators.index,
                y=df_indicators['rsi'],
                name='RSI',
                line=dict(color='#2196F3', width=2)
            ),
            row=1, col=1
        )

        # RSI levels
        fig.add_hline(y=70, line_dash="dash", line_color="red", opacity=0.5, row=1, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", opacity=0.5, row=1, col=1)
        fig.add_hline(y=50, line_dash="dot", line_color="gray", opacity=0.3, row=1, col=1)

        # MACD
        fig.add_trace(
            go.Scatter(
                x=df_indicators.index,
                y=df_indicators['macd'],
                name='MACD',
                line=dict(color='#2196F3', width=2)
            ),
            row=2, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=df_indicators.index,
                y=df_indicators['macd_signal'],
                name='Signal',
                line=dict(color='#FF5722', width=2)
            ),
            row=2, col=1
        )

        # MACD histogram
        colors = ['green' if val >= 0 else 'red' for val in df_indicators['macd_histogram']]
        fig.add_trace(
            go.Bar(
                x=df_indicators.index,
                y=df_indicators['macd_histogram'],
                name='Histogram',
                marker_color=colors,
                opacity=0.5
            ),
            row=2, col=1
        )

        # Stochastic
        fig.add_trace(
            go.Scatter(
                x=df_indicators.index,
                y=df_indicators['stoch_k'],
                name='%K',
                line=dict(color='#2196F3', width=2)
            ),
            row=3, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=df_indicators.index,
                y=df_indicators['stoch_d'],
                name='%D',
                line=dict(color='#FF5722', width=2)
            ),
            row=3, col=1
        )

        # Stochastic levels
        fig.add_hline(y=80, line_dash="dash", line_color="red", opacity=0.5, row=3, col=1)
        fig.add_hline(y=20, line_dash="dash", line_color="green", opacity=0.5, row=3, col=1)

        # Update layout
        fig.update_layout(
            height=900,
            title_text=title,
            template='plotly_dark' if self.theme == 'dark' else 'plotly_white',
            showlegend=True,
            hovermode='x unified'
        )

        # Update axes
        fig.update_xaxes(gridcolor=self.COLORS['grid'], showgrid=True)
        fig.update_yaxes(gridcolor=self.COLORS['grid'], showgrid=True)

        fig.update_yaxes(title_text="RSI", row=1, col=1, range=[0, 100])
        fig.update_yaxes(title_text="MACD", row=2, col=1)
        fig.update_yaxes(title_text="Stochastic", row=3, col=1, range=[0, 100])
        fig.update_xaxes(title_text="Date", row=3, col=1)

        return fig

    def add_ict_overlays(
        self,
        fig: go.Figure,
        df: pd.DataFrame,
        fvgs: Optional[List[Dict]] = None,
        order_blocks: Optional[List[Dict]] = None,
        liquidity_pools: Optional[List[Dict]] = None
    ) -> go.Figure:
        """
        Add ICT concept overlays to existing chart

        Args:
            fig: Existing Plotly figure
            df: DataFrame with OHLCV data
            fvgs: List of Fair Value Gaps
            order_blocks: List of Order Blocks
            liquidity_pools: List of Liquidity Pools

        Returns:
            Updated figure
        """
        # Add Fair Value Gaps
        if fvgs:
            for fvg in fvgs:
                # Determine color based on type
                color = self.COLORS['fvg_bullish'] if fvg['type'] == 'bullish' else self.COLORS['fvg_bearish']

                # Add rectangle
                fig.add_shape(
                    type="rect",
                    x0=fvg['start_time'],
                    x1=fvg['end_time'] if 'end_time' in fvg else df.index[-1],
                    y0=fvg['lower'],
                    y1=fvg['upper'],
                    fillcolor=color,
                    line=dict(width=0),
                    layer="below",
                    row=1, col=1
                )

                # Add label
                fig.add_annotation(
                    x=fvg['start_time'],
                    y=fvg['upper'],
                    text=f"FVG {fvg['fill_percentage']:.0f}% filled",
                    showarrow=False,
                    font=dict(size=10, color='white'),
                    bgcolor=color,
                    row=1, col=1
                )

        # Add Order Blocks
        if order_blocks:
            for ob in order_blocks:
                fig.add_shape(
                    type="rect",
                    x0=ob['start_time'],
                    x1=ob['end_time'] if 'end_time' in ob else df.index[-1],
                    y0=ob['lower'],
                    y1=ob['upper'],
                    fillcolor=self.COLORS['order_block'],
                    line=dict(color='blue', width=1, dash='dot'),
                    layer="below",
                    row=1, col=1
                )

                fig.add_annotation(
                    x=ob['start_time'],
                    y=ob['upper'],
                    text=f"OB ({ob.get('strength', 0):.0f})",
                    showarrow=False,
                    font=dict(size=10, color='white'),
                    bgcolor='blue',
                    row=1, col=1
                )

        # Add Liquidity Pools
        if liquidity_pools:
            for pool in liquidity_pools:
                # Horizontal line at liquidity level
                fig.add_hline(
                    y=pool['price'],
                    line_dash="dash",
                    line_color='yellow',
                    opacity=0.6,
                    annotation_text=f"Liq: ${pool['price']:.2f}",
                    row=1, col=1
                )

        return fig

    def create_volume_profile(
        self,
        df: pd.DataFrame,
        bins: int = 50,
        title: str = "Volume Profile"
    ) -> go.Figure:
        """
        Create horizontal volume profile

        Args:
            df: DataFrame with OHLCV data
            bins: Number of price bins
            title: Chart title

        Returns:
            Plotly Figure
        """
        # Calculate price range
        price_min = df['low'].min()
        price_max = df['high'].max()
        price_range = price_max - price_min

        # Create bins
        bin_size = price_range / bins
        price_bins = np.arange(price_min, price_max + bin_size, bin_size)

        # Calculate volume at each price level
        volume_at_price = np.zeros(len(price_bins) - 1)

        for i in range(len(df)):
            # Typical price for this candle
            typical_price = (df['high'].iloc[i] + df['low'].iloc[i] + df['close'].iloc[i]) / 3
            volume = df['volume'].iloc[i]

            # Find which bin this belongs to
            bin_idx = int((typical_price - price_min) / bin_size)
            if 0 <= bin_idx < len(volume_at_price):
                volume_at_price[bin_idx] += volume

        # Find POC (Point of Control - highest volume)
        poc_idx = np.argmax(volume_at_price)
        poc_price = price_bins[poc_idx] + bin_size / 2

        # Calculate Value Area (70% of volume)
        total_volume = volume_at_price.sum()
        target_volume = total_volume * 0.70

        # Sort by volume to find value area
        sorted_indices = np.argsort(volume_at_price)[::-1]
        cumulative_volume = 0
        value_area_indices = []

        for idx in sorted_indices:
            cumulative_volume += volume_at_price[idx]
            value_area_indices.append(idx)
            if cumulative_volume >= target_volume:
                break

        vah_price = price_bins[max(value_area_indices)] + bin_size  # Value Area High
        val_price = price_bins[min(value_area_indices)]  # Value Area Low

        # Create figure
        fig = go.Figure()

        # Add horizontal bars for volume profile
        colors = ['yellow' if i == poc_idx else 'cyan' if i in value_area_indices else 'gray'
                 for i in range(len(volume_at_price))]

        fig.add_trace(
            go.Bar(
                y=[(price_bins[i] + price_bins[i+1]) / 2 for i in range(len(volume_at_price))],
                x=volume_at_price,
                orientation='h',
                marker=dict(color=colors, opacity=0.6),
                name='Volume Profile',
                hovertemplate='Price: $%{y:.2f}<br>Volume: %{x:,.0f}<extra></extra>'
            )
        )

        # Add POC line
        fig.add_hline(
            y=poc_price,
            line_dash="solid",
            line_color="yellow",
            line_width=2,
            annotation_text=f"POC: ${poc_price:.2f}",
            annotation_position="right"
        )

        # Add VAH line
        fig.add_hline(
            y=vah_price,
            line_dash="dash",
            line_color="cyan",
            annotation_text=f"VAH: ${vah_price:.2f}",
            annotation_position="right"
        )

        # Add VAL line
        fig.add_hline(
            y=val_price,
            line_dash="dash",
            line_color="cyan",
            annotation_text=f"VAL: ${val_price:.2f}",
            annotation_position="right"
        )

        # Update layout
        fig.update_layout(
            title=title,
            height=600,
            template='plotly_dark' if self.theme == 'dark' else 'plotly_white',
            xaxis_title="Volume",
            yaxis_title="Price",
            showlegend=False
        )

        return fig

    def create_market_heatmap(
        self,
        data: Dict[str, float],
        title: str = "Market Heatmap",
        colorscale: str = 'RdYlGn'
    ) -> go.Figure:
        """
        Create market heatmap (e.g., sector performance)

        Args:
            data: Dict of {name: percent_change}
            title: Chart title
            colorscale: Plotly colorscale

        Returns:
            Plotly Figure
        """
        # Sort by value
        sorted_data = sorted(data.items(), key=lambda x: x[1], reverse=True)
        names = [item[0] for item in sorted_data]
        values = [item[1] for item in sorted_data]

        # Create treemap
        fig = go.Figure(go.Treemap(
            labels=names,
            values=[abs(v) for v in values],  # Use absolute for sizing
            parents=[""] * len(names),
            marker=dict(
                colors=values,
                colorscale=colorscale,
                cmid=0,
                colorbar=dict(title="Change %")
            ),
            text=[f"{n}<br>{v:+.2f}%" for n, v in zip(names, values)],
            textposition="middle center",
            hovertemplate='<b>%{label}</b><br>Change: %{color:+.2f}%<extra></extra>'
        ))

        fig.update_layout(
            title=title,
            height=600,
            template='plotly_dark' if self.theme == 'dark' else 'plotly_white'
        )

        return fig
