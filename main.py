# main.py

import logging
import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
)
from roles import (
    WRITER_IDS,
    MCQS_TEAM_IDS,
    CHECKER_TEAM_IDS,
    WORD_TEAM_IDS,
    DESIGN_TEAM_IDS,
    KING_TEAM_IDS,
)

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

async def forward_message(bot, message, target_ids):
    for user_id in target_ids:
        try:
            await bot.forward_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
        except Exception as e:
            logger.error(f"Failed to forward message to {user_id}: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_id = message.from_user.id
    role = get_user_role(user_id)

    if not role:
        await message.reply_text("You don't have a role assigned to use this bot.")
        return

    logger.info(f"Received message from {user_id} with role {role}")

    if role == 'writer':
        # Forward to MCQs team and Checker team
        target_ids = MCQS_TEAM_IDS.union(CHECKER_TEAM_IDS)
        await forward_message(context.bot, message, target_ids)

    elif role == 'mcqs_team':
        # Forward to Design team
        target_ids = DESIGN_TEAM_IDS
        await forward_message(context.bot, message, target_ids)

    elif role == 'checker_team':
        # Forward to Word team
        target_ids = WORD_TEAM_IDS
        await forward_message(context.bot, message, target_ids)

    elif role == 'word_team':
        # Forward to Design team
        target_ids = DESIGN_TEAM_IDS
        await forward_message(context.bot, message, target_ids)

    elif role == 'design_team':
        # Forward to King team
        target_ids = KING_TEAM_IDS
        await forward_message(context.bot, message, target_ids)

    else:
        # For other roles (king_team), no action defined
        await message.reply_text("Your role does not have permissions to send messages through this bot.")

def main():
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set in environment variables.")
        return

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handle all text and document messages
    message_handler = MessageHandler(filters.TEXT | filters.Document.ALL, handle_message)
    application.add_handler(message_handler)

    # Start the Bot
    application.run_polling()
    logger.info("Bot started polling...")

if __name__ == '__main__':
    main()
