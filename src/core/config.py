"""MarketPulse Core Configuration
Handles settings, credentials, and application configuration
"""

import os
from typing import Optional, Dict, Any
from pydantic import Field, ConfigDict
from pydantic_settings import BaseSettings
from pathlib import Path
import yaml
import re


def interpolate_env_vars(value: str, env_vars: Dict[str, str]) -> str:
    """Interpolate environment variables in configuration values"""
    if not isinstance(value, str):
        return value
    
    # Handle ${section:key:subkey} format
    pattern = r'\$\{([^}]+)\}'
    
    def replace_match(match):
        path = match.group(1)
        env_key = path.replace(':', '_').upper()
        return env_vars.get(env_key, match.group(0))
    
    return re.sub(pattern, replace_match, value)


class ApiKeys(BaseSettings):
    """API Keys configuration"""
    
    class AlpacaConfig(BaseSettings):
        key_id: str = "your_alpaca_key_here"
        secret_key: str = "your_alpaca_secret_here"
        base_url: str = "https://paper-api.alpaca.markets"
    
    class RithmicConfig(BaseSettings):
        username: str = "your_rithmic_username"
        password: str = "your_rithmic_password"
        system_name: str = "your_system_name"
        login_prefix: str = "your_login_prefix"
    
    class CoinbaseConfig(BaseSettings):
        api_key: str = "your_coinbase_api_key"
        api_secret: str = "your_coinbase_secret"
        passphrase: str = "your_coinbase_passphrase"
    
    class OpenRouterConfig(BaseSettings):
        api_key: str = "your_openrouter_api_key"
    
    alpaca: AlpacaConfig = Field(default_factory=AlpacaConfig)
    rithmic: RithmicConfig = Field(default_factory=RithmicConfig)
    coinbase: CoinbaseConfig = Field(default_factory=CoinbaseConfig)
    openrouter: OpenRouterConfig = Field(default_factory=OpenRouterConfig)


class LLMSettings(BaseSettings):
    """LLM Configuration"""
    
    class PrimaryConfig(BaseSettings):
        base_url: str = "http://localhost:1234/v1"
        api_key: str = "not-needed"
        timeout: int = 30
    
    class FallbackConfig(BaseSettings):
        base_url: str = "https://openrouter.ai/api/v1"
        api_key: str = "your_openrouter_api_key"
        timeout: int = 60
    
    primary: PrimaryConfig = Field(default_factory=PrimaryConfig)
    fallback: FallbackConfig = Field(default_factory=FallbackConfig)


class MarketSettings(BaseSettings):
    """Market-specific settings"""
    
    class NQConfig(BaseSettings):
        symbol: str = "MNQ"
        timezone: str = "America/New_York"
        trading_hours: str = "09:30-16:00"
        tick_size: float = 0.25
        tick_value: float = 5.00
    
    class BTCConfig(BaseSettings):
        symbol: str = "BTC-USD"
        timezone: str = "UTC"
        trading_hours: str = "24/7"
        tick_size: float = 1.0
        tick_value: float = "varies"
    
    class ETHConfig(BaseSettings):
        symbol: str = "ETH-USD"
        timezone: str = "UTC"
        trading_hours: str = "24/7"
        tick_size: float = 0.01
        tick_value: str = "varies"
    
    nq: NQConfig = Field(default_factory=NQConfig)
    btc: BTCConfig = Field(default_factory=BTCConfig)
    eth: ETHConfig = Field(default_factory=ETHConfig)


class AnalysisSettings(BaseSettings):
    """Analysis and monitoring settings"""
    
    internals_interval: int = 60
    llm_analysis_interval: int = 300
    
    class AlertThresholds(BaseSettings):
        volatility_spike: float = 2.0
        volume_spike: float = 3.0
        momentum_shift: float = 0.5
    
    alert_thresholds: AlertThresholds = Field(default_factory=AlertThresholds)


class LoggingSettings(BaseSettings):
    """Logging configuration"""
    
    level: str = "INFO"
    format: str = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}"
    rotation: str = "10 MB"
    retention: str = "30 days"


class Settings(BaseSettings):
    """Main MarketPulse settings"""
    
    # Database
    database_host: str = "localhost"
    database_port: int = 5432
    database_name: str = "marketpulse"
    database_user: str = "marketpulse"
    database_password: str = "marketpulse_password"
    
    # API Keys
    api_keys: ApiKeys = Field(default_factory=ApiKeys)
    
    # LLM Settings
    llm: LLMSettings = Field(default_factory=LLMSettings)
    
    # Market settings
    markets: MarketSettings = Field(default_factory=MarketSettings)
    analysis: AnalysisSettings = Field(default_factory=AnalysisSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    
    # Convenience aliases for backward compatibility
    nq_symbol: str = "MNQ"
    btc_symbol: str = "BTC-USD"
    eth_symbol: str = "ETH-USD"
    internals_interval: int = 60
    llm_analysis_interval: int = 300
    
    model_config = ConfigDict(
        env_file=[".env", "config/.env"],
        case_sensitive=False,
        extra="allow"
    )
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._load_from_yaml()
    
    def _load_from_yaml(self):
        """Load configuration from YAML file if available"""
        yaml_path = Path("config/credentials.yaml")
        if not yaml_path.exists():
            yaml_path = Path("config/credentials.example.yaml")
        
        if yaml_path.exists():
            try:
                with open(yaml_path, 'r') as f:
                    yaml_data = yaml.safe_load(f)
                
                # Get environment variables for interpolation
                env_vars = dict(os.environ)
                
                # Update settings from YAML data
                for section, values in yaml_data.items():
                    if hasattr(self, section):
                        section_obj = getattr(self, section)
                        if hasattr(section_obj, 'model_dump'):
                            # It's a Pydantic model
                            updated_values = self._interpolate_dict(values, env_vars)
                            for key, value in updated_values.items():
                                if hasattr(section_obj, key):
                                    setattr(section_obj, key, value)
                        else:
                            # It's a regular attribute
                            updated_values = self._interpolate_dict(values, env_vars)
                            for key, value in updated_values.items():
                                setattr(section_obj, key, value)
                    
                    # Handle convenience aliases
                    if section == 'markets':
                        if 'nq' in values:
                            self.nq_symbol = values['nq'].get('symbol', self.nq_symbol)
                        if 'btc' in values:
                            self.btc_symbol = values['btc'].get('symbol', self.btc_symbol)
                        if 'eth' in values:
                            self.eth_symbol = values['eth'].get('symbol', self.eth_symbol)
                    
                    if section == 'analysis':
                        if 'internals_interval' in values:
                            self.internals_interval = values['internals_interval']
                            self.analysis.internals_interval = values['internals_interval']
                        if 'llm_analysis_interval' in values:
                            self.llm_analysis_interval = values['llm_analysis_interval']
                            self.analysis.llm_analysis_interval = values['llm_analysis_interval']
                
            except Exception as e:
                print(f"Warning: Could not load YAML config: {e}")
    
    def _interpolate_dict(self, obj: Any, env_vars: Dict[str, str]) -> Any:
        """Recursively interpolate environment variables in a dictionary"""
        if isinstance(obj, dict):
            return {k: self._interpolate_dict(v, env_vars) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._interpolate_dict(item, env_vars) for item in obj]
        elif isinstance(obj, str):
            return interpolate_env_vars(obj, env_vars)
        else:
            return obj
    
    @property
    def database_url(self) -> str:
        """Database connection URL"""
        return f"postgresql://{self.database_user}:{self.database_password}@{self.database_host}:{self.database_port}/{self.database_name}"
    
    def get_api_key(self, service: str, key_type: str = "api_key") -> str:
        """Get API key for a specific service"""
        if service == "alpaca":
            return getattr(self.api_keys.alpaca, key_type)
        elif service == "coinbase":
            return getattr(self.api_keys.coinbase, key_type)
        elif service == "openrouter":
            return getattr(self.api_keys.openrouter, key_type)
        else:
            return ""


# Global settings instance
_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create settings instance"""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance


def reload_settings() -> Settings:
    """Reload settings (useful for development)"""
    global _settings_instance
    _settings_instance = None
    return get_settings()