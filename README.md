# 📢 Bulk Media Sender Bot — VPS Deploy Guide

## Ek baar setup (VPS pe)

```bash
# 1. VPS mein SSH karo
ssh root@your_vps_ip

# 2. Setup script run karo
bash setup.sh
```

## Manual setup (agar script nahi use karna)

```bash
# Python & screen install karo
sudo apt update && sudo apt install -y python3 python3-pip python3-venv screen

# Folder banao
mkdir ~/bulk_bot && cd ~/bulk_bot

# Virtual env banao
python3 -m venv venv
source venv/bin/activate
pip install python-telegram-bot==21.5 python-dotenv==1.0.0
```

## Files upload karo

Apne local machine se VPS pe files copy karo:

```bash
scp bot.py database.py requirements.txt root@your_vps_ip:~/bulk_bot/
```

Ya seedha VPS pe nano se banao.

## .env file banao

```bash
nano ~/bulk_bot/.env
```

Yeh likho:
```
BOT_TOKEN=1234567890:ABCdefGhIJKlmNoPQRsTUVwXyZ
ADMIN_IDS=123456789
```

Multiple admins ke liye:
```
ADMIN_IDS=123456789,987654321
```

**BOT_TOKEN** → @BotFather se mila token
**ADMIN_IDS** → @userinfobot se apna ID pata karo

## Bot start karo (screen ke saath)

```bash
cd ~/bulk_bot

# Screen session shuru karo
screen -S bot

# Virtual env activate karo
source venv/bin/activate

# Bot chalao
python3 bot.py
```

## Screen ke useful commands

| Command | Kaam |
|---------|------|
| `Ctrl+A` phir `D` | Screen se bahar niklo (bot chalta rehta hai) |
| `screen -r bot` | Wapas bot screen mein jao |
| `screen -ls` | Saari screens dekho |
| `Ctrl+C` | Bot band karo |

## Bot restart karna ho toh

```bash
screen -r bot
# Ctrl+C se band karo
python3 bot.py
# Ctrl+A phir D
```

## Bot ka use

1. Telegram pe apna bot open karo → `/start`
2. **Select Target** → channel/group add karo (bot wahan admin hona chahiye)
3. **Add to Queue** → media/text bhejo → repeat count set karo
4. Jitne items chahiye utne add karo
5. **Publish** → confirm → sab automatically chala jayega!

## Files ka structure

```
~/bulk_bot/
├── bot.py           # Main bot
├── database.py      # SQLite handler
├── requirements.txt # Dependencies
├── .env             # Secrets (BOT_TOKEN, ADMIN_IDS)
├── bot_data.db      # Auto-banta hai pehli baar run pe
└── venv/            # Virtual environment
```
