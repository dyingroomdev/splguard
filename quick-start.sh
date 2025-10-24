#!/bin/bash
# Quick start script - minimal version for experienced users

set -e

echo "🛡️ SPL Shield Bot - Quick Start"
echo ""

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Install: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check .env
if [ ! -f .env ]; then
    echo "📝 Creating .env from template..."
    cp .env.example .env
    echo "⚠️  Edit .env and add your BOT_TOKEN!"
    echo "   Run: nano .env"
    exit 1
fi

# Check BOT_TOKEN
if grep -q "BOT_TOKEN=your_bot_token_here" .env; then
    echo "⚠️  BOT_TOKEN not configured in .env"
    echo "   Edit .env and add your real token"
    exit 1
fi

# Build and start
echo "🔨 Building and starting bot..."
docker-compose up -d --build

# Run migrations
echo "📊 Running database migrations..."
docker-compose run --rm bot alembic upgrade head

echo ""
echo "✅ Bot started!"
echo ""
echo "📋 View logs:  docker-compose logs -f bot"
echo "🛑 Stop bot:   docker-compose stop"
echo ""
