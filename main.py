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
    'word_team': ['tara_team' , 'design_team'],  # Assuming word_team can only send to tara_team
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

async def forward_message(bot, message, target_ids):
    """Forward a message to a list of target user IDs."""
    for user_id in target_ids:
        try:
            await bot.forward_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
            logger.info(f"Forwarded message {message.message_id} to {user_id}")
        except Exception as e:
            logger.error(f"Failed to forward message to {user_id}: {e}")

async def handle_role_message(bot, chat_id, message_text, role):
    """Handle messages prefixed with -role and send them to the sender's team and tara_team."""
    # Extract the actual message by removing the prefix
    actual_message = message_text[len('-role'):].strip()
    if not actual_message:
        await bot.send_message(chat_id=chat_id, text="Please provide a message after '-role'.")
        return

    # Get the list of user IDs for the sender's role
    target_ids = ROLE_MAP.get(role, []).copy()  # Copy to avoid modifying the original list

    # Optionally, exclude the sender from receiving their own message
    # Uncomment the following line if needed:
    # target_ids = [uid for uid in target_ids if uid != chat_id]

    # Send the message to each target user in the sender's team
    for user_id in target_ids:
        try:
            await bot.send_message(chat_id=user_id, text=f"[{role}] {actual_message}")
            logger.info(f"Sent role-specific message to {user_id}")
        except Exception as e:
            logger.error(f"Failed to send role-specific message to {user_id}: {e}")

    # Now, send the message to tara_team with role information
    tara_ids = ROLE_MAP.get('tara_team', [])
    if tara_ids:
        tara_message = f"[{role}] {actual_message}"
        for tara_id in tara_ids:
            try:
                await bot.send_message(chat_id=tara_id, text=tara_message)
                logger.info(f"Sent message to tara_team member {tara_id}")
            except Exception as e:
                logger.error(f"Failed to send message to tara_team member {tara_id}: {e}")
    else:
        logger.warning("No members found in tara_team.")

async def forward_message_to_targets(bot, message, target_ids):
    """Forward the actual message to target user IDs."""
    try:
        for user_id in target_ids:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
            logger.info(f"Copied message {message.message_id} to {user_id}")
    except Exception as e:
        logger.error(f"Failed to copy message to {user_id}: {e}")

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

    if message_text.startswith('-role'):
        # Handle role-specific message
        logger.info(f"Handling role-specific message from '{role}'")
        await handle_role_message(context.bot, message.chat.id, message_text, role)
    else:
        # Determine target roles based on sender's role
        target_roles = SENDING_ROLE_TARGETS.get(role, [])

        # Aggregate target user IDs from target roles
        target_ids = set()
        for target_role in target_roles:
            target_ids.update(ROLE_MAP.get(target_role, []))

        # If the sender is not tara_team, exclude their own user ID from the targets
        if role != 'tara_team':
            target_ids.discard(user_id)

        # Log the forwarding action
        logger.info(f"Forwarding message from '{role}' to roles: {target_roles}")

        # Forward the message to the aggregated target user IDs
        await forward_message_to_targets(context.bot, message, target_ids)

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
