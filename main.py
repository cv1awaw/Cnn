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
}

# Define target roles for each role
SENDING_ROLE_TARGETS = {
    'writer': ['mcqs_team', 'checker_team', 'tara_team', 'mind_map_form_creator'],
    'mcqs_team': ['design_team', 'tara_team', 'mind_map_form_creator'],
    'checker_team': ['tara_team', 'word_team'],
    'word_team': ['tara_team', 'design_team'],
    'design_team': ['tara_team', 'king_team'],
    'king_team': ['tara_team'],
    'tara_team': list(ROLE_MAP.keys()),  # Tara can send to all roles
    'mind_map_form_creator': ['design_team', 'tara_team'],
}

# Define conversation states
TEAM_MESSAGE = 1
SPECIFIC_TEAM_MESSAGE = 2
SPECIFIC_USER_MESSAGE = 3

# User data storage: username (lowercase) -> user_id
USER_DATA_FILE = Path('user_data.json')

# Load existing user data if the file exists
if USER_DATA_FILE.exists():
    with open(USER_DATA_FILE, 'r') as f:
        user_data_store = json.load(f)
        # Convert keys to lowercase to maintain consistency
        user_data_store = {k.lower(): v for k, v in user_data_store.items()}
        logger.info("Loaded existing user data from user_data.json.")
else:
    user_data_store = {}

def save_user_data():
    """Save the user_data_store to a JSON file."""
    with open(USER_DATA_FILE, 'w') as f:
        json.dump(user_data_store, f)
        logger.info("Saved user data to user_data.json.")

def get_user_role(user_id):
    """Determine the role of a user based on their user ID."""
    for role, ids in ROLE_MAP.items():
        if user_id in ids:
            return role
    return None

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

async def handle_general_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages and forward them based on user roles."""
    message = update.message
    if not message:
        return  # Ignore non-message updates

    user_id = message.from_user.id
    username = message.from_user.username

    # Store the username and user_id if username exists
    if username:
        user_data_store[username.lower()] = user_id
        logger.info(f"Stored username '{username.lower()}' for user ID {user_id}.")

        # Save to JSON file
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
    user_data_store[user.username.lower()] = user.id
    logger.info(f"User {user.id} with username '{user.username.lower()}' started the bot.")
    
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

async def specific_user_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trigger function when a Tara team member sends a '-@username' command."""
    user_id = update.message.from_user.id
    role = get_user_role(user_id)

    if role != 'tara_team':
        await update.message.reply_text("You are not authorized to use this command.")
        logger.warning(f"Unauthorized access attempt by user {user_id} for specific user commands.")
        return ConversationHandler.END

    message = update.message.text.strip()

    # Extract the username using regex
    match = re.match(r'^-@([A-Za-z0-9_]{5,32})$', message)
    if not match:
        await update.message.reply_text("Invalid command format. Use `-@username`.")
        logger.warning(f"Invalid command format '{message}' from user {user_id}.")
        return ConversationHandler.END

    target_username = match.group(1).lower()
    target_user_id = user_data_store.get(target_username)

    if not target_user_id:
        await update.message.reply_text(f"User `@{target_username}` not found or hasn't interacted with the bot.", parse_mode='Markdown')
        logger.warning(f"User '@{target_username}' not found in user data store.")
        return ConversationHandler.END

    # Store target user ID in user_data for later use
    context.user_data['target_user_id'] = target_user_id

    logger.info(f"User {user_id} ({role}) is sending a message to user {target_user_id} (@{target_username}).")
    await update.message.reply_text(f"Write your message for `@{target_username}`.", parse_mode='Markdown')
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

        # Send a confirmation message to the Tara team member
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

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the conversation."""
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

# Define the ConversationHandler for specific user commands
specific_user_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(r'(?i)^-@([A-Za-z0-9_]{5,32})$'), specific_user_trigger)],
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

    # Add the ConversationHandler for specific user commands
    application.add_handler(specific_user_conv_handler)

    # Add the ConversationHandler for specific team commands
    application.add_handler(specific_team_conv_handler)

    # Add the ConversationHandler for general team messages
    application.add_handler(team_conv_handler)

    # Handle all other text and document messages
    message_handler = MessageHandler(filters.TEXT | filters.Document.ALL, handle_general_message)
    application.add_handler(message_handler)

    # Start the Bot
    logger.info("Bot started polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
