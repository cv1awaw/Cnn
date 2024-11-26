# main.py

import logging
import os
import re
import json
from pathlib import Path
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler,
    CommandHandler,
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
    '-t': ['tara_team'],             # Newly added trigger for Tara Team
}

# Define target roles for each role
# Adjusted to ensure that other roles can only send messages to 'tara_team'
SENDING_ROLE_TARGETS = {
    'writer': ['tara_team'],
    'mcqs_team': ['tara_team'],
    'checker_team': ['tara_team'],
    'word_team': ['tara_team'],
    'design_team': ['tara_team'],
    'king_team': ['tara_team'],
    'tara_team': list(ROLE_MAP.keys()),  # Tara can send to all roles
    'mind_map_form_creator': ['tara_team'],
}

# ------------------ Define Conversation States ------------------

TEAM_MESSAGE = 1
SPECIFIC_TEAM_MESSAGE = 2
SPECIFIC_USER_MESSAGE = 3
TARA_MESSAGE = 4  # Newly added state for Tara messages

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

def get_user_role(user_id):
    """Determine the role of a user based on their user ID."""
    for role, ids in ROLE_MAP.items():
        if user_id in ids:
            return role
    return None

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

# ------------------ Message Forwarding ------------------

async def forward_message(bot, message, target_ids, sender_role):
    """Forward a message to a list of target user IDs and notify about the sender's role."""
    # Get the display name for the sender's role
    sender_display_name = ROLE_DISPLAY_NAMES.get(sender_role, sender_role.capitalize())

    for user_id in target_ids:
        try:
            # Forward the original message
            await bot.forward_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
            logger.info(f"Forwarded message {message.message_id} to {user_id}")

            # Send an additional message indicating the sender's role with display name
            role_notification = f"🔄 *This message was sent by **{sender_display_name}**.*"
            await bot.send_message(
                chat_id=user_id,
                text=role_notification,
                parse_mode='Markdown'
            )
            logger.info(f"Sent role notification to {user_id}")

        except Exception as e:
            logger.error(f"Failed to forward message or send role notification to {user_id}: {e}")

# ------------------ Additional Functions ------------------

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the conversation."""
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

# ------------------ Command Handlers ------------------

async def handle_general_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages and forward them based on user roles."""
    message = update.message
    if not message:
        return  # Ignore non-message updates

    user_id = message.from_user.id
    username = message.from_user.username

    # Check if the user is muted
    if user_id in muted_users:
        await message.reply_text("You have been muted and cannot send messages through this bot.")
        logger.info(f"Muted user {user_id} attempted to send a message.")
        return

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

    role = get_user_role(user_id)

    if not role:
        await message.reply_text("You don't have a role assigned to use this bot.")
        logger.warning(f"Unauthorized access attempt by user {user_id}")
        return

    logger.info(f"Received message from user {user_id} with role '{role}'")

    # Determine target roles based on sender's role
    target_roles = SENDING_ROLE_TARGETS.get(role, [])

    # Aggregate target user IDs from target roles
    target_ids = set()
    for target_role in target_roles:
        target_ids.update(ROLE_MAP.get(target_role, []))

    # Exclude the sender's user ID from all forwards
    target_ids.discard(user_id)

    if not target_ids:
        await message.reply_text("No recipients found to send your message.")
        return

    # Log the forwarding action
    logger.info(f"Forwarding message from '{role}' to roles: {target_roles}")

    # Forward the message to the aggregated target user IDs with role notification
    await forward_message(context.bot, message, target_ids, sender_role=role)

    # Optionally, send a confirmation to the sender
    sender_display_name = ROLE_DISPLAY_NAMES.get(role, role.capitalize())
    recipient_display_names = [ROLE_DISPLAY_NAMES.get(r, r.capitalize()) for r in target_roles]
    confirmation = (
        f"✅ *Your message has been sent from **{sender_display_name}** "
        f"to **{', '.join(recipient_display_names)}**.*"
    )
    await message.reply_text(confirmation, parse_mode='Markdown')

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

    await update.message.reply_text(
        f"Hello, {user.first_name}! Welcome to the Team Communication Bot.\n\n"
        "Feel free to send messages using the available commands."
    )

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all stored usernames and their user IDs. Restricted to Tara Team."""
    user_id = update.message.from_user.id
    role = get_user_role(user_id)
    
    if role != 'tara_team':
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
    """Provide help information to users."""
    help_text = (
        "📘 *Available Commands:*\n\n"
        "/start - Initialize interaction with the bot.\n"
        "/listusers - List all registered users (Tara Team only).\n"
        "/help - Show this help message.\n"
        "/refresh - Refresh your user information.\n\n"
        "*Specific Commands for Tara Team:*\n"
        "/mute - Mute yourself.\n"
        "/muteid <user_id> - Mute a specific user by their ID.\n"
        "/unmuteid <user_id> - Unmute a specific user by their ID.\n"
        "/listmuted - List all currently muted users."
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
    role = get_user_role(user_id)

    # Restrict to Tara Team only
    if role != 'tara_team':
        await update.message.reply_text("You are not authorized to use this command.")
        logger.warning(f"Unauthorized mute attempt by user {user_id} with role '{role}'.")
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
    role = get_user_role(user_id)

    # Restrict to Tara Team only
    if role != 'tara_team':
        await update.message.reply_text("You are not authorized to use this command.")
        logger.warning(f"Unauthorized unmute attempt by user {user_id} with role '{role}'.")
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
    role = get_user_role(user_id)

    if role != 'tara_team':
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

# ------------------ Conversation Handlers ------------------

# Define the ConversationHandler for specific user commands
specific_user_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(r'(?i)^\s*-\@([A-Za-z0-9_]{5,32})\s*$'), specific_user_trigger)],
    states={
        SPECIFIC_USER_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, specific_user_message_handler)],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

# Define the ConversationHandler for specific team commands
specific_team_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(r'(?i)^-(w|e|mcq|d|de|mf)$'), specific_team_trigger)],
    states={
        SPECIFIC_TEAM_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, specific_team_message_handler)],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

# Define the ConversationHandler for general team messages
team_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(r'(?i)^-?team-?$'), team_trigger)],
    states={
        TEAM_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, team_message_handler)],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

# Define the ConversationHandler for Tara team messages using -t or -T
tara_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(r'(?i)^-t$'), tara_trigger)],
    states={
        TARA_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, tara_message_handler)],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

# ------------------ Additional Conversation Handlers ------------------

async def specific_user_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trigger function when a Tara team member sends a specific user command."""
    user_id = update.message.from_user.id
    role = get_user_role(user_id)

    if role != 'tara_team':
        await update.message.reply_text("You are not authorized to use this command.")
        logger.warning(f"Unauthorized access attempt by user {user_id} for specific user triggers.")
        return ConversationHandler.END

    # Extract username from the command using regex
    match = re.match(r'(?i)^\s*-\@([A-Za-z0-9_]{5,32})\s*$', update.message.text)
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

    # Store target user ID in user_data
    context.user_data['target_user_id'] = target_user_id

    await update.message.reply_text(f"Write your message for user `@{target_username}`.", parse_mode='Markdown')
    return SPECIFIC_USER_MESSAGE

async def specific_user_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the message intended for a specific user."""
    message = update.message
    user_id = message.from_user.id
    role = get_user_role(user_id)

    if not role:
        await message.reply_text("You don't have a role assigned to use this bot.")
        logger.warning(f"Unauthorized access attempt by user {user_id}")
        return ConversationHandler.END

    target_user_id = context.user_data.get('target_user_id')
    if not target_user_id:
        await message.reply_text("An error occurred. Please try again.")
        logger.error(f"No target user ID found in user_data for user {user_id}.")
        return ConversationHandler.END

    # Forward the message to the specific user
    try:
        await message.forward(chat_id=target_user_id)
        logger.info(f"Forwarded message {message.message_id} from user {user_id} to user {target_user_id}.")

        # Retrieve the target username for confirmation
        target_username = None
        for uname, uid in user_data_store.items():
            if uid == target_user_id:
                target_username = uname
                break

        if target_username:
            confirmation = (
                f"✅ *Your message has been sent to `@{target_username}`.*"
            )
        else:
            confirmation = (
                f"✅ *Your message has been sent to the specified user.*"
            )
        await message.reply_text(confirmation, parse_mode='Markdown')
        logger.info(f"Confirmation sent to user {user_id} for message to user {target_user_id}.")

    except Exception as e:
        logger.error(f"Failed to forward message to user {target_user_id}: {e}")
        await message.reply_text("Failed to send your message. Please try again later.")

    return ConversationHandler.END

async def specific_team_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trigger function when a Tara team member sends a specific team command."""
    user_id = update.message.from_user.id
    role = get_user_role(user_id)

    if role != 'tara_team':
        await update.message.reply_text("You are not authorized to use this command.")
        logger.warning(f"Unauthorized access attempt by user {user_id} for specific team triggers.")
        return ConversationHandler.END

    message = update.message.text.lower().strip()
    target_roles = TRIGGER_TARGET_MAP.get(message)

    if not target_roles:
        await update.message.reply_text("Invalid trigger. Please try again.")
        logger.warning(f"Invalid trigger '{message}' from user {user_id}.")
        return ConversationHandler.END

    # Store target roles in user_data
    context.user_data['specific_target_roles'] = target_roles

    await update.message.reply_text("Write your message for your team.")
    return SPECIFIC_TEAM_MESSAGE

async def specific_team_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the team message after the specific trigger."""
    message = update.message
    user_id = message.from_user.id
    role = get_user_role(user_id)

    if not role:
        await message.reply_text("You don't have a role assigned to use this bot.")
        logger.warning(f"Unauthorized access attempt by user {user_id}")
        return ConversationHandler.END

    target_roles = context.user_data.get('specific_target_roles', [])
    target_ids = set()

    for target_role in target_roles:
        target_ids.update(ROLE_MAP.get(target_role, []))

    # Exclude the sender's user ID from all forwards
    target_ids.discard(user_id)

    if not target_ids:
        await message.reply_text("No recipients found to send your message.")
        logger.warning(f"No recipients found for user {user_id} with role '{role}'.")
        return ConversationHandler.END

    # Forward the message
    await forward_message(context.bot, message, target_ids, sender_role=role)

    # Prepare display names for confirmation
    sender_display_name = ROLE_DISPLAY_NAMES.get(role, role.capitalize())
    recipient_display_names = [ROLE_DISPLAY_NAMES.get(r, r.capitalize()) for r in target_roles]

    confirmation = (
        f"✅ *Your message has been sent from **{sender_display_name}** "
        f"to **{', '.join(recipient_display_names)}**.*"
    )
    await message.reply_text(confirmation, parse_mode='Markdown')

    return ConversationHandler.END

async def team_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the general team trigger."""
    user_id = update.message.from_user.id
    role = get_user_role(user_id)

    if not role:
        await update.message.reply_text("You don't have a role assigned to use this bot.")
        logger.warning(f"Unauthorized access attempt by user {user_id} for general team trigger.")
        return ConversationHandler.END

    # Determine which roles the sender can send messages to
    target_roles = SENDING_ROLE_TARGETS.get(role, [])

    if not target_roles:
        await update.message.reply_text("You have no teams to send messages to.")
        logger.info(f"No target roles found for user {user_id} with role '{role}'.")
        return ConversationHandler.END

    # Store target roles in user_data for use in the next step
    context.user_data['specific_target_roles'] = target_roles

    await update.message.reply_text("Write your message for your team.")
    return TEAM_MESSAGE

async def team_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the team message after the general trigger."""
    message = update.message
    user_id = message.from_user.id
    role = get_user_role(user_id)

    if not role:
        await message.reply_text("You don't have a role assigned to use this bot.")
        logger.warning(f"Unauthorized access attempt by user {user_id}")
        return ConversationHandler.END

    target_roles = context.user_data.get('specific_target_roles', [])
    target_ids = set()

    for target_role in target_roles:
        target_ids.update(ROLE_MAP.get(target_role, []))

    # Exclude the sender's user ID from all forwards
    target_ids.discard(user_id)

    if not target_ids:
        await message.reply_text("No recipients found to send your message.")
        logger.warning(f"No recipients found for user {user_id} with role '{role}'.")
        return ConversationHandler.END

    # Forward the message
    await forward_message(context.bot, message, target_ids, sender_role=role)

    # Prepare display names for confirmation
    sender_display_name = ROLE_DISPLAY_NAMES.get(role, role.capitalize())
    recipient_display_names = [ROLE_DISPLAY_NAMES.get(r, r.capitalize()) for r in target_roles]

    confirmation = (
        f"✅ *Your message has been sent from **{sender_display_name}** "
        f"to **{', '.join(recipient_display_names)}**.*"
    )
    await message.reply_text(confirmation, parse_mode='Markdown')

    return ConversationHandler.END

async def tara_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the -t trigger to send a message to Tara team."""
    user_id = update.message.from_user.id
    role = get_user_role(user_id)

    # Tara Team can send messages to themselves and others as defined in SENDING_ROLE_TARGETS
    # Based on your requirements, messages sent by Tara Team should not be forwarded to any other roles
    # Therefore, we'll handle it separately to ensure no forwarding occurs

    await update.message.reply_text("Write your message for the Tara Team.")
    return TARA_MESSAGE

async def tara_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the message intended for Tara team."""
    message = update.message
    user_id = message.from_user.id
    role = get_user_role(user_id)

    if not role:
        await message.reply_text("You don't have a role assigned to use this bot.")
        logger.warning(f"Unauthorized access attempt by user {user_id}")
        return ConversationHandler.END

    target_roles = ['tara_team']
    target_ids = set(ROLE_MAP.get('tara_team', []))

    # Exclude the sender's user ID from all forwards (if user is in Tara team)
    target_ids.discard(user_id)

    if not target_ids:
        await message.reply_text("No recipients found to send your message.")
        logger.warning(f"No recipients found for user {user_id} with role '{role}'.")
        return ConversationHandler.END

    # Forward the message to Tara team
    await forward_message(context.bot, message, target_ids, sender_role=role)

    # Prepare display names for confirmation
    sender_display_name = ROLE_DISPLAY_NAMES.get(role, role.capitalize())
    recipient_display_names = [ROLE_DISPLAY_NAMES.get('tara_team', 'Tara Team')]

    confirmation = (
        f"✅ *Your message has been sent from **{sender_display_name}** "
        f"to **{', '.join(recipient_display_names)}**.*"
    )
    await message.reply_text(confirmation, parse_mode='Markdown')

    return ConversationHandler.END

# ------------------ Main Function ------------------

def main():
    """Main function to start the Telegram bot."""
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set in environment variables.")
        return

    # Build the application
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Add the /start command handler
    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)

    # Add the /listusers command handler
    list_users_handler = CommandHandler('listusers', list_users)
    application.add_handler(list_users_handler)

    # Add the /help command handler
    help_handler = CommandHandler('help', help_command)
    application.add_handler(help_handler)

    # Add the /refresh command handler
    refresh_handler = CommandHandler('refresh', refresh)
    application.add_handler(refresh_handler)

    # Add the /mute command handler (only for Tara Team)
    mute_handler = CommandHandler('mute', mute_command)
    application.add_handler(mute_handler)

    # Add the /muteid command handler (only for Tara Team)
    mute_id_handler = CommandHandler('muteid', mute_id_command)
    application.add_handler(mute_id_handler)

    # Add the /unmuteid command handler (only for Tara Team)
    unmute_id_handler = CommandHandler('unmuteid', unmute_id_command)
    application.add_handler(unmute_id_handler)

    # Add the /listmuted command handler (only for Tara Team)
    list_muted_handler = CommandHandler('listmuted', list_muted_command)
    application.add_handler(list_muted_handler)

    # Add the ConversationHandler for specific user commands
    application.add_handler(specific_user_conv_handler)

    # Add the ConversationHandler for specific team commands
    application.add_handler(specific_team_conv_handler)

    # Add the ConversationHandler for general team messages
    application.add_handler(team_conv_handler)

    # Add the ConversationHandler for Tara team messages (-t)
    application.add_handler(tara_conv_handler)

    # Handle all other text and document messages, excluding commands
    message_handler = MessageHandler(
        (filters.TEXT & ~filters.COMMAND) | filters.Document.ALL, 
        handle_general_message
    )
    application.add_handler(message_handler)

    # Start the Bot
    logger.info("Bot started polling...")
    application.run_polling()

if __name__ == '__main__':
       main()
