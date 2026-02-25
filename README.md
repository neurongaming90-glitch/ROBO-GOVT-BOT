# 🤖 GovtJobsBot — Indian Government Exam & Job Updates Bot

A fully automated Telegram bot that fetches, classifies, and posts Indian Government exam & job updates to groups and channels.

---

## 📁 Project Structure

```
tgbot/
├── bot.py           # Main bot + scheduler + handlers
├── config.py        # Configuration (reads env vars)
├── database.py      # SQLite database layer
├── rss_fetcher.py   # RSS feed fetching & deduplication
├── classifier.py    # Keyword-based update classifier
├── templates.py     # 4 premium message templates
├── requirements.txt
├── Procfile         # For Railway
├── railway.toml     # Railway config
└── .env.example     # Environment variable template
```

---

## 🚀 Deploy on Railway

### Step 1 — Upload to GitHub
1. Create a new GitHub repo (private)
2. Upload all files in this folder

### Step 2 — Deploy to Railway
1. Go to [railway.app](https://railway.app)
2. Click **New Project → Deploy from GitHub Repo**
3. Select your repo

### Step 3 — Set Environment Variables
In Railway dashboard → Variables, set:

| Variable | Value |
|---|---|
| `BOT_TOKEN` | `8155847480:AAHiRP1qzcK27SgIaY9kdSFN5QGMxct5sX0` |
| `ADMIN_ID` | `6593860853` |
| `CHANNEL_USERNAME` | `@Roboallbotchannel` |
| `FETCH_INTERVAL_MINUTES` | `15` |
| `DATABASE_PATH` | `govtjobs.db` |

### Step 4 — Deploy
Click **Deploy**. Railway installs dependencies and starts the bot automatically.

---

## ⚙️ How It Works

1. Bot starts and initializes SQLite database
2. Scheduler runs every 15 minutes
3. Fetches 14+ RSS feeds (NTA, UPSC, SSC, Railway, IBPS, SBI, etc.)
4. New items are classified: result / admit_card / last_date / exam_update / general
5. Appropriate premium template is applied
6. Posted to all registered groups & channels
7. Item ID saved to DB — no duplicates ever

---

## 🔧 Admin Commands

Send these to the bot from your Telegram account (`6593860853`):

| Command | Action |
|---|---|
| `/stats` | View active chats & post count |
| `/forcefetch` | Manually trigger RSS fetch |
| `/listchats` | List all active chats |
| `/removechat <id>` | Remove a chat |
| `/broadcast <msg>` | Send message to all chats |
| `/logs` | View last 30 log lines |

---

## 📢 Adding the Bot to Groups/Channels

1. Add bot to your group/channel
2. Make bot an **Admin** (so it can post)
3. Bot automatically registers and starts posting

---

## 📡 RSS Sources Monitored

- NTA (exams.nta.ac.in)
- UPSC
- SSC
- Indian Railways (RRB)
- IBPS
- Employment News (Rozgar Samachar)
- SarkariResult
- FreeJobAlert
- SarkariNaukri
- GovtJobGuru
- India Post
- Indian Army
- BPSC
- And more...

---

## 🔔 Private Chat Behavior

When a user messages the bot privately:
- Shows welcome message
- Asks them to join `@Roboallbotchannel`
- Verifies membership before unlocking

---

## 🛡️ Security

- Admin commands restricted to `ADMIN_ID` only
- Token stored in Railway environment variables (not in code)
- Auto-removes dead/kicked chat entries from DB
