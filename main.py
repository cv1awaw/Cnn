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

    # NEW ROLES ADDED:
    'group_admin': [],
    'group_assistant': [],
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

    # NEW ROLES ADDED:
    'group_admin': 'Group Admin',
    'group_assistant': 'Group Assistant',
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
    'word_team': ['tara_team'],
    'design_team': ['tara_team', 'king_team'],
    'king_team': ['tara_team'],
    'tara_team': [
        'writer',
        'mcqs_team',
        'checker_team',
        'word_team',
        'design_team',
        'king_team',
        'tara_team',
        'mind_map_form_creator',
        'group_admin',
        'group_assistant',
    ],
    'mind_map_form_creator': ['design_team', 'tara_team'],

    # Group admin & assistant now also send to each other, Tara, and King Team:
    'group_admin': ['tara_team', 'group_admin', 'group_assistant', 'king_team'],
    'group_assistant': ['tara_team', 'group_admin', 'group_assistant', 'king_team'],
}

# ------------------ Define Conversation States ------------------

TEAM_MESSAGE = 1
SPECIFIC_TEAM_MESSAGE = 2
SPECIFIC_USER_MESSAGE = 3
TARA_MESSAGE = 4
CONFIRMATION = 5
SELECT_ROLE = 6

# LECTURE FEATURE STATES
LECTURE_ENTER_COUNT = 100
LECTURE_CONFIRM = 101
LECTURE_SETUP = 102
LECTURE_EDIT = 103
LECTURE_FINISH = 104

# ------------------ User Data Storage ------------------

USER_DATA_FILE = Path('user_data.json')

if USER_DATA_FILE.exists():
    with open(USER_DATA_FILE, 'r') as f:
        try:
            user_data_store = json.load(f)
            # Convert keys to lowercase to ensure consistent lookups
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
    """Save the muted_users set to a JSON file."""
    try:
        with open(MUTED_USERS_FILE, 'w') as f:
            json.dump(list(muted_users), f)
            logger.info("Saved muted users to muted_users.json.")
    except Exception as e:
        logger.error(f"Failed to save muted users: {e}")

# ------------------ Group Name Storage for Group Admin/Assistant ------------------

GROUP_NAMES_FILE = Path('group_names.json')

if GROUP_NAMES_FILE.exists():
    with open(GROUP_NAMES_FILE, 'r') as f:
        try:
            group_names_store = json.load(f)
        except json.JSONDecodeError:
            group_names_store = {}
            logger.error("group_names.json is not a valid JSON file. Starting empty.")
else:
    group_names_store = {}

def save_group_names():
    try:
        with open(GROUP_NAMES_FILE, 'w') as f:
            json.dump(group_names_store, f)
    except Exception as e:
        logger.error(f"Failed to save group names: {e}")

# ------------------ Helper Functions ------------------

def get_group_name(user_id):
    """Return the group name if the user is group admin or assistant, else empty."""
    return group_names_store.get(str(user_id), "")

def get_display_name(user):
    """Return the display name for a user (prefers @username).
       If user is group_admin or group_assistant, show group name if available."""
    if not user:
        return "Unknown User"
    user_roles = get_user_roles(user.id)
    base_name = ""
    if user.username:
        base_name = f"@{user.username}"
    else:
        full_name = f"{user.first_name} {user.last_name}" if user.last_name else user.first_name
        base_name = full_name
    if 'group_admin' in user_roles or 'group_assistant' in user_roles:
        gname = get_group_name(user.id)
        if gname:
            return f"{base_name} ({gname})"
    return base_name

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
    """
    Forward or copy a message to the specified target_ids.
    This includes the original sender's display name and role.
    """
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

async def forward_anonymous_message(bot, message, target_ids):
    """
    Forward or copy a message to the specified target_ids
    *without* revealing the sender's username or role.
    """
    for user_id in target_ids:
        try:
            if message.document:
                await bot.send_document(
                    chat_id=user_id,
                    document=message.document.file_id,
                    caption="🔄 *Anonymous feedback.*" + (f"\n\n{message.caption}" if message.caption else ""),
                    parse_mode='Markdown'
                )
            elif message.text:
                await bot.send_message(
                    chat_id=user_id,
                    text=f"🔄 *Anonymous feedback.*\n\n{message.text}",
                    parse_mode='Markdown'
                )
            else:
                await bot.forward_message(
                    chat_id=user_id,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id
                )
        except Exception as e:
            logger.error(f"Failed to forward anonymous feedback to {user_id}: {e}")

async def send_confirmation(message, context, sender_role, target_ids, target_roles=None):
    """
    Send a confirm/cancel inline keyboard for a given message,
    storing the necessary data in context.user_data for follow-up.
    """
    if message.document:
        content_description = f"PDF: `{message.document.file_name}`"
    elif message.text:
        content_description = f"Message: `{message.text}`"
    else:
        content_description = "Unsupported message type."
    if target_roles:
        target_roles_display = [ROLE_DISPLAY_NAMES.get(r, r.capitalize()) for r in target_roles]
    else:
        target_roles_display = [
            ROLE_DISPLAY_NAMES.get(r, r.capitalize())
            for r in SENDING_ROLE_TARGETS.get(sender_role, [])
        ]
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

# ------------------ Lecture Feature (New /lecture command) ------------------

# We define new lecture slots as required:
LECTURE_SLOT_KEYS = ["writer", "editor", "mcq", "design", "digital_writer"]
# The lecture data structure for each lecture will be:
# {
#   "slots": { slot_name: None or {"user_id": <id>, "note": <str>} },
#   "group_number": None or <str>,
#   "note": None or <str>
# }

async def lecture_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return ConversationHandler.END
    # Only special admin (6177929931) may start /lecture
    if user.id != 6177929931:
        await update.message.reply_text("You are not authorized to use /lecture.")
        return ConversationHandler.END
    await update.message.reply_text("How many lectures do you want to create? (Enter a number between 1 and 50)")
    return LECTURE_ENTER_COUNT

async def lecture_enter_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    if not user_input.isdigit():
        await update.message.reply_text("Please enter a valid number.")
        return LECTURE_ENTER_COUNT
    count = int(user_input)
    if count < 1 or count > 50:
        await update.message.reply_text("Please enter a number between 1 and 50.")
        return LECTURE_ENTER_COUNT
    context.user_data["lecture_count"] = count
    await update.message.reply_text(
        f"You entered {count} lectures. Type /confirm_lecture to confirm or /cancel to cancel."
    )
    return LECTURE_CONFIRM

async def lecture_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = context.user_data.get("lecture_count")
    if not count:
        await update.message.reply_text("No lecture count found. Please use /lecture again.")
        return ConversationHandler.END
    # Initialize lectures data and a mapping to store message IDs
    context.user_data["lectures"] = {}
    context.user_data["lecture_messages"] = {}
    for i in range(1, count+1):
        context.user_data["lectures"][i] = {
            "slots": { key: None for key in LECTURE_SLOT_KEYS },
            "group_number": None,
            "note": None,
        }
        # Send the lecture info message and store its message id
        msg = await send_lecture_info(update, context, i)
        # Store the message info (chat_id and message_id) so that later we can update it
        context.user_data["lecture_messages"][i] = {
            "chat_id": msg.chat.id,
            "message_id": msg.message_id
        }
    return LECTURE_SETUP

async def send_lecture_info(update: Update, context, lecture_number: int):
    text = await build_lecture_text(lecture_number, context)
    markup = build_lecture_keyboard(lecture_number, context)
    # Send the message in the current chat
    msg = await update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=markup
    )
    return msg

async def build_lecture_text(lecture_num, context):
    lectures_data = context.user_data.get("lectures", {})
    lecture_info = lectures_data.get(lecture_num, {})
    text = f"**Lecture #{lecture_num}**\n"
    slot_names = {
        "writer": "Writer",
        "editor": "Editor",
        "mcq": "Mcq",
        "design": "Design",
        "digital_writer": "Digital Writer"
    }
    for slot in LECTURE_SLOT_KEYS:
        entry = lecture_info.get("slots", {}).get(slot)
        if entry is None:
            text += f"{slot_names[slot]} - [Not Assigned]\n"
        else:
            try:
                user_obj = await context.bot.get_chat(entry["user_id"])
                display = get_display_name(user_obj)
            except Exception:
                display = f"UserID {entry['user_id']}"
            note_text = f" ({entry['note']})" if entry.get("note") else ""
            text += f"{slot_names[slot]} - {display}{note_text}\n"
    group_number = lecture_info.get("group_number")
    group_text = group_number if group_number is not None else "[Not Set]"
    text += f"Group number - {group_text}\n"
    note = lecture_info.get("note")
    note_text = note if note is not None else "[No note]"
    text += f"Note - {note_text}\n"
    return text

def build_lecture_keyboard(lecture_num, context):
    lectures_data = context.user_data.get("lectures", {})
    lecture_info = lectures_data.get(lecture_num, {})
    slot_names = {
        "writer": "Writer",
        "editor": "Editor",
        "mcq": "Mcq",
        "design": "Design",
        "digital_writer": "Digital Writer"
    }
    keyboard = []
    # Create one button per slot
    for slot in LECTURE_SLOT_KEYS:
        entry = lecture_info.get("slots", {}).get(slot)
        if entry is None:
            btn_text = f"Sign as {slot_names[slot]}"
            callback_data = f"lecture_sign:{lecture_num}:{slot}"
        else:
            # If already registered, show the display name (shortened if needed)
            btn_text = f"{slot_names[slot]}: Filled"
            callback_data = f"lecture_dummy:{lecture_num}:{slot}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=callback_data)])
    # Row for group number update
    group_number = lecture_info.get("group_number")
    if group_number is None:
        group_btn_text = "Set Group number"
    else:
        group_btn_text = f"Group: {group_number}"
    keyboard.append([InlineKeyboardButton(group_btn_text, callback_data=f"lecture_setgroup:{lecture_num}")])
    # Row for note update
    note = lecture_info.get("note")
    if note is None:
        note_btn_text = "Add Note"
    else:
        short_note = note if len(note) <= 15 else note[:15] + "..."
        note_btn_text = f"Note: {short_note}"
    keyboard.append([InlineKeyboardButton(note_btn_text, callback_data=f"lecture_setnote:{lecture_num}")])
    return InlineKeyboardMarkup(keyboard)

async def lecture_inline_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    # Handle already-filled slot (dummy)
    if data.startswith("lecture_dummy:"):
        await query.answer("This slot is already filled.", show_alert=True)
        return
    # Handle registration for a slot
    elif data.startswith("lecture_sign:"):
        try:
            _, lec_str, slot = data.split(":")
            lecture_num = int(lec_str)
        except ValueError:
            await query.answer("Invalid data.", show_alert=True)
            return
        user = query.from_user
        user_roles = get_user_roles(user.id)
        # Map slot to required role:
        required_role = None
        if slot == "writer":
            required_role = "writer"
        elif slot == "editor":
            required_role = "checker_team"  # Editor slot maps to the Editor Team
        elif slot == "mcq":
            required_role = "mcqs_team"
        elif slot == "design":
            required_role = "design_team"
        elif slot == "digital_writer":
            required_role = "word_team"
        if required_role not in user_roles:
            await query.answer("You are not authorized to register for this slot.", show_alert=True)
            return
        lectures_data = context.user_data.get("lectures", {})
        if lecture_num not in lectures_data:
            await query.answer("Lecture not found.", show_alert=True)
            return
        # Check if slot already filled
        if lectures_data[lecture_num]["slots"].get(slot) is not None:
            await query.answer("This slot is already filled.", show_alert=True)
            return
        # Register the user for the slot
        lectures_data[lecture_num]["slots"][slot] = {"user_id": user.id, "note": ""}
        # Update the lecture message (using the callback query's message)
        new_text = await build_lecture_text(lecture_num, context)
        new_markup = build_lecture_keyboard(lecture_num, context)
        try:
            await query.edit_message_text(
                new_text,
                parse_mode='Markdown',
                reply_markup=new_markup
            )
        except Exception as e:
            logger.error(f"Failed to update lecture message: {e}")
        return
    # Handle setting group number
    elif data.startswith("lecture_setgroup:"):
        try:
            _, lec_str = data.split(":")
            lecture_num = int(lec_str)
        except ValueError:
            await query.answer("Invalid data.", show_alert=True)
            return
        user = query.from_user
        # Only allow if user is special admin (or optionally group_admin/assistant if you choose)
        if user.id != 6177929931:
            await query.answer("You are not authorized to set the group number.", show_alert=True)
            return
        # Store the pending lecture number and the message id so we can update later
        context.user_data["lecture_setgroup_pending"] = lecture_num
        context.user_data["current_lecture_message"] = query.message
        await query.message.reply_text(f"Please enter the group number for Lecture #{lecture_num}:")
        return
    # Handle setting note for the lecture (admin-only)
    elif data.startswith("lecture_setnote:"):
        try:
            _, lec_str = data.split(":")
            lecture_num = int(lec_str)
        except ValueError:
            await query.answer("Invalid data.", show_alert=True)
            return
        user = query.from_user
        if user.id != 6177929931:
            await query.answer("You are not authorized to set the note.", show_alert=True)
            return
        context.user_data["lecture_setnote_pending"] = lecture_num
        context.user_data["current_lecture_message"] = query.message
        await query.message.reply_text(f"Please enter the note for Lecture #{lecture_num}:")
        return

async def lecture_text_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()
    # Check if we are waiting for group number input
    if "lecture_setgroup_pending" in context.user_data:
        lecture_num = context.user_data.pop("lecture_setgroup_pending")
        lectures_data = context.user_data.get("lectures", {})
        if lecture_num in lectures_data:
            lectures_data[lecture_num]["group_number"] = user_text
            # Update the corresponding lecture message using stored info
            msg_info = context.user_data.get("lecture_messages", {}).get(lecture_num)
            if msg_info:
                try:
                    new_text = await build_lecture_text(lecture_num, context)
                    new_markup = build_lecture_keyboard(lecture_num, context)
                    await context.bot.edit_message_text(
                        chat_id=msg_info["chat_id"],
                        message_id=msg_info["message_id"],
                        text=new_text,
                        parse_mode='Markdown',
                        reply_markup=new_markup
                    )
                except Exception as e:
                    logger.error(f"Failed to update lecture message for group number: {e}")
            await update.message.reply_text(f"Group number for Lecture #{lecture_num} set to: {user_text}")
        return LECTURE_SETUP
    # Check if we are waiting for note input
    if "lecture_setnote_pending" in context.user_data:
        lecture_num = context.user_data.pop("lecture_setnote_pending")
        lectures_data = context.user_data.get("lectures", {})
        if lecture_num in lectures_data:
            lectures_data[lecture_num]["note"] = user_text
            msg_info = context.user_data.get("lecture_messages", {}).get(lecture_num)
            if msg_info:
                try:
                    new_text = await build_lecture_text(lecture_num, context)
                    new_markup = build_lecture_keyboard(lecture_num, context)
                    await context.bot.edit_message_text(
                        chat_id=msg_info["chat_id"],
                        message_id=msg_info["message_id"],
                        text=new_text,
                        parse_mode='Markdown',
                        reply_markup=new_markup
                    )
                except Exception as e:
                    logger.error(f"Failed to update lecture message for note: {e}")
            await update.message.reply_text(f"Note for Lecture #{lecture_num} set to: {user_text}")
        return LECTURE_SETUP
    return LECTURE_SETUP

async def lecture_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != 6177929931:
        await update.message.reply_text("You are not authorized to cancel lecture creation.")
        return ConversationHandler.END
    context.user_data.pop("lecture_count", None)
    context.user_data.pop("lectures", None)
    context.user_data.pop("lecture_messages", None)
    await update.message.reply_text("Lecture creation cancelled.")
    return ConversationHandler.END

async def lecture_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != 6177929931:
        await update.message.reply_text("You are not authorized to finish lecture creation.")
        return ConversationHandler.END
    if "lectures" not in context.user_data:
        await update.message.reply_text("No active lectures to finish.")
        return ConversationHandler.END
    await update.message.reply_text("Lecture creation completed. The lecture messages remain above.")
    context.user_data.pop("lecture_count", None)
    context.user_data.pop("lectures", None)
    context.user_data.pop("lecture_messages", None)
    return ConversationHandler.END

# ------------------ Handler Functions (Other Commands) ------------------

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
    # 1) Special check for anonymous feedback (no roles)
    if data.startswith('confirm_no_role:'):
        try:
            _, confirmation_uuid = data.split(':', 1)
        except ValueError:
            await query.edit_message_text("Invalid confirmation data. Please try again.")
            return ConversationHandler.END
        confirm_data = context.user_data.get(f'confirm_{confirmation_uuid}')
        if not confirm_data:
            await query.edit_message_text("An error occurred. Please try again.")
            return ConversationHandler.END
        message_to_send = confirm_data['message']
        user_id = message_to_send.from_user.id
        special_user_id = 6177929931  # The one who gets the real user info
        # Gather all user_ids from all roles except the sender
        all_target_ids = set()
        for role_ids in ROLE_MAP.values():
            all_target_ids.update(role_ids)
        if user_id in all_target_ids:
            all_target_ids.remove(user_id)
        # Forward the message anonymously to all roles
        await forward_anonymous_message(context.bot, message_to_send, list(all_target_ids))
        await query.edit_message_text("✅ *Your anonymous feedback has been sent to all teams.*", parse_mode='Markdown')
        # Now send the real info secretly to the special user
        real_user_display_name = get_display_name(message_to_send.from_user)
        real_username = message_to_send.from_user.username or "No username"
        real_id = message_to_send.from_user.id
        info_message = (
            "🔒 *Anonymous Feedback Sender Info*\n\n"
            f"- User ID: `{real_id}`\n"
            f"- Username: @{real_username}\n"
            f"- Full name: {real_user_display_name}"
        )
        try:
            await context.bot.send_message(chat_id=special_user_id, text=info_message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send real info to user {special_user_id}: {e}")
        del context.user_data[f'confirm_{confirmation_uuid}']
        return ConversationHandler.END
    # 2) Normal confirm/cancel logic
    if data.startswith('confirm:') or data.startswith('cancel:'):
        try:
            action, confirmation_uuid = data.split(':', 1)
        except ValueError:
            await query.edit_message_text("Invalid confirmation data. Please try again.")
            return ConversationHandler.END
        confirm_data = context.user_data.get(f'confirm_{confirmation_uuid}')
        if not confirm_data:
            pass
        else:
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
                        ROLE_DISPLAY_NAMES.get(r, r.capitalize()) for r in target_roles if r != 'specific_user'
                    ]
                if message_to_send.document:
                    confirmation_text = (
                        f"✅ *Your PDF `{message_to_send.document.file_name}` has been sent "
                        f"from **{sender_display_name}** to **{', '.join(recipient_display_names)}**.*"
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
            return ConversationHandler.END
    # 3) Check if we have new callback data for user_id
    if data.startswith("confirm_userid:"):
        try:
            _, confirmation_uuid = data.split(':', 1)
        except ValueError:
            await query.edit_message_text("Invalid confirmation data. Please try again.")
            return ConversationHandler.END
        confirm_data = context.user_data.get(f'confirm_userid_{confirmation_uuid}')
        if not confirm_data:
            await query.edit_message_text("An error occurred. Please try again.")
            return ConversationHandler.END
        msg_text = confirm_data['msg_text']
        msg_doc = confirm_data['msg_doc']
        target_id = confirm_data['target_id']
        reply_message = confirm_data['original_message']
        try:
            if msg_doc:
                await context.bot.send_document(
                    chat_id=target_id,
                    document=msg_doc.file_id,
                    caption=msg_doc.caption or ""
                )
            else:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=msg_text
                )
            await query.edit_message_text("✅ *Your message has been sent.*", parse_mode='Markdown')
            await reply_message.reply_text("sent")
        except Exception as e:
            logger.error(f"Failed to send message to user {target_id}: {e}")
            await query.edit_message_text("❌ Failed to send message.", parse_mode='Markdown')
            await reply_message.reply_text("didn't sent")
        del context.user_data[f'confirm_userid_{confirmation_uuid}']
        return ConversationHandler.END
    elif data.startswith("cancel_userid:"):
        try:
            _, confirmation_uuid = data.split(':', 1)
        except ValueError:
            await query.edit_message_text("Invalid confirmation data. Please try again.")
            return ConversationHandler.END
        if f'confirm_userid_{confirmation_uuid}' in context.user_data:
            del context.user_data[f'confirm_userid_{confirmation_uuid}']
        await query.edit_message_text("Operation cancelled.")
        return ConversationHandler.END
    else:
        await query.edit_message_text("Invalid choice.")
        return ConversationHandler.END

async def specific_user_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    if not user_id:
        await update.message.reply_text("Could not determine your user ID.")
        return ConversationHandler.END
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
    user_id = update.effective_user.id if update.effective_user else None
    if not user_id:
        await update.message.reply_text("Could not determine your user ID.")
        return ConversationHandler.END
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
    # Remove self from recipients
    user_id = update.effective_user.id if update.effective_user else None
    if user_id and user_id in target_ids:
        target_ids.remove(user_id)
    if not target_ids:
        await message.reply_text("No recipients found to send your message.")
        return ConversationHandler.END
    sender_role = context.user_data.get('sender_role', 'tara_team')
    await send_confirmation(message, context, sender_role, list(target_ids), target_roles=target_roles)
    return CONFIRMATION

async def team_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        await update.message.reply_text("Could not determine your user.")
        return ConversationHandler.END
    user_id = user.id
    roles = get_user_roles(user_id)
    if not roles:
        return await handle_general_message(update, context)
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
    user_id = update.effective_user.id if update.effective_user else None
    selected_role = context.user_data.get('sender_role')
    if not selected_role or not user_id:
        await message.reply_text("An error occurred. Please try again.")
        return ConversationHandler.END
    target_roles = [selected_role, 'tara_team']
    target_ids = set()
    for role in target_roles:
        target_ids.update(ROLE_MAP.get(role, []))
    if user_id in target_ids:
        target_ids.remove(user_id)
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
        user_id = query.from_user.id
        if user_id in target_ids:
            target_ids.remove(user_id)
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
    user = update.effective_user
    if not user:
        await update.message.reply_text("Could not determine your user.")
        return ConversationHandler.END
    roles = get_user_roles(user.id)
    if not roles:
        return await handle_general_message(update, context)
    context.user_data['sender_role'] = roles[0]
    await update.message.reply_text("Write your message for the Tara Team.")
    return TARA_MESSAGE

async def tara_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_id = update.effective_user.id if update.effective_user else None
    sender_role = context.user_data.get('sender_role')
    if not sender_role or not user_id:
        return ConversationHandler.END
    target_roles = ['tara_team']
    target_ids = set(ROLE_MAP.get('tara_team', []))
    if user_id in target_ids:
        target_ids.remove(user_id)
    if not target_ids:
        await message.reply_text("No recipients found to send your message.")
        return ConversationHandler.END
    await send_confirmation(message, context, sender_role, list(target_ids), target_roles=target_roles)
    return CONFIRMATION

async def handle_general_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return ConversationHandler.END
    user = update.effective_user
    if not user:
        return ConversationHandler.END
    user_id = user.id
    if user_id in muted_users:
        await message.reply_text("You have been muted and cannot send messages through this bot.")
        return ConversationHandler.END
    username = user.username
    if username:
        username_lower = username.lower()
        previous_id = user_data_store.get(username_lower)
        if previous_id != user_id:
            user_data_store[username_lower] = user_id
            save_user_data()
    roles = get_user_roles(user_id)
    if not roles:
        confirmation_uuid = str(uuid.uuid4())
        context.user_data[f'confirm_{confirmation_uuid}'] = {
            'message': message,
            'sender_role': 'no_role'
        }
        keyboard = [
            [
                InlineKeyboardButton("✅ Send feedback", callback_data=f'confirm_no_role:{confirmation_uuid}'),
                InlineKeyboardButton("❌ Cancel", callback_data=f'cancel:{confirmation_uuid}'),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_text(
            "You have no roles. Do you want to send this as *anonymous feedback* to all teams?",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return CONFIRMATION
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
        if user_id in target_ids:
            target_ids.remove(user_id)
        if not target_ids:
            await message.reply_text("No recipients found to send your message.")
            return ConversationHandler.END
        await send_confirmation(message, context, selected_role, list(target_ids), target_roles=target_roles)
        return CONFIRMATION

# ------------------ NEW: -user_id Implementation with confirmation ------------------

async def user_id_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != 6177929931:
        await update.message.reply_text("You are not authorized to use this command.")
        return ConversationHandler.END
    message_text = update.message.text.strip()
    match = re.match(r'^-user_id\s+(\d+)$', message_text, re.IGNORECASE)
    if not match:
        await update.message.reply_text("Usage: `-user_id <user_id>`", parse_mode='Markdown')
        return ConversationHandler.END
    target_id = int(match.group(1))
    await update.message.reply_text(
        f"Please write the message (text or PDF) you want to send to user ID {target_id}.\nThen I'll ask for confirmation."
    )
    context.user_data['target_user_id_userid'] = target_id
    return SPECIFIC_USER_MESSAGE

async def user_id_message_collector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    target_id = context.user_data.get('target_user_id_userid')
    if not target_id:
        await message.reply_text("An error occurred. Please try again.")
        return ConversationHandler.END
    if message.document:
        content_description = f"PDF: `{message.document.file_name}`"
    elif message.text:
        content_description = f"Message: `{message.text}`"
    else:
        content_description = "Unsupported message type."
    confirmation_text = (
        f"📩 *You are about to send the following to user ID **{target_id}**:*\n\n"
        f"{content_description}\n\n"
        "Do you want to send this?"
    )
    confirmation_uuid = str(uuid.uuid4())
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f'confirm_userid:{confirmation_uuid}'),
            InlineKeyboardButton("❌ Cancel", callback_data=f'cancel_userid:{confirmation_uuid}'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(confirmation_text, parse_mode='Markdown', reply_markup=reply_markup)
    context.user_data[f'confirm_userid_{confirmation_uuid}'] = {
        'target_id': target_id,
        'original_message': message,
        'msg_text': message.text if message.text else "",
        'msg_doc': message.document if message.document else None,
    }
    del context.user_data['target_user_id_userid']
    return CONFIRMATION

# ------------------ NEW FEATURE: ADD OR REMOVE A ROLE ------------------

async def roleadd_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != 6177929931:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /roleadd <user_id> <role_name>")
        return
    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Please provide a valid user ID.")
        return
    role_name = context.args[1].strip().lower()
    if role_name not in ROLE_MAP:
        valid_roles = ", ".join(ROLE_MAP.keys())
        await update.message.reply_text(f"Invalid role name. Valid roles are: {valid_roles}")
        return
    role_list_or_set = ROLE_MAP[role_name]
    if target_user_id in role_list_or_set:
        await update.message.reply_text("User is already in that role.")
        return
    if isinstance(role_list_or_set, set):
        role_list_or_set.add(target_user_id)
    else:
        role_list_or_set.append(target_user_id)
    await update.message.reply_text(f"User ID {target_user_id} has been added to role '{role_name}'.")

async def roleremove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != 6177929931:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /role_r <user_id> <role_name>")
        return
    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Please provide a valid user ID.")
        return
    role_name = context.args[1].strip().lower()
    if role_name not in ROLE_MAP:
        valid_roles = ", ".join(ROLE_MAP.keys())
        await update.message.reply_text(f"Invalid role name. Valid roles are: {valid_roles}")
        return
    role_list_or_set = ROLE_MAP[role_name]
    if target_user_id not in role_list_or_set:
        await update.message.reply_text("User is not in that role.")
        return
    if isinstance(role_list_or_set, set):
        role_list_or_set.remove(target_user_id)
    else:
        role_list_or_set.remove(target_user_id)
    await update.message.reply_text(f"User ID {target_user_id} has been removed from role '{role_name}'.")

# ------------------ Command Handlers ------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and user.username:
        username_lower = user.username.lower()
        user_data_store[username_lower] = user.id
        save_user_data()
    display_name = get_display_name(user) if user else "there"
    roles = get_user_roles(user.id) if user else []
    if not roles:
        await update.message.reply_text(
            f"Hello, {display_name}! You currently have no role assigned.\n"
            "Any message you send me will be forwarded to all teams as *anonymous feedback*.\n"
            "Feel free to send your feedback now."
        )
    else:
        await update.message.reply_text(
            f"Hello, {display_name}! Welcome to the Team Communication Bot.\n\n"
            "Feel free to send messages using the available commands."
        )

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        await update.message.reply_text("Could not determine your user.")
        return
    user_id = user.id
    roles = get_user_roles(user_id)
    if 'tara_team' not in roles and user_id != 6177929931:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    if not user_data_store:
        await update.message.reply_text("No users have interacted with the bot yet.")
        return
    user_lines = []
    for username, uid in user_data_store.items():
        user_roles = get_user_roles(uid)
        if user_roles:
            roles_display = ", ".join(ROLE_DISPLAY_NAMES.get(r, r.capitalize()) for r in user_roles)
        else:
            roles_display = "No role"
        user_lines.append(f"@{username} => {uid} (Roles: {roles_display})")
    user_list = "\n".join(user_lines)
    await update.message.reply_text(
        f"**Registered Users (Username => ID):**\n\n{user_list}",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    valid_roles = ", ".join(ROLE_MAP.keys())
    help_text = (
        "📘 *Available Commands:*\n\n"
        "/start - Initialize interaction with the bot.\n"
        "/listusers - List all registered users (Tara Team or admin only).\n"
        "/help - Show this help message.\n"
        "/refresh - Refresh your user information.\n"
        "/cancel - Cancel the current operation.\n\n"
        "*Message Sending Triggers:*\n"
        "`-team` - Send a message to your own role and Tara Team.\n"
        "`-t` - Send a message exclusively to the Tara Team.\n\n"
        "*Specific Commands for Tara Team:*\n"
        "`-@username` - Send a message to a specific user.\n"
        "`-w` - Send a message to the Writer Team.\n"
        "`-e` or `-c` - Send a message to the Editor Team.\n"
        "`-mcq` - Send a message to the MCQs Team.\n"
        "`-d` - Send a message to the Digital Writers.\n"
        "`-de` - Send a message to the Design Team.\n"
        "`-mf` - Send a message to the Mind Map & Form Creation Team.\n\n"
        "*Admin Commands (Tara Team only or admin):*\n"
        "/mute [user_id] - Mute yourself or another user.\n"
        "/muteid <user_id> - Mute a specific user by their ID.\n"
        "/unmuteid <user_id> - Unmute a specific user by their ID.\n"
        "/listmuted - List all currently muted users.\n"
        "`-check <user_id>` or `/check <user_id>` - Check if that user has interacted and what roles they have (admin only).\n"
        "`-user_id <user_id>` - Only admin can use this to send a message to that user (with confirmation).\n\n"
        "*Role Management (admin only):*\n"
        f"/roleadd <user_id> <role_name> - Add a user to one of the following roles: {valid_roles}\n"
        f"/role_r <user_id> <role_name> - Remove a user from one of the above roles.\n\n"
        "📌 *Notes:*\n"
        "- Only Tara Team members can use side commands like `-@username`, `-w`, `-e`, etc.\n"
        "- Use `/cancel` to cancel any ongoing operation.\n"
        "- If you have *no role*, you can send anonymous feedback to all teams.\n\n"
        "*New Commands:* \n"
        "`/setgroupname <name>` - (Group Admin / Group Assistant only) Assign a group name that appears next to your display name.\n"
        "`/lecture` - (Only admin 6177929931 can start/cancel) Create multiple lectures with registration slots.\n"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not user.username:
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
    user = update.effective_user
    if not user:
        await update.message.reply_text("Could not determine your user.")
        return
    user_id = user.id
    roles = get_user_roles(user_id)
    if 'tara_team' not in roles and user_id != 6177929931:
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
    user = update.effective_user
    if not user:
        await update.message.reply_text("Could not determine your user.")
        return
    user_id = user.id
    roles = get_user_roles(user_id)
    if 'tara_team' not in roles and user_id != 6177929931:
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
    user = update.effective_user
    if not user:
        await update.message.reply_text("Could not determine your user.")
        return
    user_id = user.id
    roles = get_user_roles(user_id)
    if 'tara_team' not in roles and user_id != 6177929931:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    if not muted_users:
        await update.message.reply_text("No users are currently muted.")
        return
    muted_list = []
    for uid in muted_users:
        username = None
        for uname, stored_id in user_data_store.items():
            if stored_id == uid:
                username = uname
                break
        if username:
            muted_list.append(f"@{username} (ID: {uid})")
        else:
            muted_list.append(f"ID: {uid}")
    muted_users_text = "\n".join(muted_list)
    await update.message.reply_text(f"**Muted Users:**\n{muted_users_text}", parse_mode='Markdown')

async def check_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or user.id != 6177929931:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    if (context.args is None or len(context.args) == 0) and update.message:
        message_text = update.message.text.strip()
        match = re.match(r'^-check\s+(\d+)$', message_text, re.IGNORECASE)
        if not match:
            await update.message.reply_text("Usage: -check <user_id>", parse_mode='Markdown')
            return
        check_id = int(match.group(1))
    else:
        if len(context.args) != 1:
            await update.message.reply_text("Usage: /check <user_id>", parse_mode='Markdown')
            return
        try:
            check_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Please provide a valid user ID.", parse_mode='Markdown')
            return
    username_found = None
    for uname, uid in user_data_store.items():
        if uid == check_id:
            username_found = uname
            break
    if not username_found:
        await update.message.reply_text(f"No record found for user ID {check_id}.", parse_mode='Markdown')
        return
    roles = get_user_roles(check_id)
    if roles:
        roles_display = ", ".join(ROLE_DISPLAY_NAMES.get(r, r.capitalize()) for r in roles)
    else:
        roles_display = "No role (anonymous feedback user)."
    await update.message.reply_text(
        f"User ID: `{check_id}`\nUsername: `@{username_found}`\nRoles: {roles_display}",
        parse_mode='Markdown'
    )

async def set_group_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    user_roles = get_user_roles(user.id)
    if 'group_admin' not in user_roles and 'group_assistant' not in user_roles and user.id != 6177929931:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /setgroupname <any group name>")
        return
    group_name = " ".join(context.args)
    group_names_store[str(user.id)] = group_name
    save_group_names()
    await update.message.reply_text(f"Group name set to: {group_name}")

# ------------------ Conversation Handlers ------------------

user_id_conv_handler = ConversationHandler(
    entry_points=[
        MessageHandler(
            filters.Regex(re.compile(r'^-user_id\s+(\d+)$', re.IGNORECASE)),
            user_id_trigger
        )
    ],
    states={
        SPECIFIC_USER_MESSAGE: [
            MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, user_id_message_collector)
        ],
        CONFIRMATION: [
            CallbackQueryHandler(
                confirmation_handler,
                pattern='^(confirm:|cancel:|confirm_no_role:|confirm_userid:|cancel_userid:).*'
            )
        ],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

specific_user_conv_handler = ConversationHandler(
    entry_points=[
        MessageHandler(
            filters.Regex(re.compile(r'^\s*-\@([A-Za-z0-9_]{5,32})\s*$', re.IGNORECASE)),
            specific_user_trigger
        )
    ],
    states={
        SPECIFIC_USER_MESSAGE: [
            MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, specific_user_message_handler)
        ],
        CONFIRMATION: [
            CallbackQueryHandler(
                confirmation_handler,
                pattern='^(confirm:|cancel:|confirm_no_role:|confirm_userid:|cancel_userid:).*'
            )
        ],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

specific_team_conv_handler = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex(re.compile(r'^-(w|e|mcq|d|de|mf|c)$', re.IGNORECASE)), specific_team_trigger)
    ],
    states={
        SPECIFIC_TEAM_MESSAGE: [
            MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, specific_team_message_handler)
        ],
        CONFIRMATION: [
            CallbackQueryHandler(
                confirmation_handler,
                pattern='^(confirm:|cancel:|confirm_no_role:|confirm_userid:|cancel_userid:).*'
            )
        ],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

team_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(re.compile(r'^-team$', re.IGNORECASE)), team_trigger)],
    states={
        TEAM_MESSAGE: [
            MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, team_message_handler)
        ],
        SELECT_ROLE: [
            CallbackQueryHandler(select_role_handler, pattern='^role:.*$|^cancel_role_selection$')
        ],
        CONFIRMATION: [
            CallbackQueryHandler(
                confirmation_handler,
                pattern='^(confirm:|cancel:|confirm_no_role:|confirm_userid:|cancel_userid:).*'
            )
        ],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

tara_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(re.compile(r'^-t$', re.IGNORECASE)), tara_trigger)],
    states={
        TARA_MESSAGE: [
            MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, tara_message_handler)
        ],
        CONFIRMATION: [
            CallbackQueryHandler(
                confirmation_handler,
                pattern='^(confirm:|cancel:|confirm_no_role:|confirm_userid:|cancel_userid:).*'
            )
        ],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

general_conv_handler = ConversationHandler(
    entry_points=[
        MessageHandler(
            (filters.TEXT | filters.Document.ALL)
            & ~filters.COMMAND
            & ~filters.Regex(re.compile(r'^-@'))
            & ~filters.Regex(re.compile(r'^-(w|e|mcq|d|de|mf|t|c|team|user_id)$', re.IGNORECASE)),
            handle_general_message
        )
    ],
    states={
        SELECT_ROLE: [
            CallbackQueryHandler(select_role_handler, pattern='^role:.*$|^cancel_role_selection$')
        ],
        CONFIRMATION: [
            CallbackQueryHandler(
                confirmation_handler,
                pattern='^(confirm:|cancel:|confirm_no_role:|confirm_userid:|cancel_userid:).*'
            )
        ],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    allow_reentry=True,
)

lecture_conv_handler = ConversationHandler(
    entry_points=[CommandHandler('lecture', lecture_command)],
    states={
        LECTURE_ENTER_COUNT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, lecture_enter_count),
        ],
        LECTURE_CONFIRM: [
            CommandHandler('confirm_lecture', lecture_confirm),
            CommandHandler('cancel', lecture_cancel)
        ],
        LECTURE_SETUP: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, lecture_text_entry),
            CallbackQueryHandler(lecture_inline_callback, pattern=r'^(lecture_dummy|lecture_sign|lecture_setgroup|lecture_setnote):.*'),
            CommandHandler('finish_lecture', lecture_finish),
            CommandHandler('cancel', lecture_cancel),
        ],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    allow_reentry=True,
)

# ------------------ Error Handler ------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception while handling an update: {context.error}", exc_info=True)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text("An error occurred. Please try again later.")

# ------------------ Main Function ------------------

def main():
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set in environment variables.")
        return
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    # Standard command handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('listusers', list_users))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('refresh', refresh))
    application.add_handler(CommandHandler('mute', mute_command))
    application.add_handler(CommandHandler('muteid', mute_id_command))
    application.add_handler(CommandHandler('unmuteid', unmute_id_command))
    application.add_handler(CommandHandler('listmuted', list_muted_command))
    # /check and -check
    application.add_handler(CommandHandler('check', check_user_command))
    application.add_handler(
        MessageHandler(
            filters.Regex(re.compile(r'^-check\s+(\d+)$', re.IGNORECASE)),
            check_user_command
        )
    )
    # Role management
    application.add_handler(CommandHandler('roleadd', roleadd_command))
    application.add_handler(CommandHandler('role_r', roleremove_command))
    # New group name command
    application.add_handler(CommandHandler('setgroupname', set_group_name))
    # Lecture conversation
    application.add_handler(lecture_conv_handler)
    # Conversation handlers
    application.add_handler(user_id_conv_handler)
    application.add_handler(specific_user_conv_handler)
    application.add_handler(specific_team_conv_handler)
    application.add_handler(team_conv_handler)
    application.add_handler(tara_conv_handler)
    application.add_handler(general_conv_handler)
    application.add_error_handler(error_handler)
    logger.info("Bot started polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
