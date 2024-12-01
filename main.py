# main.py

import logging
import os
import re
import json
import uuid
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
TARA_MESSAGE = 4
CONFIRMATION = 5
SELECT_ROLE = 6

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

def get_confirmation_keyboard(uuid_str):
    """Return an inline keyboard for confirmation with unique callback data."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f'confirm:{uuid_str}'),
            InlineKeyboardButton("❌ Cancel", callback_data=f'cancel:{uuid_str}'),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_role_selection_keyboard(roles):
    """Return an inline keyboard for role selection with a Cancel option."""
    keyboard = []
    for role in roles:
        display_name = ROLE_DISPLAY_NAMES.get(role, role.capitalize())
        callback_data = f"role:{role}"
        keyboard.append([InlineKeyboardButton(display_name, callback_data=callback_data)])
    # Add a Cancel button
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data='cancel_role_selection')])
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

    # Generate a unique UUID for this confirmation
    confirmation_uuid = str(uuid.uuid4())

    # Create confirmation keyboard with UUID in callback_data
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f'confirm:{confirmation_uuid}'),
            InlineKeyboardButton("❌ Cancel", callback_data=f'cancel:{confirmation_uuid}'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send the confirmation message
    confirmation_message = await message.reply_text(confirmation_text, parse_mode='Markdown', reply_markup=reply_markup)

    # Store confirmation data using UUID
    context.user_data[f'confirm_{confirmation_uuid}'] = {
        'message': message,
        'target_ids': target_ids,
        'sender_role': sender_role,
        'target_roles': target_roles if target_roles else SENDING_ROLE_TARGETS.get(sender_role, [])
    }

# ------------------ Handler Functions ------------------

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the conversation."""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Operation cancelled.")
    else:
        await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

async def confirmation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the user's confirmation response."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith('confirm:') or data.startswith('cancel:'):
        try:
            action, confirmation_uuid = data.split(':', 1)
        except ValueError:
            await query.edit_message_text("Invalid confirmation data. Please try again.")
            logger.error("Failed to parse confirmation data.")
            return ConversationHandler.END

        confirm_data = context.user_data.get(f'confirm_{confirmation_uuid}')

        if not confirm_data:
            await query.edit_message_text("An error occurred. Please try again.")
            logger.error(f"No confirmation data found for UUID {confirmation_uuid}.")
            return ConversationHandler.END

        if action == 'confirm':
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
            del context.user_data[f'confirm_{confirmation_uuid}']

        elif action == 'cancel':
            await query.edit_message_text("Operation cancelled.")
            logger.info(f"User {query.from_user.id} cancelled the message sending for UUID {confirmation_uuid}.")

            # Clean up the stored data
            if f'confirm_{confirmation_uuid}' in context.user_data:
                del context.user_data[f'confirm_{confirmation_uuid}']

    else:
        await query.edit_message_text("Invalid choice.")
        logger.warning(f"User {query.from_user.id} sent invalid confirmation choice: {data}")

    return ConversationHandler.END

async def specific_user_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trigger function when a Tara team member sends a specific user command."""
    user_id = update.message.from_user.id
    roles = get_user_roles(user_id)

    if 'tara_team' not in roles:
        await update.message.reply_text("You are not authorized to use this command.")
        logger.warning(f"Unauthorized access attempt by user {user_id} for specific user triggers.")
        return ConversationHandler.END

    # Extract username from the command using regex
    match = re.match(r'^\s*-\@([A-Za-z0-9_]{5,32})\s*$', update.message.text, re.IGNORECASE)
    if not match:
        await update.message.reply_text("Invalid format. Please use `-@username` to target a user.", parse_mode='Markdown')
        logger.warning(f"Invalid user command format from user {user_id}.")
        return ConversationHandler.END

    target_username = match.group(1).lower()
    target_user_id = user_data_store.get(target_username)

    if not target_user_id:
        await update.message.reply_text(f"User `@{target_username}` not found.", parse_mode='Markdown')
        logger.warning(f"Tara Team member {user_id} attempted to target non-existent user @{target_username}.")
        return ConversationHandler.END

    # Store target user ID and other necessary data in user_data
    context.user_data['target_user_id'] = target_user_id
    context.user_data['target_username'] = target_username
    context.user_data['sender_role'] = 'tara_team'  # Tara Team is sending the message

    await update.message.reply_text(f"Write your message for user `@{target_username}`.", parse_mode='Markdown')
    return SPECIFIC_USER_MESSAGE

async def specific_user_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the message intended for a specific user and ask for confirmation."""
    message = update.message
    user_id = message.from_user.id

    target_user_id = context.user_data.get('target_user_id')
    target_username = context.user_data.get('target_username')

    if not target_user_id:
        await message.reply_text("An error occurred. Please try again.")
        logger.error(f"No target user ID found in user_data for user {user_id}.")
        return ConversationHandler.END

    # Ensure only the specific user is targeted
    context.user_data['target_ids'] = [target_user_id]
    context.user_data['target_roles'] = ['specific_user']
    sender_role = context.user_data.get('sender_role', 'Tara Team')

    # Retrieve the target user's display name
    try:
        target_user = await context.bot.get_chat(target_user_id)
        target_display_name = get_display_name(target_user)
    except Exception as e:
        await message.reply_text(f"Failed to retrieve user information: {e}")
        logger.error(f"Failed to get chat for user ID {target_user_id}: {e}")
        return ConversationHandler.END

    # Store the message and targets for confirmation
    context.user_data['message_to_send'] = message

    if message.document:
        content_description = f"PDF: `{message.document.file_name}`"
    elif message.text:
        content_description = f"Message: `{message.text}`"
    else:
        content_description = "Unsupported message type."

    # Send confirmation using UUID
    await send_confirmation(message, context, sender_role, [target_user_id], target_roles=['specific_user'])

    return CONFIRMATION

async def specific_team_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trigger function when a Tara team member sends a specific team command."""
    user_id = update.message.from_user.id
    roles = get_user_roles(user_id)

    if 'tara_team' not in roles:
        await update.message.reply_text("You are not authorized to use this command.")
        logger.warning(f"Unauthorized access attempt by user {user_id} for specific team triggers.")
        return ConversationHandler.END

    message_text = update.message.text.strip()
    message = message_text.lower()
    target_roles = TRIGGER_TARGET_MAP.get(message)

    if not target_roles:
        await update.message.reply_text("Invalid trigger. Please try again.")
        logger.warning(f"Invalid trigger '{message}' from user {user_id}.")
        return ConversationHandler.END

    # Store target roles in user_data
    context.user_data['specific_target_roles'] = target_roles
    context.user_data['sender_role'] = 'tara_team'  # Tara Team is sending the message

    await update.message.reply_text("Write your message for your team.")
    return SPECIFIC_TEAM_MESSAGE

async def specific_team_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the team message after the specific trigger and ask for confirmation."""
    message = update.message
    user_id = message.from_user.id

    target_roles = context.user_data.get('specific_target_roles', [])
    target_ids = set()

    for target_role in target_roles:
        target_ids.update(ROLE_MAP.get(target_role, []))

    # Exclude the sender's user ID from all forwards
    target_ids.discard(user_id)

    if not target_ids:
        await message.reply_text("No recipients found to send your message.")
        logger.warning(f"No recipients found for user {user_id}.")
        return ConversationHandler.END

    # Store the message and targets for confirmation
    context.user_data['message_to_send'] = message
    context.user_data['target_ids'] = list(target_ids)
    context.user_data['target_roles'] = target_roles
    sender_role = context.user_data.get('sender_role', 'Tara Team')

    if message.document:
        content_description = f"PDF: `{message.document.file_name}`"
    elif message.text:
        content_description = f"Message: `{message.text}`"
    else:
        content_description = "Unsupported message type."

    # Send confirmation using UUID
    await send_confirmation(message, context, sender_role, list(target_ids), target_roles=target_roles)

    return CONFIRMATION

async def team_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the general team trigger."""
    user_id = update.message.from_user.id
    roles = get_user_roles(user_id)

    if not roles:
        await update.message.reply_text("You don't have a role assigned to use this bot.")
        logger.warning(f"Unauthorized access attempt by user {user_id} for general team trigger.")
        return ConversationHandler.END

    # Determine which roles the sender can send messages to
    # If user has multiple roles, they need to choose which role to use
    if len(roles) > 1:
        # Present role selection keyboard
        keyboard = get_role_selection_keyboard(roles)
        await update.message.reply_text(
            "You have multiple roles. Please choose which role you want to use to send this message:",
            reply_markup=keyboard
        )
        # Store pending message
        context.user_data['pending_message'] = update.message
        return SELECT_ROLE
    else:
        # Single role, proceed to message writing
        selected_role = roles[0]
        context.user_data['sender_role'] = selected_role

        await update.message.reply_text("Write your message for your team and Tara Team.")
        return TEAM_MESSAGE

async def team_message_handler(message, context, sender_role, target_ids, target_roles):
    """Handle the team message after the general trigger and ask for confirmation."""
    # Pass the message directly to send_confirmation
    await send_confirmation(message, context, sender_role, target_ids, target_roles)
    return CONFIRMATION

async def select_role_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the role selection from the user."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith('role:'):
        selected_role = data.split(':')[1]
        context.user_data['sender_role'] = selected_role

        # Retrieve the pending message
        pending_message = context.user_data.get('pending_message')
        if not pending_message:
            await query.edit_message_text("An error occurred. Please try again.")
            logger.error(f"No pending message found for user {query.from_user.id}.")
            return ConversationHandler.END

        # Remove the pending message from user_data
        del context.user_data['pending_message']

        # Determine target_ids and target_roles based on selected_role
        target_roles = SENDING_ROLE_TARGETS.get(selected_role, [])
        target_ids = set()
        for role in target_roles:
            target_ids.update(ROLE_MAP.get(role, []))
        target_ids.discard(query.from_user.id)

        if not target_ids:
            await query.edit_message_text("No recipients found to send your message.")
            logger.warning(f"No recipients found for user {user_id} with role '{selected_role}'.")
            return ConversationHandler.END

        # Send confirmation using UUID
        await send_confirmation(pending_message, context, selected_role, list(target_ids), target_roles=target_roles)

        await query.edit_message_text("Processing your message...")
        return CONFIRMATION

    elif data == 'cancel_role_selection':
        await query.edit_message_text("Operation cancelled.")
        logger.info(f"User {query.from_user.id} cancelled role selection.")
        return ConversationHandler.END
    else:
        await query.edit_message_text("Invalid role selection.")
        logger.warning(f"User {query.from_user.id} sent invalid role selection: {data}")
        return ConversationHandler.END

# ... [Remaining handler functions remain unchanged]

# ------------------ Conversation Handlers ------------------

# Define the ConversationHandler for specific user commands
specific_user_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(re.compile(r'^\s*-\@([A-Za-z0-9_]{5,32})\s*$', re.IGNORECASE)), specific_user_trigger)],
    states={
        SPECIFIC_USER_MESSAGE: [MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, specific_user_message_handler)],
        CONFIRMATION: [CallbackQueryHandler(confirmation_handler, pattern='^(confirm:|cancel:).*')],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

# Define the ConversationHandler for specific team commands
specific_team_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(re.compile(r'^-(w|e|mcq|d|de|mf|c)$', re.IGNORECASE)), specific_team_trigger)],
    states={
        SPECIFIC_TEAM_MESSAGE: [MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, specific_team_message_handler)],
        CONFIRMATION: [CallbackQueryHandler(confirmation_handler, pattern='^(confirm:|cancel:).*')],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

# Define the ConversationHandler for general team messages (-team)
team_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(re.compile(r'^-team$', re.IGNORECASE)), team_trigger)],
    states={
        SELECT_ROLE: [CallbackQueryHandler(select_role_handler, pattern='^role:.*$|^cancel_role_selection$')],
        CONFIRMATION: [CallbackQueryHandler(confirmation_handler, pattern='^(confirm:|cancel:).*')],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

# Define the ConversationHandler for Tara team messages (-t)
tara_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(re.compile(r'^-t$', re.IGNORECASE)), tara_trigger)],
    states={
        TARA_MESSAGE: [MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, tara_message_handler)],
        CONFIRMATION: [CallbackQueryHandler(confirmation_handler, pattern='^(confirm:|cancel:).*')],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

# Define the ConversationHandler for general messages
general_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(
        (filters.TEXT | filters.Document.ALL) &
        ~filters.COMMAND &
        ~filters.Regex(re.compile(r'^-@')) &
        ~filters.Regex(re.compile(r'^-(w|e|mcq|d|de|mf|t|c|team)$', re.IGNORECASE)),
        handle_general_message
    )],
    states={
        SELECT_ROLE: [CallbackQueryHandler(select_role_handler, pattern='^role:.*$|^cancel_role_selection$')],
        CONFIRMATION: [CallbackQueryHandler(confirmation_handler, pattern='^(confirm:|cancel:).*')],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    allow_reentry=True,
)

# ------------------ Error Handler ------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log the error and send a message to the user if necessary."""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=True)
    # Optionally, notify the user about the error
    if isinstance(update, Update) and update.message:
        await update.message.reply_text("An error occurred. Please try again later.")

# ------------------ Command Handlers ------------------

# Add the /start command handler
start_handler = CommandHandler('start', start)

# Add the /listusers command handler
list_users_handler = CommandHandler('listusers', list_users)

# Add the /help command handler
help_handler = CommandHandler('help', help_command)

# Add the /refresh command handler
refresh_handler = CommandHandler('refresh', refresh)

# Add the /mute command handler (only for Tara Team)
mute_handler = CommandHandler('mute', mute_command)

# Add the /muteid command handler (only for Tara Team)
mute_id_handler = CommandHandler('muteid', mute_id_command)

# Add the /unmuteid command handler (only for Tara Team)
unmute_id_handler = CommandHandler('unmuteid', unmute_id_command)

# Add the /listmuted command handler (only for Tara Team)
list_muted_handler = CommandHandler('listmuted', list_muted_command)

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
