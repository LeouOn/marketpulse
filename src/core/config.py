"""MarketPulse Core Configuration
Handles settings, credentials, and application configuration
"""

import os
from typing import Optional
from pydantic import BaseSettings, Field
from pathlib import Path


class ApiKeys(BaseSettings):
    """API Keys configuration"""
    
    class AlpacaConfig(BaseSettings):
        key_id: str
        secret_key: str
        base_url: str = "https://paper-api.alpaca.markets"
    
    class RithmicConfig(BaseSettings):
        username: str
        password: str
        system_name: str
        login_prefix: str
    
    class CoinbaseConfig(BaseSettings):
        api_key: str
        api_secret: str
        passphrase: str
    
    class OpenRouterConfig(BaseSettings):
        api_key: str
    
    alpaca: AlpacaConfig
    rithmic: RithmicConfig
    coinbase: CoinbaseConfig
    openrouter: OpenRouterConfig


class LLMSettings(BaseSettings):
    """LLM Configuration"""
    
    class PrimaryConfig(BaseSettings):
        base_url: str = "http://localhost:1234/v1"
        api_key: str = "not-needed"
        timeout: int = 30
    
    class FallbackConfig(BaseSettings):
        base_url: str = "https://openrouter.ai/api/v1"
        api_key: str
        timeout: int = 60
    
    primary: PrimaryConfig
    fallback: FallbackConfig


class Settings(BaseSettings):
    """Main MarketPulse settings"""
    
    # Database
    database_host: str = "localhost"
    database_port: int = 5432
    database_name: str = "marketpulse"
    database_user: str = "marketpulse"
    database_password: str = "marketpulse_password"
    
    # API Keys
    api_keys: ApiKeys
    
    # LLM Settings
    llm: LLMSettings
    
    # Market settings
    nq_symbol: str = "MNQ"
    btc_symbol: str = "BTC-USD"
    eth_symbol: str = "ETH-USD"
    
    # Analysis intervals (seconds)
    internals_interval: int = 60
    llm_analysis_interval: int = 300
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    @property
    def database_url(self) -> str:
        """Database connection URL"""
        return f"postgresql://{self.database_user}:{self.database_password}@{self.database_host}:{self.database_port}/{self.database_name}"


# Global settings instance
settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create settings instance"""
    global settings
    if settings is None:
        settings = Settings()
    return settings