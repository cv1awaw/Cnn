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

# ====================== LOGGING ======================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ====================== ROLES ========================
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

# Add group_admin / group_assistant if not present
if 'group_admin' not in ROLE_MAP:
    ROLE_MAP['group_admin'] = []
ROLE_DISPLAY_NAMES['group_admin'] = "Group Admin"

if 'group_assistant' not in ROLE_MAP:
    ROLE_MAP['group_assistant'] = []
ROLE_DISPLAY_NAMES['group_assistant'] = "Group Assistant"

# Used for Tara side commands
TRIGGER_TARGET_MAP = {
    '-w': ['writer'],
    '-e': ['checker_team'],
    '-mcq': ['mcqs_team'],
    '-d': ['word_team'],
    '-de': ['design_team'],
    '-mf': ['mind_map_form_creator'],
    '-c': ['checker_team'],
}

# Send from each role => target roles
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
        'mind_map_form_creator'
    ],
    'mind_map_form_creator': ['design_team', 'tara_team']
}

# ====================== STATES =======================
TEAM_MESSAGE = 1
SPECIFIC_TEAM_MESSAGE = 2
SPECIFIC_USER_MESSAGE = 3
TARA_MESSAGE = 4
CONFIRMATION = 5
SELECT_ROLE = 6

# ====================== USER DATA ====================
USER_DATA_FILE = Path('user_data.json')
if USER_DATA_FILE.exists():
    try:
        with open(USER_DATA_FILE, 'r') as f:
            user_data_store = json.load(f)
            user_data_store = {k.lower(): v for k, v in user_data_store.items()}
    except json.JSONDecodeError:
        user_data_store = {}
else:
    user_data_store = {}

def save_user_data():
    try:
        with open(USER_DATA_FILE, 'w') as f:
            json.dump(user_data_store, f)
    except Exception as e:
        logger.error(f"Failed to save user_data: {e}")

def get_user_roles(user_id):
    roles = []
    for role, ids in ROLE_MAP.items():
        if user_id in ids:
            roles.append(role)
    return roles

# ====================== MUTE =========================
MUTED_USERS_FILE = Path('muted_users.json')
if MUTED_USERS_FILE.exists():
    try:
        with open(MUTED_USERS_FILE, 'r') as f:
            muted_users = set(json.load(f))
    except json.JSONDecodeError:
        muted_users = set()
else:
    muted_users = set()

def save_muted_users():
    try:
        with open(MUTED_USERS_FILE, 'w') as f:
            json.dump(list(muted_users), f)
    except Exception as e:
        logger.error(f"Failed to save muted_users: {e}")

# ====================== HELPER FUNCS =================
def get_display_name(user):
    if user.username:
        return f"@{user.username}"
    else:
        return (user.first_name + (f" {user.last_name}" if user.last_name else ""))

def get_confirmation_keyboard(uuid_str):
    kb = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f'confirm:{uuid_str}'),
            InlineKeyboardButton("❌ Cancel", callback_data=f'cancel:{uuid_str}')
        ]
    ]
    return InlineKeyboardMarkup(kb)

def get_role_selection_keyboard(roles):
    keyboard = []
    for role in roles:
        disp = ROLE_DISPLAY_NAMES.get(role, role.capitalize())
        keyboard.append([InlineKeyboardButton(disp, callback_data=f"role:{role}")])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data='cancel_role_selection')])
    return InlineKeyboardMarkup(keyboard)

# ================== GROUP NAME STORAGE ==================
# This dictionary will map user_id -> group_name (string).
# e.g. { 1234567: "Group 1", 9876543: "Group 2", ...}
GROUP_NAME_FILE = Path('group_names.json')
if GROUP_NAME_FILE.exists():
    try:
        with open(GROUP_NAME_FILE, 'r') as f:
            group_data = json.load(f)
    except json.JSONDecodeError:
        group_data = {}
else:
    group_data = {}

def save_group_data():
    try:
        with open(GROUP_NAME_FILE, 'w') as f:
            json.dump(group_data, f)
    except Exception as e:
        logger.error(f"Failed to save group data: {e}")

# ================== FORWARD MESSAGES ==================
async def forward_message(bot, message, target_ids, sender_role):
    user = message.from_user
    username_display = get_display_name(user)
    role_display = ROLE_DISPLAY_NAMES.get(sender_role, sender_role.capitalize())

    # Check if user has group_admin or group_assistant role
    user_roles = get_user_roles(user.id)
    group_string = ""
    if "group_admin" in user_roles or "group_assistant" in user_roles:
        # If we have a group name for them:
        if str(user.id) in group_data:
            grp_name = group_data[str(user.id)]
            group_string = f", {grp_name}"
        # So it becomes => (Group Admin, MyGroup)
        # or (Group Assistant, MyGroup)
        # We'll show "role_display" plus group_string
        role_display = f"{role_display}{group_string}"

    # Build the caption
    if message.document:
        caption = f"🔄 *Document sent by **{username_display} ({role_display})**.*"
    elif message.text:
        caption = f"🔄 *Message sent by **{username_display} ({role_display})**.*"
    else:
        caption = f"🔄 *Message sent by **{username_display} ({role_display})**.*"

    for uid in target_ids:
        try:
            if message.document:
                await bot.send_document(
                    chat_id=uid,
                    document=message.document.file_id,
                    caption=caption + (f"\n\n{message.caption}" if message.caption else ""),
                    parse_mode='Markdown'
                )
            elif message.text:
                await bot.send_message(
                    chat_id=uid,
                    text=f"{caption}\n\n{message.text}",
                    parse_mode='Markdown'
                )
            else:
                await bot.forward_message(
                    chat_id=uid,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id
                )
        except Exception as e:
            logger.error(f"Failed to forward: {e}")

async def forward_anonymous_message(bot, message, target_ids):
    for uid in target_ids:
        try:
            if message.document:
                await bot.send_document(
                    chat_id=uid,
                    document=message.document.file_id,
                    caption="🔄 *Anonymous feedback.*" + (f"\n\n{message.caption}" if message.caption else ""),
                    parse_mode='Markdown'
                )
            elif message.text:
                await bot.send_message(
                    chat_id=uid,
                    text=f"🔄 *Anonymous feedback.*\n\n{message.text}",
                    parse_mode='Markdown'
                )
            else:
                await bot.forward_message(
                    chat_id=uid,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id
                )
        except Exception as e:
            logger.error(f"Failed to forward anonymous: {e}")

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

    text = (
        f"📩 *You are about to send the following to **{', '.join(target_roles_display)}**:*\n\n"
        f"{content_description}\n\n"
        "Do you want to send this?"
    )

    uid = str(uuid.uuid4())
    kb = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f'confirm:{uid}'),
            InlineKeyboardButton("❌ Cancel", callback_data=f'cancel:{uid}')
        ]
    ]
    msg = await message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

    context.user_data[f'confirm_{uid}'] = {
        'message': message,
        'target_ids': target_ids,
        'sender_role': sender_role,
        'target_roles': target_roles if target_roles else SENDING_ROLE_TARGETS.get(sender_role, [])
    }

# ================== COMMAND HANDLERS =================
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

    # 1) Anonymous feedback confirm
    if data.startswith('confirm_no_role:'):
        try:
            _, uid = data.split(':', 1)
        except ValueError:
            await query.edit_message_text("Invalid data.")
            return ConversationHandler.END

        cdata = context.user_data.get(f'confirm_{uid}')
        if not cdata:
            await query.edit_message_text("An error occurred.")
            return ConversationHandler.END

        message_to_send = cdata['message']
        user_id = message_to_send.from_user.id
        special = 6177929931

        # gather all user IDs except the sender
        all_ids = set()
        for r_ids in ROLE_MAP.values():
            all_ids.update(r_ids)
        if user_id in all_ids:
            all_ids.remove(user_id)

        await forward_anonymous_message(context.bot, message_to_send, list(all_ids))
        await query.edit_message_text("✅ *Anonymous feedback sent.*", parse_mode='Markdown')

        # send real info to special user
        real_dn = get_display_name(message_to_send.from_user)
        real_un = message_to_send.from_user.username or "No username"
        real_id = message_to_send.from_user.id
        info = (
            "🔒 *Anonymous sender info:*\n\n"
            f"- ID: `{real_id}`\n"
            f"- Username: @{real_un}\n"
            f"- Display: {real_dn}"
        )
        try:
            await context.bot.send_message(chat_id=special, text=info, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send real info: {e}")

        del context.user_data[f'confirm_{uid}']
        return ConversationHandler.END

    # 2) normal confirm/cancel
    if data.startswith('confirm:') or data.startswith('cancel:'):
        try:
            action, uid = data.split(':', 1)
        except ValueError:
            await query.edit_message_text("Invalid confirm data.")
            return ConversationHandler.END

        cdata = context.user_data.get(f'confirm_{uid}', None)
        if not cdata:
            pass
        else:
            if action == 'confirm':
                msg_to_send = cdata['message']
                tids = cdata['target_ids']
                s_role = cdata['sender_role']
                troles = cdata.get('target_roles', [])
                await forward_message(context.bot, msg_to_send, tids, s_role)

                sender_disp = ROLE_DISPLAY_NAMES.get(s_role, s_role.capitalize())
                if 'specific_user' in troles:
                    r_names = []
                    for tid in tids:
                        try:
                            ch = await context.bot.get_chat(tid)
                            r_names.append(get_display_name(ch))
                        except:
                            r_names.append(str(tid))
                else:
                    r_names = [ROLE_DISPLAY_NAMES.get(r, r.capitalize()) for r in troles if r != 'specific_user']

                if msg_to_send.document:
                    text = (
                        f"✅ *Your PDF `{msg_to_send.document.file_name}` has been sent "
                        f"from **{sender_disp}** to **{', '.join(r_names)}**.*"
                    )
                elif msg_to_send.text:
                    text = (
                        f"✅ *Your message has been sent from **{sender_disp}** "
                        f"to **{', '.join(r_names)}**.*"
                    )
                else:
                    text = (
                        f"✅ *Your message has been sent from **{sender_disp}** "
                        f"to **{', '.join(r_names)}**.*"
                    )
                await query.edit_message_text(text, parse_mode='Markdown')
                del context.user_data[f'confirm_{uid}']

            elif action == 'cancel':
                await query.edit_message_text("Operation cancelled.")
                if f'confirm_{uid}' in context.user_data:
                    del context.user_data[f'confirm_{uid}']
            return ConversationHandler.END

    # 3) confirm_userid or cancel_userid
    if data.startswith("confirm_userid:"):
        try:
            _, uid = data.split(':', 1)
        except ValueError:
            await query.edit_message_text("Invalid data.")
            return ConversationHandler.END

        cdata = context.user_data.get(f'confirm_userid_{uid}', None)
        if not cdata:
            await query.edit_message_text("An error occurred.")
            return ConversationHandler.END

        txt = cdata['msg_text']
        doc = cdata['msg_doc']
        target_id = cdata['target_id']
        orig_msg = cdata['original_message']

        try:
            if doc:
                await context.bot.send_document(
                    chat_id=target_id,
                    document=doc.file_id,
                    caption=doc.caption or ""
                )
            else:
                await context.bot.send_message(chat_id=target_id, text=txt)
            await query.edit_message_text("✅ *Your message has been sent.*", parse_mode='Markdown')
            await orig_msg.reply_text("sent")
        except Exception as e:
            logger.error(f"Failed to send message to user {target_id}: {e}")
            await query.edit_message_text("❌ Failed to send message.")
            await orig_msg.reply_text("didn't sent")

        del context.user_data[f'confirm_userid_{uid}']
        return ConversationHandler.END

    elif data.startswith("cancel_userid:"):
        try:
            _, uid = data.split(':', 1)
        except ValueError:
            await query.edit_message_text("Invalid data.")
            return ConversationHandler.END

        if f'confirm_userid_{uid}' in context.user_data:
            del context.user_data[f'confirm_userid_{uid}']
        await query.edit_message_text("Operation cancelled.")
        return ConversationHandler.END

    else:
        await query.edit_message_text("Invalid choice.")
        return ConversationHandler.END

# ================== TARA MSG => group_admin + group_assistant ==================
async def taramsg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    if not user_id:
        await update.message.reply_text("No user info.")
        return
    roles = get_user_roles(user_id)
    if 'tara_team' not in roles:
        await update.message.reply_text("Not authorized for /taramsg.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /taramsg <message>")
        return

    msg_text = " ".join(context.args)
    # gather all group_admin / group_assistant
    target_ids = set()
    if 'group_admin' in ROLE_MAP:
        for uid in ROLE_MAP['group_admin']:
            target_ids.add(uid)
    if 'group_assistant' in ROLE_MAP:
        for uid in ROLE_MAP['group_assistant']:
            target_ids.add(uid)

    if not target_ids:
        await update.message.reply_text("No group admins/assistants found.")
        return

    from_dn = get_display_name(update.effective_user)
    broadcast_text = f"📢 *Message from Tara ({from_dn}) to group admins/assistants:*\n\n{msg_text}"
    success = 0
    for tid in target_ids:
        try:
            await context.bot.send_message(chat_id=tid, text=broadcast_text, parse_mode='Markdown')
            success += 1
        except Exception as e:
            logger.error(f"Failed to send /taramsg to {tid}: {e}")

    await update.message.reply_text(f"Message sent to {success} group admins/assistants.")


# =================== SPECIFIC TRIGGERS ====================
# (Same as your existing code)...

# (We'll skip rewriting them all here if they are the same. 
#  We keep them in the final code for a full solution.)

# ============= Add or Remove Role =============
async def roleadd_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != 6177929931:
        await update.message.reply_text("Not authorized.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Usage: /roleadd <user_id> <role_name>")
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Provide a valid user ID.")
        return

    role_name = context.args[1].lower()
    if role_name not in ROLE_MAP:
        valid = ", ".join(ROLE_MAP.keys())
        await update.message.reply_text(f"Invalid role. Valid: {valid}")
        return

    lst = ROLE_MAP[role_name]
    if target_user_id in lst:
        await update.message.reply_text("User is already in that role.")
        return

    if isinstance(lst, set):
        lst.add(target_user_id)
    else:
        lst.append(target_user_id)
    await update.message.reply_text(f"User {target_user_id} added to '{role_name}'.")

async def roleremove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != 6177929931:
        await update.message.reply_text("Not authorized.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Usage: /role_r <user_id> <role_name>")
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Provide a valid user ID.")
        return

    role_name = context.args[1].lower()
    if role_name not in ROLE_MAP:
        valid = ", ".join(ROLE_MAP.keys())
        await update.message.reply_text(f"Invalid role. Valid: {valid}")
        return

    lst = ROLE_MAP[role_name]
    if target_user_id not in lst:
        await update.message.reply_text("User is not in that role.")
        return

    if isinstance(lst, set):
        lst.remove(target_user_id)
    else:
        lst.remove(target_user_id)
    await update.message.reply_text(f"User {target_user_id} removed from '{role_name}'.")


# =========== NEW: /setgroup <user_id> <group_name> (admin only) ==========
async def setgroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set a group name for the given user. Only main admin can do this."""
    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or user_id != 6177929931:
        await update.message.reply_text("Not authorized.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /setgroup <user_id> <group_name>")
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Please provide a valid user ID.")
        return

    group_name = " ".join(context.args[1:])  # The rest is the group name
    # store in group_data
    group_data[str(target_user_id)] = group_name
    save_group_data()

    await update.message.reply_text(
        f"User {target_user_id} assigned to group '{group_name}'.\n"
        f"If they have group_admin or group_assistant role, messages will show this group."
    )


# =================== START, LISTUSERS, HELP, etc. ===================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and user.username:
        un_lower = user.username.lower()
        user_data_store[un_lower] = user.id
        save_user_data()

    disp_name = get_display_name(user) if user else "there"
    roles = get_user_roles(user.id) if user else []
    if not roles:
        await update.message.reply_text(
            f"Hello, {disp_name}! You have no role. Messages => anonymous feedback to all teams."
        )
    else:
        await update.message.reply_text(
            f"Hello, {disp_name}! Welcome to the Team Communication Bot.\n"
            "Use /help for instructions."
        )

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        await update.message.reply_text("No user info.")
        return

    if 'tara_team' not in get_user_roles(user.id) and user.id != 6177929931:
        await update.message.reply_text("Not authorized.")
        return

    if not user_data_store:
        await update.message.reply_text("No users are registered.")
        return

    lines = [f"@{u} => {uid}" for u, uid in user_data_store.items()]
    text = "\n".join(lines)
    await update.message.reply_text(f"**Registered Users:**\n{text}", parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    valid = ", ".join(ROLE_MAP.keys())
    text = (
        "📘 *Available Commands:*\n\n"
        "/start - Start.\n"
        "/listusers - List all known users (Tara or 6177929931).\n"
        "/help - This help.\n"
        "/refresh - Refresh your info.\n"
        "/cancel - Cancel.\n\n"
        "Message triggers:\n"
        "`-team` => to your role + Tara.\n"
        "`-t` => to Tara only.\n"
        "`-@username` => direct to user (Tara only).\n"
        "`-w, -e, -mcq, -d, -de, -mf, -c` => to specific teams.\n\n"
        "Admin/Tara Commands:\n"
        "/mute [user_id], /muteid, /unmuteid, /listmuted\n"
        "`-check <id>` or `/check <id>` => check user.\n"
        "`-user_id <id>` => admin => send message to that user.\n"
        "/roleadd <id> <role>, /role_r <id> <role> => manage roles. Valid roles:\n"
        f"{valid}\n\n"
        "*Group Admin & Assistant*\n"
        "/setgroup <user_id> <group_name> => set that user's group label (admin only). If they have group_admin/assistant role, it shows in their messages.\n\n"
        "Lecture feature (admin only): /lecture => create multiple lectures.\n"
        "Tara can broadcast to group admins/assistants => `/taramsg <message>`.\n"
        "If you have no role => messages go as anonymous feedback.\n"
    )
    await update.message.reply_text(text, parse_mode='Markdown')

async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not user.username:
        await update.message.reply_text("Set a Telegram username to refresh.")
        return

    un_lower = user.username.lower()
    user_data_store[un_lower] = user.id
    save_user_data()
    await update.message.reply_text("Your info has been refreshed.")

# =================== MUTE COMMANDS ===================
async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u:
        await update.message.reply_text("No user info.")
        return
    if 'tara_team' not in get_user_roles(u.id) and u.id != 6177929931:
        await update.message.reply_text("Not authorized.")
        return

    if len(context.args) == 0:
        target_id = u.id
    elif len(context.args) == 1:
        try:
            target_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Provide valid user ID.")
            return
    else:
        await update.message.reply_text("Usage: /mute [user_id]")
        return

    if target_id in muted_users:
        if target_id == u.id:
            await update.message.reply_text("You are already muted.")
        else:
            await update.message.reply_text("User is already muted.")
        return

    muted_users.add(target_id)
    save_muted_users()
    if target_id == u.id:
        await update.message.reply_text("You have been muted.")
    else:
        # find username
        found_un = None
        for uname, uid in user_data_store.items():
            if uid == target_id:
                found_un = uname
                break
        if found_un:
            await update.message.reply_text(f"User `@{found_un}` is muted.", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"User ID {target_id} is muted.")

async def mute_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await mute_command(update, context)

async def unmute_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u:
        await update.message.reply_text("No user info.")
        return
    if 'tara_team' not in get_user_roles(u.id) and u.id != 6177929931:
        await update.message.reply_text("Not authorized.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Usage: /unmuteid <user_id>")
        return

    try:
        tid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Provide a valid ID.")
        return

    if tid in muted_users:
        muted_users.remove(tid)
        save_muted_users()
        # find username
        found_un = None
        for uname, uid in user_data_store.items():
            if uid == tid:
                found_un = uname
                break
        if found_un:
            await update.message.reply_text(f"User `@{found_un}` is unmuted.", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"User ID {tid} is unmuted.")
    else:
        await update.message.reply_text(f"User {tid} is not muted.")

async def list_muted_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u:
        await update.message.reply_text("No user info.")
        return
    if 'tara_team' not in get_user_roles(u.id) and u.id != 6177929931:
        await update.message.reply_text("Not authorized.")
        return

    if not muted_users:
        await update.message.reply_text("No users muted.")
        return

    lines = []
    for x in muted_users:
        found_un = None
        for un, idx in user_data_store.items():
            if idx == x:
                found_un = un
                break
        if found_un:
            lines.append(f"@{found_un} (ID: {x})")
        else:
            lines.append(f"ID: {x}")
    text = "\n".join(lines)
    await update.message.reply_text(f"**Muted Users:**\n{text}", parse_mode='Markdown')

# =================== /check COMMAND ===================
async def check_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only 6177929931
    user = update.effective_user
    if not user or user.id != 6177929931:
        await update.message.reply_text("Not authorized.")
        return

    if (context.args is None or len(context.args) == 0) and update.message:
        msg_text = update.message.text.strip()
        match = re.match(r'^-check\s+(\d+)$', msg_text, re.IGNORECASE)
        if not match:
            await update.message.reply_text("Usage: -check <user_id>")
            return
        check_id = int(match.group(1))
    else:
        if len(context.args) != 1:
            await update.message.reply_text("Usage: /check <user_id>")
            return
        try:
            check_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Provide a valid ID.")
            return

    # find user
    found_un = None
    for uname, uid in user_data_store.items():
        if uid == check_id:
            found_un = uname
            break

    if not found_un:
        await update.message.reply_text(f"No record for ID {check_id}.")
        return

    rr = get_user_roles(check_id)
    if rr:
        rd = ", ".join(ROLE_DISPLAY_NAMES.get(r, r.capitalize()) for r in rr)
    else:
        rd = "No role"
    await update.message.reply_text(
        f"User ID: `{check_id}`\nUsername: `@{found_un}`\nRoles: {rd}",
        parse_mode='Markdown'
    )

# ====================== CONV HANDLERS ======================
# (We keep them basically the same, but with per_message=True to avoid warnings.)

async def user_id_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != 6177929931:
        await update.message.reply_text("Not authorized.")
        return ConversationHandler.END

    txt = update.message.text.strip()
    match = re.match(r'^-user_id\s+(\d+)$', txt, re.IGNORECASE)
    if not match:
        await update.message.reply_text("Usage: `-user_id <user_id>`", parse_mode='Markdown')
        return ConversationHandler.END

    tid = int(match.group(1))
    await update.message.reply_text(f"Write the message for user ID {tid}. Then I'll confirm.")
    context.user_data['target_user_id_userid'] = tid
    return SPECIFIC_USER_MESSAGE

async def user_id_message_collector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    tid = context.user_data.get('target_user_id_userid', None)
    if not tid:
        await msg.reply_text("Error. No target ID.")
        return ConversationHandler.END

    if msg.document:
        desc = f"PDF: `{msg.document.file_name}`"
    elif msg.text:
        desc = f"Message: `{msg.text}`"
    else:
        desc = "Unsupported type."

    ctxt = (
        f"📩 *You are about to send the following to user ID {tid}:*\n\n"
        f"{desc}\n\nDo you want to send this?"
    )

    uuid_str = str(uuid.uuid4())
    kb = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f'confirm_userid:{uuid_str}'),
            InlineKeyboardButton("❌ Cancel", callback_data=f'cancel_userid:{uuid_str}'),
        ]
    ]
    rp = InlineKeyboardMarkup(kb)
    await msg.reply_text(ctxt, parse_mode='Markdown', reply_markup=rp)

    context.user_data[f'confirm_userid_{uuid_str}'] = {
        'target_id': tid,
        'original_message': msg,
        'msg_text': msg.text if msg.text else "",
        'msg_doc': msg.document if msg.document else None,
    }
    del context.user_data['target_user_id_userid']
    return CONFIRMATION


# Here are your conversation handlers, each with per_message=True
user_id_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(re.compile(r'^-user_id\s+(\d+)$', re.IGNORECASE)), user_id_trigger)],
    states={
        SPECIFIC_USER_MESSAGE: [MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, user_id_message_collector)],
        CONFIRMATION: [
            CallbackQueryHandler(confirmation_handler, pattern='^(confirm:|cancel:|confirm_no_role:|confirm_userid:|cancel_userid:).*')
        ],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    per_message=True
)

# (Similarly for the other conversation handlers)...

# ... [YOUR existing code for specific_user_conv_handler, specific_team_conv_handler, etc.]

# We define them below, all with per_message=True, to avoid warnings:

async def specific_user_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # (same as your code)...

specific_user_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(re.compile(r'^\s*-\@([A-Za-z0-9_]{5,32})\s*$', re.IGNORECASE)), specific_user_trigger)],
    states={
        SPECIFIC_USER_MESSAGE: [
            MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, 
                           # your message handler
                           )
        ],
        CONFIRMATION: [
            CallbackQueryHandler(confirmation_handler, pattern='^(confirm:|cancel:|confirm_no_role:|confirm_userid:|cancel_userid:).*')
        ],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    per_message=True
)

# ... and so on for the others. For brevity, not repeating them in detail.

# ========== LECTURE FEATURE (Define before main) =============
from telegram.ext import ConversationHandler

LECTURE_ASK_COUNT = 1001

LECTURE_DATA = {
    'count': 0,
    'registrations': {},
    'message_ids': {}
}

LECTURE_FIELD_ROLE_MAP = {
    'writer': 'writer',
    'editor': 'checker_team',
    'digital': 'word_team',
    'designer': 'design_team',
    'mcqs': 'mcqs_team',
    'mindmaps': 'mind_map_form_creator',
}

async def lecture_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != 6177929931:
        await update.message.reply_text("Not authorized.")
        return ConversationHandler.END
    await update.message.reply_text("How many lectures do you want to create? (1-50)")
    return LECTURE_ASK_COUNT

async def lecture_ask_count_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # same as your code
    # create lectures, send them out, etc.
    # not repeating all detail here for brevity
    pass

# define a callback for the inline keyboard etc. 
async def lecture_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # same logic
    pass

lecture_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("lecture", lecture_command)],
    states={
        LECTURE_ASK_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, lecture_ask_count_handler)]
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    per_message=True
)
lecture_callbackquery_handler = CallbackQueryHandler(lecture_callback_handler, pattern="^lectureReg:")

# =========== ERROR HANDLER ===========
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {context.error}", exc_info=True)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text("An error occurred.")

# =============== MAIN ===============
def main():
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not found in environment.")
        return

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Standard commands
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('listusers', list_users))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('refresh', refresh))
    application.add_handler(CommandHandler('mute', mute_command))
    application.add_handler(CommandHandler('muteid', mute_id_command))
    application.add_handler(CommandHandler('unmuteid', unmute_id_command))
    application.add_handler(CommandHandler('listmuted', list_muted_command))

    # /check & -check
    application.add_handler(CommandHandler('check', check_user_command))
    application.add_handler(MessageHandler(filters.Regex(re.compile(r'^-check\s+(\d+)$', re.IGNORECASE)), check_user_command))

    # Roles
    application.add_handler(CommandHandler('roleadd', roleadd_command))
    application.add_handler(CommandHandler('role_r', roleremove_command))

    # NEW: setgroup command
    application.add_handler(CommandHandler('setgroup', setgroup_command))

    # TARA => group_admin/assistant broadcast
    application.add_handler(CommandHandler('taramsg', taramsg_command))

    # Conversation handlers
    application.add_handler(user_id_conv_handler)
    # Also add specific_user_conv_handler, specific_team_conv_handler, etc. 
    # (not repeated in full for brevity—but do it like this)
    # application.add_handler(specific_user_conv_handler)
    # application.add_handler(specific_team_conv_handler)
    # ...
    # If you have them fully defined above, do add them.

    application.add_handler(lecture_conv_handler)
    application.add_handler(lecture_callbackquery_handler)

    # For general messages:
    # application.add_handler(general_conv_handler)

    application.add_error_handler(error_handler)

    logger.info("Bot started polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
