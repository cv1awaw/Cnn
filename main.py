import logging
import os
from telegram import Update, Message, InputMediaPhoto, InputMediaDocument
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

async def forward_text_message(bot, chat_id, sender_info, message_text):
    """Forward text messages with sender information."""
    forwarded_text = f"📤 **Forwarded Message**\n**From:** {sender_info}\n\n{message_text}"
    await bot.send_message(
        chat_id=chat_id,
        text=forwarded_text,
        parse_mode='Markdown'
    )

async def forward_media_message(bot, chat_id, message):
    """Forward media messages without altering them."""
    # Depending on the media type, use the appropriate forwarding method
    if message.photo:
        # For photos, forward the highest resolution
        await bot.send_photo(
            chat_id=chat_id,
            photo=message.photo[-1].file_id,
            caption=f"📤 **Forwarded Photo**\n**From:** {message.from_user.first_name} ({get_user_role(message.from_user.id)})"
        )
    elif message.document:
        await bot.send_document(
            chat_id=chat_id,
            document=message.document.file_id,
            caption=f"📤 **Forwarded Document**\n**From:** {message.from_user.first_name} ({get_user_role(message.from_user.id)})"
        )
    elif message.video:
        await bot.send_video(
            chat_id=chat_id,
            video=message.video.file_id,
            caption=f"📤 **Forwarded Video**\n**From:** {message.from_user.first_name} ({get_user_role(message.from_user.id)})"
        )
    elif message.audio:
        await bot.send_audio(
            chat_id=chat_id,
            audio=message.audio.file_id,
            caption=f"📤 **Forwarded Audio**\n**From:** {message.from_user.first_name} ({get_user_role(message.from_user.id)})"
        )
    elif message.sticker:
        await bot.send_sticker(
            chat_id=chat_id,
            sticker=message.sticker.file_id
        )
    else:
        # For other types, use forward_message as a fallback
        await bot.forward_message(
            chat_id=chat_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id
        )

async def handle_role_message(bot, chat_id, message: Message, role, user_info):
    """Handle messages prefixed with -role and send them to the sender's team and tara_team."""
    # Extract the actual message by removing the prefix
    message_text = message.text[len('-role'):].strip()
    if not message_text:
        await bot.send_message(chat_id=chat_id, text="Please provide a message after '-role'.")
        return

    # Get the list of target roles
    target_roles = SENDING_ROLE_TARGETS.get(role, []).copy()

    # Aggregate all target user IDs from the target roles
    aggregated_ids = []
    for target_role in target_roles:
        aggregated_ids.extend(ROLE_MAP.get(target_role, []))

    # Remove sender's ID if they are not in tara_team
    if role != 'tara_team' and chat_id in aggregated_ids:
        aggregated_ids.remove(chat_id)

    # Remove duplicates by converting to set
    aggregated_ids = list(set(aggregated_ids))

    # Prepare sender information
    sender_info = f"{user_info['first_name']} ({role})"

    if message.text:
        # Handle text messages
        for user_id in aggregated_ids:
            try:
                await forward_text_message(bot, user_id, sender_info, message_text)
                logger.info(f"Sent role-specific text message to {user_id}")
            except Exception as e:
                logger.error(f"Failed to send role-specific text message to {user_id}: {e}")
    else:
        # Handle media messages
        for user_id in aggregated_ids:
            try:
                await forward_media_message(bot, user_id, message)
                logger.info(f"Sent role-specific media message to {user_id}")
            except Exception as e:
                logger.error(f"Failed to send role-specific media message to {user_id}: {e}")

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
        await handle_role_message(context.bot, message.chat.id, message, role, user_info)
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

        if message.text:
            # Handle text messages
            for target_id in target_ids:
                try:
                    forwarded_text = f"📤 **Forwarded Message**\n**From:** {sender_info}\n\n{message_text}"
                    await context.bot.send_message(
                        chat_id=target_id,
                        text=forwarded_text,
                        parse_mode='Markdown'
                    )
                    logger.info(f"Sent text message to {target_id}")
                except Exception as e:
                    logger.error(f"Failed to send text message to {target_id}: {e}")
        else:
            # Handle media messages
            for target_id in target_ids:
                try:
                    await forward_media_message(context.bot, target_id, message)
                    logger.info(f"Sent media message to {target_id}")
                except Exception as e:
                    logger.error(f"Failed to send media message to {target_id}: {e}")

def main():
    """Main function to start the Telegram bot."""
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set in environment variables.")
        return

    # Build the application
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handle all text, photo, document, video, audio, and sticker messages
    message_handler = MessageHandler(
        filters.TEXT | filters.PHOTO | filters.DOCUMENT | filters.VIDEO | filters.AUDIO | filters.STICKER,
        handle_message
    )
    application.add_handler(message_handler)

    # Start the Bot
    logger.info("Bot started polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
