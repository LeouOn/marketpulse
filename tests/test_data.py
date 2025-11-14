import sys
sys.path.append('.')
from src.data.market_collector import MarketPulseCollector
import asyncio

async def test_data():
    print('Testing market data collection...')
    collector = MarketPulseCollector()
    init_result = await collector.initialize()
    print(f'Initialization result: {init_result}')

    try:
        internals = await collector.collect_market_internals()
        if internals:
            print(f'Success! Data source: {internals.get("data_source", "unknown")}')
            print(f'Available symbols: {list(internals.keys())[:5]}')  # First 5 keys

            # Check for specific market data
            if 'spy' in internals:
                spy_data = internals['spy']
                print(f'SPY data: Price=${spy_data.get("price", "N/A")}, Change={spy_data.get("change", "N/A")}')

            if 'volume_flow' in internals:
                print(f'Volume flow data available: {internals["volume_flow"]}')

        else:
            print('No data collected')
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_data())