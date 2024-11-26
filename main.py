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
    TARA_TEAM_IDS,
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
    'tara_team': TARA_TEAM_IDS,
}

# Define target roles for each role
SENDING_ROLE_TARGETS = {
    'writer': ['mcqs_team', 'checker_team', 'tara_team'],
    'mcqs_team': ['design_team', 'tara_team'],
    'checker_team': ['tara_team', 'word_team'],
    'word_team': ['tara_team', 'design_team'],
    'design_team': ['tara_team', 'king_team'],
    'king_team': ['tara_team'],
    'tara_team': list(ROLE_MAP.keys()),  # Tara can send to all roles
}

def get_user_role(user_id):
    """Determine the role of a user based on their user ID."""
    for role, ids in ROLE_MAP.items():
        if user_id in ids:
            return role
    return None

async def forward_message(bot, message, target_ids, sender_info=None):
    """Forward a message to a list of target user IDs with sender information."""
    for user_id in target_ids:
        try:
            if sender_info:
                # Customize the message with sender information
                forwarded_text = f"📤 **Forwarded Message**\n**From:** {sender_info}\n\n{message.text}"
                await bot.send_message(
                    chat_id=user_id,
                    text=forwarded_text,
                    parse_mode='Markdown'
                )
            else:
                # If no sender info is provided, just forward the message
                await bot.forward_message(
                    chat_id=user_id,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id
                )
            logger.info(f"Forwarded message {message.message_id} to {user_id}")
        except Exception as e:
            logger.error(f"Failed to forward message to {user_id}: {e}")

async def handle_role_message(bot, chat_id, message_text, role, user_info):
    """Handle messages prefixed with -role and send them to the sender's team and tara_team."""
    # Extract the actual message by removing the prefix
    actual_message = message_text[len('-role'):].strip()
    if not actual_message:
        await bot.send_message(chat_id=chat_id, text="Please provide a message after '-role'.")
        return

    # Get the list of user IDs for the sender's role
    target_ids = SENDING_ROLE_TARGETS.get(role, []).copy()

    # Aggregate all target user IDs from the target roles
    aggregated_ids = []
    for target_role in target_ids:
        aggregated_ids.extend(ROLE_MAP.get(target_role, []))

    # Remove sender's ID if they are not in tara_team
    if role != 'tara_team' and chat_id in aggregated_ids:
        aggregated_ids.remove(chat_id)

    # Remove duplicates by converting to set
    aggregated_ids = list(set(aggregated_ids))

    # Send the message to each target user with sender info
    sender_info = f"{user_info['first_name']} ({role})"
    for user_id in aggregated_ids:
        try:
            forwarded_text = f"📤 **Forwarded Message**\n**From:** {sender_info}\n\n{actual_message}"
            await bot.send_message(
                chat_id=user_id,
                text=forwarded_text,
                parse_mode='Markdown'
            )
            logger.info(f"Sent role-specific message to {user_id}")
        except Exception as e:
            logger.error(f"Failed to send role-specific message to {user_id}: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages and forward them based on user roles."""
    message = update.message
    if not message:
        return  # Ignore non-message updates

    user_id = message.from_user.id
    role = get_user_role(user_id)

    if not role:
        await message.reply_text("You don't have a role assigned to use this bot.")
        logger.warning(f"Unauthorized access attempt by user {user_id}")
        return

    logger.info(f"Received message from user {user_id} with role '{role}'")

    message_text = message.text or ""

    # Get user info for sender details
    user_info = {
        'first_name': message.from_user.first_name,
        'username': message.from_user.username,
    }

    if message_text.startswith('-role'):
        # Handle role-specific message
        logger.info(f"Handling role-specific message from '{role}'")
        await handle_role_message(context.bot, message.chat.id, message_text, role, user_info)
    else:
        # Determine target roles based on sender's role
        target_roles = SENDING_ROLE_TARGETS.get(role, [])

        # Aggregate target user IDs from target roles
        target_ids = []
        for target_role in target_roles:
            target_ids.extend(ROLE_MAP.get(target_role, []))

        # Remove sender's ID if they are not in tara_team
        if role != 'tara_team' and user_id in target_ids:
            target_ids.remove(user_id)

        # Remove duplicates by converting to set
        target_ids = list(set(target_ids))

        # Log the forwarding action
        logger.info(f"Forwarding message from '{role}' to roles: {target_roles}")

        # Prepare sender information
        sender_info = f"{user_info['first_name']} ({role})"

        # Send the message to each target user with sender info
        for target_id in target_ids:
            try:
                forwarded_text = f"📤 **Forwarded Message**\n**From:** {sender_info}\n\n{message_text}"
                await context.bot.send_message(
                    chat_id=target_id,
                    text=forwarded_text,
                    parse_mode='Markdown'
                )
                logger.info(f"Sent message to {target_id}")
            except Exception as e:
                logger.error(f"Failed to send message to {target_id}: {e}")

def main():
    """Main function to start the Telegram bot."""
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set in environment variables.")
        return

    # Build the application
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handle all text and document messages
    message_handler = MessageHandler(filters.TEXT | filters.Document.ALL, handle_message)
    application.add_handler(message_handler)

    # Start the Bot
    logger.info("Bot started polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
