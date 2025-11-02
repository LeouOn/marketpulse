"""MarketPulse - API Integration Layer
Handles data collection from multiple sources: Alpaca, Rithmic, Coinbase
"""

from .alpaca_client import AlpacaClient
from .rithmic_client import RithmicClient  
from .coinbase_client import CoinbaseClient

__all__ = [
    'AlpacaClient',
    'RithmicClient', 
    'CoinbaseClient'
]