# SPL Shield Bot - Deployment Guide

## 🚀 Quick Start (One Command Installation)

```bash
curl -fsSL https://raw.githubusercontent.com/yourusername/splguard/main/install.sh | bash
```

Or clone the repository and run:

```bash
git clone https://github.com/yourusername/splguard.git
cd splguard
./install.sh
```

The installation script will:
1. ✓ Check for Docker and Docker Compose
2. ✓ Create `.env` configuration file
3. ✓ Build Docker images
4. ✓ Initialize the database
5. ✓ Populate initial data (team, settings, presale)
6. ✓ Start the bot

## 📋 Prerequisites

- **Docker** (version 20.10+)
- **Docker Compose** (version 2.0+)
- **Telegram Bot Token** (get from [@BotFather](https://t.me/BotFather))

### Installing Docker

**Ubuntu/Debian:**
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

**macOS:**
```bash
brew install --cask docker
```

**Windows:**
Download from [Docker Desktop](https://www.docker.com/products/docker-desktop/)

## ⚙️ Configuration

### 1. Get Your Bot Token

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow instructions
3. Copy the bot token

### 2. Get Your User ID

1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. Copy your user ID

### 3. Configure .env

Edit the `.env` file:

```bash
nano .env
```

**Required settings:**
```bash
BOT_TOKEN=your_bot_token_here          # From @BotFather
OWNER_ID=123456789                      # Your Telegram user ID
```

**Optional settings:**
```bash
ADMIN_IDS="123456789,987654321"        # Comma-separated admin IDs
ADMIN_CHANNEL_ID=-1001234567890         # Admin log channel
REDIS_URL=redis://redis-stack:6379      # Redis host on pg-network
```

## 🐳 Docker Commands

### Start the bot
```bash
docker-compose up -d
```

### View logs
```bash
docker-compose logs -f bot
```

### Stop the bot
```bash
docker-compose stop
```

### Restart the bot
```bash
docker-compose restart
```

### Update and rebuild
```bash
git pull
docker-compose up -d --build
```

### View running containers
```bash
docker-compose ps
```

### Access bot shell
```bash
docker-compose exec bot bash
```

## 📊 Database Management

### Run migrations
```bash
docker-compose run --rm bot alembic upgrade head
```

### Create new migration
```bash
docker-compose run --rm bot alembic revision -m "description"
```

### Backup database
```bash
cp splguard.db splguard.db.backup.$(date +%Y%m%d_%H%M%S)
```

### Restore database
```bash
docker-compose stop
cp splguard.db.backup.YYYYMMDD_HHMMSS splguard.db
docker-compose start
```

## 🔧 Updating Bot Data

### Update Contract Address

Edit the database directly or use this script:

```bash
docker-compose exec bot sqlite3 /app/splguard.db "UPDATE settings SET contract_addresses = '[\"YOUR_CONTRACT_ADDRESS\"]', explorer_url = 'https://solscan.io/token/YOUR_CONTRACT_ADDRESS' WHERE id = 1;"
```

### Update Team Members

Use the admin panel in Telegram (send `/admin` to your bot)

### Update Presale Information

Use the admin panel or edit the database:

```bash
docker-compose exec bot sqlite3 /app/splguard.db
```

## 🐛 Troubleshooting

### Bot not starting

1. Check logs:
   ```bash
   docker-compose logs bot
   ```

2. Verify BOT_TOKEN is correct:
   ```bash
   grep BOT_TOKEN .env
   ```

3. Test token manually:
   ```bash
   curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe
   ```

### Database errors

1. Check database file exists:
   ```bash
   ls -lh splguard.db
   ```

2. Run migrations:
   ```bash
   docker-compose run --rm bot alembic upgrade head
   ```

3. Reset database (WARNING: deletes all data):
   ```bash
   docker-compose stop
   rm splguard.db
   ./install.sh
   ```

### Permission errors

```bash
sudo chown -R $USER:$USER .
chmod 644 splguard.db
```

### Docker issues

```bash
# Clean up Docker
docker-compose down
docker system prune -a

# Rebuild from scratch
docker-compose build --no-cache
docker-compose up -d
```

## 📈 Production Deployment

### Recommended Setup

1. **Use a VPS** (DigitalOcean, AWS, Linode, etc.)
2. **Enable Redis** for better performance
3. **Set up monitoring** (Sentry, logs)
4. **Regular backups** (daily database backups)
5. **Use reverse proxy** for web interface (Nginx/Caddy)

### Environment-specific .env

**Production:**
```bash
DATABASE_URL=sqlite+aiosqlite:////app/splguard.db
REDIS_URL=redis://redis-stack:6379
SENTRY_DSN=your_sentry_dsn_here
```

**Development:**
```bash
DATABASE_URL=sqlite+aiosqlite:///./splguard.db
REDIS_URL=
SENTRY_DSN=
```

### Systemd Service (Alternative to Docker)

Create `/etc/systemd/system/splguard-bot.service`:

```ini
[Unit]
Description=SPL Shield Telegram Bot
After=network.target

[Service]
Type=simple
User=splguard
WorkingDirectory=/opt/splguard
Environment=PATH=/opt/splguard/.venv/bin:/usr/bin
ExecStart=/opt/splguard/.venv/bin/splguard-bot
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable splguard-bot
sudo systemctl start splguard-bot
sudo systemctl status splguard-bot
```

## 📝 Testing Commands

Test all bot commands:

```bash
# /help
# /team
# /contract
# /presale
# /links
# /commands
# /status
# /ping
```

Admin commands (only for configured admins):

```bash
# /admin
```

## 🔐 Security Best Practices

1. **Never commit .env to git**
   ```bash
   echo ".env" >> .gitignore
   ```

2. **Rotate bot token periodically** (use @BotFather)

3. **Keep admin IDs private**

4. **Use strong passwords** for VPS access

5. **Enable firewall**:
   ```bash
   sudo ufw allow 22
   sudo ufw allow 8105  # If using web interface
   sudo ufw enable
   ```

6. **Regular updates**:
   ```bash
   git pull
   docker-compose up -d --build
   ```

## 🌐 Domain & OAuth Setup

- Production web access is served at **https://dc.splshield.com**. Create a DNS record pointing `dc.splshield.com` to your server’s public IP and ensure TLS termination (Caddy/NGINX/Traefik + Let’s Encrypt) is configured for that host.
- Discord OAuth must use `https://dc.splshield.com/broadcast/callback` as the Redirect URI. Add this exact URL in the Discord Developer Portal under *OAuth2 → Redirects*, and set `DISCORD_REDIRECT_URI` in `.env` to the same value.
- For local or staging environments, add additional redirect URLs to the portal and swap the `.env` value when testing (e.g., `http://localhost:8105/broadcast/callback`).

## 📞 Support

- **Documentation**: [docs.splshield.com](https://docs.splshield.com)
- **Support Bot**: [@splshieldhelpbot](https://t.me/splshieldhelpbot)
- **Community**: [@SPLShieldOfficial](https://t.me/SPLShieldOfficial)

## 📄 License

See [LICENSE](LICENSE) file for details.
