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
    MIND_MAP_FORM_CREATOR_IDS,
)

# ------------------ Setup Logging ------------------

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------ Define Roles ------------------

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

TEAM_MESSAGE = 1
CONFIRMATION = 2

USER_DATA_FILE = Path('user_data.json')
MUTED_USERS_FILE = Path('muted_users.json')

if USER_DATA_FILE.exists():
    with open(USER_DATA_FILE, 'r') as f:
        try:
            user_data_store = json.load(f)
            user_data_store = {k.lower(): v for k, v in user_data_store.items()}
        except json.JSONDecodeError:
            user_data_store = {}
else:
    user_data_store = {}

if MUTED_USERS_FILE.exists():
    with open(MUTED_USERS_FILE, 'r') as f:
        try:
            muted_users = set(json.load(f))
        except json.JSONDecodeError:
            muted_users = set()
else:
    muted_users = set()

def save_user_data():
    with open(USER_DATA_FILE, 'w') as f:
        json.dump(user_data_store, f)

def save_muted_users():
    with open(MUTED_USERS_FILE, 'w') as f:
        json.dump(list(muted_users), f)

def get_user_role(user_id):
    for role, ids in ROLE_MAP.items():
        if user_id in ids:
            return role
    return None

async def forward_message(bot, message, target_ids, sender_role):
    sender_display_name = ROLE_DISPLAY_NAMES.get(sender_role, sender_role.capitalize())
    for user_id in target_ids:
        try:
            await bot.forward_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
            role_notification = f"🔄 *This message was sent by **{sender_display_name}**.*"
            await bot.send_message(chat_id=user_id, text=role_notification, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to forward message to {user_id}: {e}")

def get_confirmation_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data='confirm'),
            InlineKeyboardButton("❌ Cancel", callback_data='cancel'),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

async def team_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    role = get_user_role(user_id)

    if not role:
        await update.message.reply_text("You don't have a role assigned to use this bot.")
        return ConversationHandler.END

    target_roles = [role, 'tara_team']
    context.user_data['specific_target_roles'] = target_roles
    context.user_data['sender_role'] = role

    await update.message.reply_text("Write your message for your team and Tara Team.")
    return TEAM_MESSAGE

async def team_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_id = message.from_user.id
    role = get_user_role(user_id)

    if not role:
        await message.reply_text("You don't have a role assigned to use this bot.")
        return ConversationHandler.END

    target_roles = context.user_data.get('specific_target_roles', [])
    target_ids = set()

    for target_role in target_roles:
        target_ids.update(ROLE_MAP.get(target_role, []))

    target_ids.discard(user_id)

    if not target_ids:
        await message.reply_text("No recipients found to send your message.")
        return ConversationHandler.END

    context.user_data['message_to_send'] = message
    context.user_data['target_ids'] = list(target_ids)
    context.user_data['target_roles'] = target_roles

    confirmation_text = (
        f"📩 *You are about to send the following message to **{', '.join([ROLE_DISPLAY_NAMES.get(r, r.capitalize()) for r in target_roles])}**:*\n\n"
        f"{message.text}\n\n"
        "Do you want to send this message?"
    )
    await message.reply_text(confirmation_text, parse_mode='Markdown', reply_markup=get_confirmation_keyboard())

    return CONFIRMATION

async def confirmation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data

    if choice == 'confirm':
        message_to_send = context.user_data.get('message_to_send')
        target_ids = context.user_data.get('target_ids')
        sender_role = context.user_data.get('sender_role')

        if not message_to_send or not target_ids or not sender_role:
            await query.edit_message_text("An error occurred. Please try again.")
            return ConversationHandler.END

        await forward_message(context.bot, message_to_send, target_ids, sender_role)

        sender_display_name = ROLE_DISPLAY_NAMES.get(sender_role, sender_role.capitalize())
        target_roles = context.user_data.get('target_roles', [])
        recipient_display_names = [ROLE_DISPLAY_NAMES.get(r, r.capitalize()) for r in target_roles]

        confirmation_text = (
            f"✅ *Your message has been sent from **{sender_display_name}** "
            f"to **{', '.join(recipient_display_names)}**.*"
        )
        await query.edit_message_text(confirmation_text, parse_mode='Markdown')
    elif choice == 'cancel':
        await query.edit_message_text("Operation cancelled.")
    else:
        await query.edit_message_text("Invalid choice.")

    return ConversationHandler.END

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user.username:
        await update.message.reply_text("Please set a Telegram username in your profile.")
        return

    username_lower = user.username.lower()
    user_data_store[username_lower] = user.id
    save_user_data()

    await update.message.reply_text(
        f"Hello, {user.first_name}! Welcome to the Team Communication Bot."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📘 *Available Commands:*\n\n"
        "/start - Initialize interaction with the bot.\n"
        "/help - Show this help message.\n\n"
        "*Message Triggers:*\n"
        "-team - Send a message to your role and Tara Team.\n\n"
        "Each role can only send messages to their role and the Tara Team."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

def main():
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set in environment variables.")
        return

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)

    help_handler = CommandHandler('help', help_command)
    application.add_handler(help_handler)

    team_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'(?i)^-?team-?$'), team_trigger)],
        states={
            TEAM_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, team_message_handler)],
            CONFIRMATION: [CallbackQueryHandler(confirmation_handler)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(team_conv_handler)

    logger.info("Bot started polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
