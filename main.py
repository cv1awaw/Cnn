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
LECTURE_SUBJECT = 90
LECTURE_ENTER_COUNT = 100
LECTURE_CONFIRM = 101
LECTURE_SETUP = 102
LECTURE_EDIT = 103
LECTURE_FINISH = 104

# ------------------ Global Variables for Lecture Feature ------------------
# These globals are used so that lecture data is shared across all users.
LECTURE_STORE = {}         # { lecture_num: { "slots": {slot: [registrations]}, "group_number": ..., "note": ... } }
LECTURE_BROADCAST = {}     # { lecture_num: [ { "chat_id": ..., "message_id": ... }, ... ] }
GLOBAL_LECTURE_SUBJECT = None
GLOBAL_LECTURE_COUNT = 0

# ------------------ Global Variables for Lecture Test Feature ------------------
# These are used for testing purposes (allowed only for testers).
TEST_LECTURE_STORE = {}
TEST_LECTURE_BROADCAST = {}
TEST_GLOBAL_LECTURE_SUBJECT = None
TEST_GLOBAL_LECTURE_COUNT = 0

# Global set to store tester IDs. Use the /addtester command to add a tester.
TESTER_IDS = set()

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
    return group_names_store.get(str(user_id), "")

def get_display_name(user):
    if not user:
        return "Unknown User"
    user_roles = get_user_roles(user.id)
    base_name = f"@{user.username}" if user.username else (f"{user.first_name} {user.last_name}" if user.last_name else user.first_name)
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

# ------------------ Lecture Feature (Admin Only) ------------------
# These functions handle lecture creation and registration.
async def broadcast_lecture_info(lecture_num, context: ContextTypes.DEFAULT_TYPE):
    text = await build_lecture_text(lecture_num, context, test_mode=False)
    markup = build_lecture_keyboard(lecture_num, context, test_mode=False)
    broadcast_ids = set()
    for ids in ROLE_MAP.values():
        broadcast_ids.update(ids)
    broadcast_messages = []
    for uid in broadcast_ids:
        try:
            msg = await context.bot.send_message(
                chat_id=uid,
                text=text,
                parse_mode='Markdown',
                reply_markup=markup
            )
            broadcast_messages.append({"chat_id": msg.chat.id, "message_id": msg.message_id})
        except Exception as e:
            logger.error(f"Failed to send broadcast lecture message to {uid}: {e}")
    return broadcast_messages

async def update_broadcast(lecture_num, context: ContextTypes.DEFAULT_TYPE, test_mode=False):
    text = await build_lecture_text(lecture_num, context, test_mode=test_mode)
    markup = build_lecture_keyboard(lecture_num, context, test_mode=test_mode)
    store = TEST_LECTURE_BROADCAST if test_mode else LECTURE_BROADCAST
    broadcast_list = store.get(lecture_num, [])
    for msg_info in broadcast_list:
        try:
            await context.bot.edit_message_text(
                chat_id=msg_info["chat_id"],
                message_id=msg_info["message_id"],
                text=text,
                parse_mode='Markdown',
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Failed to update broadcast lecture message for lecture {lecture_num}: {e}")

async def build_lecture_text(lecture_num, context: ContextTypes.DEFAULT_TYPE, test_mode=False):
    store = TEST_LECTURE_STORE if test_mode else LECTURE_STORE
    subject = TEST_GLOBAL_LECTURE_SUBJECT if test_mode else GLOBAL_LECTURE_SUBJECT
    subject = subject if subject else "Subject"
    slot_titles = {
        "writer": "Writer",
        "editor": "Editor",
        "mcq": "Mcq",
        "design": "Design",
        "digital_writer": "Digital Writer"
    }
    lines = [f"Lecture #{lecture_num}", f"{subject}"]
    lecture_info = store.get(lecture_num, {})
    for slot in ["writer", "editor", "mcq", "design", "digital_writer"]:
        registrations = lecture_info.get("slots", {}).get(slot, [])
        if not registrations:
            line = f"{slot_titles[slot]} - Not Assigned"
        else:
            # Use stored display name if available
            names = [reg.get("display_name", f"ID {reg['user_id']}") for reg in registrations]
            line = f"{slot_titles[slot]} - " + ", ".join(names)
        lines.append(line)
    group_number = lecture_info.get("group_number") or "Not Set"
    global_note = lecture_info.get("note") or "No note"
    lines.append(f"Group number - {group_number}")
    lines.append(f"Note - {global_note}")
    return "\n".join(lines)

def build_lecture_keyboard(lecture_num, context: ContextTypes.DEFAULT_TYPE, test_mode=False):
    keyboard = []
    for slot in ["writer", "editor", "mcq", "design", "digital_writer"]:
        keyboard.append([
            InlineKeyboardButton("Register", callback_data=f"lecture_sign:{lecture_num}:{slot}{':test' if test_mode else ''}"),
            InlineKeyboardButton("Withdraw", callback_data=f"lecture_withdraw:{lecture_num}:{slot}{':test' if test_mode else ''}"),
            InlineKeyboardButton("Note", callback_data=f"lecture_updatenote:{lecture_num}:{slot}{':test' if test_mode else ''}")
        ])
    keyboard.append([
        InlineKeyboardButton("Set Group", callback_data=f"lecture_setgroup:{lecture_num}{':test' if test_mode else ''}"),
        InlineKeyboardButton("Set Global Note", callback_data=f"lecture_setnote:{lecture_num}{':test' if test_mode else ''}")
    ])
    return InlineKeyboardMarkup(keyboard)

# /lecture command (Admin only)
async def lecture_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return ConversationHandler.END
    if user.id != 6177929931:
        await update.message.reply_text("You are not authorized to use /lecture.")
        return ConversationHandler.END
    await update.message.reply_text("Please enter the subject name for the lectures (e.g. Endocrine):")
    return LECTURE_SUBJECT

async def lecture_subject_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GLOBAL_LECTURE_SUBJECT
    subject = update.message.text.strip()
    if not subject:
        await update.message.reply_text("Please enter a valid subject name.")
        return LECTURE_SUBJECT
    GLOBAL_LECTURE_SUBJECT = subject
    await update.message.reply_text(f"Subject set as: {subject}\nNow, how many lectures do you want to create? (1-50)")
    return LECTURE_ENTER_COUNT

async def lecture_enter_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GLOBAL_LECTURE_COUNT
    user_input = update.message.text.strip()
    if not user_input.isdigit():
        await update.message.reply_text("Please enter a valid number.")
        return LECTURE_ENTER_COUNT
    count = int(user_input)
    if count < 1 or count > 50:
        await update.message.reply_text("Please enter a number between 1 and 50.")
        return LECTURE_ENTER_COUNT
    GLOBAL_LECTURE_COUNT = count
    await update.message.reply_text(
        f"You entered {count} lectures. Type /confirm_lecture to confirm or /cancel to cancel."
    )
    return LECTURE_CONFIRM

async def lecture_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global LECTURE_STORE, LECTURE_BROADCAST, GLOBAL_LECTURE_COUNT, GLOBAL_LECTURE_SUBJECT
    if GLOBAL_LECTURE_COUNT == 0:
        await update.message.reply_text("No lecture count found. Please use /lecture again.")
        return ConversationHandler.END
    LECTURE_STORE = {}
    LECTURE_BROADCAST = {}
    for i in range(1, GLOBAL_LECTURE_COUNT + 1):
        LECTURE_STORE[i] = {
            "slots": { key: [] for key in ["writer", "editor", "mcq", "design", "digital_writer"] },
            "group_number": None,
            "note": None,
        }
        broadcast_msgs = await broadcast_lecture_info(i, context)
        LECTURE_BROADCAST[i] = broadcast_msgs
    await update.message.reply_text("Lecture messages have been broadcast to all teams.")
    return LECTURE_SETUP

# Inline callback for lecture (both register/withdraw/update)
async def lecture_inline_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    test_mode = data.endswith(":test")
    if test_mode:
        data = data.replace(":test", "")
    if data.startswith("lecture_sign:"):
        try:
            _, lec_str, slot = data.split(":")
            lecture_num = int(lec_str)
        except ValueError:
            await query.answer("Invalid data.", show_alert=True)
            return
        user = query.from_user
        store = TEST_LECTURE_STORE if test_mode else LECTURE_STORE
        if lecture_num not in store:
            await query.answer("Lecture not found.", show_alert=True)
            return
        registrations = store[lecture_num]["slots"].get(slot, [])
        if any(reg["user_id"] == user.id for reg in registrations):
            await query.answer("You are already registered in this slot.", show_alert=True)
            return
        registrations.append({"user_id": user.id, "display_name": get_display_name(user), "note": ""})
        await update_broadcast(lecture_num, context, test_mode=test_mode)
        await query.answer("Registered successfully.", show_alert=True)
        return

    elif data.startswith("lecture_withdraw:"):
        try:
            _, lec_str, slot = data.split(":")
            lecture_num = int(lec_str)
        except ValueError:
            await query.answer("Invalid data.", show_alert=True)
            return
        user = query.from_user
        store = TEST_LECTURE_STORE if test_mode else LECTURE_STORE
        if lecture_num not in store:
            await query.answer("Lecture not found.", show_alert=True)
            return
        registrations = store[lecture_num]["slots"].get(slot, [])
        new_regs = [reg for reg in registrations if reg["user_id"] != user.id]
        if len(new_regs) == len(registrations):
            await query.answer("You are not registered in this slot.", show_alert=True)
            return
        store[lecture_num]["slots"][slot] = new_regs
        await update_broadcast(lecture_num, context, test_mode=test_mode)
        await query.answer("Withdrawn successfully.", show_alert=True)
        return

    elif data.startswith("lecture_updatenote:"):
        try:
            _, lec_str, slot = data.split(":")
            lecture_num = int(lec_str)
        except ValueError:
            await query.answer("Invalid data.", show_alert=True)
            return
        user = query.from_user
        store = TEST_LECTURE_STORE if test_mode else LECTURE_STORE
        if lecture_num not in store:
            await query.answer("Lecture not found.", show_alert=True)
            return
        registrations = store[lecture_num]["slots"].get(slot, [])
        if not any(reg["user_id"] == user.id for reg in registrations):
            await query.answer("You are not registered in this slot.", show_alert=True)
            return
        context.user_data["lecture_updatenote_pending"] = {"lecture_num": lecture_num, "slot": slot, "user_id": user.id, "test_mode": test_mode}
        await query.message.reply_text(f"Please enter your new note for the {slot} slot in Lecture #{lecture_num}:")
        return

    elif data.startswith("lecture_setgroup:"):
        try:
            _, lec_str = data.split(":")
            lecture_num = int(lec_str)
        except ValueError:
            await query.answer("Invalid data.", show_alert=True)
            return
        context.user_data["lecture_setgroup_pending"] = {"lecture_num": lecture_num, "test_mode": test_mode}
        await query.message.reply_text(f"Please enter the group number for Lecture #{lecture_num}:")
        return

    elif data.startswith("lecture_setnote:"):
        try:
            _, lec_str = data.split(":")
            lecture_num = int(lec_str)
        except ValueError:
            await query.answer("Invalid data.", show_alert=True)
            return
        context.user_data["lecture_setnote_pending"] = {"lecture_num": lecture_num, "test_mode": test_mode}
        await query.message.reply_text(f"Please enter the global note for Lecture #{lecture_num}:")
        return

async def lecture_text_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()
    if "lecture_updatenote_pending" in context.user_data:
        pending = context.user_data.pop("lecture_updatenote_pending")
        lecture_num = pending["lecture_num"]
        slot = pending["slot"]
        test_mode = pending.get("test_mode", False)
        store = TEST_LECTURE_STORE if test_mode else LECTURE_STORE
        if lecture_num in store:
            registrations = store[lecture_num]["slots"].get(slot, [])
            for reg in registrations:
                if reg["user_id"] == pending["user_id"]:
                    reg["note"] = user_text
                    break
            await update.message.reply_text(f"Note updated for your registration in the {slot} slot of Lecture #{lecture_num}.")
            await update_broadcast(lecture_num, context, test_mode=test_mode)
        return LECTURE_SETUP
    if "lecture_setgroup_pending" in context.user_data:
        pending = context.user_data.pop("lecture_setgroup_pending")
        lecture_num = pending["lecture_num"]
        test_mode = pending.get("test_mode", False)
        store = TEST_LECTURE_STORE if test_mode else LECTURE_STORE
        if lecture_num in store:
            store[lecture_num]["group_number"] = user_text
            await update.message.reply_text(f"Group number for Lecture #{lecture_num} set to: {user_text}")
            await update_broadcast(lecture_num, context, test_mode=test_mode)
        return LECTURE_SETUP
    if "lecture_setnote_pending" in context.user_data:
        pending = context.user_data.pop("lecture_setnote_pending")
        lecture_num = pending["lecture_num"]
        test_mode = pending.get("test_mode", False)
        store = TEST_LECTURE_STORE if test_mode else LECTURE_STORE
        if lecture_num in store:
            store[lecture_num]["note"] = user_text
            await update.message.reply_text(f"Global note for Lecture #{lecture_num} set to: {user_text}")
            await update_broadcast(lecture_num, context, test_mode=test_mode)
        return LECTURE_SETUP
    return LECTURE_SETUP

async def lecture_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global LECTURE_STORE, LECTURE_BROADCAST, GLOBAL_LECTURE_COUNT, GLOBAL_LECTURE_SUBJECT
    user = update.effective_user
    if user.id != 6177929931:
        await update.message.reply_text("You are not authorized to cancel lecture creation.")
        return ConversationHandler.END
    GLOBAL_LECTURE_COUNT = 0
    LECTURE_STORE.clear()
    LECTURE_BROADCAST.clear()
    GLOBAL_LECTURE_SUBJECT = None
    await update.message.reply_text("Lecture creation cancelled.")
    return ConversationHandler.END

async def lecture_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global LECTURE_STORE, LECTURE_BROADCAST, GLOBAL_LECTURE_COUNT, GLOBAL_LECTURE_SUBJECT
    user = update.effective_user
    if user.id != 6177929931:
        await update.message.reply_text("You are not authorized to finish lecture creation.")
        return ConversationHandler.END
    if not LECTURE_STORE:
        await update.message.reply_text("No active lectures to finish.")
        return ConversationHandler.END
    await update.message.reply_text("Lecture creation completed. The broadcast messages remain updated.")
    GLOBAL_LECTURE_COUNT = 0
    LECTURE_STORE.clear()
    LECTURE_BROADCAST.clear()
    GLOBAL_LECTURE_SUBJECT = None
    return ConversationHandler.END

# ------------------ Lecture Test Feature (Tester Only) ------------------
# These functions are analogous to the lecture functions above but allow testers to create test lectures.
async def lecture_test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or user.id not in TESTER_IDS:
        await update.message.reply_text("You are not authorized to use /lecture_test.")
        return ConversationHandler.END
    await update.message.reply_text("Please enter the subject name for the test lectures (e.g. Test Subject):")
    return LECTURE_SUBJECT

async def lecture_test_subject_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TEST_GLOBAL_LECTURE_SUBJECT
    subject = update.message.text.strip()
    if not subject:
        await update.message.reply_text("Please enter a valid subject name.")
        return LECTURE_SUBJECT
    TEST_GLOBAL_LECTURE_SUBJECT = subject
    await update.message.reply_text(f"Test subject set as: {subject}\nNow, how many test lectures do you want to create? (1-50)")
    return LECTURE_ENTER_COUNT

async def lecture_test_enter_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TEST_GLOBAL_LECTURE_COUNT
    user_input = update.message.text.strip()
    if not user_input.isdigit():
        await update.message.reply_text("Please enter a valid number.")
        return LECTURE_ENTER_COUNT
    count = int(user_input)
    if count < 1 or count > 50:
        await update.message.reply_text("Please enter a number between 1 and 50.")
        return LECTURE_ENTER_COUNT
    TEST_GLOBAL_LECTURE_COUNT = count
    await update.message.reply_text(
        f"You entered {count} test lectures. Type /confirm_lecture to confirm or /cancel to cancel."
    )
    return LECTURE_CONFIRM

async def lecture_test_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TEST_LECTURE_STORE, TEST_LECTURE_BROADCAST, TEST_GLOBAL_LECTURE_COUNT, TEST_GLOBAL_LECTURE_SUBJECT
    if TEST_GLOBAL_LECTURE_COUNT == 0:
        await update.message.reply_text("No test lecture count found. Please use /lecture_test again.")
        return ConversationHandler.END
    TEST_LECTURE_STORE = {}
    TEST_LECTURE_BROADCAST = {}
    for i in range(1, TEST_GLOBAL_LECTURE_COUNT + 1):
        TEST_LECTURE_STORE[i] = {
            "slots": { key: [] for key in ["writer", "editor", "mcq", "design", "digital_writer"] },
            "group_number": None,
            "note": None,
        }
        broadcast_msgs = await broadcast_lecture_info(i, context)  # reuse same broadcast function
        TEST_LECTURE_BROADCAST[i] = broadcast_msgs
    await update.message.reply_text("Test lecture messages have been broadcast to all teams.")
    return LECTURE_SETUP

async def lecture_test_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TEST_LECTURE_STORE, TEST_LECTURE_BROADCAST, TEST_GLOBAL_LECTURE_COUNT, TEST_GLOBAL_LECTURE_SUBJECT
    user = update.effective_user
    if user.id not in TESTER_IDS:
        await update.message.reply_text("You are not authorized to cancel test lecture creation.")
        return ConversationHandler.END
    TEST_GLOBAL_LECTURE_COUNT = 0
    TEST_LECTURE_STORE.clear()
    TEST_LECTURE_BROADCAST.clear()
    TEST_GLOBAL_LECTURE_SUBJECT = None
    await update.message.reply_text("Test lecture creation cancelled.")
    return ConversationHandler.END

async def lecture_test_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TEST_LECTURE_STORE, TEST_LECTURE_BROADCAST, TEST_GLOBAL_LECTURE_COUNT, TEST_GLOBAL_LECTURE_SUBJECT
    user = update.effective_user
    if user.id not in TESTER_IDS:
        await update.message.reply_text("You are not authorized to finish test lecture creation.")
        return ConversationHandler.END
    if not TEST_LECTURE_STORE:
        await update.message.reply_text("No active test lectures to finish.")
        return ConversationHandler.END
    await update.message.reply_text("Test lecture creation completed. The broadcast messages remain updated.")
    TEST_GLOBAL_LECTURE_COUNT = 0
    TEST_LECTURE_STORE.clear()
    TEST_LECTURE_BROADCAST.clear()
    TEST_GLOBAL_LECTURE_SUBJECT = None
    return ConversationHandler.END

# ------------------ New Command: Add Tester (Admin Only) ------------------
async def add_tester_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only admin (user ID 6177929931) is allowed to add testers.
    if update.effective_user.id != 6177929931:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /addtester <user_id>")
        return
    try:
        tester_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Please provide a valid user ID.")
        return
    TESTER_IDS.add(tester_id)
    await update.message.reply_text(f"Tester with user ID {tester_id} has been added.")

# ------------------ Other Handler Functions ------------------
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
        special_user_id = 6177929931
        all_target_ids = set()
        for role_ids in ROLE_MAP.values():
            all_target_ids.update(role_ids)
        if user_id in all_target_ids:
            all_target_ids.remove(user_id)
        await forward_anonymous_message(context.bot, message_to_send, list(all_target_ids))
        await query.edit_message_text("✅ *Your anonymous feedback has been sent to all teams.*", parse_mode='Markdown')
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
        "*Tester Commands:*\n"
        "/addtester <user_id> - (Admin only) Add a user as a tester for lecture test mode.\n\n"
        "*New Commands:* \n"
        "/setgroupname <name> - (Group Admin / Group Assistant only) Assign a group name that appears next to your display name.\n"
        "/lecture - (Only admin 6177929931 can start/cancel) Create multiple lectures with registration slots.\n"
        "/lecture_test - (Testers only) Create test lectures to try out the lecture functionality."
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
        LECTURE_SUBJECT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, lecture_subject_entry),
        ],
        LECTURE_ENTER_COUNT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, lecture_enter_count),
        ],
        LECTURE_CONFIRM: [
            CommandHandler('confirm_lecture', lecture_confirm),
            CommandHandler('cancel', lecture_cancel)
        ],
        LECTURE_SETUP: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, lecture_text_entry),
            CallbackQueryHandler(lecture_inline_callback, pattern=r'^(lecture_sign|lecture_withdraw|lecture_updatenote|lecture_setgroup|lecture_setnote):.*'),
            CommandHandler('finish_lecture', lecture_finish),
            CommandHandler('cancel', lecture_cancel),
        ],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    allow_reentry=True,
)

lecture_test_conv_handler = ConversationHandler(
    entry_points=[CommandHandler('lecture_test', lecture_test_command)],
    states={
        LECTURE_SUBJECT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, lecture_test_subject_entry),
        ],
        LECTURE_ENTER_COUNT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, lecture_test_enter_count),
        ],
        LECTURE_CONFIRM: [
            CommandHandler('confirm_lecture', lecture_test_confirm),
            CommandHandler('cancel', lecture_test_cancel)
        ],
        LECTURE_SETUP: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, lecture_text_entry),
            CallbackQueryHandler(lecture_inline_callback, pattern=r'^(lecture_sign|lecture_withdraw|lecture_updatenote|lecture_setgroup|lecture_setnote):.*'),
            CommandHandler('finish_lecture', lecture_test_finish),
            CommandHandler('cancel', lecture_test_cancel),
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
    # New addtester command (admin only)
    application.add_handler(CommandHandler('addtester', add_tester_command))
    # Lecture conversation (admin)
    application.add_handler(lecture_conv_handler)
    # Lecture test conversation (testers only)
    application.add_handler(lecture_test_conv_handler)
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
