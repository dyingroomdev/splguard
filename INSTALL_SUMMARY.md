# 🎉 SPL Shield Bot - Ready for Deployment!

Your bot is now fully configured and ready for deployment with Docker Compose.

## 📦 What's Included

### Deployment Files Created:

1. **`install.sh`** (9.8 KB)
   - Comprehensive installation script
   - Checks dependencies
   - Creates and validates .env
   - Builds Docker images
   - Runs migrations
   - Populates initial data
   - Starts the bot
   - Usage: `./install.sh`

2. **`quick-start.sh`** (1.0 KB)
   - Minimal quick-start for experienced users
   - Fast deployment without prompts
   - Usage: `./quick-start.sh`

3. **`.env.example`** (1.1 KB)
   - Complete environment configuration template
   - Includes all required and optional settings
   - Well-documented with comments

4. **`DEPLOYMENT.md`** (5.9 KB)
   - Comprehensive deployment guide
   - Docker commands reference
   - Database management
   - Troubleshooting guide
   - Production best practices

5. **`.dockerignore`** (438 B)
   - Optimized Docker build context
   - Excludes unnecessary files

6. **`README.md`** (Updated)
   - Quick start instructions
   - Docker and local development guides

## 🚀 Deployment Options

### Option 1: Automated Installation (Recommended)

```bash
./install.sh
```

This is the easiest way! The script will guide you through everything.

### Option 2: Quick Start (Experienced Users)

```bash
cp .env.example .env
nano .env  # Add your BOT_TOKEN
./quick-start.sh
```

### Option 3: Manual Docker Deployment

```bash
# 1. Configure environment
cp .env.example .env
nano .env

# 2. Build and start
docker-compose up -d --build

# 3. Run migrations
docker-compose run --rm bot alembic upgrade head

# 4. View logs
docker-compose logs -f bot
```

### Option 4: Local Development (No Docker)

```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -e .

# 3. Configure
cp .env.example .env
nano .env

# 4. Run migrations
alembic upgrade head

# 5. Start bot
.venv/bin/splguard-bot
```

## ✅ Pre-configured Features

The bot comes with all features already configured:

### ✓ Commands Working
- `/help` - Links to support bot (@splsupportbot)
- `/team` - Shows 3 team members with full bios
- `/contract` - Displays $TDL contract information
- `/presale` - Shows presale details (Oct 26, 2025, 6 PM UTC)
- `/links` - All official links (website, docs, social media)
- `/commands` - Lists all available commands
- `/status` - Bot health and metrics
- `/ping` - Quick health check
- `/admin` - Admin panel (for configured admins)

### ✓ Database Pre-populated
- **Settings**: Project name, token ticker, contract addresses
- **Team Members**: Aragorn, Tom Harris, Ethan Miller (with bios)
- **Presale**: Status, platform, start time, FAQs
- **Official Links**: Website, docs, Twitter, Dapp, etc.

### ✓ Welcome Message
- Permanent welcome messages (no auto-delete)
- 8-button keyboard layout
- Links to presale, contract, support, risk scanner
- Markdown V2 formatting fixed

### ✓ Bug Fixes Applied
- ✅ Timezone comparison errors fixed
- ✅ Team bio field added and working
- ✅ Presale showing "$TDL Presale" correctly
- ✅ All markdown escaping issues resolved

## 🔧 Required Configuration

Before starting, you **MUST** configure:

1. **BOT_TOKEN** (required)
   - Get from [@BotFather](https://t.me/BotFather)
   - Edit `.env` and replace `your_bot_token_here`

2. **OWNER_ID** (required)
   - Get from [@userinfobot](https://t.me/userinfobot)
   - Your Telegram user ID

3. **Contract Address** (optional, can update later)
   - Current placeholder: `TDLTokenAddressWillBeProvidedSoon`
   - Update when contract is deployed

## 📊 Database Schema

The SQLite database includes:

```
settings
├── id (primary key)
├── project_name: "SPL Shield"
├── token_ticker: "TDL"
├── contract_addresses: ["TDLTokenAddressWillBeProvidedSoon"]
├── explorer_url
├── website: "https://splshield.com/"
├── docs: "https://docs.splshield.com/"
└── social_links: {...}

team_members
├── id
├── settings_id (foreign key)
├── name
├── role
├── contact
├── bio ← NEW FIELD
└── display_order

presales
├── id
├── settings_id (foreign key)
├── status: "UPCOMING"
├── platform: "SPL Shield Platform"
├── start_time: 2025-10-26 18:00:00 UTC
├── links: {"presale": "..."}
└── faqs: [...]
```

## 🐳 Docker Services

The `docker-compose.yml` includes:

1. **bot** - Main Telegram bot service
2. **web** - FastAPI health/admin web interface (port 8101)
3. **redis** - Caching and rate limiting (port 56379)

## 📝 Useful Commands

```bash
# View logs
docker-compose logs -f bot

# Restart bot
docker-compose restart bot

# Stop all services
docker-compose stop

# Start all services
docker-compose start

# Rebuild and restart
docker-compose up -d --build

# Access database
docker-compose exec bot sqlite3 /app/splguard.db

# Run migrations
docker-compose run --rm bot alembic upgrade head

# Backup database
cp splguard.db splguard.db.backup.$(date +%Y%m%d_%H%M%S)
```

## 🔐 Security Checklist

- [ ] BOT_TOKEN configured in .env
- [ ] .env file NOT committed to git
- [ ] OWNER_ID set to your Telegram user ID
- [ ] ADMIN_IDS configured
- [ ] Strong VPS password (if using cloud)
- [ ] Firewall configured (if production)
- [ ] Regular database backups scheduled

## 🎯 Next Steps

1. **Configure .env**
   ```bash
   nano .env
   # Add your BOT_TOKEN
   ```

2. **Run installation**
   ```bash
   ./install.sh
   ```

3. **Test the bot**
   - Message your bot on Telegram
   - Try `/help`, `/team`, `/contract`, `/presale`
   - Test welcome message by joining a group

4. **Update contract address** (when available)
   ```bash
   docker-compose exec bot sqlite3 /app/splguard.db "UPDATE settings SET contract_addresses = '[\"REAL_ADDRESS\"]' WHERE id = 1;"
   ```

5. **Monitor logs**
   ```bash
   docker-compose logs -f bot
   ```

## 📞 Support

- **Documentation**: See [DEPLOYMENT.md](DEPLOYMENT.md)
- **Support Bot**: [@splsupportbot](https://t.me/splsupportbot)
- **Community**: [@splshield](https://t.me/splshield)

## 🎊 You're All Set!

Your SPL Shield bot is ready to deploy. Just run:

```bash
./install.sh
```

And follow the prompts. Good luck! 🚀
