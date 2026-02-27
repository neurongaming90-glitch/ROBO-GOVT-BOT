import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8155847480:AAHiRP1qzcK27SgIaY9kdSFN5QGMxct5sX0")
ADMIN_ID = os.environ.get("ADMIN_ID", "6593860853")
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "@Roboallbotchannel")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "@GovtExamAlertBot")
OWNER_USERNAME = "@ethicalrobo"
FETCH_INTERVAL_MINUTES = int(os.environ.get("FETCH_INTERVAL_MINUTES", "30"))
DATABASE_PATH = os.environ.get("DATABASE_PATH", "govtjobs.db")

# AI Keys
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyAxy2TxMHhJ0heyIhu9k5bt453Cnb13y8I")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")
