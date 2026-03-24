#!/bin/bash
# Bulk Media Sender Bot - VPS Setup Script
# Ubuntu 20.04 / 22.04

set -e

echo "======================================"
echo "  Bulk Media Bot - VPS Setup"
echo "======================================"

# 1. Update system
echo "[1/5] Updating system..."
sudo apt update -y && sudo apt upgrade -y

# 2. Install Python & pip
echo "[2/5] Installing Python 3.11..."
sudo apt install -y python3 python3-pip python3-venv screen git

# 3. Create project folder
echo "[3/5] Setting up project folder..."
mkdir -p ~/bulk_bot
cd ~/bulk_bot

# 4. Virtual environment
echo "[4/5] Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install python-telegram-bot==21.5

# 5. Create .env file
echo "[5/5] Creating .env file..."
if [ ! -f .env ]; then
    echo "BOT_TOKEN=your_bot_token_here" > .env
    echo "ADMIN_IDS=your_telegram_id_here" >> .env
    echo ""
    echo "⚠️  .env file bana diya! Ab isko edit karo:"
    echo "    nano ~/bulk_bot/.env"
else
    echo ".env file already exists, skipping."
fi

echo ""
echo "======================================"
echo "  Setup Complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo "  1. .env file mein apna BOT_TOKEN aur ADMIN_IDS daalo:"
echo "     nano ~/bulk_bot/.env"
echo ""
echo "  2. bot.py aur database.py copy karo ~/bulk_bot/ mein"
echo ""
echo "  3. Bot start karo:"
echo "     cd ~/bulk_bot && screen -S bot"
echo "     source venv/bin/activate"
echo "     python3 bot.py"
echo ""
echo "  4. Screen se bahar nikalne ke liye: Ctrl+A, phir D"
echo "  5. Wapas aane ke liye: screen -r bot"
