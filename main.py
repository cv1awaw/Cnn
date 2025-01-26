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

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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

if 'group_admin' not in ROLE_MAP:
    ROLE_MAP['group_admin'] = []
ROLE_DISPLAY_NAMES['group_admin'] = "Group Admin"

if 'group_assistant' not in ROLE_MAP:
    ROLE_MAP['group_assistant'] = []
ROLE_DISPLAY_NAMES['group_assistant'] = "Group Assistant"

TRIGGER_TARGET_MAP = {
    '-w': ['writer'],
    '-e': ['checker_team'],
    '-mcq': ['mcqs_team'],
    '-d': ['word_team'],
    '-de': ['design_team'],
    '-mf': ['mind_map_form_creator'],
    '-c': ['checker_team'],
}
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

TEAM_MESSAGE = 1
SPECIFIC_TEAM_MESSAGE = 2
SPECIFIC_USER_MESSAGE = 3
TARA_MESSAGE = 4
CONFIRMATION = 5
SELECT_ROLE = 6

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

def get_display_name(user):
    if user.username:
        return f"@{user.username}"
    else:
        return user.first_name + (f" {user.last_name}" if user.last_name else "")

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

async def forward_message(bot, message, target_ids, sender_role):
    user = message.from_user
    username_display = get_display_name(user)
    role_display = ROLE_DISPLAY_NAMES.get(sender_role, sender_role.capitalize())
    user_roles = get_user_roles(user.id)
    group_string = ""
    if "group_admin" in user_roles or "group_assistant" in user_roles:
        if str(user.id) in group_data:
            grp_name = group_data[str(user.id)]
            group_string = f", {grp_name}"
        role_display = f"{role_display}{group_string}"
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
        desc = f"PDF: `{message.document.file_name}`"
    elif message.text:
        desc = f"Message: `{message.text}`"
    else:
        desc = "Unsupported message type."
    if target_roles:
        tr_disp = [ROLE_DISPLAY_NAMES.get(r, r.capitalize()) for r in target_roles]
    else:
        tr_disp = [ROLE_DISPLAY_NAMES.get(r, r.capitalize()) for r in SENDING_ROLE_TARGETS.get(sender_role, [])]
    text = (
        f"📩 *You are about to send the following to **{', '.join(tr_disp)}**:*\n\n"
        f"{desc}\n\n"
        "Do you want to send this?"
    )
    uid = str(uuid.uuid4())
    kb = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f'confirm:{uid}'),
            InlineKeyboardButton("❌ Cancel", callback_data=f'cancel:{uid}')
        ]
    ]
    rm = InlineKeyboardMarkup(kb)
    await message.reply_text(text, parse_mode='Markdown', reply_markup=rm)
    context.user_data[f'confirm_{uid}'] = {
        'message': message,
        'target_ids': target_ids,
        'sender_role': sender_role,
        'target_roles': target_roles if target_roles else SENDING_ROLE_TARGETS.get(sender_role, [])
    }

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
            _, cuuid = data.split(':', 1)
        except ValueError:
            await query.edit_message_text("Invalid.")
            return ConversationHandler.END
        cdata = context.user_data.get(f'confirm_{cuuid}')
        if not cdata:
            await query.edit_message_text("Error occurred.")
            return ConversationHandler.END
        msg = cdata['message']
        sender_id = msg.from_user.id
        special = 6177929931
        all_ids = set()
        for rids in ROLE_MAP.values():
            all_ids.update(rids)
        if sender_id in all_ids:
            all_ids.remove(sender_id)
        await forward_anonymous_message(context.bot, msg, list(all_ids))
        await query.edit_message_text("✅ *Anonymous feedback sent.*", parse_mode='Markdown')
        real_dn = get_display_name(msg.from_user)
        real_un = msg.from_user.username or "No username"
        real_id = msg.from_user.id
        info = (
            "🔒 *Anonymous Sender Info*\n\n"
            f"- User ID: `{real_id}`\n"
            f"- Username: @{real_un}\n"
            f"- Full name: {real_dn}"
        )
        try:
            await context.bot.send_message(chat_id=special, text=info, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send real info: {e}")
        del context.user_data[f'confirm_{cuuid}']
        return ConversationHandler.END
    if data.startswith('confirm:') or data.startswith('cancel:'):
        try:
            action, cuuid = data.split(':', 1)
        except ValueError:
            await query.edit_message_text("Invalid confirm data.")
            return ConversationHandler.END
        cdata = context.user_data.get(f'confirm_{cuuid}', None)
        if not cdata:
            pass
        else:
            if action == 'confirm':
                msg2 = cdata['message']
                tids = cdata['target_ids']
                srole = cdata['sender_role']
                troles = cdata.get('target_roles', [])
                await forward_message(context.bot, msg2, tids, srole)
                sdisp = ROLE_DISPLAY_NAMES.get(srole, srole.capitalize())
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
                    txt = (
                        f"✅ *Your PDF `{msg2.document.file_name}` has been sent "
                        f"from **{sdisp}** to **{', '.join(rnames)}**.*"
                    )
                elif msg2.text:
                    txt = (
                        f"✅ *Your message has been sent from **{sdisp}** "
                        f"to **{', '.join(rnames)}**.*"
                    )
                else:
                    txt = (
                        f"✅ *Your message has been sent from **{sdisp}** "
                        f"to **{', '.join(rnames)}**.*"
                    )
                await query.edit_message_text(txt, parse_mode='Markdown')
                del context.user_data[f'confirm_{cuuid}']
            elif action == 'cancel':
                await query.edit_message_text("Operation cancelled.")
                if f'confirm_{cuuid}' in context.user_data:
                    del context.user_data[f'confirm_{cuuid}']
            return ConversationHandler.END
    if data.startswith("confirm_userid:"):
        try:
            _, cuuid = data.split(':', 1)
        except ValueError:
            await query.edit_message_text("Invalid data.")
            return ConversationHandler.END
        cdata = context.user_data.get(f'confirm_userid_{cuuid}', None)
        if not cdata:
            await query.edit_message_text("Error.")
            return ConversationHandler.END
        txt = cdata['msg_text']
        doc = cdata['msg_doc']
        targid = cdata['target_id']
        origmsg = cdata['original_message']
        try:
            if doc:
                await context.bot.send_document(chat_id=targid, document=doc.file_id, caption=doc.caption or "")
            else:
                await context.bot.send_message(chat_id=targid, text=txt)
            await query.edit_message_text("✅ *Your message has been sent.*", parse_mode='Markdown')
            await origmsg.reply_text("sent")
        except Exception as e:
            logger.error(f"Failed to send to user {targid}: {e}")
            await query.edit_message_text("❌ Failed to send.")
            await origmsg.reply_text("didn't sent")
        del context.user_data[f'confirm_userid_{cuuid}']
        return ConversationHandler.END
    elif data.startswith("cancel_userid:"):
        try:
            _, cuuid = data.split(':', 1)
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

async def taramsg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else None
    if not uid:
        await update.message.reply_text("No user info.")
        return
    if 'tara_team' not in get_user_roles(uid):
        await update.message.reply_text("Not authorized for /taramsg.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /taramsg <message>")
        return
    msg_txt = " ".join(context.args)
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
    from_dn = get_display_name(update.effective_user)
    final_text = f"📢 *Message from Tara ({from_dn}) to group admins/assistants:*\n\n{msg_txt}"
    succ = 0
    for t in targets:
        try:
            await context.bot.send_message(chat_id=t, text=final_text, parse_mode='Markdown')
            succ += 1
        except Exception as e:
            logger.error(f"Failed to send taramsg to {t}: {e}")
    await update.message.reply_text(f"Message sent to {succ} group admins/assistants.")

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
        await update.message.reply_text("Provide a valid user ID.")
        return
    rn = context.args[1].lower()
    if rn not in ROLE_MAP:
        valids = ", ".join(ROLE_MAP.keys())
        await update.message.reply_text(f"Invalid role. Valid: {valids}")
        return
    lst = ROLE_MAP[rn]
    if tid in lst:
        await update.message.reply_text("User already in that role.")
        return
    if isinstance(lst, set):
        lst.add(tid)
    else:
        lst.append(tid)
    await update.message.reply_text(f"User {tid} added to role '{rn}'.")

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
        await update.message.reply_text("Provide a valid user ID.")
        return
    rn = context.args[1].lower()
    if rn not in ROLE_MAP:
        valids = ", ".join(ROLE_MAP.keys())
        await update.message.reply_text(f"Invalid role. Valid: {valids}")
        return
    lst = ROLE_MAP[rn]
    if tid not in lst:
        await update.message.reply_text("User not in that role.")
        return
    if isinstance(lst, set):
        lst.remove(tid)
    else:
        lst.remove(tid)
    await update.message.reply_text(f"User {tid} removed from role '{rn}'.")

async def setgroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != 6177929931:
        await update.message.reply_text("Not authorized.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /setgroup <user_id> <group_name>")
        return
    try:
        tgt = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Provide valid user ID.")
        return
    grp_name = " ".join(context.args[1:])
    group_data[str(tgt)] = grp_name
    save_group_data()
    await update.message.reply_text(
        f"User {tgt} assigned group '{grp_name}'. If they are group_admin/assistant, messages show it."
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and user.username:
        uname_l = user.username.lower()
        user_data_store[uname_l] = user.id
        save_user_data()
    dn = get_display_name(user) if user else "there"
    roles = get_user_roles(user.id) if user else []
    if not roles:
        await update.message.reply_text(
            f"Hello, {dn}! You have no role. Messages => anonymous feedback."
        )
    else:
        await update.message.reply_text(
            f"Hello, {dn}! Welcome. Use /help for commands."
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
        await update.message.reply_text("No users are registered.")
        return
    lines = [f"@{k} => {v}" for k, v in user_data_store.items()]
    msg = "\n".join(lines)
    await update.message.reply_text(f"**Registered Users:**\n{msg}", parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = ", ".join(ROLE_MAP.keys())
    txt = (
        "📘 *Commands:*\n\n"
        "/start\n"
        "/listusers (tara/admin)\n"
        "/help\n"
        "/refresh\n"
        "/cancel\n"
        "/mute [id], /muteid <id>, /unmuteid <id>, /listmuted\n"
        "`-check <id>` or `/check <id>`\n"
        "`-user_id <id>` (admin)\n"
        "/roleadd <id> <role>, /role_r <id> <role>\n"
        f"Valid roles: {val}\n\n"
        "/setgroup <id> <name> => set user's group name (admin). If user is group_admin/assistant, their messages show the group.\n"
        "/taramsg => broadcast to group_admin & group_assistant\n"
        "/lecture => create multiple lectures (admin)\n"
        "If no role => anonymous feedback.\n"
        "Message triggers:\n"
        "`-team`, `-t`, `-@username`, `-w`, `-e`, `-mcq`, `-d`, `-de`, `-mf`, `-c`.\n"
    )
    await update.message.reply_text(txt, parse_mode='Markdown')

async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not user.username:
        await update.message.reply_text("Set a username first.")
        return
    unl = user.username.lower()
    user_data_store[unl] = user.id
    save_user_data()
    await update.message.reply_text("Refreshed.")

async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u:
        await update.message.reply_text("No user info.")
        return
    if 'tara_team' not in get_user_roles(u.id) and u.id != 6177929931:
        await update.message.reply_text("Not authorized.")
        return
    if len(context.args) == 0:
        target = u.id
    elif len(context.args) == 1:
        try:
            target = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Valid user ID.")
            return
    else:
        await update.message.reply_text("Usage: /mute [id]")
        return
    if target in muted_users:
        if target == u.id:
            await update.message.reply_text("You are already muted.")
        else:
            await update.message.reply_text("User is already muted.")
        return
    muted_users.add(target)
    save_muted_users()
    if target == u.id:
        await update.message.reply_text("You are muted.")
    else:
        un = None
        for k, v in user_data_store.items():
            if v == target:
                un = k
                break
        if un:
            await update.message.reply_text(f"User `@{un}` is muted.", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"User ID {target} is muted.")

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
        await update.message.reply_text("Usage: /unmuteid <id>")
        return
    try:
        t = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Valid ID.")
        return
    if t in muted_users:
        muted_users.remove(t)
        save_muted_users()
        found = None
        for k, v in user_data_store.items():
            if v == t:
                found = k
                break
        if found:
            await update.message.reply_text(f"User `@{found}` is unmuted.", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"User ID {t} is unmuted.")
    else:
        await update.message.reply_text(f"User {t} is not muted.")

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
        found = None
        for k, v in user_data_store.items():
            if v == x:
                found = k
                break
        if found:
            lines.append(f"@{found} (ID: {x})")
        else:
            lines.append(f"ID: {x}")
    await update.message.reply_text(f"**Muted Users:**\n" + "\n".join(lines), parse_mode='Markdown')

async def check_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != 6177929931:
        await update.message.reply_text("Not authorized.")
        return
    if (context.args is None or len(context.args) == 0) and update.message:
        mt = update.message.text.strip()
        mm = re.match(r'^-check\s+(\d+)$', mt, re.IGNORECASE)
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
            await update.message.reply_text("Valid ID.")
            return
    found_un = None
    for k, v in user_data_store.items():
        if v == cid:
            found_un = k
            break
    if not found_un:
        await update.message.reply_text(f"No record for ID {cid}.")
        return
    r = get_user_roles(cid)
    if r:
        rr = ", ".join(ROLE_DISPLAY_NAMES.get(x, x.capitalize()) for x in r)
    else:
        rr = "No role"
    await update.message.reply_text(
        f"User ID: `{cid}`\nUsername: `@{found_un}`\nRoles: {rr}",
        parse_mode='Markdown'
    )

async def user_id_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != 6177929931:
        await update.message.reply_text("Not authorized.")
        return ConversationHandler.END
    txt = update.message.text.strip()
    mm = re.match(r'^-user_id\s+(\d+)$', txt, re.IGNORECASE)
    if not mm:
        await update.message.reply_text("Usage: `-user_id <user_id>`", parse_mode='Markdown')
        return ConversationHandler.END
    tid = int(mm.group(1))
    await update.message.reply_text(
        f"Please write the message for user {tid}. Then I'll confirm."
    )
    context.user_data['target_user_id_userid'] = tid
    return SPECIFIC_USER_MESSAGE

async def user_id_message_collector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    tid = context.user_data.get('target_user_id_userid', None)
    if not tid:
        await msg.reply_text("Error no target ID.")
        return ConversationHandler.END
    if msg.document:
        desc = f"PDF: `{msg.document.file_name}`"
    elif msg.text:
        desc = f"Message: `{msg.text}`"
    else:
        desc = "Unsupported message type."
    txt = (
        f"📩 *You are about to send the following to user ID {tid}:*\n\n"
        f"{desc}\n\nDo you want to send this?"
    )
    uid = str(uuid.uuid4())
    kb = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f'confirm_userid:{uid}'),
            InlineKeyboardButton("❌ Cancel", callback_data=f'cancel_userid:{uid}')
        ]
    ]
    rm = InlineKeyboardMarkup(kb)
    await msg.reply_text(txt, parse_mode='Markdown', reply_markup=rm)
    context.user_data[f'confirm_userid_{uid}'] = {
        'target_id': tid,
        'original_message': msg,
        'msg_text': msg.text if msg.text else "",
        'msg_doc': msg.document if msg.document else None,
    }
    del context.user_data['target_user_id_userid']
    return CONFIRMATION

user_id_conv_handler = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex(re.compile(r'^-user_id\s+(\d+)$', re.IGNORECASE)), user_id_trigger)
    ],
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

async def specific_user_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else None
    if not uid:
        await update.message.reply_text("No user ID.")
        return ConversationHandler.END
    if 'tara_team' not in get_user_roles(uid):
        await update.message.reply_text("Not authorized.")
        return ConversationHandler.END
    mm = re.match(r'^\s*-\@([A-Za-z0-9_]{5,32})\s*$', update.message.text, re.IGNORECASE)
    if not mm:
        await update.message.reply_text("Usage: `-@username`", parse_mode='Markdown')
        return ConversationHandler.END
    tname = mm.group(1).lower()
    tuser_id = user_data_store.get(tname)
    if not tuser_id:
        await update.message.reply_text(f"User `@{tname}` not found.", parse_mode='Markdown')
        return ConversationHandler.END
    context.user_data['target_user_id'] = tuser_id
    context.user_data['target_username'] = tname
    context.user_data['sender_role'] = 'tara_team'
    await update.message.reply_text(f"Write your message for user `@{tname}`.", parse_mode='Markdown')
    return SPECIFIC_USER_MESSAGE

async def specific_user_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    t_id = context.user_data.get('target_user_id', None)
    if not t_id:
        await msg.reply_text("Error occurred.")
        return ConversationHandler.END
    context.user_data['target_ids'] = [t_id]
    context.user_data['target_roles'] = ['specific_user']
    s_role = context.user_data.get('sender_role', 'tara_team')
    await send_confirmation(msg, context, s_role, [t_id], target_roles=['specific_user'])
    return CONFIRMATION

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
    per_message=True
)

async def specific_team_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else None
    if not uid:
        await update.message.reply_text("No user ID.")
        return ConversationHandler.END
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
    troles = context.user_data.get('specific_target_roles', [])
    tids = set()
    for r in troles:
        tids.update(ROLE_MAP.get(r, []))
    uid = update.effective_user.id
    if uid in tids:
        tids.remove(uid)
    if not tids:
        await msg.reply_text("No recipients found.")
        return ConversationHandler.END
    srole = context.user_data.get('sender_role', 'tara_team')
    await send_confirmation(msg, context, srole, list(tids), target_roles=troles)
    return CONFIRMATION

specific_team_conv_handler = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex(re.compile(r'^-(w|e|mcq|d|de|mf|c)$', re.IGNORECASE)), specific_team_trigger)
    ],
    states={
        SPECIFIC_TEAM_MESSAGE: [
            MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, specific_team_message_handler)
        ],
        CONFIRMATION: [
            CallbackQueryHandler(confirmation_handler, pattern='^(confirm:|cancel:|confirm_no_role:|confirm_userid:|cancel_userid:).*')
        ],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    per_message=True
)

async def team_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u:
        await update.message.reply_text("No user.")
        return ConversationHandler.END
    uid = u.id
    rs = get_user_roles(uid)
    if not rs:
        return await handle_general_message(update, context)
    if len(rs) > 1:
        kb = get_role_selection_keyboard(rs)
        context.user_data['pending_message'] = update.message
        await update.message.reply_text("You have multiple roles. Choose:", reply_markup=kb)
        return SELECT_ROLE
    else:
        sr = rs[0]
        context.user_data['sender_role'] = sr
        await update.message.reply_text("Write your message for your role + Tara.")
        return TEAM_MESSAGE

async def team_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    sr = context.user_data.get('sender_role', None)
    uid = update.effective_user.id if update.effective_user else None
    if not sr or not uid:
        await msg.reply_text("Error occurred.")
        return ConversationHandler.END
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
    dt = query.data
    if dt.startswith('role:'):
        sr = dt.split(':')[1]
        context.user_data['sender_role'] = sr
        pm = context.user_data.get('pending_message', None)
        if not pm:
            await query.edit_message_text("Error.")
            return ConversationHandler.END
        del context.user_data['pending_message']
        ctext = pm.text.strip().lower() if pm.text else ""
        if ctext == '-team':
            troles = [sr, 'tara_team']
        else:
            troles = SENDING_ROLE_TARGETS.get(sr, [])
        tids = set()
        for r in troles:
            tids.update(ROLE_MAP.get(r, []))
        user_id = query.from_user.id
        if user_id in tids:
            tids.remove(user_id)
        if not tids:
            await query.edit_message_text("No recipients.")
            return ConversationHandler.END
        await send_confirmation(pm, context, sr, list(tids), target_roles=troles)
        await query.edit_message_text("Processing...")
        return CONFIRMATION
    elif dt == 'cancel_role_selection':
        await query.edit_message_text("Operation cancelled.")
        return ConversationHandler.END
    else:
        await query.edit_message_text("Invalid role selection.")
        return ConversationHandler.END

async def tara_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u:
        await update.message.reply_text("No user.")
        return ConversationHandler.END
    rs = get_user_roles(u.id)
    if not rs:
        return await handle_general_message(update, context)
    context.user_data['sender_role'] = rs[0]
    await update.message.reply_text("Write your message for Tara Team.")
    return TARA_MESSAGE

async def tara_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    uid = update.effective_user.id if update.effective_user else None
    sr = context.user_data.get('sender_role', None)
    if not sr or not uid:
        return ConversationHandler.END
    troles = ['tara_team']
    tids = set(ROLE_MAP.get('tara_team', []))
    if uid in tids:
        tids.remove(uid)
    if not tids:
        await msg.reply_text("No recipients.")
        return ConversationHandler.END
    await send_confirmation(msg, context, sr, list(tids), target_roles=troles)
    return CONFIRMATION

async def handle_general_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return ConversationHandler.END
    u = update.effective_user
    if not u:
        return ConversationHandler.END
    uid = u.id
    if uid in muted_users:
        await msg.reply_text("You are muted.")
        return ConversationHandler.END
    if u.username:
        unl = u.username.lower()
        prev = user_data_store.get(unl)
        if prev != uid:
            user_data_store[unl] = uid
            save_user_data()
    rs = get_user_roles(uid)
    if not rs:
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
        await msg.reply_text(
            "You have no roles. Send as *anonymous feedback*?",
            parse_mode='Markdown',
            reply_markup=rm
        )
        return CONFIRMATION
    if len(rs) > 1:
        keyboard = get_role_selection_keyboard(rs)
        context.user_data['pending_message'] = msg
        await msg.reply_text(
            "You have multiple roles. Choose which to use:",
            reply_markup=keyboard
        )
        return SELECT_ROLE
    else:
        sr = rs[0]
        context.user_data['sender_role'] = sr
        troles = SENDING_ROLE_TARGETS.get(sr, [])
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
    txt = update.message.text.strip()
    try:
        c = int(txt)
        if c < 1 or c > 50:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Please enter a valid integer 1-50.")
        return ConversationHandler.END
    LECTURE_DATA['count'] = c
    LECTURE_DATA['registrations'] = {}
    for i in range(1, c+1):
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
    for v in ROLE_MAP.values():
        for x in v:
            all_ids.add(x)
    for uid in all_ids:
        try:
            m = await context.bot.send_message(chat_id=uid, text=_lecture_build_status_text())
            LECTURE_DATA['message_ids'][uid] = (uid, m.message_id)
            await context.bot.edit_message_reply_markup(
                chat_id=uid,
                message_id=m.message_id,
                reply_markup=_lecture_build_keyboard()
            )
        except Exception as e:
            logger.error(f"Could not send lecture reg to {uid}: {e}")
    await update.message.reply_text(f"Created {c} lectures. All notified.")
    return ConversationHandler.END

def _lecture_build_status_text():
    lines = []
    lines.append("**Lecture Registrations**")
    if LECTURE_DATA['count'] == 0:
        return "No lectures."
    for i in range(1, LECTURE_DATA['count']+1):
        d = LECTURE_DATA['registrations'][i]
        line = f"\n**Lecture {i}:**\n"
        line += f"Writer: { _fmt_list(d['writer']) }\n"
        line += f"Editor: { _fmt_list(d['editor']) }\n"
        line += f"Digital: { _fmt_list(d['digital']) }\n"
        line += f"Designer: { _fmt_list(d['designer']) }\n"
        line += f"MCQs: { _fmt_list(d['mcqs']) }\n"
        line += f"Mindmaps: { _fmt_list(d['mindmaps']) }\n"
        line += f"Note: { _fmt_list(d['note']) }\n"
        line += f"Group: {d['group'] if d['group'] else 'None'}\n"
        lines.append(line)
    return "\n".join(lines)

def _fmt_list(l):
    if not l:
        return "None"
    return ", ".join(str(x) for x in l)

def _lecture_build_keyboard():
    if LECTURE_DATA['count'] == 0:
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
            if len(row) == 8:
                kb.append(row)
                row = []
        if row:
            kb.append(row)
        kb.append([InlineKeyboardButton("Cancel", callback_data="lectureReg:cancel")])
        await query.edit_message_text("Choose a Lecture number:", reply_markup=InlineKeyboardMarkup(kb))
        return
    if data.startswith("lectureReg:pickLecture:"):
        _, _, num = data.split(":")
        idx = int(num)
        fields = ["writer","editor","digital","designer","mcqs","mindmaps","note","group"]
        kb = []
        row = []
        for f in fields:
            row.append(InlineKeyboardButton(f.capitalize(), callback_data=f"lectureReg:pickField:{idx}:{f}"))
            if len(row) == 3:
                kb.append(row)
                row = []
        if row:
            kb.append(row)
        kb.append([InlineKeyboardButton("Cancel", callback_data="lectureReg:cancel")])
        await query.edit_message_text(f"Lecture {idx}: pick a field to register/unregister.", reply_markup=InlineKeyboardMarkup(kb))
        return
    if data.startswith("lectureReg:pickField:"):
        _, _, num, field = data.split(":")
        idx = int(num)
        uid = query.from_user.id
        reg_list = LECTURE_DATA['registrations'][idx][field]
        if field == "note":
            if uid not in reg_list:
                reg_list.append(uid)
                msg = f"You registered for Note in Lecture {idx}."
            else:
                reg_list.remove(uid)
                msg = f"You unregistered from Note in Lecture {idx}."
        elif field == "group":
            roles = get_user_roles(uid)
            if "group_admin" not in roles:
                await query.edit_message_text("No permission to assign a group.")
                return
            cur = LECTURE_DATA['registrations'][idx]['group']
            if cur is None:
                LECTURE_DATA['registrations'][idx]['group'] = f"ChosenBy_{uid}"
                msg = f"You assigned a group for Lecture {idx}."
            else:
                LECTURE_DATA['registrations'][idx]['group'] = None
                msg = f"You cleared the group for Lecture {idx}."
        else:
            needed = LECTURE_FIELD_ROLE_MAP[field]
            rr = get_user_roles(uid)
            if needed not in rr:
                await query.edit_message_text("You do not have the required role.")
                return
            if uid in reg_list:
                reg_list.remove(uid)
                msg = f"You unregistered from {field.capitalize()} in Lecture {idx}."
            else:
                reg_list.append(uid)
                msg = f"You registered for {field.capitalize()} in Lecture {idx}."
        await _lecture_update_all(context)
        await query.edit_message_text(msg, parse_mode='Markdown')
        return
    if data == "lectureReg:cancel":
        await query.edit_message_text("Cancelled.")
        return

async def _lecture_update_all(context: ContextTypes.DEFAULT_TYPE):
    text = _lecture_build_status_text()
    for uid, (c, mid) in LECTURE_DATA['message_ids'].items():
        try:
            await context.bot.edit_message_text(
                chat_id=c,
                message_id=mid,
                text=text,
                parse_mode='Markdown',
                reply_markup=_lecture_build_keyboard()
            )
        except Exception as e:
            logger.debug(f"Could not update lecture msg for {uid}: {e}")

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

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {context.error}", exc_info=True)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text("An error occurred.")

def main():
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set.")
        return
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('listusers', list_users))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('refresh', refresh))
    application.add_handler(CommandHandler('mute', mute_command))
    application.add_handler(CommandHandler('muteid', mute_id_command))
    application.add_handler(CommandHandler('unmuteid', unmute_id_command))
    application.add_handler(CommandHandler('listmuted', list_muted_command))
    application.add_handler(CommandHandler('check', check_user_command))
    application.add_handler(MessageHandler(filters.Regex(re.compile(r'^-check\s+(\d+)$', re.IGNORECASE)), check_user_command))
    application.add_handler(CommandHandler('roleadd', roleadd_command))
    application.add_handler(CommandHandler('role_r', roleremove_command))
    application.add_handler(CommandHandler('setgroup', setgroup_command))
    application.add_handler(CommandHandler('taramsg', taramsg_command))
    application.add_handler(user_id_conv_handler)
    application.add_handler(specific_user_conv_handler)
    application.add_handler(specific_team_conv_handler)

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
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=True
    )
    application.add_handler(team_conv)

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
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=True
    )
    application.add_handler(tara_conv)

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
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=True,
        allow_reentry=True
    )
    application.add_handler(general_conv)

    application.add_handler(lecture_conv_handler)
    application.add_handler(lecture_callbackquery_handler)

    application.add_error_handler(error_handler)

    logger.info("Bot started polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
