import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ['TOKEN']
ADMIN_ID = int(os.environ['ADMIN_ID'])

EXPORT_LOG = 'export_log.json'
IDS_FILE = 'ids_yme.txt'
ACTIVE_USERS_FILE = 'active_users.txt'
INACTIVE_USERS_FILE = 'inactive_users.txt'
DB_FILE = 'bot.db'
PROMO_FILE = 'promo.txt'
