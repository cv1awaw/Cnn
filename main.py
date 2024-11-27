# main.py

import logging
import os
import re
import json
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler,
    CommandHandler,
    CallbackQueryHandler,
)
from roles import (
    WRITER_IDS,
    MCQS_TEAM_IDS,
    CHECKER_TEAM_IDS,
    WORD_TEAM_IDS,
    DESIGN_TEAM_IDS,
    KING_TEAM_IDS,
    TARA_TEAM_IDS,
    MIND_MAP_FORM_CREATOR_IDS,  # Newly added
)

# ------------------ Setup Logging ------------------

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------ Define Roles ------------------

ROLE_MAP = {
    'writer': WRITER_IDS,
    'mcqs_team': MCQS_TEAM_IDS,
    'checker_team': CHECKER_TEAM_IDS,
    'word_team': WORD_TEAM_IDS,
    'design_team': DESIGN_TEAM_IDS,
    'king_team': KING_TEAM_IDS,
    'tara_team': TARA_TEAM_IDS,
    'mind_map_form_creator': MIND_MAP_FORM_CREATOR_IDS,
}

ROLE_DISPLAY_NAMES = {
    'writer': 'Writer Team',
    'mcqs_team': 'MCQs Team',
    'checker_team': 'Editor Team',
    'word_team': 'Digital Writers',
    'design_team': 'Design Team',
    'king_team': 'Admin Team',
    'tara_team': 'Tara Team',
    'mind_map_form_creator': 'Mind Map & Form Creation Team',
}

TRIGGER_TARGET_MAP = {
    '-w': ['writer'],
    '-e': ['checker_team'],
    '-mcq': ['mcqs_team'],
    '-d': ['word_team'],
    '-de': ['design_team'],
    '-mf': ['mind_map_form_creator'],
    '-t': ['tara_team'],
}

SENDING_ROLE_TARGETS = {
    'writer': ['tara_team'],
    'mcqs_team': ['tara_team'],
    'checker_team': ['tara_team'],
    'word_team': ['tara_team'],
    'design_team': ['tara_team'],
    'king_team': ['tara_team'],
    'tara_team': list(ROLE_MAP.keys()),
    'mind_map_form_creator': ['tara_team'],
}

TEAM_MESSAGE = 1
SPECIFIC_TEAM_MESSAGE = 2
SPECIFIC_USER_MESSAGE = 3
TARA_MESSAGE = 4
CONFIRMATION = 5

USER_DATA_FILE = Path('user_data.json')
if USER_DATA_FILE.exists():
    with open(USER_DATA_FILE, 'r') as f:
        try:
            user_data_store = json.load(f)
            user_data_store = {k.lower(): v for k, v in user_data_store.items()}
            logger.info("Loaded existing user data from user_data.json.")
        except json.JSONDecodeError:
            user_data_store = {}
            logger.error("user_data.json is not a valid JSON file.")
else:
    user_data_store = {}

def save_user_data():
    try:
        with open(USER_DATA_FILE, 'w') as f:
            json.dump(user_data_store, f)
            logger.info("Saved user data to user_data.json.")
    except Exception as e:
        logger.error(f"Failed to save user data: {e}")

def get_user_role(user_id):
    for role, ids in ROLE_MAP.items():
        if user_id in ids:
            return role
    return None

MUTED_USERS_FILE = Path('muted_users.json')
if MUTED_USERS_FILE.exists():
    with open(MUTED_USERS_FILE, 'r') as f:
        try:
            muted_users = set(json.load(f))
            logger.info("Loaded existing muted users from muted_users.json.")
        except json.JSONDecodeError:
            muted_users = set()
else:
    muted_users = set()

def save_muted_users():
    try:
        with open(MUTED_USERS_FILE, 'w') as f:
            json.dump(list(muted_users), f)
            logger.info("Saved muted users to muted_users.json.")
    except Exception as e:
        logger.error(f"Failed to save muted users: {e}")

# ------------------ /help Command ------------------

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provide help information to users."""
    help_text = (
        "📘 *Available Commands:*\n\n"
        "/start - Initialize interaction with the bot.\n"
        "/listusers - List all registered users (Tara Team only).\n"
        "/help - Show this help message.\n"
        "/refresh - Refresh your user information.\n\n"
        "*Specific Commands for Tara Team:*\n"
        "/mute - Mute yourself or another user.\n"
        "/muteid <user_id> - Mute a specific user by their ID.\n"
        "/unmuteid <user_id> - Unmute a specific user by their ID.\n"
        "/listmuted - List all currently muted users.\n\n"
        "*Message Triggers:*\n"
        "-w - Send a message to the Writer Team.\n"
        "-e - Send a message to the Editor Team.\n"
        "-mcq - Send a message to the MCQs Team.\n"
        "-d - Send a message to the Digital Writers Team.\n"
        "-de - Send a message to the Design Team.\n"
        "-mf - Send a message to the Mind Map & Form Creation Team.\n"
        "-t - Send a message to the Tara Team.\n"
        "-team - Send a general message to your assigned team(s).\n\n"
        "*Who Can Use These Triggers:*\n"
        "Each role can send messages only to the Tara Team, except Tara Team members, who can send messages to all teams and individual users.\n\n"
        "*Message Workflow:*\n"
        "1. Use a trigger (e.g., `-w` for Writer Team) or direct command (`/start`).\n"
        "2. Type your message.\n"
        "3. Confirm or cancel the message before sending.\n\n"
        "For detailed information or troubleshooting, contact the Admin Team."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')
    logger.info(f"User {update.effective_user.id} requested help.")

# ------------------ Main Function ------------------

def main():
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set in environment variables.")
        return

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    help_handler = CommandHandler('help', help_command)
    application.add_handler(help_handler)

    logger.info("Bot started polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
