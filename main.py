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
    MIND_MAP_FORM_CREATOR_IDS,
)

import uvloop
import asyncio

# ------------------ Setup Logging ------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------ Define Roles ------------------
HIDDEN_IDS = [6177929931]

ROLE_MAP = {
    'writer': WRITER_IDS,
    'mcqs_team': MCQS_TEAM_IDS,
    'checker_team': CHECKER_TEAM_IDS,
    'word_team': WORD_TEAM_IDS,
    'design_team': DESIGN_TEAM_IDS,
    'king_team': KING_TEAM_IDS,
    'tara_team': TARA_TEAM_IDS,
    'mind_map_form_creator': MIND_MAP_FORM_CREATOR_IDS,
    'hidden': HIDDEN_IDS,  # Hidden role for special access
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
    'hidden': 'Hidden Admin',
}

# Define trigger to target roles mapping for Tara Team side commands
TRIGGER_TARGET_MAP = {
    '-w': ['writer'],
    '-e': ['checker_team'],
    '-mcq': ['mcqs_team'],
    '-d': ['word_team'],
    '-de': ['design_team'],
    '-mf': ['mind_map_form_creator'],
    '-c': ['checker_team'],
}

# Updated forwarding rules
SENDING_ROLE_TARGETS = {
    'writer': ['mcqs_team', 'checker_team', 'tara_team'],
    'mcqs_team': ['design_team', 'tara_team'],
    'checker_team': ['tara_team', 'word_team'],
    'word_team': ['tara_team', 'design_team'],
    'design_team': ['tara_team', 'king_team'],
    'king_team': ['tara_team'],
    'tara_team': [
        'writer', 'mcqs_team', 'checker_team', 'word_team',
        'design_team', 'king_team', 'tara_team', 'mind_map_form_creator'
    ],
    'mind_map_form_creator': ['design_team', 'tara_team'],
    'hidden': [],
}

# ------------------ Define Conversation States ------------------
TEAM_MESSAGE = 1
SPECIFIC_TEAM_MESSAGE = 2
SPECIFIC_USER_MESSAGE = 3
TARA_MESSAGE = 4
CONFIRMATION = 5
SELECT_ROLE = 6

# ------------------ User Data Storage ------------------
USER_DATA_FILE = Path('user_data.json')
if USER_DATA_FILE.exists():
    with open(USER_DATA_FILE, 'r') as f:
        try:
            user_data_store = json.load(f)
            user_data_store = {k.lower(): v for k, v in user_data_store.items()}
            logger.info("Loaded existing user data from user_data.json.")
        except json.JSONDecodeError:
            user_data_store = {}
            logger.error("user_data.json is not a valid JSON file. Starting with an empty data store.")
else:
    user_data_store = {}

def save_user_data():
    try:
        with open(USER_DATA_FILE, 'w') as f:
            json.dump(user_data_store, f)
            logger.info("Saved user data to user_data.json.")
    except Exception as e:
        logger.error(f"Failed to save user data: {e}")

def get_user_roles(user_id):
    roles = []
    for role, ids in ROLE_MAP.items():
        if user_id in ids:
            roles.append(role)
    return roles

# ------------------ Mute Functionality ------------------
MUTED_USERS_FILE = Path('muted_users.json')
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
    try:
        with open(MUTED_USERS_FILE, 'w') as f:
            json.dump(list(muted_users), f)
            logger.info("Saved muted users to muted_users.json.")
    except Exception as e:
        logger.error(f"Failed to save muted users: {e}")

# ------------------ Helper Functions ------------------
def get_display_name(user):
    if user.username:
        return f"@{user.username}"
    else:
        full_name = f"{user.first_name} {user.last_name}" if user.last_name else user.first_name
        return full_name

def get_confirmation_keyboard(uuid_str):
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f'confirm:{uuid_str}'),
            InlineKeyboardButton("❌ Cancel", callback_data=f'cancel:{uuid_str}'),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_role_selection_keyboard(roles):
    keyboard = []
    for role in roles:
        display_name = ROLE_DISPLAY_NAMES.get(role, role.capitalize())
        callback_data = f"role:{role}"
        keyboard.append([InlineKeyboardButton(display_name, callback_data=callback_data)])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data='cancel_role_selection')])
    return InlineKeyboardMarkup(keyboard)

async def forward_message(bot, message, target_ids, sender_role):
    sender_display_name = ROLE_DISPLAY_NAMES.get(sender_role, sender_role.capitalize())
    username_display = get_display_name(message.from_user)

    if message.document:
        caption = f"🔄 *This document was sent by **{username_display} ({sender_display_name})**.*"
    elif message.text:
        caption = f"🔄 *This message was sent by **{username_display} ({sender_display_name})**.*"
    else:
        caption = f"🔄 *This message was sent by **{username_display} ({sender_display_name})**.*"

    for user_id in target_ids:
        try:
            if message.document:
                await bot.send_document(
                    chat_id=user_id,
                    document=message.document.file_id,
                    caption=caption + (f"\n\n{message.caption}" if message.caption else ""),
                    parse_mode='Markdown'
                )
                logger.info(f"Forwarded document {message.document.file_id} to {user_id}")
            elif message.text:
                await bot.send_message(
                    chat_id=user_id,
                    text=f"{caption}\n\n{message.text}",
                    parse_mode='Markdown'
                )
                logger.info(f"Forwarded text message to {user_id}")
            else:
                await bot.forward_message(
                    chat_id=user_id,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id
                )
                logger.info(f"Forwarded message {message.message_id} to {user_id}")

        except Exception as e:
            logger.error(f"Failed to forward message or send role notification to {user_id}: {e}")

async def send_confirmation(message, context, sender_role, target_ids, target_roles=None):
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

    confirmation_uuid = str(uuid.uuid4())
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f'confirm:{confirmation_uuid}'),
            InlineKeyboardButton("❌ Cancel", callback_data=f'cancel:{confirmation_uuid}'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(confirmation_text, parse_mode='Markdown', reply_markup=reply_markup)

    context.user_data[f'confirm_{confirmation_uuid}'] = {
        'message': message,
        'target_ids': target_ids,
        'sender_role': sender_role,
        'target_roles': target_roles if target_roles else SENDING_ROLE_TARGETS.get(sender_role, [])
    }

# ------------------ Handler Functions ------------------
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Operation cancelled.")
    else:
        await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

async def confirmation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith('confirm:') or data.startswith('cancel:'):
        try:
            action, confirmation_uuid = data.split(':', 1)
        except ValueError:
            await query.edit_message_text("Invalid confirmation data. Please try again.")
            return ConversationHandler.END

        confirm_data = context.user_data.get(f'confirm_{confirmation_uuid}')
        if not confirm_data:
            await query.edit_message_text("An error occurred. Please try again.")
            return ConversationHandler.END

        if action == 'confirm':
            message_to_send = confirm_data['message']
            target_ids = confirm_data['target_ids']
            sender_role = confirm_data['sender_role']
            target_roles = confirm_data.get('target_roles', [])

            await forward_message(context.bot, message_to_send, target_ids, sender_role)
            sender_display_name = ROLE_DISPLAY_NAMES.get(sender_role, sender_role.capitalize())

            if 'specific_user' in target_roles:
                recipient_display_names = []
                for tid in target_ids:
                    try:
                        target_user = await context.bot.get_chat(tid)
                        recipient_display_names.append(get_display_name(target_user))
                    except:
                        recipient_display_names.append(str(tid))
            else:
                recipient_display_names = [
                    ROLE_DISPLAY_NAMES.get(r, r.capitalize())
                    for r in target_roles
                    if r != 'specific_user'
                ]

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
            del context.user_data[f'confirm_{confirmation_uuid}']

        elif action == 'cancel':
            await query.edit_message_text("Operation cancelled.")
            if f'confirm_{confirmation_uuid}' in context.user_data:
                del context.user_data[f'confirm_{confirmation_uuid}']
    else:
        await query.edit_message_text("Invalid choice.")

    return ConversationHandler.END

async def specific_user_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    roles = get_user_roles(user_id)

    if 'tara_team' not in roles:
        await update.message.reply_text("You are not authorized to use this command.")
        return ConversationHandler.END

    match = re.match(r'^\s*-\@([A-Za-z0-9_]{5,32})\s*$', update.message.text, re.IGNORECASE)
    if not match:
        await update.message.reply_text("Invalid format. Please use `-@username` to target a user.", parse_mode='Markdown')
        return ConversationHandler.END

    target_username = match.group(1).lower()
    target_user_id = user_data_store.get(target_username)

    if not target_user_id:
        await update.message.reply_text(f"User `@{target_username}` not found.", parse_mode='Markdown')
        return ConversationHandler.END

    context.user_data['target_user_id'] = target_user_id
    context.user_data['target_username'] = target_username
    context.user_data['sender_role'] = 'tara_team'
    await update.message.reply_text(f"Write your message for user `@{target_username}`.", parse_mode='Markdown')
    return SPECIFIC_USER_MESSAGE

async def specific_user_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    target_user_id = context.user_data.get('target_user_id')

    if not target_user_id:
        await message.reply_text("An error occurred. Please try again.")
        return ConversationHandler.END

    context.user_data['target_ids'] = [target_user_id]
    context.user_data['target_roles'] = ['specific_user']
    sender_role = context.user_data.get('sender_role', 'tara_team')

    await send_confirmation(message, context, sender_role, [target_user_id], target_roles=['specific_user'])
    return CONFIRMATION

async def specific_team_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    roles = get_user_roles(user_id)

    if 'tara_team' not in roles:
        await update.message.reply_text("You are not authorized to use this command.")
        return ConversationHandler.END

    message_text = update.message.text.strip().lower()
    target_roles = TRIGGER_TARGET_MAP.get(message_text)
    if not target_roles:
        await update.message.reply_text("Invalid trigger. Please try again.")
        return ConversationHandler.END

    context.user_data['specific_target_roles'] = target_roles
    context.user_data['sender_role'] = 'tara_team'
    await update.message.reply_text("Write your message for your team.")
    return SPECIFIC_TEAM_MESSAGE

async def specific_team_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    target_roles = context.user_data.get('specific_target_roles', [])
    target_ids = set()

    for target_role in target_roles:
        target_ids.update(ROLE_MAP.get(target_role, []))

    target_ids.discard(update.message.from_user.id)
    if not target_ids:
        await message.reply_text("No recipients found to send your message.")
        return ConversationHandler.END

    sender_role = context.user_data.get('sender_role', 'tara_team')
    await send_confirmation(message, context, sender_role, list(target_ids), target_roles=target_roles)
    return CONFIRMATION

async def team_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    roles = get_user_roles(user_id)

    if not roles:
        await update.message.reply_text("You don't have a role assigned to use this bot.")
        return ConversationHandler.END

    if len(roles) > 1:
        keyboard = get_role_selection_keyboard(roles)
        await update.message.reply_text(
            "You have multiple roles. Please choose which role you want to use to send this message:",
            reply_markup=keyboard
        )
        context.user_data['pending_message'] = update.message
        return SELECT_ROLE
    else:
        selected_role = roles[0]
        context.user_data['sender_role'] = selected_role
        await update.message.reply_text("Write your message for your role and Tara Team.")
        return TEAM_MESSAGE

async def team_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_id = message.from_user.id
    selected_role = context.user_data.get('sender_role')

    if not selected_role:
        await message.reply_text("An error occurred. Please try again.")
        return ConversationHandler.END

    target_roles = [selected_role, 'tara_team']
    target_ids = set()
    for role in target_roles:
        target_ids.update(ROLE_MAP.get(role, []))

    target_ids.discard(user_id)
    if not target_ids:
        await message.reply_text("No recipients found to send your message.")
        return ConversationHandler.END

    await send_confirmation(message, context, selected_role, list(target_ids), target_roles=target_roles)
    return CONFIRMATION

async def select_role_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith('role:'):
        selected_role = data.split(':')[1]
        context.user_data['sender_role'] = selected_role

        pending_message = context.user_data.get('pending_message')
        if not pending_message:
            await query.edit_message_text("An error occurred. Please try again.")
            return ConversationHandler.END

        del context.user_data['pending_message']
        command_text = pending_message.text.strip().lower() if pending_message.text else ""
        if command_text == '-team':
            target_roles = [selected_role, 'tara_team']
        else:
            target_roles = SENDING_ROLE_TARGETS.get(selected_role, [])

        target_ids = set()
        for role in target_roles:
            target_ids.update(ROLE_MAP.get(role, []))
        target_ids.discard(query.from_user.id)

        if not target_ids:
            await query.edit_message_text("No recipients found to send your message.")
            return ConversationHandler.END

        await send_confirmation(pending_message, context, selected_role, list(target_ids), target_roles=target_roles)
        await query.edit_message_text("Processing your message...")
        return CONFIRMATION

    elif data == 'cancel_role_selection':
        await query.edit_message_text("Operation cancelled.")
        return ConversationHandler.END
    else:
        await query.edit_message_text("Invalid role selection.")
        return ConversationHandler.END

async def tara_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    roles = get_user_roles(user_id)

    if not roles:
        await update.message.reply_text("You don't have a role assigned to use this bot.")
        return ConversationHandler.END

    context.user_data['sender_role'] = roles[0]
    await update.message.reply_text("Write your message for the Tara Team.")
    return TARA_MESSAGE

async def tara_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_id = message.from_user.id
    sender_role = context.user_data.get('sender_role')

    if not sender_role:
        await message.reply_text("You don't have a role assigned to use this bot.")
        return ConversationHandler.END

    target_roles = ['tara_team']
    target_ids = set(ROLE_MAP.get('tara_team', []))
    target_ids.discard(user_id)

    if not target_ids:
        await message.reply_text("No recipients found to send your message.")
        return ConversationHandler.END

    await send_confirmation(message, context, sender_role, list(target_ids), target_roles=target_roles)
    return CONFIRMATION

async def handle_general_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return ConversationHandler.END

    user_id = message.from_user.id
    if user_id in muted_users:
        await message.reply_text("You have been muted and cannot send messages through this bot.")
        return ConversationHandler.END

    username = message.from_user.username
    if username:
        username_lower = username.lower()
        previous_id = user_data_store.get(username_lower)
        if previous_id != user_id:
            user_data_store[username_lower] = user_id
            save_user_data()

    roles = get_user_roles(user_id)
    if not roles:
        await message.reply_text("You don't have a role assigned to use this bot.")
        return ConversationHandler.END

    if len(roles) > 1:
        keyboard = get_role_selection_keyboard(roles)
        await message.reply_text(
            "You have multiple roles. Please choose which role you want to use to send this message:",
            reply_markup=keyboard
        )
        context.user_data['pending_message'] = message
        return SELECT_ROLE
    else:
        selected_role = roles[0]
        context.user_data['sender_role'] = selected_role
        target_roles = SENDING_ROLE_TARGETS.get(selected_role, [])
        target_ids = set()

        for role in target_roles:
            target_ids.update(ROLE_MAP.get(role, []))
        target_ids.discard(user_id)

        if not target_ids:
            await message.reply_text("No recipients found to send your message.")
            return ConversationHandler.END

        await send_confirmation(message, context, selected_role, list(target_ids), target_roles=target_roles)
        return CONFIRMATION

# ------------------ Hidden Role Commands ------------------
async def hide_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    roles = get_user_roles(user_id)

    if 'hidden' not in roles:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    # Build the "roles_formatted" string by escaping underscores separately
    escaped_roles = []
    for r in ROLE_MAP.keys():
        role_escaped = r.replace('_', '\\_')
        escaped_roles.append(f'`{role_escaped}`')
    roles_formatted = ', '.join(escaped_roles)

    hide_help_text = (
        "🔒 *Hidden Admin Commands:*\n\n"
        "/addrole <user_id> <role_name>\n"
        "   - Add a user to the specified role.\n\n"
        "/removerole <user_id> <role_name>\n"
        "   - Remove a user from the specified role.\n\n"
        "🪄 Example:\n"
        "`/addrole 123456789 writer`\n\n"
        "*Available Roles:* "
        f"{roles_formatted}"
    )

    await update.message.reply_text(hide_help_text, parse_mode='Markdown')

async def add_role_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    roles = get_user_roles(user_id)

    if 'hidden' not in roles:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addrole <user_id> <role_name>")
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Please provide a valid user ID.")
        return

    role_name = context.args[1].lower().strip()
    if role_name not in ROLE_MAP:
        await update.message.reply_text("Invalid role name. Use /hide to see all available roles.")
        return

    if target_user_id not in ROLE_MAP[role_name]:
        ROLE_MAP[role_name].append(target_user_id)
        await update.message.reply_text(f"User ID {target_user_id} added to role '{role_name}'.")
    else:
        await update.message.reply_text(f"User ID {target_user_id} is already in role '{role_name}'.")

async def remove_role_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    roles = get_user_roles(user_id)

    if 'hidden' not in roles:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /removerole <user_id> <role_name>")
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Please provide a valid user ID.")
        return

    role_name = context.args[1].lower().strip()
    if role_name not in ROLE_MAP:
        await update.message.reply_text("Invalid role name. Use /hide to see all available roles.")
        return

    if target_user_id in ROLE_MAP[role_name]:
        ROLE_MAP[role_name].remove(target_user_id)
        await update.message.reply_text(f"User ID {target_user_id} removed from role '{role_name}'.")
    else:
        await update.message.reply_text(f"User ID {target_user_id} is not in role '{role_name}'.")

# ------------------ Conversation Handlers ------------------
specific_user_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(
        filters.Regex(re.compile(r'^\s*-\@([A-Za-z0-9_]{5,32})\s*$', re.IGNORECASE)),
        specific_user_trigger
    )],
    states={
        SPECIFIC_USER_MESSAGE: [
            MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, specific_user_message_handler)
        ],
        CONFIRMATION: [
            CallbackQueryHandler(confirmation_handler, pattern='^(confirm:|cancel:).*')
        ],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    per_message=True
)

specific_team_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(
        filters.Regex(re.compile(r'^-(w|e|mcq|d|de|mf|c)$', re.IGNORECASE)),
        specific_team_trigger
    )],
    states={
        SPECIFIC_TEAM_MESSAGE: [
            MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, specific_team_message_handler)
        ],
        CONFIRMATION: [
            CallbackQueryHandler(confirmation_handler, pattern='^(confirm:|cancel:).*')
        ],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    per_message=True
)

team_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(
        filters.Regex(re.compile(r'^-team$', re.IGNORECASE)),
        team_trigger
    )],
    states={
        TEAM_MESSAGE: [
            MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, team_message_handler)
        ],
        SELECT_ROLE: [
            CallbackQueryHandler(select_role_handler, pattern='^role:.*$|^cancel_role_selection$')
        ],
        CONFIRMATION: [
            CallbackQueryHandler(confirmation_handler, pattern='^(confirm:|cancel:).*')
        ],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    per_message=True
)

tara_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(
        filters.Regex(re.compile(r'^-t$', re.IGNORECASE)),
        tara_trigger
    )],
    states={
        TARA_MESSAGE: [
            MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, tara_message_handler)
        ],
        CONFIRMATION: [
            CallbackQueryHandler(confirmation_handler, pattern='^(confirm:|cancel:).*')
        ],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    per_message=True
)

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
            CallbackQueryHandler(select_role_handler, pattern='^role:.*$|^cancel_role_selection$')
        ],
        CONFIRMATION: [
            CallbackQueryHandler(confirmation_handler, pattern='^(confirm:|cancel:).*')
        ],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    per_message=True,
    allow_reentry=True
)

# ------------------ Start Command Definition ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user.username:
        await update.message.reply_text(
            "Please set a Telegram username in your profile to use specific commands like `-@username`.",
            parse_mode='Markdown'
        )
        return

    username_lower = user.username.lower()
    user_data_store[username_lower] = user.id
    save_user_data()

    display_name = get_display_name(user)
    await update.message.reply_text(
        f"Hello, {display_name}! Welcome to the Team Communication Bot.\n\n"
        "Feel free to send messages using the available commands."
    )

# ------------------ Other Command Handlers ------------------
async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    roles = get_user_roles(user_id)

    if 'tara_team' not in roles and 'hidden' not in roles:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    if not user_data_store:
        await update.message.reply_text("No users have interacted with the bot yet.")
        return

    user_list = "\n".join([f"@{username}: {uid}" for username, uid in user_data_store.items()])
    await update.message.reply_text(f"**Registered Users:**\n{user_list}", parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📘 *Available Commands:*\n\n"
        "/start - Initialize interaction with the bot.\n"
        "/listusers - List all registered users (Tara Team / Hidden Admin only).\n"
        "/help - Show this help message.\n"
        "/refresh - Refresh your user information.\n"
        "/cancel - Cancel the current operation.\n\n"
        "*Message Sending Triggers:*\n"
        "`-team` - Send a message to your own role and Tara Team.\n"
        "`-t` - Send a message exclusively to the Tara Team.\n\n"
        "*Tara Team Commands:*\n"
        "`-@username` - Send a message to a specific user.\n"
        "`-w` - Send a message to the Writer Team.\n"
        "`-e` or `-c` - Send a message to the Editor Team.\n"
        "`-mcq` - Send a message to the MCQs Team.\n"
        "`-d` - Send a message to the Digital Writers.\n"
        "`-de` - Send a message to the Design Team.\n"
        "`-mf` - Send a message to the Mind Map & Form Creation Team.\n\n"
        "*Admin Commands (Tara Team / Hidden Admin):*\n"
        "/mute [user_id] - Mute yourself or another user.\n"
        "/muteid <user_id> - Mute a specific user by their ID.\n"
        "/unmuteid <user_id> - Unmute a specific user by their ID.\n"
        "/listmuted - List all currently muted users.\n\n"
        "*Hidden Admin Commands:*\n"
        "/hide - Show hidden admin usage.\n"
        "/addrole <user_id> <role_name>\n"
        "/removerole <user_id> <role_name>\n\n"
        "📌 *Notes:*\n"
        "- Only authorized roles can use side commands.\n"
        "- Use `/cancel` to cancel any ongoing operation."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user.username:
        await update.message.reply_text(
            "Please set a Telegram username in your profile to refresh your information.",
            parse_mode='Markdown'
        )
        return

    username_lower = user.username.lower()
    user_data_store[username_lower] = user.id
    save_user_data()

    await update.message.reply_text("Your information has been refreshed successfully.")

async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    roles = get_user_roles(user_id)

    if 'tara_team' not in roles and 'hidden' not in roles:
        await update.message.reply_text("You are not authorized to use this command.")
        return

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
        return

    muted_users.add(target_user_id)
    save_muted_users()

    if target_user_id == user_id:
        await update.message.reply_text("You have been muted and can no longer send messages through this bot.")
    else:
        target_username = None
        for uname, uid in user_data_store.items():
            if uid == target_user_id:
                target_username = uname
                break
        if target_username:
            await update.message.reply_text(f"User `@{target_username}` has been muted.", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"User ID {target_user_id} has been muted.")

async def mute_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await mute_command(update, context)

async def unmute_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    roles = get_user_roles(user_id)

    if 'tara_team' not in roles and 'hidden' not in roles:
        await update.message.reply_text("You are not authorized to use this command.")
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
        target_username = None
        for uname, uid in user_data_store.items():
            if uid == target_user_id:
                target_username = uname
                break
        if target_username:
            await update.message.reply_text(f"User `@{target_username}` has been unmuted.", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"User ID {target_user_id} has been unmuted.")
    else:
        await update.message.reply_text(f"User ID {target_user_id} is not muted.")

async def list_muted_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    roles = get_user_roles(user_id)

    if 'tara_team' not in roles and 'hidden' not in roles:
        await update.message.reply_text("You are not authorized to use this command.")
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

# ------------------ Error Handler ------------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception while handling an update: {context.error}", exc_info=True)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text("An error occurred. Please try again later.")

# ------------------ Main ------------------
def main():
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        logger.warning("BOT_TOKEN is not set in environment variables. Attempting to run anyway...")

    application = ApplicationBuilder().token(BOT_TOKEN if BOT_TOKEN else "").build()

    # Commands
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('listusers', list_users))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('refresh', refresh))
    application.add_handler(CommandHandler('mute', mute_command))
    application.add_handler(CommandHandler('muteid', mute_id_command))
    application.add_handler(CommandHandler('unmuteid', unmute_id_command))
    application.add_handler(CommandHandler('listmuted', list_muted_command))

    # Hidden role commands
    application.add_handler(CommandHandler('hide', hide_command))
    application.add_handler(CommandHandler('addrole', add_role_command))
    application.add_handler(CommandHandler('removerole', remove_role_command))

    # Conversation handlers
    application.add_handler(specific_user_conv_handler)
    application.add_handler(specific_team_conv_handler)
    application.add_handler(team_conv_handler)
    application.add_handler(tara_conv_handler)
    application.add_handler(general_conv_handler)

    application.add_error_handler(error_handler)

    logger.info("Bot started polling...")
    application.run_polling()

if __name__ == '__main__':
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    main()
