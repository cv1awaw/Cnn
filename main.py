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

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------ Define Roles ------------------

# Define roles and their corresponding IDs
ROLE_MAP = {
    'writer': WRITER_IDS,
    'mcqs_team': MCQS_TEAM_IDS,
    'checker_team': CHECKER_TEAM_IDS,
    'word_team': WORD_TEAM_IDS,
    'design_team': DESIGN_TEAM_IDS,
    'king_team': KING_TEAM_IDS,
    'tara_team': TARA_TEAM_IDS,
    'mind_map_form_creator': MIND_MAP_FORM_CREATOR_IDS,  # Newly added
}

# Define display names for each role
ROLE_DISPLAY_NAMES = {
    'writer': 'Writer Team',
    'mcqs_team': 'MCQs Team',
    'checker_team': 'Editor Team',
    'word_team': 'Digital Writers',
    'design_team': 'Design Team',
    'king_team': 'Admin Team',
    'tara_team': 'Tara Team',
    'mind_map_form_creator': 'Mind Map & Form Creation Team',  # Newly added
}

# Define trigger to target roles mapping
TRIGGER_TARGET_MAP = {
    '-w': ['writer'],
    '-e': ['checker_team'],          # Editor Team
    '-mcq': ['mcqs_team'],
    '-d': ['word_team'],
    '-de': ['design_team'],
    '-mf': ['mind_map_form_creator'],
    '-c': ['checker_team'],          # Newly added trigger for Checker Team
}

# Define target roles for each role
# Adjusted to ensure that other roles can only send messages to 'tara_team' and their own role
SENDING_ROLE_TARGETS = {
    'writer': ['writer', 'tara_team'],
    'mcqs_team': ['mcqs_team', 'tara_team'],
    'checker_team': ['checker_team', 'tara_team'],
    'word_team': ['word_team', 'tara_team'],
    'design_team': ['design_team', 'tara_team'],
    'king_team': ['king_team', 'tara_team'],
    'tara_team': list(ROLE_MAP.keys()),  # Tara can send to all roles
    'mind_map_form_creator': ['mind_map_form_creator', 'tara_team'],
}

# ------------------ Define Conversation States ------------------

TEAM_MESSAGE = 1
SPECIFIC_TEAM_MESSAGE = 2
SPECIFIC_USER_MESSAGE = 3
TARA_MESSAGE = 4  # Newly added
CONFIRMATION = 5  # Newly added state for confirmation
SELECT_ROLE = 6    # Newly added state for role selection

# ------------------ User Data Storage ------------------

# User data storage: username (lowercase) -> user_id
USER_DATA_FILE = Path('user_data.json')

# Load existing user data if the file exists
if USER_DATA_FILE.exists():
    with open(USER_DATA_FILE, 'r') as f:
        try:
            user_data_store = json.load(f)
            # Convert keys to lowercase to maintain consistency
            user_data_store = {k.lower(): v for k, v in user_data_store.items()}
            logger.info("Loaded existing user data from user_data.json.")
        except json.JSONDecodeError:
            user_data_store = {}
            logger.error("user_data.json is not a valid JSON file. Starting with an empty data store.")
else:
    user_data_store = {}

def save_user_data():
    """Save the user_data_store to a JSON file."""
    try:
        with open(USER_DATA_FILE, 'w') as f:
            json.dump(user_data_store, f)
            logger.info("Saved user data to user_data.json.")
    except Exception as e:
        logger.error(f"Failed to save user data: {e}")

def get_user_roles(user_id):
    """Determine all roles of a user based on their user ID."""
    roles = []
    for role, ids in ROLE_MAP.items():
        if user_id in ids:
            roles.append(role)
    return roles

# ------------------ Mute Functionality ------------------

# Mute data storage: list of muted user IDs
MUTED_USERS_FILE = Path('muted_users.json')

# Load existing muted users if the file exists
if MUTED_USERS_FILE.exists():
    with open(MUTED_USERS_FILE, 'r') as f:
        try:
            muted_users = set(json.load(f))
            logger.info("Loaded existing muted users from muted_users.json.")
        except json.JSONDecodeError:
            muted_users = set()
            logger.error("muted_users.json is not a valid JSON file. Starting with an empty muted users set.")
else:
    muted_users = set()

def save_muted_users():
    """Save the muted_users set to a JSON file."""
    try:
        with open(MUTED_USERS_FILE, 'w') as f:
            json.dump(list(muted_users), f)
            logger.info("Saved muted users to muted_users.json.")
    except Exception as e:
        logger.error(f"Failed to save muted users: {e}")

# ------------------ Helper Functions ------------------

def get_display_name(user):
    """Return the display name for a user."""
    if user.username:
        return f"@{user.username}"
    else:
        full_name = f"{user.first_name} {user.last_name}" if user.last_name else user.first_name
        return full_name

def get_confirmation_keyboard(message_id):
    """Return an inline keyboard for confirmation with unique callback data."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f'confirm:{message_id}'),
            InlineKeyboardButton("❌ Cancel", callback_data=f'cancel:{message_id}'),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_role_selection_keyboard(roles):
    """Return an inline keyboard for role selection."""
    keyboard = []
    for role in roles:
        display_name = ROLE_DISPLAY_NAMES.get(role, role.capitalize())
        callback_data = f"role:{role}"
        keyboard.append([InlineKeyboardButton(display_name, callback_data=callback_data)])
    return InlineKeyboardMarkup(keyboard)

async def forward_message(bot, message, target_ids, sender_role):
    """Forward a document or text message to a list of target user IDs and notify about the sender's role."""
    # Get the display name for the sender's role
    sender_display_name = ROLE_DISPLAY_NAMES.get(sender_role, sender_role.capitalize())

    # Get the sender's display name using the helper function
    username_display = get_display_name(message.from_user)

    if message.document:
        # Construct the caption with @username and role name
        caption = f"🔄 *This document was sent by **{username_display} ({sender_display_name})**.*"
    elif message.text:
        # Construct the message with @username and role name
        caption = f"🔄 *This message was sent by **{username_display} ({sender_display_name})**.*"
    else:
        # Handle other message types if necessary
        caption = f"🔄 *This message was sent by **{username_display} ({sender_display_name})**.*"

    for user_id in target_ids:
        try:
            if message.document:
                # Forward the document with the updated caption
                await bot.send_document(
                    chat_id=user_id,
                    document=message.document.file_id,
                    caption=caption,
                    parse_mode='Markdown'
                )
                logger.info(f"Forwarded document {message.document.file_id} to {user_id}")
            elif message.text:
                # Forward the text message with the updated caption
                await bot.send_message(
                    chat_id=user_id,
                    text=f"{caption}\n\n{message.text}",
                    parse_mode='Markdown'
                )
                logger.info(f"Forwarded text message to {user_id}")
            else:
                # Forward other types of messages if needed
                await bot.forward_message(
                    chat_id=user_id,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id
                )
                logger.info(f"Forwarded message {message.message_id} to {user_id}")

        except Exception as e:
            logger.error(f"Failed to forward message or send role notification to {user_id}: {e}")

async def send_confirmation(message, context, sender_role, target_ids, target_roles=None):
    """Send a confirmation message with inline buttons for a specific document or text."""
    if message.document:
        content_description = f"PDF: `{message.document.file_name}`"
    elif message.text:
        content_description = f"Message: `{message.text}`"
    else:
        content_description = "Unsupported message type."

    if target_roles:
        target_roles_display = [ROLE_DISPLAY_NAMES.get(r, r.capitalize()) for r in target_roles]
    else:
        target_roles_display = [ROLE_DISPLAY_NAMES.get(r, r.capitalize()) for r in SENDING_ROLE_TARGETS.get(sender_role, [])]

    confirmation_text = (
        f"📩 *You are about to send the following to **{', '.join(target_roles_display)}**:*\n\n"
        f"{content_description}\n\n"
        "Do you want to send this?"
    )

    # Use the message ID to uniquely identify the confirmation
    callback_data_confirm = f"confirm:{message.message_id}"
    callback_data_cancel = f"cancel:{message.message_id}"

    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=callback_data_confirm),
            InlineKeyboardButton("❌ Cancel", callback_data=callback_data_cancel),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.reply_text(confirmation_text, parse_mode='Markdown', reply_markup=reply_markup)

    # Store necessary data in context.user_data with a unique key
    context.user_data[f'confirm_{message.message_id}'] = {
        'message': message,
        'target_ids': target_ids,
        'sender_role': sender_role,
        'target_roles': target_roles if target_roles else SENDING_ROLE_TARGETS.get(sender_role, [])
    }

# ------------------ Handler Functions ------------------

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the conversation."""
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

async def confirmation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the user's confirmation response."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith('confirm:'):
        message_id = int(data.split(':')[1])
        confirm_data = context.user_data.get(f'confirm_{message_id}')

        if not confirm_data:
            await query.edit_message_text("An error occurred. Please try again.")
            logger.error(f"No confirmation data found for message ID {message_id}.")
            return ConversationHandler.END

        message_to_send = confirm_data['message']
        target_ids = confirm_data['target_ids']
        sender_role = confirm_data['sender_role']
        target_roles = confirm_data.get('target_roles', [])

        # Forward the message
        await forward_message(context.bot, message_to_send, target_ids, sender_role)

        # Prepare display names for confirmation
        sender_display_name = ROLE_DISPLAY_NAMES.get(sender_role, sender_role.capitalize())

        if 'specific_user' in target_roles:
            recipient_display_names = [get_display_name(await context.bot.get_chat(tid)) for tid in target_ids]
        else:
            recipient_display_names = [ROLE_DISPLAY_NAMES.get(r, r.capitalize()) for r in target_roles if r != 'specific_user']

        if message_to_send.document:
            confirmation_text = (
                f"✅ *Your PDF `{message_to_send.document.file_name}` has been sent from **{sender_display_name}** "
                f"to **{', '.join(recipient_display_names)}**.*"
            )
        elif message_to_send.text:
            confirmation_text = (
                f"✅ *Your message has been sent from **{sender_display_name}** "
                f"to **{', '.join(recipient_display_names)}**.*"
            )
        else:
            confirmation_text = (
                f"✅ *Your message has been sent from **{sender_display_name}** "
                f"to **{', '.join(recipient_display_names)}**.*"
            )

        await query.edit_message_text(confirmation_text, parse_mode='Markdown')
        logger.info(f"User {query.from_user.id} confirmed and sent the message {message_to_send.message_id}.")

        # Clean up the stored data
        del context.user_data[f'confirm_{message_id}']

    elif data.startswith('cancel:'):
        message_id = int(data.split(':')[1])
        await query.edit_message_text("Operation cancelled.")
        logger.info(f"User {query.from_user.id} cancelled the message sending for message ID {message_id}.")

        # Clean up the stored data
        if f'confirm_{message_id}' in context.user_data:
            del context.user_data[f'confirm_{message_id}']

    else:
        await query.edit_message_text("Invalid choice.")
        logger.warning(f"User {query.from_user.id} sent invalid confirmation choice: {data}")

    return ConversationHandler.END

# ... (The rest of your code remains the same)

# ------------------ Main Function ------------------

def main():
    """Main function to start the Telegram bot."""
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set in environment variables.")
        return

    # Build the application
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(start_handler)
    application.add_handler(list_users_handler)
    application.add_handler(help_handler)
    application.add_handler(refresh_handler)
    application.add_handler(mute_handler)
    application.add_handler(mute_id_handler)
    application.add_handler(unmute_id_handler)
    application.add_handler(list_muted_handler)

    # Add ConversationHandlers
    application.add_handler(specific_user_conv_handler)
    application.add_handler(specific_team_conv_handler)
    application.add_handler(team_conv_handler)
    application.add_handler(tara_conv_handler)
    application.add_handler(general_conv_handler)  # Newly added

    # Add the error handler
    application.add_error_handler(error_handler)

    # Start the Bot using long polling
    logger.info("Bot started polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
