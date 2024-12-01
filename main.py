# main.py

import logging
import os
import re
import json
from pathlib import Path
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputMediaDocument
)
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
    MIND_MAP_FORM_CREATOR_IDS,
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
    'mind_map_form_creator': MIND_MAP_FORM_CREATOR_IDS,
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
    'mind_map_form_creator': 'Mind Map & Form Creation Team',
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
CANCEL = ConversationHandler.END

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

    elif data == 'cancel_role_selection':
        await query.edit_message_text("Operation cancelled.")
        logger.info(f"User {query.from_user.id} cancelled role selection.")
        return ConversationHandler.END

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

    confirmation_text = (
        f"📩 *You are about to send the following to `{target_display_name}`:*\n\n"
        f"{content_description}\n\n"
        "Do you want to send this?"
    )
    await message.reply_text(confirmation_text, parse_mode='Markdown', reply_markup=get_confirmation_keyboard(message.message_id))

    # Store confirmation data
    context.user_data[f'confirm_{message.message_id}'] = {
        'message': message,
        'target_ids': [target_user_id],
        'sender_role': sender_role,
        'target_roles': ['specific_user']
    }

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

    confirmation_text = (
        f"📩 *You are about to send the following to **{', '.join([ROLE_DISPLAY_NAMES.get(r, r.capitalize()) for r in target_roles])}**:*\n\n"
        f"{content_description}\n\n"
        "Do you want to send this?"
    )
    await message.reply_text(confirmation_text, parse_mode='Markdown', reply_markup=get_confirmation_keyboard(message.message_id))

    # Store confirmation data
    context.user_data[f'confirm_{message.message_id}'] = {
        'message': message,
        'target_ids': list(target_ids),
        'sender_role': sender_role,
        'target_roles': target_roles
    }

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
        return SELECT_ROLE
    else:
        # Single role, proceed to message writing
        selected_role = roles[0]
        context.user_data['sender_role'] = selected_role

        await update.message.reply_text("Write your message for your team and Tara Team.")
        return TEAM_MESSAGE

async def team_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, message=None):
    """Handle the team message after the general trigger and ask for confirmation."""
    if message is None:
        message = update.message

    user_id = message.from_user.id
    selected_role = context.user_data.get('sender_role')

    if not selected_role:
        await message.reply_text("An error occurred. Please try again.")
        logger.error(f"No sender role found in user_data for user {user_id}.")
        return ConversationHandler.END

    target_roles = SENDING_ROLE_TARGETS.get(selected_role, [])
    target_ids = set()

    for target_role in target_roles:
        target_ids.update(ROLE_MAP.get(target_role, []))

    # Exclude the sender's user ID from all forwards
    target_ids.discard(user_id)

    if not target_ids:
        await message.reply_text("No recipients found to send your message.")
        logger.warning(f"No recipients found for user {user_id} with role '{selected_role}'.")
        return ConversationHandler.END

    # Handle PDF documents and text messages
    if message.document and message.document.mime_type == 'application/pdf':
        await send_confirmation(message, context, selected_role, list(target_ids), target_roles=target_roles)
    elif message.text:
        await send_confirmation(message, context, selected_role, list(target_ids), target_roles=target_roles)
    else:
        await message.reply_text("Please send PDF documents or text messages only.")
        logger.warning(f"User {user_id} sent an unsupported message type.")
        return ConversationHandler.END

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

        # Proceed to handle the message
        await query.edit_message_text("Processing your message...")
        # Capture the state returned by team_message_handler
        state = await team_message_handler(update, context, message=pending_message)
        # Return the state to continue the conversation
        return state

    elif data == 'cancel_role_selection':
        await query.edit_message_text("Operation cancelled.")
        logger.info(f"User {query.from_user.id} cancelled role selection.")
        return ConversationHandler.END

    else:
        await query.edit_message_text("Invalid role selection.")
        logger.warning(f"User {query.from_user.id} sent invalid role selection: {data}")
        return ConversationHandler.END

async def tara_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the -t trigger to send a message to Tara team."""
    user_id = update.message.from_user.id
    roles = get_user_roles(user_id)

    if not roles:
        await update.message.reply_text("You don't have a role assigned to use this bot.")
        logger.warning(f"User {user_id} attempted to use -t without a role.")
        return ConversationHandler.END

    # Store the user's role
    context.user_data['sender_role'] = roles[0]  # Use the first role

    await update.message.reply_text("Write your message for the Tara Team.")
    return TARA_MESSAGE

async def tara_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the message intended for Tara team and ask for confirmation."""
    message = update.message
    user_id = message.from_user.id
    sender_role = context.user_data.get('sender_role')

    if not sender_role:
        await message.reply_text("You don't have a role assigned to use this bot.")
        logger.warning(f"Unauthorized access attempt by user {user_id}")
        return ConversationHandler.END

    target_roles = ['tara_team']
    target_ids = set(ROLE_MAP.get('tara_team', []))

    # Exclude the sender's user ID from all forwards (if user is in Tara team)
    target_ids.discard(user_id)

    if not target_ids:
        await message.reply_text("No recipients found to send your message.")
        logger.warning(f"No recipients found for user {user_id} with role '{sender_role}'.")
        return ConversationHandler.END

    # Store the message and targets for confirmation
    context.user_data['message_to_send'] = message
    context.user_data['target_ids'] = list(target_ids)
    context.user_data['target_roles'] = target_roles

    await send_confirmation(message, context, sender_role, list(target_ids), target_roles=target_roles)

    return CONFIRMATION

async def handle_general_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages and forward them based on user roles."""
    message = update.message
    if not message:
        return ConversationHandler.END  # Ignore non-message updates

    user_id = message.from_user.id
    username = message.from_user.username

    # Check if the user is muted
    if user_id in muted_users:
        await message.reply_text("You have been muted and cannot send messages through this bot.")
        logger.info(f"Muted user {user_id} attempted to send a message.")
        return ConversationHandler.END

    # Store the username and user_id if username exists
    if username:
        username_lower = username.lower()
        previous_id = user_data_store.get(username_lower)
        if previous_id != user_id:
            # Update if the user_id has changed
            user_data_store[username_lower] = user_id
            logger.info(f"Stored/Updated username '{username_lower}' for user ID {user_id}.")
            save_user_data()
    else:
        logger.info(f"User {user_id} has no username and cannot be targeted.")

    roles = get_user_roles(user_id)

    if not roles:
        await message.reply_text("You don't have a role assigned to use this bot.")
        logger.warning(f"Unauthorized access attempt by user {user_id}")
        return ConversationHandler.END

    logger.info(f"Received message from user {user_id} with roles '{roles}'")

    # Determine target roles based on sender's roles
    if len(roles) > 1:
        # Present role selection keyboard
        keyboard = get_role_selection_keyboard(roles)
        await message.reply_text(
            "You have multiple roles. Please choose which role you want to use to send this message:",
            reply_markup=keyboard
        )
        # Store pending message
        context.user_data['pending_message'] = message
        return SELECT_ROLE
    else:
        # Single role, proceed to send message
        selected_role = roles[0]
        context.user_data['sender_role'] = selected_role

        # Handle PDF documents and text messages
        if message.document and message.document.mime_type == 'application/pdf':
            # Proceed to confirmation
            await team_message_handler(update, context)
        elif message.text:
            # Proceed to confirmation
            await team_message_handler(update, context)
        else:
            await message.reply_text("Please send PDF documents or text messages only.")
            logger.warning(f"User {user_id} sent an unsupported message type.")
            return ConversationHandler.END

        return ConversationHandler.END

# ------------------ Command Handlers ------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command."""
    user = update.effective_user
    if not user.username:
        await update.message.reply_text(
            "Please set a Telegram username in your profile to use specific commands like `-@username`."
        )
        logger.warning(f"User {user.id} has no username and cannot be targeted.")
        return

    # Store the username and user_id
    username_lower = user.username.lower()
    user_data_store[username_lower] = user.id
    logger.info(f"User {user.id} with username '{username_lower}' started the bot.")

    # Save to JSON file
    save_user_data()

    display_name = get_display_name(user)

    await update.message.reply_text(
        f"Hello, {display_name}! Welcome to the Team Communication Bot.\n\n"
        "Feel free to send messages using the available commands."
    )

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all stored usernames and their user IDs. Restricted to Tara Team."""
    user_id = update.message.from_user.id
    roles = get_user_roles(user_id)

    if 'tara_team' not in roles:
        await update.message.reply_text("You are not authorized to use this command.")
        logger.warning(f"Unauthorized access attempt by user {user_id} for /listusers.")
        return

    if not user_data_store:
        await update.message.reply_text("No users have interacted with the bot yet.")
        return

    user_list = "\n".join([f"@{username}: {uid}" for username, uid in user_data_store.items()])
    await update.message.reply_text(f"**Registered Users:**\n{user_list}", parse_mode='Markdown')
    logger.info(f"User {user_id} requested the list of users.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provide help information to users with subcommands explanations."""
    help_text = (
        "📘 *Available Commands:*\n\n"
        "/start - Initialize interaction with the bot.\n"
        "/listusers - List all registered users (Tara Team only).\n"
        "/help - Show this help message.\n"
        "/refresh - Refresh your user information.\n"
        "/cancel - Cancel the current operation.\n\n"
        "*Message Sending Triggers:*\n"
        "`-team` - Send a message to your own team and Tara Team.\n"
        "`-t` - Send a message exclusively to the Tara Team.\n\n"
        "*Specific Commands for Tara Team:*\n"
        "`-@username` - Send a message to a specific user.\n"
        "`-w` - Send a message to the Writer Team.\n"
        "`-e` - Send a message to the Editor Team.\n"
        "`-mcq` - Send a message to the MCQs Team.\n"
        "`-d` - Send a message to the Digital Writers.\n"
        "`-de` - Send a message to the Design Team.\n"
        "`-mf` - Send a message to the Mind Map & Form Creation Team.\n"
        "`-c` - Send a message to the Editor Team.\n\n"
        "*Admin Commands (Tara Team only):*\n"
        "/mute [user_id] - Mute yourself or another user.\n"
        "/muteid <user_id> - Mute a specific user by their ID.\n"
        "/unmuteid <user_id> - Unmute a specific user by their ID.\n"
        "/listmuted - List all currently muted users.\n\n"
        "📌 *Notes:*\n"
        "- Only Tara Team members can use the side commands and `-@username` command.\n"
        "- Use `/cancel` to cancel any ongoing operation."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')
    logger.info(f"User {update.effective_user.id} requested help.")

async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Refresh user information."""
    user = update.effective_user
    if not user.username:
        await update.message.reply_text(
            "Please set a Telegram username in your profile to refresh your information."
        )
        logger.warning(f"User {user.id} has no username and cannot be refreshed.")
        return

    # Store the username and user_id
    username_lower = user.username.lower()
    user_data_store[username_lower] = user.id
    logger.info(f"User {user.id} with username '{username_lower}' refreshed their info.")

    # Save to JSON file
    save_user_data()

    await update.message.reply_text(
        "Your information has been refreshed successfully."
    )

# ------------------ Mute Command Handlers ------------------

async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /mute command for Tara Team."""
    user_id = update.message.from_user.id
    roles = get_user_roles(user_id)

    # Restrict to Tara Team only
    if 'tara_team' not in roles:
        await update.message.reply_text("You are not authorized to use this command.")
        logger.warning(f"Unauthorized mute attempt by user {user_id} with roles '{roles}'.")
        return

    # Mute self or another user
    if len(context.args) == 0:
        target_user_id = user_id
    elif len(context.args) == 1:
        try:
            target_user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Please provide a valid user ID.")
            return
    else:
        await update.message.reply_text("Usage: /mute [user_id]")
        return

    if target_user_id in muted_users:
        if target_user_id == user_id:
            await update.message.reply_text("You are already muted.")
        else:
            await update.message.reply_text("This user is already muted.")
        logger.info(f"Attempt to mute already muted user {target_user_id} by {user_id}.")
        return

    muted_users.add(target_user_id)
    save_muted_users()

    if target_user_id == user_id:
        await update.message.reply_text("You have been muted and can no longer send messages through this bot.")
        logger.info(f"User {user_id} has muted themselves.")
    else:
        # Attempt to get the username of the target user
        target_username = None
        for uname, uid in user_data_store.items():
            if uid == target_user_id:
                target_username = uname
                break

        if target_username:
            await update.message.reply_text(f"User `@{target_username}` has been muted.", parse_mode='Markdown')
            logger.info(f"User {user_id} has muted user {target_user_id} (@{target_username}).")
        else:
            await update.message.reply_text(f"User ID {target_user_id} has been muted.")
            logger.info(f"User {user_id} has muted user {target_user_id}.")

async def mute_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /muteid command for Tara Team."""
    await mute_command(update, context)

async def unmute_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /unmuteid command for Tara Team."""
    user_id = update.message.from_user.id
    roles = get_user_roles(user_id)

    # Restrict to Tara Team only
    if 'tara_team' not in roles:
        await update.message.reply_text("You are not authorized to use this command.")
        logger.warning(f"Unauthorized unmute attempt by user {user_id} with roles '{roles}'.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Usage: /unmuteid <user_id>")
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Please provide a valid user ID.")
        return

    if target_user_id in muted_users:
        muted_users.remove(target_user_id)
        save_muted_users()

        # Attempt to get the username of the target user
        target_username = None
        for uname, uid in user_data_store.items():
            if uid == target_user_id:
                target_username = uname
                break

        if target_username:
            await update.message.reply_text(f"User `@{target_username}` has been unmuted.", parse_mode='Markdown')
            logger.info(f"User {user_id} has unmuted user {target_user_id} (@{target_username}).")
        else:
            await update.message.reply_text(f"User ID {target_user_id} has been unmuted.")
            logger.info(f"User {user_id} has unmuted user {target_user_id}.")
    else:
        await update.message.reply_text(f"User ID {target_user_id} is not muted.")
        logger.warning(f"Attempt to unmute user {target_user_id} who is not muted by user {user_id}.")

async def list_muted_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /listmuted command for Tara Team."""
    user_id = update.message.from_user.id
    roles = get_user_roles(user_id)

    if 'tara_team' not in roles:
        await update.message.reply_text("You are not authorized to use this command.")
        logger.warning(f"Unauthorized access attempt by user {user_id} for /listmuted.")
        return

    if not muted_users:
        await update.message.reply_text("No users are currently muted.")
        return

    muted_list = []
    for uid in muted_users:
        username = None
        for uname, id_ in user_data_store.items():
            if id_ == uid:
                username = uname
                break
        if username:
            muted_list.append(f"@{username} (ID: {uid})")
        else:
            muted_list.append(f"ID: {uid}")

    muted_users_text = "\n".join(muted_list)
    await update.message.reply_text(f"**Muted Users:**\n{muted_users_text}", parse_mode='Markdown')
    logger.info(f"User {user_id} requested the list of muted users.")

# ------------------ Error Handler ------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log the error and send a message to the user if necessary."""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=True)
    # You can also notify the user about the error if needed
    # if update and hasattr(update, 'message'):
    #     await update.message.reply_text("An error occurred. Please try again later.")

# ------------------ Conversation Handlers ------------------

# Define the ConversationHandler for specific user commands
specific_user_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(re.compile(r'^\s*-\@([A-Za-z0-9_]{5,32})\s*$', re.IGNORECASE)), specific_user_trigger)],
    states={
        SPECIFIC_USER_MESSAGE: [MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, specific_user_message_handler)],
        # Add the confirmation handler to all states
        ConversationHandler.ALL: [CallbackQueryHandler(confirmation_handler, pattern=r'^confirm:.*|^cancel:.*$')],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

# Define the ConversationHandler for specific team commands
specific_team_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(re.compile(r'^-(w|e|mcq|d|de|mf|c)$', re.IGNORECASE)), specific_team_trigger)],
    states={
        SPECIFIC_TEAM_MESSAGE: [MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, specific_team_message_handler)],
        # Add the confirmation handler to all states
        ConversationHandler.ALL: [CallbackQueryHandler(confirmation_handler, pattern=r'^confirm:.*|^cancel:.*$')],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

# Define the ConversationHandler for general team messages (-team)
team_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(re.compile(r'^-team$', re.IGNORECASE)), team_trigger)],
    states={
        SELECT_ROLE: [
            CallbackQueryHandler(select_role_handler, pattern=r'^role:.*$|^cancel_role_selection$'),
            # Add the confirmation handler to all states
            CallbackQueryHandler(confirmation_handler, pattern=r'^confirm:.*|^cancel:.*$'),
        ],
        TEAM_MESSAGE: [MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, team_message_handler)],
        # Add the confirmation handler to all states
        ConversationHandler.ALL: [CallbackQueryHandler(confirmation_handler, pattern=r'^confirm:.*|^cancel:.*$')],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

# Define the ConversationHandler for Tara team messages (-t)
tara_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(re.compile(r'^-t$', re.IGNORECASE)), tara_trigger)],
    states={
        TARA_MESSAGE: [MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, tara_message_handler)],
        # Add the confirmation handler to all states
        ConversationHandler.ALL: [CallbackQueryHandler(confirmation_handler, pattern=r'^confirm:.*|^cancel:.*$')],
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
        SELECT_ROLE: [
            CallbackQueryHandler(select_role_handler, pattern=r'^role:.*$|^cancel_role_selection$'),
            # Add the confirmation handler to all states
            CallbackQueryHandler(confirmation_handler, pattern=r'^confirm:.*|^cancel:.*$'),
        ],
        # Add the confirmation handler to all states
        ConversationHandler.ALL: [CallbackQueryHandler(confirmation_handler, pattern=r'^confirm:.*|^cancel:.*$')],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    allow_reentry=True,
)

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
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('listusers', list_users))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('refresh', refresh))
    application.add_handler(CommandHandler('mute', mute_command))
    application.add_handler(CommandHandler('muteid', mute_id_command))
    application.add_handler(CommandHandler('unmuteid', unmute_id_command))
    application.add_handler(CommandHandler('listmuted', list_muted_command))

    # Add ConversationHandlers
    application.add_handler(specific_user_conv_handler)
    application.add_handler(specific_team_conv_handler)
    application.add_handler(team_conv_handler)
    application.add_handler(tara_conv_handler)
    application.add_handler(general_conv_handler)

    # Add the error handler
    application.add_error_handler(error_handler)

    # Start the Bot using long polling
    logger.info("Bot started polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
