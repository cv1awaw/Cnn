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

# ============================== LOGGING ==============================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============================ ROLE IMPORTS ===========================
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

# ============================ DEFINE ROLES ===========================
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

# Add group admin & assistant roles if not present
if 'group_admin' not in ROLE_MAP:
    ROLE_MAP['group_admin'] = []
ROLE_DISPLAY_NAMES['group_admin'] = "Group Admin"

if 'group_assistant' not in ROLE_MAP:
    ROLE_MAP['group_assistant'] = []
ROLE_DISPLAY_NAMES['group_assistant'] = "Group Assistant"

# Trigger => target roles (Tara side commands)
TRIGGER_TARGET_MAP = {
    '-w': ['writer'],
    '-e': ['checker_team'],
    '-mcq': ['mcqs_team'],
    '-d': ['word_team'],
    '-de': ['design_team'],
    '-mf': ['mind_map_form_creator'],
    '-c': ['checker_team'],
}

# Forwarding rules
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

# ======================== CONVERSATION STATES ========================
TEAM_MESSAGE = 1
SPECIFIC_TEAM_MESSAGE = 2
SPECIFIC_USER_MESSAGE = 3
TARA_MESSAGE = 4
CONFIRMATION = 5
SELECT_ROLE = 6

# ========================= USER DATA STORE ===========================
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
        logger.error(f"Failed to save user data: {e}")

def get_user_roles(user_id):
    roles = []
    for role, ids in ROLE_MAP.items():
        if user_id in ids:
            roles.append(role)
    return roles

# ========================= MUTE FUNCTIONALITY ========================
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
        logger.error(f"Failed to save muted users: {e}")

# ======================= GROUP NAME STORAGE ==========================
# For group_admin/assistant, store user_id -> group_name
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
        logger.error(f"Failed to save group_data: {e}")

# ========================== HELPER FUNCS =============================
def get_display_name(user):
    """Return display name. Prefers @username; else first/last name."""
    if user.username:
        return f"@{user.username}"
    else:
        if user.last_name:
            return f"{user.first_name} {user.last_name}"
        else:
            return user.first_name

# ========================== FORWARDING ===============================
async def forward_message(bot, message, target_ids, sender_role):
    user = message.from_user
    username_display = get_display_name(user)
    role_display = ROLE_DISPLAY_NAMES.get(sender_role, sender_role.capitalize())

    # If user is group_admin or group_assistant, append group name if any
    roles = get_user_roles(user.id)
    if ("group_admin" in roles) or ("group_assistant" in roles):
        if str(user.id) in group_data:
            grp = group_data[str(user.id)]
            role_display = f"{role_display}, {grp}"

    if message.document:
        caption = f"🔄 <b>Document sent by {username_display} ({role_display}).</b>"
    elif message.text:
        caption = f"🔄 <b>Message sent by {username_display} ({role_display}).</b>"
    else:
        caption = f"🔄 <b>Message sent by {username_display} ({role_display}).</b>"

    for uid in target_ids:
        try:
            if message.document:
                await bot.send_document(
                    chat_id=uid,
                    document=message.document.file_id,
                    caption=caption + (f"\n\n{message.caption}" if message.caption else ""),
                    parse_mode='HTML'
                )
            elif message.text:
                await bot.send_message(
                    chat_id=uid,
                    text=f"{caption}\n\n{message.text}",
                    parse_mode='HTML'
                )
            else:
                await bot.forward_message(
                    chat_id=uid,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id
                )
        except Exception as e:
            logger.error(f"Failed to forward message: {e}")

async def forward_anonymous_message(bot, message, target_ids):
    """Forward without revealing identity."""
    for uid in target_ids:
        try:
            if message.document:
                await bot.send_document(
                    chat_id=uid,
                    document=message.document.file_id,
                    caption="🔄 <b>Anonymous feedback.</b>" + (f"\n\n{message.caption}" if message.caption else ""),
                    parse_mode='HTML'
                )
            elif message.text:
                await bot.send_message(
                    chat_id=uid,
                    text=f"🔄 <b>Anonymous feedback.</b>\n\n{message.text}",
                    parse_mode='HTML'
                )
            else:
                await bot.forward_message(
                    chat_id=uid,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id
                )
        except Exception as e:
            logger.error(f"Failed to forward anonymous: {e}")

# ========================= CONFIRMATION ==============================
async def send_confirmation(message, context, sender_role, target_ids, target_roles=None):
    """Send confirm/cancel inline keyboard for the message."""
    if message.document:
        desc = f"PDF: `{message.document.file_name}`"
    elif message.text:
        desc = f"Message: `{message.text}`"
    else:
        desc = "Unsupported message type."

    if target_roles:
        disp = [ROLE_DISPLAY_NAMES.get(r, r.capitalize()) for r in target_roles]
    else:
        disp = [ROLE_DISPLAY_NAMES.get(r, r.capitalize()) for r in SENDING_ROLE_TARGETS.get(sender_role, [])]

    txt = (
        f"📩 <b>You are about to send to: {', '.join(disp)}</b>\n\n"
        f"{desc}\n\n"
        "Do you want to send this?"
    )

    cuuid = str(uuid.uuid4())
    kb = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"confirm:{cuuid}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"cancel:{cuuid}")
        ]
    ]
    rm = InlineKeyboardMarkup(kb)
    m = await message.reply_text(txt, parse_mode='HTML', reply_markup=rm)
    context.user_data[f'confirm_{cuuid}'] = {
        'message': message,
        'target_ids': target_ids,
        'sender_role': sender_role,
        'target_roles': target_roles if target_roles else SENDING_ROLE_TARGETS.get(sender_role, [])
    }

# ====================== CANCEL & CONFIRM HANDLER =====================
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
    if data.startswith("confirm_no_role:"):
        try:
            _, cuuid = data.split(':', 1)
        except ValueError:
            await query.edit_message_text("Invalid data.")
            return ConversationHandler.END
        cdata = context.user_data.get(f'confirm_{cuuid}')
        if not cdata:
            await query.edit_message_text("Error occurred.")
            return ConversationHandler.END
        msg = cdata['message']
        user_id = msg.from_user.id
        special_id = 6177929931
        # gather all IDs
        all_ids = set()
        for v in ROLE_MAP.values():
            for x in v:
                all_ids.add(x)
        if user_id in all_ids:
            all_ids.remove(user_id)
        await forward_anonymous_message(context.bot, msg, list(all_ids))
        await query.edit_message_text("✅ <b>Anonymous feedback sent to all teams.</b>", parse_mode='HTML')

        # send real info to special user
        dn = get_display_name(msg.from_user)
        un = msg.from_user.username or "No username"
        rid = msg.from_user.id
        info = (
            f"🔒 <b>Anonymous Sender Info</b>\n\n"
            f"- ID: <code>{rid}</code>\n"
            f"- Username: @{un}\n"
            f"- Display: {dn}"
        )
        try:
            await context.bot.send_message(chat_id=special_id, text=info, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Failed to send real info: {e}")

        del context.user_data[f'confirm_{cuuid}']
        return ConversationHandler.END

    # 2) Normal confirm/cancel
    if data.startswith("confirm:") or data.startswith("cancel:"):
        try:
            action, cuuid = data.split(':', 1)
        except ValueError:
            await query.edit_message_text("Invalid confirm data.")
            return ConversationHandler.END
        cdata = context.user_data.get(f'confirm_{cuuid}', None)
        if not cdata:
            pass
        else:
            if action == "confirm":
                msg2 = cdata['message']
                tids = cdata['target_ids']
                sr = cdata['sender_role']
                troles = cdata.get('target_roles', [])
                await forward_message(context.bot, msg2, tids, sr)
                sdisp = ROLE_DISPLAY_NAMES.get(sr, sr.capitalize())
                if 'specific_user' in troles:
                    rnames = []
                    for t in tids:
                        try:
                            ch = await context.bot.get_chat(t)
                            rnames.append(get_display_name(ch))
                        except:
                            rnames.append(str(t))
                else:
                    rnames = [ROLE_DISPLAY_NAMES.get(r, r.capitalize()) for r in troles if r != 'specific_user']

                if msg2.document:
                    text = (
                        f"✅ <b>Your PDF '{msg2.document.file_name}' sent from {sdisp} "
                        f"to {', '.join(rnames)}.</b>"
                    )
                elif msg2.text:
                    text = (
                        f"✅ <b>Your message was sent from {sdisp} "
                        f"to {', '.join(rnames)}.</b>"
                    )
                else:
                    text = (
                        f"✅ <b>Your message was sent from {sdisp} "
                        f"to {', '.join(rnames)}.</b>"
                    )
                await query.edit_message_text(text, parse_mode='HTML')
                del context.user_data[f'confirm_{cuuid}']
            elif action == "cancel":
                await query.edit_message_text("Operation cancelled.")
                if f'confirm_{cuuid}' in context.user_data:
                    del context.user_data[f'confirm_{cuuid}']
            return ConversationHandler.END

    # 3) confirm_userid / cancel_userid
    if data.startswith("confirm_userid:"):
        try:
            _, cuuid = data.split(':',1)
        except ValueError:
            await query.edit_message_text("Invalid data.")
            return ConversationHandler.END
        cdata = context.user_data.get(f'confirm_userid_{cuuid}', None)
        if not cdata:
            await query.edit_message_text("Error.")
            return ConversationHandler.END
        txt = cdata['msg_text']
        doc = cdata['msg_doc']
        targ_id = cdata['target_id']
        orig = cdata['original_message']
        try:
            if doc:
                await context.bot.send_document(chat_id=targ_id, document=doc.file_id, caption=doc.caption or "")
            else:
                await context.bot.send_message(chat_id=targ_id, text=txt)
            await query.edit_message_text("✅ <b>Your message was sent.</b>", parse_mode='HTML')
            await orig.reply_text("sent")
        except Exception as e:
            logger.error(f"Failed to send to user {targ_id}: {e}")
            await query.edit_message_text("❌ Failed to send.")
            await orig.reply_text("didn't sent")
        del context.user_data[f'confirm_userid_{cuuid}']
        return ConversationHandler.END
    elif data.startswith("cancel_userid:"):
        try:
            _, cuuid = data.split(':',1)
        except ValueError:
            await query.edit_message_text("Invalid data.")
            return ConversationHandler.END
        if f'confirm_userid_{cuuid}' in context.user_data:
            del context.user_data[f'confirm_userid_{cuuid}']
        await query.edit_message_text("Operation cancelled.")
        return ConversationHandler.END
    else:
        await query.edit_message_text("Invalid choice.")
        return ConversationHandler.END

# ============================= COMMANDS ==============================

async def setgroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set group name for a user (admin 6177929931 only)."""
    if update.effective_user.id != 6177929931:
        await update.message.reply_text("Not authorized.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /setgroup <user_id> <group_name>")
        return
    try:
        tgt_user = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Provide a valid user ID.")
        return
    grp_name = " ".join(context.args[1:])
    group_data[str(tgt_user)] = grp_name
    save_group_data()
    await update.message.reply_text(
        f"User {tgt_user} assigned group '{grp_name}'. If they have group_admin/group_assistant role, it shows in messages."
    )

async def taramsg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tara => group_admin & group_assistant only."""
    uid = update.effective_user.id if update.effective_user else None
    if not uid or 'tara_team' not in get_user_roles(uid):
        await update.message.reply_text("Not authorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /taramsg <message>")
        return
    msg_text = " ".join(context.args)
    targets = set()
    if 'group_admin' in ROLE_MAP:
        for x in ROLE_MAP['group_admin']:
            targets.add(x)
    if 'group_assistant' in ROLE_MAP:
        for x in ROLE_MAP['group_assistant']:
            targets.add(x)
    if not targets:
        await update.message.reply_text("No group admins/assistants found.")
        return
    from_name = get_display_name(update.effective_user)
    broadcast = f"📢 <b>Message from Tara ({from_name}) to group admins/assistants:</b>\n\n{msg_text}"
    count = 0
    for t in targets:
        try:
            await context.bot.send_message(chat_id=t, text=broadcast, parse_mode='HTML')
            count += 1
        except Exception as e:
            logger.error(f"Failed to send taramsg: {e}")
    await update.message.reply_text(f"Message sent to {count} group admins/assistants.")

async def roleadd_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != 6177929931:
        await update.message.reply_text("Not authorized.")
        return
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /roleadd <user_id> <role_name>")
        return
    try:
        tid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("User ID must be an integer.")
        return
    rname = context.args[1].lower()
    if rname not in ROLE_MAP:
        valid_roles = ", ".join(ROLE_MAP.keys())
        await update.message.reply_text(f"Invalid role. Valid: {valid_roles}")
        return
    store = ROLE_MAP[rname]
    if tid in store:
        await update.message.reply_text("User is already in that role.")
        return
    if isinstance(store, set):
        store.add(tid)
    else:
        store.append(tid)
    await update.message.reply_text(f"User {tid} added to role '{rname}'.")

async def roleremove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != 6177929931:
        await update.message.reply_text("Not authorized.")
        return
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /role_r <user_id> <role_name>")
        return
    try:
        tid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("User ID must be integer.")
        return
    rname = context.args[1].lower()
    if rname not in ROLE_MAP:
        valid_roles = ", ".join(ROLE_MAP.keys())
        await update.message.reply_text(f"Invalid role. Valid: {valid_roles}")
        return
    store = ROLE_MAP[rname]
    if tid not in store:
        await update.message.reply_text("User not in that role.")
        return
    if isinstance(store, set):
        store.remove(tid)
    else:
        store.remove(tid)
    await update.message.reply_text(f"User {tid} removed from role '{rname}'.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and user.username:
        user_data_store[user.username.lower()] = user.id
        save_user_data()
    dn = get_display_name(user) if user else "there"
    roles = get_user_roles(user.id) if user else []
    if not roles:
        await update.message.reply_text(
            f"Hello, {dn}! You have no role; your messages => anonymous feedback."
        )
    else:
        await update.message.reply_text(
            f"Hello, {dn}! Welcome to the bot. Use /help to see commands."
        )

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u:
        await update.message.reply_text("No user info.")
        return
    if 'tara_team' not in get_user_roles(u.id) and u.id != 6177929931:
        await update.message.reply_text("Not authorized.")
        return
    if not user_data_store:
        await update.message.reply_text("No users recorded.")
        return
    lines = [f"@{k} => {v}" for k, v in user_data_store.items()]
    msg = "\n".join(lines)
    await update.message.reply_text(f"<b>Registered Users:</b>\n{msg}", parse_mode='HTML')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    valid_roles = ", ".join(ROLE_MAP.keys())
    txt = (
        "<b>Available Commands</b>\n\n"
        "<b>/start</b> - Start / greet.\n"
        "<b>/listusers</b> - List all known users (tara_team or admin only).\n"
        "<b>/help</b> - Show this help.\n"
        "<b>/refresh</b> - Refresh your username info.\n"
        "<b>/cancel</b> - Cancel current operation.\n\n"
        "<b>Message Sending Triggers:</b>\n"
        "-team => send to your role + Tara.\n"
        "-t => send to Tara only.\n"
        "-@username => send to that user (Tara only).\n"
        "-w, -e, -c, -d, -de, -mf, -mcq => send to specific teams.\n\n"
        "<b>Admin/Tara Commands:</b>\n"
        "/mute [user_id], /muteid <id>, /unmuteid <id>, /listmuted\n"
        "-check <id> or /check <id> => check user.\n"
        "-user_id <id> => admin only => send message to user.\n\n"
        "<b>Role Management (admin only):</b>\n"
        f"/roleadd <id> <role>, /role_r <id> <role>\n"
        f"Valid roles: {valid_roles}\n\n"
        "<b>/setgroup <id> <group_name></b> => Assign group to user (if they are group_admin/assistant).\n"
        "<b>/taramsg</b> => Tara => broadcast to all group_admin & group_assistant.\n"
        "<b>/lecture</b> => Create multiple lectures (admin only).\n\n"
        "If you have no role => messages go as anonymous feedback.\n"
    )
    await update.message.reply_text(txt, parse_mode='HTML')

async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not user.username:
        await update.message.reply_text("Please set a Telegram username to refresh.")
        return
    user_data_store[user.username.lower()] = user.id
    save_user_data()
    await update.message.reply_text("Refreshed your info.")

async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        await update.message.reply_text("No user info.")
        return
    if 'tara_team' not in get_user_roles(user.id) and user.id != 6177929931:
        await update.message.reply_text("Not authorized.")
        return
    if len(context.args) == 0:
        targ = user.id
    elif len(context.args) == 1:
        try:
            targ = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Please provide valid user ID.")
            return
    else:
        await update.message.reply_text("Usage: /mute [user_id]")
        return

    if targ in muted_users:
        if targ == user.id:
            await update.message.reply_text("You are already muted.")
        else:
            await update.message.reply_text("This user is already muted.")
        return

    muted_users.add(targ)
    save_muted_users()
    if targ == user.id:
        await update.message.reply_text("You have been muted.")
    else:
        un = None
        for k,v in user_data_store.items():
            if v == targ:
                un = k
                break
        if un:
            await update.message.reply_text(f"User @{un} is muted.")
        else:
            await update.message.reply_text(f"User ID {targ} is muted.")

async def mute_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await mute_command(update, context)

async def unmute_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        await update.message.reply_text("No user info.")
        return
    if 'tara_team' not in get_user_roles(user.id) and user.id != 6177929931:
        await update.message.reply_text("Not authorized.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /unmuteid <user_id>")
        return
    try:
        tid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Provide a valid user ID.")
        return

    if tid in muted_users:
        muted_users.remove(tid)
        save_muted_users()
        found = None
        for k,v in user_data_store.items():
            if v == tid:
                found = k
                break
        if found:
            await update.message.reply_text(f"User @{found} is unmuted.")
        else:
            await update.message.reply_text(f"User ID {tid} is unmuted.")
    else:
        await update.message.reply_text(f"User {tid} is not muted.")

async def list_muted_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        await update.message.reply_text("No user info.")
        return
    if 'tara_team' not in get_user_roles(user.id) and user.id != 6177929931:
        await update.message.reply_text("Not authorized.")
        return
    if not muted_users:
        await update.message.reply_text("No users currently muted.")
        return
    lines = []
    for x in muted_users:
        found = None
        for k,v in user_data_store.items():
            if v == x:
                found = k
                break
        if found:
            lines.append(f"@{found} (ID: {x})")
        else:
            lines.append(f"ID: {x}")
    txt = "\n".join(lines)
    await update.message.reply_text(f"<b>Muted Users:</b>\n{txt}", parse_mode='HTML')

async def check_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != 6177929931:
        await update.message.reply_text("Not authorized.")
        return
    if (context.args is None or len(context.args)==0) and update.message:
        txt = update.message.text.strip()
        mm = re.match(r'^-check\s+(\d+)$', txt, re.IGNORECASE)
        if not mm:
            await update.message.reply_text("Usage: -check <user_id>")
            return
        cid = int(mm.group(1))
    else:
        if len(context.args) != 1:
            await update.message.reply_text("Usage: /check <user_id>")
            return
        try:
            cid = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Please provide valid ID.")
            return
    found_un = None
    for k,v in user_data_store.items():
        if v == cid:
            found_un = k
            break
    if not found_un:
        await update.message.reply_text(f"No record for ID {cid}.")
        return
    roles = get_user_roles(cid)
    if roles:
        rr = ", ".join(ROLE_DISPLAY_NAMES.get(r,r.capitalize()) for r in roles)
    else:
        rr = "No role"
    await update.message.reply_text(
        f"User ID: <code>{cid}</code>\nUsername: @{found_un}\nRoles: {rr}",
        parse_mode='HTML'
    )

# ================== ConversationHandlers ==================

# 1) -user_id
async def user_id_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != 6177929931:
        await update.message.reply_text("Not authorized.")
        return ConversationHandler.END
    txt = update.message.text.strip()
    mm = re.match(r'^-user_id\s+(\d+)$', txt, re.IGNORECASE)
    if not mm:
        await update.message.reply_text("Usage: -user_id <user_id>")
        return ConversationHandler.END
    tid = int(mm.group(1))
    await update.message.reply_text(f"Write the message for user {tid}. Then I'll confirm.")
    context.user_data['target_user_id_userid'] = tid
    return SPECIFIC_USER_MESSAGE

async def user_id_message_collector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    tid = context.user_data.get('target_user_id_userid', None)
    if not tid:
        await msg.reply_text("Error no target id.")
        return ConversationHandler.END
    if msg.document:
        desc = f"PDF: `{msg.document.file_name}`"
    elif msg.text:
        desc = f"Message: `{msg.text}`"
    else:
        desc = "Unsupported message type."
    ctext = (
        f"📩 <b>Send to user ID {tid}:</b>\n\n"
        f"{desc}\n\n"
        "Do you want to send this?"
    )
    cuuid = str(uuid.uuid4())
    kb = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f'confirm_userid:{cuuid}'),
            InlineKeyboardButton("❌ Cancel", callback_data=f'cancel_userid:{cuuid}')
        ]
    ]
    rm = InlineKeyboardMarkup(kb)
    await msg.reply_text(ctext, parse_mode='HTML', reply_markup=rm)
    context.user_data[f'confirm_userid_{cuuid}'] = {
        'target_id': tid,
        'original_message': msg,
        'msg_text': msg.text if msg.text else "",
        'msg_doc': msg.document if msg.document else None,
    }
    del context.user_data['target_user_id_userid']
    return CONFIRMATION

user_id_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(re.compile(r'^-user_id\s+(\d+)$', re.IGNORECASE)), user_id_trigger)],
    states={
        SPECIFIC_USER_MESSAGE: [
            MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, user_id_message_collector)
        ],
        CONFIRMATION: [
            CallbackQueryHandler(confirmation_handler, pattern='^(confirm:|cancel:|confirm_no_role:|confirm_userid:|cancel_userid:).*')
        ],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    per_message=True
)

# 2) -@username => Tara => specific user
async def specific_user_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if 'tara_team' not in get_user_roles(uid):
        await update.message.reply_text("Not authorized.")
        return ConversationHandler.END
    mm = re.match(r'^\s*-\@([A-Za-z0-9_]{5,32})\s*$', update.message.text, re.IGNORECASE)
    if not mm:
        await update.message.reply_text("Usage: -@username")
        return ConversationHandler.END
    tname = mm.group(1).lower()
    tid = user_data_store.get(tname)
    if not tid:
        await update.message.reply_text(f"User @{tname} not found.")
        return ConversationHandler.END
    context.user_data['target_user_id'] = tid
    context.user_data['sender_role'] = 'tara_team'
    await update.message.reply_text(f"Write your message for @{tname}.")
    return SPECIFIC_USER_MESSAGE

async def specific_user_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    tgt = context.user_data.get('target_user_id')
    if not tgt:
        await msg.reply_text("Error.")
        return ConversationHandler.END
    context.user_data['target_ids'] = [tgt]
    context.user_data['target_roles'] = ['specific_user']
    srole = context.user_data.get('sender_role','tara_team')
    await send_confirmation(msg, context, srole, [tgt], target_roles=['specific_user'])
    return CONFIRMATION

specific_user_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(re.compile(r'^\s*-\@([A-Za-z0-9_]{5,32})\s*$', re.IGNORECASE)), specific_user_trigger)],
    states={
        SPECIFIC_USER_MESSAGE: [
            MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, specific_user_message_handler)
        ],
        CONFIRMATION: [
            CallbackQueryHandler(confirmation_handler, pattern='^(confirm:|cancel:|confirm_no_role:|confirm_userid:|cancel_userid:).*')
        ]
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    per_message=True
)

# 3) -w, -e, etc => Tara => specific team
async def specific_team_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if 'tara_team' not in get_user_roles(uid):
        await update.message.reply_text("Not authorized.")
        return ConversationHandler.END
    txt = update.message.text.strip().lower()
    troles = TRIGGER_TARGET_MAP.get(txt)
    if not troles:
        await update.message.reply_text("Invalid trigger.")
        return ConversationHandler.END
    context.user_data['specific_target_roles'] = troles
    context.user_data['sender_role'] = 'tara_team'
    await update.message.reply_text("Write your message for that team.")
    return SPECIFIC_TEAM_MESSAGE

async def specific_team_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    troles = context.user_data.get('specific_target_roles',[])
    tids = set()
    for r in troles:
        tids.update(ROLE_MAP.get(r, []))
    uid = update.effective_user.id
    if uid in tids:
        tids.remove(uid)
    if not tids:
        await msg.reply_text("No recipients.")
        return ConversationHandler.END
    srole = context.user_data.get('sender_role','tara_team')
    await send_confirmation(msg, context, srole, list(tids), target_roles=troles)
    return CONFIRMATION

specific_team_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(re.compile(r'^-(w|e|mcq|d|de|mf|c)$', re.IGNORECASE)), specific_team_trigger)],
    states={
        SPECIFIC_TEAM_MESSAGE: [
            MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, specific_team_message_handler)
        ],
        CONFIRMATION: [
            CallbackQueryHandler(confirmation_handler, pattern='^(confirm:|cancel:|confirm_no_role:|confirm_userid:|cancel_userid:).*')
        ]
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    per_message=True
)

# 4) -team => send to your role + Tara
async def team_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        await update.message.reply_text("Could not get your user info.")
        return ConversationHandler.END
    uid = user.id
    roles = get_user_roles(uid)
    if not roles:
        return await handle_general_message(update, context)
    if len(roles) > 1:
        kb = get_role_selection_keyboard(roles)
        context.user_data['pending_message'] = update.message
        await update.message.reply_text("You have multiple roles. Choose:", reply_markup=kb)
        return SELECT_ROLE
    else:
        sr = roles[0]
        context.user_data['sender_role'] = sr
        await update.message.reply_text("Write your message for your role + Tara.")
        return TEAM_MESSAGE

async def team_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    sr = context.user_data.get('sender_role', None)
    if not sr:
        await msg.reply_text("Error.")
        return ConversationHandler.END
    uid = update.effective_user.id
    troles = [sr, 'tara_team']
    tids = set()
    for x in troles:
        tids.update(ROLE_MAP.get(x, []))
    if uid in tids:
        tids.remove(uid)
    if not tids:
        await msg.reply_text("No recipients.")
        return ConversationHandler.END
    await send_confirmation(msg, context, sr, list(tids), target_roles=troles)
    return CONFIRMATION

async def select_role_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("role:"):
        sr = data.split(":")[1]
        context.user_data['sender_role'] = sr
        pm = context.user_data.get('pending_message', None)
        if not pm:
            await query.edit_message_text("Error.")
            return ConversationHandler.END
        del context.user_data['pending_message']
        txt = pm.text.strip().lower() if pm.text else ""
        if txt == '-team':
            t_roles = [sr, 'tara_team']
        else:
            t_roles = SENDING_ROLE_TARGETS.get(sr, [])
        tids = set()
        for x in t_roles:
            tids.update(ROLE_MAP.get(x,[]))
        user_id = query.from_user.id
        if user_id in tids:
            tids.remove(user_id)
        if not tids:
            await query.edit_message_text("No recipients found.")
            return ConversationHandler.END
        await send_confirmation(pm, context, sr, list(tids), target_roles=t_roles)
        await query.edit_message_text("Processing your message...")
        return CONFIRMATION
    elif data == 'cancel_role_selection':
        await query.edit_message_text("Operation cancelled.")
        return ConversationHandler.END
    else:
        await query.edit_message_text("Invalid role selection.")
        return ConversationHandler.END

# 5) -t => send to Tara only
async def tara_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        await update.message.reply_text("No user info.")
        return ConversationHandler.END
    rs = get_user_roles(user.id)
    if not rs:
        return await handle_general_message(update, context)
    context.user_data['sender_role'] = rs[0]
    await update.message.reply_text("Write your message for Tara Team.")
    return TARA_MESSAGE

async def tara_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    sr = context.user_data.get('sender_role')
    uid = update.effective_user.id
    if not sr or not uid:
        return ConversationHandler.END
    t_roles = ['tara_team']
    tids = set(ROLE_MAP.get('tara_team',[]))
    if uid in tids:
        tids.remove(uid)
    if not tids:
        await msg.reply_text("No recipients found.")
        return ConversationHandler.END
    await send_confirmation(msg, context, sr, list(tids), target_roles=t_roles)
    return CONFIRMATION

# handle general => if user has no role => anonymous
async def handle_general_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return ConversationHandler.END
    user = update.effective_user
    if not user:
        return ConversationHandler.END
    uid = user.id
    if uid in muted_users:
        await msg.reply_text("You are muted and cannot send messages.")
        return ConversationHandler.END
    if user.username:
        unl = user.username.lower()
        old_id = user_data_store.get(unl)
        if old_id != uid:
            user_data_store[unl] = uid
            save_user_data()
    roles = get_user_roles(uid)
    if not roles:
        cuuid = str(uuid.uuid4())
        context.user_data[f'confirm_{cuuid}'] = {
            'message': msg,
            'sender_role': 'no_role'
        }
        kb = [
            [
                InlineKeyboardButton("✅ Send feedback", callback_data=f'confirm_no_role:{cuuid}'),
                InlineKeyboardButton("❌ Cancel", callback_data=f'cancel:{cuuid}'),
            ]
        ]
        rm = InlineKeyboardMarkup(kb)
        text2 = "You have no roles. Send this as <b>anonymous feedback</b> to all teams?"
        await msg.reply_text(text2, parse_mode='HTML', reply_markup=rm)
        return CONFIRMATION
    if len(roles)>1:
        keyboard = get_role_selection_keyboard(roles)
        context.user_data['pending_message'] = msg
        await msg.reply_text("You have multiple roles. Which do you want to use?", reply_markup=keyboard)
        return SELECT_ROLE
    else:
        sr = roles[0]
        context.user_data['sender_role'] = sr
        t_roles = SENDING_ROLE_TARGETS.get(sr, [])
        tids = set()
        for x in t_roles:
            tids.update(ROLE_MAP.get(x, []))
        if uid in tids:
            tids.remove(uid)
        if not tids:
            await msg.reply_text("No recipients found.")
            return ConversationHandler.END
        await send_confirmation(msg, context, sr, list(tids), target_roles=t_roles)
        return CONFIRMATION

# ========================== LECTURE FEATURE ==========================
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
    """Admin only => create multiple lectures."""
    if update.effective_user.id != 6177929931:
        await update.message.reply_text("Not authorized for /lecture.")
        return ConversationHandler.END
    await update.message.reply_text("How many lectures do you want to create? (1-50)")
    return LECTURE_ASK_COUNT

async def lecture_ask_count_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        count = int(text)
        if count<1 or count>50:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Please enter a valid integer (1-50).")
        return ConversationHandler.END

    LECTURE_DATA['count'] = count
    LECTURE_DATA['registrations'] = {}
    for i in range(1, count+1):
        LECTURE_DATA['registrations'][i] = {
            'writer': [],
            'editor': [],
            'digital': [],
            'designer': [],
            'mcqs': [],
            'mindmaps': [],
            'note': [],
            'group': None
        }

    all_ids = set()
    for rids in ROLE_MAP.values():
        for x in rids:
            all_ids.add(x)

    # send them the initial
    for uid in all_ids:
        try:
            msg = await context.bot.send_message(chat_id=uid, text=_lecture_status_text(), parse_mode='HTML')
            LECTURE_DATA['message_ids'][uid] = (uid, msg.message_id)
            await context.bot.edit_message_reply_markup(
                chat_id=uid,
                message_id=msg.message_id,
                reply_markup=_lecture_build_keyboard()
            )
        except Exception as e:
            logger.error(f"Failed to send lecture registration to {uid}: {e}")

    await update.message.reply_text(f"Created {count} lectures. Everyone notified.")
    return ConversationHandler.END

def _lecture_status_text():
    lines = ["<b>Lecture Registrations</b>"]
    if LECTURE_DATA['count'] == 0:
        return "No lectures created yet."
    for i in range(1, LECTURE_DATA['count']+1):
        data = LECTURE_DATA['registrations'][i]
        line = f"\n<b>Lecture {i}:</b>\n"
        line += f"Writer: {_fmt_lecture_list(data['writer'])}\n"
        line += f"Editor: {_fmt_lecture_list(data['editor'])}\n"
        line += f"Digital: {_fmt_lecture_list(data['digital'])}\n"
        line += f"Designer: {_fmt_lecture_list(data['designer'])}\n"
        line += f"MCQs: {_fmt_lecture_list(data['mcqs'])}\n"
        line += f"Mindmaps: {_fmt_lecture_list(data['mindmaps'])}\n"
        line += f"Note: {_fmt_lecture_list(data['note'])}\n"
        line += f"Group: {data['group'] if data['group'] else 'None'}\n"
        lines.append(line)
    return "\n".join(lines)

def _fmt_lecture_list(lst):
    if not lst:
        return "None"
    return ", ".join(str(x) for x in lst)

def _lecture_build_keyboard():
    if LECTURE_DATA['count']==0:
        return None
    kb = [[InlineKeyboardButton("Register/Unregister", callback_data="lectureReg:openMenu")]]
    return InlineKeyboardMarkup(kb)

async def lecture_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "lectureReg:openMenu":
        kb = []
        row = []
        for i in range(1, LECTURE_DATA['count']+1):
            row.append(InlineKeyboardButton(str(i), callback_data=f"lectureReg:pickLecture:{i}"))
            if len(row)==8:
                kb.append(row)
                row=[]
        if row:
            kb.append(row)
        kb.append([InlineKeyboardButton("Cancel", callback_data="lectureReg:cancel")])
        await query.edit_message_text("Pick a Lecture number:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("lectureReg:pickLecture:"):
        parts = data.split(":")
        lecture_idx = int(parts[2])
        fields = ["writer","editor","digital","designer","mcqs","mindmaps","note","group"]
        kb = []
        row=[]
        for f in fields:
            row.append(InlineKeyboardButton(f.capitalize(), callback_data=f"lectureReg:pickField:{lecture_idx}:{f}"))
            if len(row)==3:
                kb.append(row)
                row=[]
        if row:
            kb.append(row)
        kb.append([InlineKeyboardButton("Cancel", callback_data="lectureReg:cancel")])
        await query.edit_message_text(f"Lecture {lecture_idx}: pick a field to register/unregister.", 
                                      reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("lectureReg:pickField:"):
        # format: lectureReg:pickField:idx:field
        parts = data.split(":")
        lecture_idx = int(parts[2])
        field_name = parts[3]
        user_id = query.from_user.id
        reg_list = LECTURE_DATA['registrations'][lecture_idx][field_name]
        if field_name == "note":
            if user_id not in reg_list:
                reg_list.append(user_id)
                msg="You registered for Note."
            else:
                reg_list.remove(user_id)
                msg="You unregistered from Note."
        elif field_name=="group":
            roles = get_user_roles(user_id)
            if "group_admin" not in roles:
                await query.edit_message_text("You do not have permission to assign a group.")
                return
            current = LECTURE_DATA['registrations'][lecture_idx]['group']
            if current is None:
                LECTURE_DATA['registrations'][lecture_idx]['group'] = f"ChosenBy_{user_id}"
                msg="You assigned a group for this lecture."
            else:
                LECTURE_DATA['registrations'][lecture_idx]['group'] = None
                msg="You cleared the group assignment."
        else:
            needed_role = LECTURE_FIELD_ROLE_MAP[field_name]
            roles = get_user_roles(user_id)
            if needed_role not in roles:
                await query.edit_message_text("You do not have the required role for that field.")
                return
            if user_id in reg_list:
                reg_list.remove(user_id)
                msg=f"You unregistered from {field_name.capitalize()}."
            else:
                reg_list.append(user_id)
                msg=f"You registered for {field_name.capitalize()}."
        await _lecture_update_all(context)
        await query.edit_message_text(msg)
        return

    if data == "lectureReg:cancel":
        await query.edit_message_text("Cancelled.")
        return

async def _lecture_update_all(context: ContextTypes.DEFAULT_TYPE):
    text = _lecture_status_text()
    for uid,(chat_id,msg_id) in LECTURE_DATA['message_ids'].items():
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=text,
                parse_mode='HTML',
                reply_markup=_lecture_build_keyboard()
            )
        except Exception as e:
            logger.debug(f"Could not update lecture for {uid}: {e}")

lecture_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("lecture", lecture_command)],
    states={
        LECTURE_ASK_COUNT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, lecture_ask_count_handler)
        ],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    per_message=True
)
lecture_callbackquery_handler = CallbackQueryHandler(lecture_callback_handler, pattern="^lectureReg:")

# ======================== ERROR HANDLER =========================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {context.error}", exc_info=True)
    if isinstance(update, Update) and update.message:
        try:
            await update.message.reply_text("An error occurred.")
        except:
            pass

# ============================= MAIN =============================

def main():
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set.")
        return

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Basic commands
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
    application.add_handler(
        MessageHandler(
            filters.Regex(re.compile(r'^-check\s+(\d+)$', re.IGNORECASE)),
            check_user_command
        )
    )

    # Role add/remove
    application.add_handler(CommandHandler('roleadd', roleadd_command))
    application.add_handler(CommandHandler('role_r', roleremove_command))

    # Group set + Tara broadcast
    application.add_handler(CommandHandler('setgroup', setgroup_command))
    application.add_handler(CommandHandler('taramsg', taramsg_command))

    # Conversation handlers
    application.add_handler(user_id_conv_handler)
    application.add_handler(specific_user_conv_handler)
    application.add_handler(specific_team_conv_handler)

    # -team => role + Tara
    team_conv = ConversationHandler(
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
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=True
    )
    application.add_handler(team_conv)

    # -t => Tara only
    tara_conv = ConversationHandler(
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
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=True
    )
    application.add_handler(tara_conv)

    # General messages
    general_conv = ConversationHandler(
        entry_points=[
            MessageHandler(
                (filters.TEXT | filters.Document.ALL)
                & ~filters.COMMAND
                & ~filters.Regex(re.compile(r'^-@', re.IGNORECASE))
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
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=True,
        allow_reentry=True
    )
    application.add_handler(general_conv)

    # Lecture system
    application.add_handler(lecture_conv_handler)
    application.add_handler(lecture_callbackquery_handler)

    application.add_error_handler(error_handler)

    logger.info("Bot started polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
