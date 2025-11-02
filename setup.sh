#!/bin/bash

# MarketPulse Setup Script
# Sets up the development environment for MarketPulse

set -e

echo "🚀 Setting up MarketPulse development environment..."
echo "=================================================="

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8+ first."
    exit 1
fi

echo "✅ Prerequisites check passed"

# Create virtual environment
echo "📦 Creating Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "ℹ️ Virtual environment already exists"
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️ Upgrading pip..."
pip install --upgrade pip

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

# Create environment file
echo "⚙️ Creating environment configuration..."
if [ ! -f ".env" ]; then
    cat > .env << EOF
# MarketPulse Environment Configuration
# Copy your API keys from config/credentials.example.yaml to this file

# Database (auto-configured by Docker)
DATABASE_URL=postgresql://marketpulse:marketpulse_password@localhost:5432/marketpulse

# API Keys (replace with your actual keys)
ALPACA_KEY_ID=your_alpaca_key_here
ALPACA_SECRET_KEY=your_alpaca_secret_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets

RITHMIC_USERNAME=your_rithmic_username
RITHMIC_PASSWORD=your_rithmic_password

COINBASE_API_KEY=your_coinbase_api_key
COINBASE_API_SECRET=your_coinbase_secret
COINBASE_PASSPHRASE=your_coinbase_passphrase

OPENROUTER_API_KEY=your_openrouter_api_key

# Logging
LOG_LEVEL=INFO
EOF
    echo "✅ Environment file created (.env)"
else
    echo "ℹ️ Environment file already exists"
fi

# Start database
echo "🐘 Starting PostgreSQL database..."
docker-compose up -d postgres

# Wait for database to be ready
echo "⏳ Waiting for database to be ready..."
sleep 5

# Check if database is ready
until docker exec marketpulse-db pg_isready -U marketpulse -d marketpulse; do
    echo "⏳ Database not ready yet..."
    sleep 2
done

echo "✅ Database is ready!"

# Create __init__.py files to make directories packages
find src -type d -exec touch {}/__init__.py \;

echo ""
echo "🎉 MarketPulse setup completed successfully!"
echo ""
echo "📋 Next steps:"
echo "1. Copy config/credentials.example.yaml to config/credentials.yaml"
echo "2. Add your actual API keys to config/credentials.yaml"
echo "3. Test the setup: python marketpulse.py --mode collect"
echo ""
echo "🔗 Quick commands:"
echo "• Single collection: python marketpulse.py --mode collect"
echo "• Continuous monitoring: python marketpulse.py --mode monitor"
echo "• View database: docker exec -it marketpulse-db psql -U marketpulse -d marketpulse"
echo "• Stop database: docker-compose down"
echo ""
echo "Happy trading! 📈"