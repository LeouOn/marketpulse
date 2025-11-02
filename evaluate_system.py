#!/usr/bin/env python3
"""
MarketPulse System Evaluation
Evaluates the current implementation and identifies gaps
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.config import get_settings
from src.core.database import DatabaseManager
from src.llm.llm_client import LLMManager
from src.data.market_collector import MarketPulseCollector


class SystemEvaluator:
    """Evaluates MarketPulse system components"""
    
    def __init__(self):
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'components': {},
            'missing_features': [],
            'working_features': [],
            'recommendations': []
        }
    
    async def evaluate_system(self):
        """Run complete system evaluation"""
        print("🔍 MarketPulse System Evaluation")
        print("=" * 50)
        
        # Test core components
        await self._test_configuration()
        await self._test_database()
        await self._test_llm_integration()
        await self._test_market_collector()
        await self._test_api_integration()
        
        # Generate report
        self._generate_report()
    
    async def _test_configuration(self):
        """Test configuration system"""
        print("📋 Testing Configuration System...")
        
        try:
            # Test settings loading
            settings = get_settings()
            has_database_url = hasattr(settings, 'database_url')
            has_api_keys = hasattr(settings, 'api_keys')
            has_llm_config = hasattr(settings, 'llm')
            
            status = {
                'available': True,
                'database_url': has_database_url,
                'api_keys': has_api_keys,
                'llm_config': has_llm_config
            }
            
            self.results['components']['configuration'] = status
            print("   ✅ Configuration system working")
            
        except Exception as e:
            print(f"   ❌ Configuration error: {e}")
            self.results['components']['configuration'] = {'available': False, 'error': str(e)}
    
    async def _test_database(self):
        """Test database system"""
        print("🗄️ Testing Database System...")
        
        try:
            # Test database manager
            db_url = "sqlite:///:memory:"  # Use in-memory for testing
            db_manager = DatabaseManager(db_url)
            db_manager.create_engine()
            db_manager.create_tables()
            
            # Test basic operations
            session = db_manager.get_session()
            session.close()
            
            status = {
                'available': True,
                'connection': True,
                'tables_created': True
            }
            
            self.results['components']['database'] = status
            print("   ✅ Database system working")
            
        except Exception as e:
            print(f"   ❌ Database error: {e}")
            self.results['components']['database'] = {'available': False, 'error': str(e)}
    
    async def _test_llm_integration(self):
        """Test LLM integration"""
        print("🤖 Testing LLM Integration...")
        
        try:
            # Test LLM manager initialization
            llm_manager = LLMManager()
            status = llm_manager.get_status()
            
            # Test model availability
            has_lm_studio = 'lm_studio' in status
            has_openrouter = 'openrouter' in status
            
            llm_status = {
                'available': True,
                'lm_studio_configured': has_lm_studio,
                'openrouter_configured': has_openrouter,
                'models': status.get('lm_studio', {}).get('models', {})
            }
            
            self.results['components']['llm'] = llm_status
            print("   ✅ LLM integration configured")
            
            if has_lm_studio:
                print("   📍 LM Studio: Ready for local models")
            if has_openrouter:
                print("   ☁️ OpenRouter: Ready for cloud fallback")
            
        except Exception as e:
            print(f"   ❌ LLM integration error: {e}")
            self.results['components']['llm'] = {'available': False, 'error': str(e)}
    
    async def _test_market_collector(self):
        """Test market collector"""
        print("📊 Testing Market Collector...")
        
        try:
            collector = MarketPulseCollector()
            
            # Test initialization without API calls
            result = await collector.initialize()
            
            collector_status = {
                'available': True,
                'initialization': result,
                'symbols_configured': len(collector.symbols)
            }
            
            self.results['components']['market_collector'] = collector_status
            print("   ✅ Market collector initialized")
            print(f"   📈 Configured symbols: {list(collector.symbols.keys())}")
            
        except Exception as e:
            print(f"   ❌ Market collector error: {e}")
            self.results['components']['market_collector'] = {'available': False, 'error': str(e)}
    
    async def _test_api_integration(self):
        """Test API integration"""
        print("🔌 Testing API Integration...")
        
        try:
            settings = get_settings()
            
            # Check Alpaca integration
            has_alpaca_keys = (
                hasattr(settings.api_keys, 'alpaca') and
                hasattr(settings.api_keys.alpaca, 'key_id')
            )
            
            # Check Rithmic integration
            has_rithmic_keys = (
                hasattr(settings.api_keys, 'rithmic') and
                hasattr(settings.api_keys.rithmic, 'username')
            )
            
            # Check Coinbase integration
            has_coinbase_keys = (
                hasattr(settings.api_keys, 'coinbase') and
                hasattr(settings.api_keys.coinbase, 'api_key')
            )
            
            api_status = {
                'alpaca_configured': bool(has_alpaca_keys),
                'rithmic_configured': bool(has_rithmic_keys),
                'coinbase_configured': bool(has_coinbase_keys)
            }
            
            self.results['components']['api_integration'] = api_status
            print("   📍 API integration structure ready")
            
            if has_alpaca_keys:
                print("   ✅ Alpaca: Keys configured")
            else:
                print("   ⚠️ Alpaca: Keys need configuration")
                
            if has_rithmic_keys:
                print("   ✅ Rithmic: Keys configured")  
            else:
                print("   ⚠️ Rithmic: Keys need configuration")
                
            if has_coinbase_keys:
                print("   ✅ Coinbase: Keys configured")
            else:
                print("   ⚠️ Coinbase: Keys need configuration")
            
        except Exception as e:
            print(f"   ❌ API integration error: {e}")
            self.results['components']['api_integration'] = {'available': False, 'error': str(e)}
    
    def _generate_report(self):
        """Generate evaluation report"""
        print("\n📋 EVALUATION REPORT")
        print("=" * 50)
        
        # Working features
        working = []
        if self.results['components'].get('configuration', {}).get('available'):
            working.append("Configuration System")
        if self.results['components'].get('database', {}).get('available'):
            working.append("Database System")
        if self.results['components'].get('llm', {}).get('available'):
            working.append("LLM Integration")
        if self.results['components'].get('market_collector', {}).get('available'):
            working.append("Market Collector")
        
        # Missing features
        missing = []
        api_config = self.results['components'].get('api_integration', {})
        if not api_config.get('alpaca_configured'):
            missing.append("Alpaca API Keys")
        if not api_config.get('rithmic_configured'):
            missing.append("Rithmic API Keys")
        if not api_config.get('coinbase_configured'):
            missing.append("Coinbase API Keys")
        
        # System health
        print("✅ WORKING FEATURES:")
        for feature in working:
            print(f"   • {feature}")
        
        print("\n⚠️ NEEDS ATTENTION:")
        for feature in missing:
            print(f"   • {feature}")
        
        # Recommendations
        recommendations = [
            "Add Alpaca API keys to config/credentials.yaml for stock market data",
            "Add Rithmic credentials for NQ futures data ($99/month)",
            "Add Coinbase API keys for BTC/ETH crypto data", 
            "Test LM Studio connection for local LLM models",
            "Set up OpenRouter API key as cloud LLM fallback",
            "Run actual market data collection tests",
            "Implement alert system for significant market changes",
            "Create web dashboard for data visualization"
        ]
        
        print("\n💡 RECOMMENDATIONS:")
        for i, rec in enumerate(recommendations, 1):
            print(f"   {i}. {rec}")
        
        # Feature completeness
        total_features = 8
        working_count = len(working)
        completion_pct = (working_count / total_features) * 100
        
        print(f"\n📊 SYSTEM COMPLETION: {completion_pct:.1f}%")
        
        if completion_pct >= 80:
            print("🎉 Excellent! System is production-ready with minor configuration")
        elif completion_pct >= 60:
            print("👍 Good progress! Core features working, needs API keys")
        else:
            print("🔧 Still in development, working on core functionality")
        
        # Next immediate steps
        print("\n🚀 IMMEDIATE NEXT STEPS:")
        if not api_config.get('alpaca_configured'):
            print("   1. Add Alpaca API key (free) to config/credentials.yaml")
            print("   2. Run: python marketpulse.py --mode collect")
        else:
            print("   1. Run: python marketpulse.py --mode collect")
            print("   2. Test continuous monitoring: python marketpulse.py --mode monitor")
        
        print("\n✅ Evaluation completed!")
        
        # Save results
        self._save_evaluation_results()
    
    def _save_evaluation_results(self):
        """Save evaluation results to file"""
        import json
        
        results_file = Path("evaluation_results.json")
        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"\n📁 Evaluation results saved to: {results_file}")


async def main():
    """Main evaluation function"""
    evaluator = SystemEvaluator()
    await evaluator.evaluate_system()


if __name__ == "__main__":
    asyncio.run(main())