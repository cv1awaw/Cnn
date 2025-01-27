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

                # If it's neither text nor document, forward the message

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

                # If it's neither text nor document, forward the message as-is

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

        real_user_display_name = get_display_name(message_to_send.from_user)  # Full name or @username

        real_username = message_to_send.from_user.username or "No username"

        real_id = message_to_send.from_user.id

        # Prepare the info message

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

        # If user has no roles, handle in general message

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

    # If user has no roles, handle in general message or do direct flow

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



    # If user has no role, ask for confirmation to send as anonymous feedback

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

    # Only user 6177929931 can use this command

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

        f"Please write the message (text or PDF) you want to send to user ID {target_id}.\n"

        "Then I'll ask for confirmation."

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

        await update.message.reply_text(

            f"Invalid role name. Valid roles are: {valid_roles}"

        )

        return



    role_list_or_set = ROLE_MAP[role_name]

    if target_user_id in role_list_or_set:

        await update.message.reply_text("User is already in that role.")

        return



    # Add user to the role list or set

    if isinstance(role_list_or_set, set):

        role_list_or_set.add(target_user_id)

    else:

        role_list_or_set.append(target_user_id)



    await update.message.reply_text(

        f"User ID {target_user_id} has been added to role '{role_name}'."

    )



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

        await update.message.reply_text(

            f"Invalid role name. Valid roles are: {valid_roles}"

        )

        return



    role_list_or_set = ROLE_MAP[role_name]

    if target_user_id not in role_list_or_set:

        await update.message.reply_text("User is not in that role.")

        return



    if isinstance(role_list_or_set, set):

        role_list_or_set.remove(target_user_id)

    else:

        role_list_or_set.remove(target_user_id)



    await update.message.reply_text(

        f"User ID {target_user_id} has been removed from role '{role_name}'."

    )



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

    """List all registered users (username => ID), restricted to Tara Team or user 6177929931."""

    user = update.effective_user

    if not user:

        await update.message.reply_text("Could not determine your user.")

        return



    user_id = user.id

    roles = get_user_roles(user_id)



    # Let Tara Team and special ID 6177929931 use this command

    if 'tara_team' not in roles and user_id != 6177929931:

        await update.message.reply_text("You are not authorized to use this command.")

        return



    if not user_data_store:

        await update.message.reply_text("No users have interacted with the bot yet.")

        return



    # Show each user’s roles

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

        "`/lecture` - (Admin user or Group Admin/Assistant) Start creating multiple lectures with placeholders for each role.\n"

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

    # Alias for /mute

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

    # Only user_id 6177929931 can use this

    user = update.effective_user

    if not user or user.id != 6177929931:

        await update.message.reply_text("You are not authorized to use this command.")

        return



    # If context.args is None, it might be from -check <user_id>

    if (context.args is None or len(context.args) == 0) and update.message:

        message_text = update.message.text.strip()

        match = re.match(r'^-check\s+(\d+)$', message_text, re.IGNORECASE)

        if not match:

            await update.message.reply_text("Usage: -check <user_id>", parse_mode='Markdown')

            return

        check_id = int(match.group(1))

    else:

        # The user typed /check <user_id>

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



# ------------------ NEW COMMAND: /setgroupname ------------------



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



# ------------------ NEW COMMAND: /lecture ------------------

#

# This feature:

# 1) Only an admin user (ID=6177929931) or someone with role group_admin/group_assistant can initiate.

# 2) Asks how many lectures.

# 3) Broadcasts that many "lecture info" messages with placeholders for writer / mcq / checker / mind_map / designer.

# 4) Each role can sign up. group_admin/group_assistant can set group & admin note.

# 5) Everyone sees updates as each slot is filled.



LECTURE_SLOTS = ["writer", "mcq", "checker", "mind_map", "designer"]



async def lecture_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if not user:

        return ConversationHandler.END



    # Check permission

    user_roles = get_user_roles(user.id)

    if user.id != 6177929931 and 'group_admin' not in user_roles and 'group_assistant' not in user_roles:

        await update.message.reply_text("You are not authorized to use /lecture.")

        return ConversationHandler.END



    await update.message.reply_text("How many lectures do you want to create?")

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

        f"You entered {count} lectures. Type /cancel to cancel or /confirm_lecture to confirm."

    )

    return LECTURE_CONFIRM



async def lecture_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):

    count = context.user_data.get("lecture_count")

    if not count:

        await update.message.reply_text("No lecture count found. Please use /lecture again.")

        return ConversationHandler.END



    # Create data structure

    context.user_data["lectures"] = {}

    for i in range(1, count+1):

        context.user_data["lectures"][i] = {

            "slots": {

                slot: None for slot in LECTURE_SLOTS

            },

            "group_took_it": None,

            "admin_note": None,

        }



    await update.message.reply_text(

        f"Created placeholders for {count} lectures. Sending them now..."

    )



    # Send messages for each lecture

    for i in range(1, count+1):

        await send_lecture_info(update, context, i)



    return LECTURE_SETUP



def build_lecture_keyboard(lecture_number, context):

    kb = []

    lectures_data = context.user_data.get("lectures", {})

    if not lectures_data or lecture_number not in lectures_data:

        return InlineKeyboardMarkup([])



    lecture_info = lectures_data[lecture_number]

    slot_buttons = []

    for slot in LECTURE_SLOTS:

        assigned_user_id = lecture_info["slots"].get(slot)

        if assigned_user_id:

            slot_buttons.append(

                InlineKeyboardButton(

                    f"{slot.capitalize()}: Filled",

                    callback_data=f"lecture_dummy:{lecture_number}"

                )

            )

        else:

            slot_buttons.append(

                InlineKeyboardButton(

                    f"Sign {slot.capitalize()}",

                    callback_data=f"lecture_sign:{lecture_number}:{slot}"

                )

            )

    kb.append(slot_buttons)



    if lecture_info["group_took_it"]:

        group_str = lecture_info["group_took_it"]

    else:

        group_str = "Not set"

    kb.append([

        InlineKeyboardButton(

            f"Group: {group_str}",

            callback_data=f"lecture_setgroup:{lecture_number}"

        )

    ])



    if lecture_info["admin_note"]:

        note_preview = (lecture_info["admin_note"][:10] + "...") if len(lecture_info["admin_note"]) > 10 else lecture_info["admin_note"]

        kb.append([

            InlineKeyboardButton(

                f"Note: {note_preview}",

                callback_data=f"lecture_setnote:{lecture_number}"

            )

        ])

    else:

        kb.append([

            InlineKeyboardButton(

                "Add Admin Note",

                callback_data=f"lecture_setnote:{lecture_number}"

            )

        ])



    return InlineKeyboardMarkup(kb)



async def send_lecture_info(update: Update, context, lecture_number: int):

    text = f"**Lecture #{lecture_number}**\n"

    lectures_data = context.user_data["lectures"]

    lecture_info = lectures_data[lecture_number]



    for slot in LECTURE_SLOTS:

        assigned_user_id = lecture_info["slots"].get(slot)

        if assigned_user_id:

            user_obj = await context.bot.get_chat(assigned_user_id)

            text += f"- {slot.capitalize()}: {get_display_name(user_obj)}\n"

        else:

            text += f"- {slot.capitalize()}: [Not Assigned]\n"



    group_str = lecture_info["group_took_it"] or "[Not Set]"

    text += f"- **Group** that took it: {group_str}\n"



    note_str = lecture_info["admin_note"] or "[No note]"

    text += f"- **Admin note**: {note_str}\n"



    markup = build_lecture_keyboard(lecture_number, context)

    await update.message.reply_text(

        text,

        parse_mode='Markdown',

        reply_markup=markup

    )



async def lecture_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    user_roles = get_user_roles(user.id)

    if user.id != 6177929931 and 'group_admin' not in user_roles and 'group_assistant' not in user_roles:

        await update.message.reply_text("You are not authorized to cancel lecture creation.")

        return ConversationHandler.END



    context.user_data.pop("lecture_count", None)

    context.user_data.pop("lectures", None)

    await update.message.reply_text("Lecture creation cancelled.")

    return ConversationHandler.END



async def lecture_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    user_roles = get_user_roles(user.id)

    if user.id != 6177929931 and 'group_admin' not in user_roles and 'group_assistant' not in user_roles:

        await update.message.reply_text("You are not authorized to finish lecture creation.")

        return ConversationHandler.END



    if "lectures" not in context.user_data:

        await update.message.reply_text("No active lectures to finish.")

        return ConversationHandler.END



    await update.message.reply_text("All done with lectures. You can still see them in the chat above.")

    context.user_data.pop("lecture_count", None)

    context.user_data.pop("lectures", None)

    return ConversationHandler.END



async def lecture_inline_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    data = query.data



    if data.startswith("lecture_dummy:"):

        await query.answer("Slot already filled.", show_alert=True)

        return



    elif data.startswith("lecture_sign:"):

        _, lec_str, slot = data.split(":")

        lecture_num = int(lec_str)

        user = query.from_user

        user_roles = get_user_roles(user.id)



        required_role = None

        if slot == "writer":

            required_role = "writer"

        elif slot == "mcq":

            required_role = "mcqs_team"

        elif slot == "checker":

            required_role = "checker_team"

        elif slot == "mind_map":

            required_role = "mind_map_form_creator"

        elif slot == "designer":

            required_role = "design_team"



        if required_role not in user_roles:

            await query.answer(f"You must be in the {required_role} role to sign up for {slot}.", show_alert=True)

            return



        lectures_data = context.user_data.get("lectures", {})

        if lecture_num not in lectures_data:

            await query.answer("Lecture not found.", show_alert=True)

            return



        if lectures_data[lecture_num]["slots"].get(slot):

            await query.answer("That slot is already filled.", show_alert=True)

            return



        lectures_data[lecture_num]["slots"][slot] = user.id



        try:

            await query.edit_message_text(

                text=await build_lecture_text(lecture_num, context),

                parse_mode='Markdown',

                reply_markup=build_lecture_keyboard(lecture_num, context)

            )

        except:

            pass



    elif data.startswith("lecture_setgroup:"):

        _, lec_str = data.split(":")

        lecture_num = int(lec_str)



        user = query.from_user

        user_roles = get_user_roles(user.id)

        if user.id != 6177929931 and 'group_admin' not in user_roles and 'group_assistant' not in user_roles:

            await query.answer("Only group admin or assistant can set the group.", show_alert=True)

            return



        context.user_data["lecture_setgroup_pending"] = lecture_num

        await query.message.reply_text("Please type the group name that took this lecture:")

        await query.answer()



    elif data.startswith("lecture_setnote:"):

        _, lec_str = data.split(":")

        lecture_num = int(lec_str)



        user = query.from_user

        user_roles = get_user_roles(user.id)

        if user.id != 6177929931 and 'group_admin' not in user_roles and 'group_assistant' not in user_roles:

            await query.answer("Only group admin or assistant can add an admin note.", show_alert=True)

            return



        context.user_data["lecture_setnote_pending"] = lecture_num

        await query.message.reply_text("Please type the admin note:")

        await query.answer()



async def build_lecture_text(lecture_num, context):

    lectures_data = context.user_data["lectures"]

    lecture_info = lectures_data[lecture_num]

    text = f"**Lecture #{lecture_num}**\n"

    for slot in LECTURE_SLOTS:

        assigned_user_id = lecture_info["slots"].get(slot)

        if assigned_user_id:

            text += f"- {slot.capitalize()}: `UserID {assigned_user_id}`\n"

        else:

            text += f"- {slot.capitalize()}: [Not Assigned]\n"



    group_str = lecture_info["group_took_it"] or "[Not Set]"

    text += f"- **Group** that took it: {group_str}\n"



    note_str = lecture_info["admin_note"] or "[No note]"

    text += f"- **Admin note**: {note_str}\n"



    return text



async def lecture_text_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_text = update.message.text.strip()



    if "lecture_setgroup_pending" in context.user_data:

        lecture_num = context.user_data.pop("lecture_setgroup_pending")

        lectures_data = context.user_data.get("lectures", {})

        if lecture_num in lectures_data:

            lectures_data[lecture_num]["group_took_it"] = user_text

            await update.message.reply_text(

                f"Group for lecture #{lecture_num} set to: {user_text}"

            )

        return LECTURE_SETUP



    if "lecture_setnote_pending" in context.user_data:

        lecture_num = context.user_data.pop("lecture_setnote_pending")

        lectures_data = context.user_data.get("lectures", {})

        if lecture_num in lectures_data:

            lectures_data[lecture_num]["admin_note"] = user_text

            await update.message.reply_text(

                f"Admin note for lecture #{lecture_num} set to: {user_text}"

            )

        return LECTURE_SETUP



    return LECTURE_SETUP



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

