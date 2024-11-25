# main.py

import logging
from telegram import Update, Bot
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext
from roles import (
    WRITER_IDS,
    MCQS_TEAM_IDS,
    CHECKER_TEAM_IDS,
    WORD_TEAM_IDS,
    DESIGN_TEAM_IDS,
    KING_TEAM_IDS,
)
import os

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Define roles and their corresponding IDs
ROLE_MAP = {
    'writer': WRITER_IDS,
    'mcqs_team': MCQS_TEAM_IDS,
    'checker_team': CHECKER_TEAM_IDS,
    'word_team': WORD_TEAM_IDS,
    'design_team': DESIGN_TEAM_IDS,
    'king_team': KING_TEAM_IDS,
}

def get_user_role(user_id):
    for role, ids in ROLE_MAP.items():
        if user_id in ids:
            return role
    return None

def forward_message(bot: Bot, message, target_ids):
    for user_id in target_ids:
        try:
            bot.forward_message(chat_id=user_id, from_chat_id=message.chat_id, message_id=message.message_id)
        except Exception as e:
            logger.error(f"Failed to forward message to {user_id}: {e}")

def handle_message(update: Update, context: CallbackContext):
    message = update.message
    user_id = message.from_user.id
    role = get_user_role(user_id)

    if not role:
        message.reply_text("You don't have a role assigned to use this bot.")
        return

    logger.info(f"Received message from {user_id} with role {role}")

    if role == 'writer':
        # Forward to MCQs team and Word team
        target_ids = MCQS_TEAM_IDS.union(WORD_TEAM_IDS)
        forward_message(context.bot, message, target_ids)

    elif role == 'word_team':
        # Forward to Design team
        target_ids = DESIGN_TEAM_IDS
        forward_message(context.bot, message, target_ids)

    elif role == 'design_team':
        # Forward to King team
        target_ids = KING_TEAM_IDS
        forward_message(context.bot, message, target_ids)

    else:
        # For other roles (mcqs_team, checker_team, king_team), no action defined
        message.reply_text("Your role does not have permissions to send messages through this bot.")

def main():
    # Get the BOT_TOKEN from environment variables
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set in environment variables.")
        return

    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Handle all text and document messages
    dp.add_handler(MessageHandler(Filters.text | Filters.document, handle_message))

    # Start the Bot
    updater.start_polling()
    logger.info("Bot started polling...")
    updater.idle()

if __name__ == '__main__':
    main()
