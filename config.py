import os
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# ALAPVETŐ BEÁLLÍTÁSOK ÉS DISCORD ID-K
# ==========================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

# Role ID-k
STAFF_ROLE_ID = int(os.getenv("STAFF_ROLE_ID", "0"))
REGULATOR_ROLE_ID = int(os.getenv("REGULATOR_ROLE_ID", "1483822408182796418"))
TESTER_ROLE_ID = int(os.getenv("TESTER_ROLE_ID", "1469755118634270864"))
BANNED_ROLE_ID = int(os.getenv("BANNED_ROLE_ID", "1469740655520780631"))
EXTRA_STAFF_ROLE_IDS = [int(x.strip()) for x in os.getenv("EXTRA_STAFF_ROLE_IDS", "").split(",") if x.strip()]
ALLOWED_USER_IDS = [int(x.strip()) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip()]

DEBUG_ALLOWED_USERS = []
DEBUG_ALLOWED_ROLES = [REGULATOR_ROLE_ID]

# Channel & Category ID-k
WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID", "1496272517759897751"))
HIGH_TEST_CHANNEL_ID = int(os.getenv("HIGH_TEST_CHANNEL_ID", "1490230276632924161"))
TIER_RESULTS_CHANNEL_ID = int(os.getenv("TIER_RESULTS_CHANNEL_ID", "1490230276632924161"))
BAN_CHANNEL_ID = int(os.getenv("BAN_CHANNEL_ID", "1469803060976160822"))
TGF_LOG_CHANNEL_ID = int(os.getenv("TGF_LOG_CHANNEL_ID", "1505522005028503582"))

TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "0"))
ELO_TICKET_CATEGORY_ID = int(os.getenv("ELO_TICKET_CATEGORY_ID", "0"))
LEGACY_TICKET_CATEGORY_ID = int(os.getenv("LEGACY_TICKET_CATEGORY_ID", "0"))
HELP_TICKET_CATEGORY_ID = int(os.getenv("HELP_TICKET_CATEGORY_ID", "0"))

TGF_COOLDOWN_DAYS = 30

# ==========================================
# ADATBÁZIS ÉS WEBOLDAL BEÁLLÍTÁSOK
# ==========================================
WEBSITE_URL = os.getenv("WEBSITE_URL", "https://neontiers.hu").rstrip('/')
BOT_API_KEY = os.getenv("BOT_API_KEY", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip('/')
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
USE_SUPABASE_API = os.getenv("USE_SUPABASE_API", "true").lower() == "true"
DATABASE_URL = os.getenv("DATABASE_URL", "")
SUPABASE_PG_URL = os.getenv("SUPABASE_PG_URL", "")

DATA_FILE = "data.json"
HTTP_TIMEOUT_SECONDS = 15
LINK_CODE_LENGTH = 8
LINK_CODE_EXPIRY_MINUTES = 10

# ==========================================
# JÁTÉKMÓDOK ÉS ELO BEÁLLÍTÁSOK
# ==========================================
MODE_LIST = [
    "vanilla", "uhc", "pot", "nethpot", "smp", "sword",
    "axe", "mace", "cart", "creeper", "diasmp", "spearelytra"
]

RANKS = ["HT1", "LT1", "HT2", "LT2", "HT3", "LT3", "HT4", "LT4", "HT5", "LT5", "Unranked"]

POINTS = {
    "HT1": 50, "LT1": 45, "HT2": 40, "LT2": 35, "HT3": 30,
    "LT3": 25, "HT4": 20, "LT4": 15, "HT5": 10, "LT5": 5, "Unranked": 0
}

ELO_MIN = 0
ELO_MATCH_SCORE_PREFIX = "MATCH_"

TICKET_TYPES = [
    ("Vanilla", "vanilla", 1489190924771381289),
    ("UHC", "uhc", 1489190956975296562),
    ("Pot", "pot", 1489190987178442833),
    ("Nethpot", "nethpot", 1489190938360918076),
    ("SMP", "smp", 1489191000868655265),
    ("Sword", "sword", 1489190892018040852),
    ("Axe", "axe", 1489190906236735518),
    ("Mace", "mace", 1489190875601535038),
    ("Cart", "cart", 1489191029272399993),
    ("Creeper", "creeper", 1489191016626655242),
    ("DiaSMP", "diasmp", 1489191039837933610),
    ("Spear Elytra", "spearelytra", 1489190973400416359),
]

LEGACY_TICKET_TYPES = [
    ("Stick Fight", "stickfight", 1502574877536948334),
    ("Trident", "trident", 1505194733629210664),
    ("Boxing", "boxing", 1520465463358783639),
    ("Combo", "combo", 1520465407474008147),
    ("Bridge", "bridge", 1520465430957916331),
    ("NoDebuff", "nodebuff", 1520465050974814319),
    ("OP", "op", 1520465323680075937),
    ("Soup", "soup", 1520465218096857280),
    ("Fireball Fight", "fireballfight", 1520465183884181636),
]

ALL_TICKET_TYPES = TICKET_TYPES + LEGACY_TICKET_TYPES

GAMEMODE_DISPLAY_NAMES = {
    "vanilla": "Vanilla", "uhc": "UHC", "pot": "Pot", "nethpot": "Nethpot",
    "smp": "SMP", "sword": "Sword", "axe": "Axe", "mace": "Mace",
    "cart": "Cart", "creeper": "Creeper", "diasmp": "DiaSMP",
    "spearelytra": "Spear Elytra", "stickfight": "Stick Fight",
    "trident": "Trident", "boxing": "Boxing", "combo": "Combo",
    "bridge": "Bridge", "nodebuff": "NoDebuff", "op": "OP",
    "soup": "Soup", "fireballfight": "Fireball Fight"
}

def normalize_gamemode(mode: str) -> str:
    if not mode:
        return ""
    m = mode.strip().lower().replace(" ", "").replace("_", "").replace("-", "")
    mapping = {
        "vanilla": "vanilla", "uhc": "uhc", "pot": "pot", "nethpot": "nethpot",
        "smp": "smp", "sword": "sword", "axe": "axe", "mace": "mace",
        "cart": "cart", "creeper": "creeper", "diasmp": "diasmp",
        "spearelytra": "spearelytra", "stickfight": "stickfight",
        "trident": "trident", "boxing": "boxing", "combo": "combo",
        "bridge": "bridge", "nodebuff": "nodebuff", "op": "op",
        "soup": "soup", "fireballfight": "fireballfight"
    }
    return mapping.get(m, m)

def get_gamemode_display_name(mode: str) -> str:
    norm = normalize_gamemode(mode)
    return GAMEMODE_DISPLAY_NAMES.get(norm, mode.capitalize())
