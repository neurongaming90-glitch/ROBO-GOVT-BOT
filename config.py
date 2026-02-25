import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8155847480:AAHiRP1qzcK27SgIaY9kdSFN5QGMxct5sX0")
ADMIN_ID = os.environ.get("ADMIN_ID", "6593860853")
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "@Roboallbotchannel")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "@YourBotUsername")   # Set this in Railway env vars!
OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "@YourOwnerUsername")  # Set this in Railway env vars!
FETCH_INTERVAL_MINUTES = int(os.environ.get("FETCH_INTERVAL_MINUTES", "15"))
DATABASE_PATH = os.environ.get("DATABASE_PATH", "govtjobs.db")
