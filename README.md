# 📡 Bulk Media Bot — VPS Deploy Guide (Ubuntu)

## Setup

```bash
# 1. VPS mein SSH karo
ssh root@your_vps_ip

# 2. Setup script run karo
bash setup.sh
```

## .env file

```bash
nano ~/bulk_bot/.env
```

```env
BOT_TOKEN=1234567890:ABCdefGhIJKlmNoPQRsTUVwXyZ
OWNER_ID=123456789
```

- **BOT_TOKEN** → @BotFather se
- **OWNER_ID**  → @userinfobot se apna ID

## Files upload

```bash
scp bot.py database.py requirements.txt setup.sh root@YOUR_IP:~/bulk_bot/
```

## Bot start karo

```bash
cd ~/bulk_bot
screen -S bot
source venv/bin/activate
python3 bot.py
# Ctrl+A phir D → background mein chala jata hai
```

## Screen commands

| Command | Kaam |
|---------|------|
| `Ctrl+A` + `D` | Background mein bhejo |
| `screen -r bot` | Wapas aao |
| `screen -ls`    | Saari screens dekho |
| `Ctrl+C`        | Bot band karo |

---

## Sudo System

| Command | Kaam | Kaun use kar sakta hai |
|---------|------|------------------------|
| `/addsudo 123456789` | Kisi ko access do | Sirf Owner |
| `/rmsudo 123456789`  | Access hatao      | Sirf Owner |
| `/sudolist`          | List dekho        | Sirf Owner |

---

## Bot ka use

1. `/start` → main menu
2. **Select Target** → channel/group select ya add karo
3. **Add Media to Album** → photos/videos bhejo (max 10)
4. **Done** → repeat count set karo
5. **Publish** → confirm → sab ek album mein chala jayega!

---

## File structure

```
~/bulk_bot/
├── bot.py
├── database.py
├── requirements.txt
├── setup.sh
├── .env          ← apna token yahan
└── bot_data.db   ← auto banta hai
```
