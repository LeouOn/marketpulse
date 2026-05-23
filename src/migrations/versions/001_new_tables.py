"""add symbols, symbol_stats, screener_snapshots, breadth_snapshots, data_fetch_log, indicators tables

Revision ID: 001
Revises: None
Create Date: 2026-05-21

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '001'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('symbols', sa.Schema('market_data'),
        sa.Column('id', sa.Integer, autoincrement=True, nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('name', sa.String(200)),
        sa.Column('asset_type', sa.String(20), nullable=False),
        sa.Column('exchange', sa.String(20)),
        sa.Column('sector', sa.String(50)),
        sa.Column('industry', sa.String(100)),
        sa.Column('currency', sa.String(3), server_default='USD'),
        sa.Column('lot_size', sa.Float, server_default='1'),
        sa.Column('tick_size', sa.Float, server_default='0.01'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('yahoo_symbol', sa.String(20)),
        sa.Column('alpaca_symbol', sa.String(20)),
        sa.Column('data_source', sa.String(20), server_default='yahoo'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('symbol', name='_symbol_uc'),
    )
    op.create_index('ix_symbols_symbol', 'symbols', ['symbol'], schema='market_data')
    op.create_index('ix_symbols_sector', 'symbols', ['sector'], schema='market_data')
    op.create_index('ix_symbols_is_active', 'symbols', ['is_active'], schema='market_data')

    op.create_table('symbol_stats', sa.Schema('market_data'),
        sa.Column('id', sa.Integer, autoincrement=True, nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('date', sa.Date, nullable=False),
        sa.Column('high_52w', sa.Float),
        sa.Column('low_52w', sa.Float),
        sa.Column('pct_from_52w_high', sa.Float),
        sa.Column('pct_from_52w_low', sa.Float),
        sa.Column('avg_volume_20d', sa.Integer),
        sa.Column('avg_volume_50d', sa.Integer),
        sa.Column('sma_20', sa.Float),
        sa.Column('sma_50', sa.Float),
        sa.Column('sma_200', sa.Float),
        sa.Column('atr_14', sa.Float),
        sa.Column('beta', sa.Float),
        sa.Column('market_cap', sa.BigInteger),
        sa.Column('pe_ratio', sa.Float),
        sa.Column('prev_close', sa.Float),
        sa.Column('day_range_pct', sa.Float),
        sa.Column('year_high_date', sa.Date),
        sa.Column('year_low_date', sa.Date),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('symbol', 'date', name='_symbol_date_uc'),
    )
    op.create_index('ix_symbol_stats_symbol', 'symbol_stats', ['symbol'], schema='market_data')

    op.create_table('screener_snapshots', sa.Schema('market_data'),
        sa.Column('id', sa.Integer, autoincrement=True, nullable=False),
        sa.Column('snapshot_date', sa.Date, nullable=False),
        sa.Column('screener_type', sa.String(20), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('rank', sa.Integer, nullable=False),
        sa.Column('price', sa.Float),
        sa.Column('change_pct', sa.Float),
        sa.Column('volume', sa.BigInteger),
        sa.Column('market_cap', sa.BigInteger),
        sa.Column('avg_volume_3m', sa.BigInteger),
        sa.Column('relative_volume', sa.Float),
        sa.Column('extra_data', sa.JSON),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('snapshot_date', 'screener_type', 'symbol', name='_snapshot_screener_symbol_uc'),
    )
    op.create_index('ix_screener_snapshots_symbol', 'screener_snapshots', ['symbol'], schema='market_data')

    op.create_table('breadth_snapshots', sa.Schema('market_data'),
        sa.Column('id', sa.Integer, autoincrement=True, nullable=False),
        sa.Column('date', sa.Date, nullable=False),
        sa.Column('nyse_advancing', sa.Integer),
        sa.Column('nyse_declining', sa.Integer),
        sa.Column('nyse_unchanged', sa.Integer),
        sa.Column('nyse_ad_ratio', sa.Float),
        sa.Column('nasdaq_advancing', sa.Integer),
        sa.Column('nasdaq_declining', sa.Integer),
        sa.Column('nasdaq_unchanged', sa.Integer),
        sa.Column('nasdaq_ad_ratio', sa.Float),
        sa.Column('new_highs_52w', sa.Integer),
        sa.Column('new_lows_52w', sa.Integer),
        sa.Column('tick_avg_30m', sa.Float),
        sa.Column('vold_nyse', sa.BigInteger),
        sa.Column('mcclellan_osc', sa.Float),
        sa.Column('mcclellan_sum', sa.Float),
        sa.Column('trin', sa.Float),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('date', name='_breadth_date_uc'),
    )

    op.create_table('data_fetch_log', sa.Schema('market_data'),
        sa.Column('id', sa.Integer, autoincrement=True, nullable=False),
        sa.Column('source', sa.String(20), nullable=False),
        sa.Column('endpoint', sa.String(200), nullable=False),
        sa.Column('symbols', sa.Text),
        sa.Column('status', sa.String(10), nullable=False),
        sa.Column('response_ms', sa.Integer),
        sa.Column('bars_fetched', sa.Integer, server_default='0'),
        sa.Column('error_message', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('indicators', sa.Schema('analysis'),
        sa.Column('id', sa.Integer, autoincrement=True, nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('timeframe', sa.String(10), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('indicator_type', sa.String(30), nullable=False),
        sa.Column('params', sa.JSON, nullable=False),
        sa.Column('value', sa.Float),
        sa.Column('values', sa.JSON),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('symbol', 'timeframe', 'timestamp', 'indicator_type', 'params', name='_indicator_uc'),
    )
    op.create_index('ix_indicators_symbol', 'indicators', ['symbol'], schema='analysis')
    op.create_index('ix_indicators_timestamp', 'indicators', ['timestamp'], schema='analysis')

    op.add_column('prices', sa.Column('adjusted_close', sa.Float), schema='market_data')
    op.add_column('prices', sa.Column('split_factor', sa.Float, server_default='1'), schema='market_data')
    op.add_column('prices', sa.Column('dividend_amount', sa.Float, server_default='0'), schema='market_data')
    op.add_column('prices', sa.Column('source', sa.String(20), server_default='yahoo'), schema='market_data')


def downgrade() -> None:
    op.drop_table('indicators', schema='analysis')
    op.drop_table('data_fetch_log', schema='market_data')
    op.drop_table('breadth_snapshots', schema='market_data')
    op.drop_table('screener_snapshots', schema='market_data')
    op.drop_table('symbol_stats', schema='market_data')
    op.drop_table('symbols', schema='market_data')

    op.drop_column('prices', 'source', schema='market_data')
    op.drop_column('prices', 'dividend_amount', schema='market_data')
    op.drop_column('prices', 'split_factor', schema='market_data')
    op.drop_column('prices', 'adjusted_close', schema='market_data')
