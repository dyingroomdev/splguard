#!/bin/bash
set -e

# ==============================================================================
# SPL Shield Bot - One-Command Installation Script
# ==============================================================================
# This script will:
# 1. Check for required dependencies (Docker, Docker Compose)
# 2. Create .env file from template
# 3. Initialize the database
# 4. Populate initial data (team, settings, presale)
# 5. Start the bot with Docker Compose
# ==============================================================================

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_header() {
    echo -e "${BLUE}"
    echo "=============================================================================="
    echo "$1"
    echo "=============================================================================="
    echo -e "${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Check if running with bash
if [ -z "$BASH_VERSION" ]; then
    print_error "This script must be run with bash"
    exit 1
fi

print_header "SPL Shield Bot Installation"

# Step 1: Check dependencies
print_info "Step 1/6: Checking dependencies..."

if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first:"
    print_info "https://docs.docker.com/get-docker/"
    exit 1
fi
print_success "Docker is installed"

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null 2>&1; then
    print_error "Docker Compose is not installed. Please install Docker Compose first:"
    print_info "https://docs.docker.com/compose/install/"
    exit 1
fi

# Detect which docker-compose command to use
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
else
    DOCKER_COMPOSE="docker compose"
fi
print_success "Docker Compose is installed ($DOCKER_COMPOSE)"

# Step 2: Create .env file
print_info "Step 2/6: Setting up environment configuration..."

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        print_success "Created .env file from template"
        print_warning "IMPORTANT: Please edit .env and add your BOT_TOKEN and other settings!"
        print_info "You can get a bot token from @BotFather on Telegram"

        # Ask if user wants to edit now
        read -p "Do you want to edit .env now? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            ${EDITOR:-nano} .env
        else
            print_warning "Remember to edit .env before starting the bot!"
            print_info "You can edit it later with: nano .env"
        fi
    else
        print_error ".env.example not found!"
        exit 1
    fi
else
    print_success ".env file already exists"

    # Check if BOT_TOKEN is still the default
    if grep -q "BOT_TOKEN=your_bot_token_here" .env; then
        print_warning "BOT_TOKEN is not configured in .env!"
        print_info "Please edit .env and add your real bot token"
        read -p "Do you want to edit .env now? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            ${EDITOR:-nano} .env
        fi
    fi
fi

# Step 3: Build Docker images
print_info "Step 3/6: Building Docker images..."
$DOCKER_COMPOSE build
print_success "Docker images built successfully"

# Step 4: Initialize database
print_info "Step 4/6: Initializing database..."

# Create an empty database file if it doesn't exist
if [ ! -f splguard.db ]; then
    touch splguard.db
    print_success "Created splguard.db"
else
    print_warning "Database file already exists, keeping existing data"
    read -p "Do you want to backup the existing database? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        BACKUP_FILE="splguard.db.backup.$(date +%Y%m%d_%H%M%S)"
        cp splguard.db "$BACKUP_FILE"
        print_success "Database backed up to $BACKUP_FILE"
    fi
fi

# Run migrations
print_info "Running database migrations..."
$DOCKER_COMPOSE run --rm bot alembic upgrade head
print_success "Database migrations completed"

# Step 5: Populate initial data
print_info "Step 5/6: Populating initial data..."

# Create a Python script to populate data
cat > /tmp/populate_initial_data.py << 'EOF'
import asyncio
import sys
from datetime import datetime, timezone

sys.path.insert(0, '/app/src')

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from splguard.models import Settings, Presale, PresaleStatus, TeamMember

async def populate_data():
    engine = create_async_engine("sqlite+aiosqlite:////app/splguard.db")
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Check if settings exist
        result = await session.execute(select(Settings).limit(1))
        settings = result.scalar_one_or_none()

        if not settings:
            print("Creating initial settings...")
            settings = Settings(
                project_name="SPL Shield",
                token_ticker="TDL",
                contract_addresses=["TDLTokenAddressWillBeProvidedSoon"],
                explorer_url="https://solscan.io/token/TDLTokenAddressWillBeProvidedSoon",
                website="https://splshield.com/",
                docs="https://docs.splshield.com/",
                social_links={
                    "Twitter": "https://twitter.com/splshield",
                    "Risk Scanner App": "https://app.splshield.com/",
                    "Dapp": "https://ex.splshield.com",
                    "Telegram": "https://t.me/splshield",
                }
            )
            session.add(settings)
            await session.commit()
            await session.refresh(settings)
            print("✓ Settings created")
        else:
            print("✓ Settings already exist")

        # Check if team members exist
        result = await session.execute(
            select(TeamMember).where(TeamMember.settings_id == settings.id)
        )
        team_count = len(result.scalars().all())

        if team_count == 0:
            print("Creating team members...")
            team_members = [
                TeamMember(
                    settings_id=settings.id,
                    name="Aragorn",
                    role="Lead Developer",
                    contact="@aragornspl",
                    bio="Building SPL Shield's AI Risk Engine and overseeing the TDL ecosystem's core smart contracts.",
                    display_order=1
                ),
                TeamMember(
                    settings_id=settings.id,
                    name="Tom Harris",
                    role="Marketing Head",
                    contact="@tomharrisuk",
                    bio="Driving global exposure, partnerships, and community growth for SPL Shield and $TDL.",
                    display_order=2
                ),
                TeamMember(
                    settings_id=settings.id,
                    name="Ethan Miller",
                    role="Chief Operating Officer",
                    contact="@ethanspl",
                    bio="Managing operations, presale strategy, and ecosystem expansion.",
                    display_order=3
                )
            ]
            for member in team_members:
                session.add(member)
            await session.commit()
            print(f"✓ Created {len(team_members)} team members")
        else:
            print(f"✓ Team members already exist ({team_count} members)")

        # Check if presale exists
        result = await session.execute(
            select(Presale).where(Presale.settings_id == settings.id).limit(1)
        )
        presale = result.scalar_one_or_none()

        if not presale:
            print("Creating presale record...")
            presale = Presale(
                settings_id=settings.id,
                status=PresaleStatus.UPCOMING,
                platform="SPL Shield Platform",
                links={"presale": "https://presale.splshield.com/"},
                start_time=datetime(2025, 10, 26, 18, 0, 0, tzinfo=timezone.utc),
                faqs=[
                    {"question": "What is the presale price?", "answer": "$0.002 per TDL"},
                    {"question": "What is the total supply?", "answer": "1 Billion TDL tokens"},
                    {"question": "When does the presale start?", "answer": "6 PM UTC (00+), 26th October 2025"}
                ]
            )
            session.add(presale)
            await session.commit()
            print("✓ Presale created")
        else:
            print("✓ Presale already exists")

    await engine.dispose()
    print("\n✓ All initial data populated successfully!")

if __name__ == "__main__":
    asyncio.run(populate_data())
EOF

$DOCKER_COMPOSE run --rm bot python /tmp/populate_initial_data.py
print_success "Initial data populated"

# Step 6: Start the bot
print_info "Step 6/6: Starting the bot..."

$DOCKER_COMPOSE up -d
print_success "Bot started successfully!"

# Final status check
sleep 3
print_header "Installation Complete!"

echo -e "${GREEN}"
echo "Your SPL Shield bot is now running!"
echo -e "${NC}"

print_info "Useful commands:"
echo "  • View logs:       $DOCKER_COMPOSE logs -f bot"
echo "  • Stop bot:        $DOCKER_COMPOSE stop"
echo "  • Restart bot:     $DOCKER_COMPOSE restart"
echo "  • Update code:     git pull && $DOCKER_COMPOSE up -d --build"
echo "  • View status:     $DOCKER_COMPOSE ps"
echo ""

print_info "Next steps:"
echo "  1. Make sure you've configured BOT_TOKEN in .env"
echo "  2. Update the contract address when available"
echo "  3. Test the bot by messaging it on Telegram"
echo ""

print_warning "Check logs to ensure the bot started correctly:"
echo "  $DOCKER_COMPOSE logs -f bot"
echo ""

print_success "Installation completed successfully!"
