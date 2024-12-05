# main.py

import logging
import os
import re
from functools import wraps
from uuid import uuid4

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    CallbackQueryHandler,
)

import roles  # Import the updated roles.py

# ------------------ Setup Logging ------------------

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO  # Change to DEBUG for more detailed logs
)
logger = logging.getLogger(__name__)

# ------------------ Conversation States ------------------

SELECT_ROLE = 1
CONFIRMATION = 2

# ------------------ Access Control Decorator ------------------

def role_master_only(func):
    """Decorator to restrict command access to Role Masters."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in roles.roles.get("role_masters", set()):
            await update.message.reply_text("🚫 You are not authorized to use this command.")
            logger.warning(f"Unauthorized access attempt by user {user_id} to command {func.__name__}.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# ------------------ Helper Functions ------------------

def get_display_name(user):
    """Return the display name for a user."""
    if user.username:
        return f"@{user.username}"
    else:
        full_name = f"{user.first_name} {user.last_name}" if user.last_name else user.first_name
        return full_name

def add_username(username, user_id):
    """Add or update a username to the mapping."""
    username_lower = username.lower()
    if username_lower not in roles.username_mapping:
        roles.username_mapping[username_lower] = user_id
        roles.save_roles(roles.roles)
        logger.info(f"➕ Added username '{username_lower}' mapped to user ID {user_id}.")
        return True
    if roles.username_mapping[username_lower] != user_id:
        # Update the mapping if user_id has changed
        roles.username_mapping[username_lower] = user_id
        roles.save_roles(roles.roles)
        logger.info(f"🔄 Updated username '{username_lower}' to map to user ID {user_id}.")
        return True
    logger.info(f"ℹ️ Username '{username_lower}' is already mapped to user ID {user_id}.")
    return False

def get_user_id(username):
    """Retrieve the user ID by username."""
    return roles.username_mapping.get(username.lower())

def get_username(user_id):
    """Retrieve the username by user ID."""
    for uname, uid in roles.username_mapping.items():
        if uid == user_id:
            return f"@{uname}"
    return None

def add_role(user_id, role):
    """Add a role to a user."""
    if role not in roles.roles:
        roles.roles[role] = set()
    if user_id not in roles.roles[role]:
        roles.roles[role].add(user_id)
        roles.save_roles(roles.roles)
        logger.info(f"➕ Added role '{role}' to user ID {user_id}.")
        return True
    logger.info(f"ℹ️ User ID {user_id} already has role '{role}'.")
    return False

def remove_role(user_id, role):
    """Remove a role from a user."""
    if role in roles.roles and user_id in roles.roles[role]:
        roles.roles[role].remove(user_id)
        roles.save_roles(roles.roles)
        logger.info(f"➖ Removed role '{role}' from user ID {user_id}.")
        return True
    logger.info(f"ℹ️ User ID {user_id} does not have role '{role}'.")
    return False

def list_role_masters_func():
    """Return a list of all Role Master User IDs."""
    return list(roles.roles.get("role_masters", set()))

def add_role_master_func(user_id):
    """Add a user as a Role Master."""
    if "role_masters" not in roles.roles:
        roles.roles["role_masters"] = set()
    if user_id not in roles.roles["role_masters"]:
        roles.roles["role_masters"].add(user_id)
        roles.save_roles(roles.roles)
        logger.info(f"🔰 User ID {user_id} has been added as a Role Master.")
        return True
    logger.info(f"ℹ️ User ID {user_id} is already a Role Master.")
    return False

def remove_role_master_func(user_id):
    """Remove a user from Role Masters."""
    if "role_masters" in roles.roles and user_id in roles.roles["role_masters"]:
        if len(roles.roles["role_masters"]) <= 1:
            logger.warning("⚠️ Attempted to remove the last Role Master. Operation denied.")
            return False  # Prevent removal to keep at least one Role Master
        roles.roles["role_masters"].remove(user_id)
        roles.save_roles(roles.roles)
        logger.info(f"🔰 User ID {user_id} has been removed from Role Masters.")
        return True
    logger.info(f"ℹ️ User ID {user_id} is not a Role Master.")
    return False

def list_users_with_role(role):
    """List all user IDs that have a specific role."""
    return list(roles.roles.get(role, set()))

# ------------------ Message Forwarding Helper ------------------

async def send_confirmation(messages, context, sender_role, target_ids, target_roles=None):
    """Send a confirmation message with inline buttons for a group of documents or text."""
    try:
        # Determine the content description
        if any(msg.document for msg in messages):
            document_names = [f"`{msg.document.file_name}`" for msg in messages if msg.document]
            content_description = f"📄 PDF Documents: {', '.join(document_names)}"
        elif all(msg.text for msg in messages):
            content_description = f"✉️ {len(messages)} Text Message(s)"
        else:
            content_description = "⚠️ Unsupported message types."

        if target_roles:
            target_roles_display = [role.replace('_', ' ').title() for role in target_roles]
        else:
            target_roles_display = [role.replace('_', ' ').title() for role in SENDING_ROLE_TARGETS.get(sender_role, [])]

        confirmation_text = (
            f"📩 *You are about to send the following to **{', '.join(target_roles_display)}**:*\n\n"
            f"{content_description}\n\n"
            "❓ Do you want to send this?"
        )

        # Generate a unique UUID for this confirmation
        confirmation_uuid = str(uuid4())

        # Create confirmation keyboard with UUID in callback_data
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm", callback_data=f'confirm:{confirmation_uuid}'),
                InlineKeyboardButton("❌ Cancel", callback_data=f'cancel:{confirmation_uuid}'),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send the confirmation message
        confirmation_message = await messages[0].reply_text(confirmation_text, parse_mode='Markdown', reply_markup=reply_markup)

        # Store confirmation data using UUID
        context.bot_data[f'confirm_{confirmation_uuid}'] = {
            'messages': messages,
            'target_ids': target_ids,
            'sender_role': sender_role,
            'target_roles': target_roles if target_roles else SENDING_ROLE_TARGETS.get(sender_role, [])
        }

        logger.debug(f"📨 Sent confirmation with UUID {confirmation_uuid} to user {messages[0].from_user.id}")

    except Exception as e:
        logger.error(f"❌ Error in send_confirmation: {e}")

# ------------------ Role Sending Targets ------------------

SENDING_ROLE_TARGETS = {
    'writer': ['writer', 'tara_team'],
    'mcqs_team': ['mcqs_team', 'tara_team'],
    'checker_team': ['checker_team', 'tara_team'],
    'word_team': ['word_team', 'tara_team'],
    'design_team': ['design_team', 'tara_team'],
    'king_team': ['king_team', 'tara_team'],
    'tara_team': [
        'writer', 'mcqs_team', 'checker_team',
        'word_team', 'design_team', 'king_team', 'tara_team'
    ],
    'mind_map_form_creator': ['mind_map_form_creator', 'tara_team'],
}

# ------------------ Conversation Handlers ------------------

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the conversation."""
    try:
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text("🛑 Operation cancelled.")
        else:
            await update.message.reply_text("🛑 Operation cancelled.")
        logger.info(f"User {update.effective_user.id} cancelled the operation.")
    except Exception as e:
        logger.error(f"❌ Error in cancel handler: {e}")
    return ConversationHandler.END

async def confirmation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the user's confirmation response."""
    try:
        query = update.callback_query
        await query.answer()
        data = query.data

        logger.debug(f"🔄 Received confirmation callback data: {data}")

        if data.startswith('confirm:') or data.startswith('cancel:'):
            try:
                action, confirmation_uuid = data.split(':', 1)
            except ValueError:
                await query.edit_message_text("⚠️ Invalid confirmation data. Please try again.")
                logger.error("❌ Failed to parse confirmation data.")
                return ConversationHandler.END

            confirm_data = context.bot_data.get(f'confirm_{confirmation_uuid}')

            if not confirm_data:
                await query.edit_message_text("⚠️ An error occurred. Please try again.")
                logger.error(f"❌ No confirmation data found for UUID {confirmation_uuid}.")
                return ConversationHandler.END

            if action == 'confirm':
                messages_to_send = confirm_data['messages']
                target_ids = confirm_data['target_ids']
                sender_role = confirm_data['sender_role']
                target_roles = confirm_data.get('target_roles', [])

                # Forward the messages
                for msg in messages_to_send:
                    for user_id in target_ids:
                        try:
                            if msg.text:
                                await context.bot.send_message(
                                    chat_id=user_id,
                                    text=f"📨 *Message from {get_display_name(msg.from_user)} ({sender_role.replace('_', ' ').title()}):*\n\n{msg.text}",
                                    parse_mode='Markdown'
                                )
                            elif msg.document:
                                await context.bot.send_document(
                                    chat_id=user_id,
                                    document=msg.document.file_id,
                                    caption=f"📄 *Document from {get_display_name(msg.from_user)} ({sender_role.replace('_', ' ').title()}):*",
                                    parse_mode='Markdown'
                                )
                        except Exception as e:
                            logger.error(f"❌ Failed to send message/document to user {user_id}: {e}")

                # Prepare confirmation text
                sender_display_name = sender_role.replace('_', ' ').title()
                recipient_display_names = [role.replace('_', ' ').title() for role in target_roles]

                if any(msg.document for msg in messages_to_send):
                    confirmation_text = (
                        f"✅ *Your PDF documents have been sent from **{sender_display_name}** "
                        f"to **{', '.join(recipient_display_names)}**.*"
                    )
                elif all(msg.text for msg in messages_to_send):
                    confirmation_text = (
                        f"✅ *Your {len(messages_to_send)} message(s) have been sent from **{sender_display_name}** "
                        f"to **{', '.join(recipient_display_names)}**.*"
                    )
                else:
                    confirmation_text = (
                        f"✅ *Your messages have been sent from **{sender_display_name}** "
                        f"to **{', '.join(recipient_display_names)}**.*"
                    )

                await query.edit_message_text(confirmation_text, parse_mode='Markdown')
                logger.info(f"User {query.from_user.id} confirmed and sent the messages.")

                # Clean up the stored data
                del context.bot_data[f'confirm_{confirmation_uuid}']

            elif action == 'cancel':
                await query.edit_message_text("🛑 Operation cancelled.")
                logger.info(f"User {query.from_user.id} cancelled the message sending for UUID {confirmation_uuid}.")

                # Clean up the stored data
                if f'confirm_{confirmation_uuid}' in context.bot_data:
                    del context.bot_data[f'confirm_{confirmation_uuid}']

        else:
            await query.edit_message_text("⚠️ Invalid choice.")
            logger.warning(f"User {query.from_user.id} sent invalid confirmation choice: {data}")

    except Exception as e:
        logger.error(f"❌ Error in confirmation_handler: {e}")
        await query.edit_message_text("❌ An error occurred. Please try again later.")
    return ConversationHandler.END

async def select_role_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the role selection from the user for general messages."""
    try:
        query = update.callback_query
        await query.answer()
        data = query.data

        logger.debug(f"🔄 Received role selection callback data: {data}")

        if data.startswith('role:'):
            selected_role = data.split(':', 1)[1]
            context.bot_data['sender_role'] = selected_role

            # Retrieve the pending message
            pending_message = context.bot_data.get('pending_message')
            if not pending_message:
                await query.edit_message_text("⚠️ No pending messages found. Please try again.")
                logger.error("❌ No pending message found during role selection.")
                return ConversationHandler.END

            # Determine target_ids based on selected_role
            target_roles = SENDING_ROLE_TARGETS.get(selected_role, [])
            target_ids = set()
            for role in target_roles:
                target_ids.update(list_users_with_role(role))
            target_ids.discard(pending_message.from_user.id)

            logger.debug(f"🔑 Selected role '{selected_role}' targets user IDs: {target_ids}")

            if not target_ids:
                await query.edit_message_text("⚠️ No recipients found to send your message.")
                logger.warning(f"⚠️ No recipients found for user {pending_message.from_user.id} with role '{selected_role}'.")
                return ConversationHandler.END

            # Store the message and targets for confirmation
            messages_to_send = [pending_message]
            target_ids = list(target_ids)
            sender_role = selected_role

            # Send confirmation using UUID
            await send_confirmation(messages_to_send, context, sender_role, target_ids, target_roles=target_roles)

            await query.edit_message_text("🕒 Processing your message...")
            logger.info(f"User {query.from_user.id} selected role '{selected_role}' and is prompted for confirmation.")

            # Remove the pending message from bot_data
            del context.bot_data['pending_message']

            return CONFIRMATION

        elif data == 'cancel_role_selection':
            await query.edit_message_text("🛑 Operation cancelled.")
            logger.info(f"User {query.from_user.id} cancelled role selection.")
            return ConversationHandler.END
        else:
            await query.edit_message_text("⚠️ Invalid role selection.")
            logger.warning(f"User {query.from_user.id} sent invalid role selection: {data}")
            return ConversationHandler.END

    except Exception as e:
        logger.error(f"❌ Error in select_role_handler: {e}")
        await query.edit_message_text("❌ An error occurred. Please try again later.")
        return ConversationHandler.END

async def specific_user_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trigger function when a Role Master sends a specific user command."""
    try:
        user_id = update.message.from_user.id
        # Since only Role Masters can trigger, no need to check roles

        # Extract username from the command using regex
        match = re.match(r'^\s*-\@([A-Za-z0-9_]{5,32})\s*$', update.message.text, re.IGNORECASE)
        if not match:
            await update.message.reply_text("⚠️ Invalid format. Please use `-@username` to target a user.", parse_mode='Markdown')
            logger.warning(f"⚠️ Invalid user command format from user {user_id}.")
            return ConversationHandler.END

        target_username = match.group(1).lower()
        target_user_id = get_user_id(target_username)

        if not target_user_id:
            await update.message.reply_text(f"❌ User `@{target_username}` not found.", parse_mode='Markdown')
            logger.warning(f"Role Master {user_id} attempted to target non-existent user @{target_username}.")
            return ConversationHandler.END

        # Prevent Role Master from sending messages to themselves via specific user trigger
        if target_user_id == user_id:
            await update.message.reply_text("⚠️ You cannot send messages to yourself using this command.")
            logger.warning(f"Role Master {user_id} attempted to send a message to themselves.")
            return ConversationHandler.END

        # Store target user ID and other necessary data in bot_data
        context.bot_data['target_user_id'] = target_user_id
        context.bot_data['target_username'] = target_username
        context.bot_data['sender_role'] = 'tara_team'  # Assuming Role Master uses 'tara_team' role for specific user commands

        await update.message.reply_text(f"✍️ Write your message for user `@{target_username}`.", parse_mode='Markdown')
        logger.info(f"Role Master {user_id} is sending a message to user @{target_username} (ID: {target_user_id}).")
        return CONFIRMATION

    except Exception as e:
        logger.error(f"❌ Error in specific_user_trigger: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again later.")
        return ConversationHandler.END

async def specific_team_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trigger function when a Role Master sends a specific team command."""
    try:
        user_id = update.message.from_user.id
        # Since only Role Masters can trigger, no need to check roles

        message_text = update.message.text.strip()
        message = message_text.lower()
        target_roles = re.findall(r'^-([a-z]{1,10})$', message)
        if not target_roles:
            await update.message.reply_text("⚠️ Invalid trigger. Please try again.")
            logger.warning(f"⚠️ Invalid trigger '{message}' from user {user_id}.")
            return ConversationHandler.END

        trigger = target_roles[0]
        # Define mapping for specific team triggers
        trigger_map = {
            'w': ['writer'],
            'e': ['checker_team'],
            'mcq': ['mcqs_team'],
            'd': ['word_team'],
            'de': ['design_team'],
            'mf': ['mind_map_form_creator'],
            'c': ['checker_team'],
        }

        target_roles = trigger_map.get(trigger)
        if not target_roles:
            await update.message.reply_text("⚠️ Invalid trigger. Please try again.")
            logger.warning(f"⚠️ Invalid trigger '{trigger}' from user {user_id}.")
            return ConversationHandler.END

        # Store sender role
        context.bot_data['sender_role'] = 'tara_team'  # Assuming Role Master uses 'tara_team' role for specific team commands

        await update.message.reply_text("✍️ Write your message for your team.")
        logger.info(f"Role Master {user_id} is sending a message to roles {target_roles}.")
        return CONFIRMATION

    except Exception as e:
        logger.error(f"❌ Error in specific_team_trigger: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again later.")
        return ConversationHandler.END

async def team_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the -team trigger to send a message to the user's team and Tara Team."""
    try:
        user_id = update.message.from_user.id
        roles_user = list_users_with_role("tara_team")  # Adjust if necessary

        roles_assigned = [role for role, users in roles.roles.items() if user_id in users and role != "role_masters"]

        if not roles_assigned:
            await update.message.reply_text("⚠️ You don't have a role assigned to use this bot.")
            logger.warning(f"⚠️ User {user_id} attempted to use -team without a role.")
            return ConversationHandler.END

        if len(roles_assigned) > 1:
            # Prompt the user to select a role
            context.bot_data['pending_message'] = update.message
            keyboard = []
            for role in roles_assigned:
                display_name = role.replace('_', ' ').title()
                callback_data = f"role:{role}"
                keyboard.append([InlineKeyboardButton(display_name, callback_data=callback_data)])
            # Add a Cancel button
            keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data='cancel_role_selection')])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "🔀 You have multiple roles. Please choose which role you want to use to send this message:",
                reply_markup=reply_markup
            )
            logger.info(f"User {user_id} has multiple roles and is prompted to select one.")
            return SELECT_ROLE
        else:
            # User has a single role, proceed to confirmation
            selected_role = roles_assigned[0]
            context.bot_data['sender_role'] = selected_role

            # Determine target roles: user's own role and Tara Team
            target_roles = SENDING_ROLE_TARGETS.get(selected_role, [])

            # Determine target user IDs
            target_ids = set()
            for role in target_roles:
                target_ids.update(list_users_with_role(role))
            target_ids.discard(user_id)  # Prevent sending to self if necessary

            logger.debug(f"🔑 Selected role '{selected_role}' targets user IDs: {target_ids}")

            if not target_ids:
                await update.message.reply_text("⚠️ No recipients found to send your message.")
                logger.warning(f"⚠️ No recipients found for user {user_id} with role '{selected_role}'.")
                return ConversationHandler.END

            # Store the message and targets for confirmation
            messages_to_send = [update.message]
            target_ids = list(target_ids)
            sender_role = selected_role

            # Send confirmation using UUID
            await send_confirmation(messages_to_send, context, sender_role, target_ids, target_roles=target_roles)

            logger.info(f"📤 User {user_id} is sending a message to roles {target_roles}.")

            return CONFIRMATION

    except Exception as e:
        logger.error(f"❌ Error in team_trigger: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again later.")
        return ConversationHandler.END

async def tara_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the -t trigger to send a message to Tara team."""
    try:
        user_id = update.message.from_user.id
        roles_user = list_users_with_role("tara_team")

        roles_assigned = [role for role, users in roles.roles.items() if user_id in users and role != "role_masters"]

        if not roles_assigned:
            await update.message.reply_text("⚠️ You don't have a role assigned to use this bot.")
            logger.warning(f"⚠️ User {user_id} attempted to use -t without a role.")
            return ConversationHandler.END

        # Store the user's role
        selected_role = roles_assigned[0]  # Use the first role
        context.bot_data['sender_role'] = selected_role

        target_roles = ['tara_team']
        target_ids = set(list_users_with_role('tara_team'))
        target_ids.discard(user_id)

        logger.debug(f"🔑 Target roles for -t: {target_roles}")
        logger.debug(f"🔍 Target user IDs for -t: {target_ids}")

        if not target_ids:
            await update.message.reply_text("⚠️ No recipients found to send your message.")
            logger.warning(f"⚠️ No recipients found for user {user_id} with role '{selected_role}'.")
            return ConversationHandler.END

        # Store the message and targets for confirmation
        messages_to_send = [update.message]
        target_ids = list(target_ids)
        sender_role = selected_role

        # Send confirmation using UUID
        await send_confirmation(messages_to_send, context, sender_role, target_ids, target_roles=target_roles)

        logger.info(f"📤 User {user_id} is sending a message to Tara Team.")

        return CONFIRMATION

    except Exception as e:
        logger.error(f"❌ Error in tara_trigger: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again later.")
        return ConversationHandler.END

async def handle_general_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages and forward them based on user roles."""
    try:
        message = update.message
        if not message:
            return ConversationHandler.END  # Ignore non-message updates

        user_id = message.from_user.id
        username = message.from_user.username

        # Check if the user is muted
        if user_id in roles.roles.get("muted_users", set()):
            await message.reply_text("⛔ You have been muted and cannot send messages through this bot.")
            logger.info(f"⛔ Muted user {user_id} attempted to send a message.")
            return ConversationHandler.END

        # Store the username and user_id if username exists
        if username:
            added = add_username(username, user_id)
            if added:
                await message.reply_text(f"✅ Username `@{username}` has been mapped to your User ID.")
        else:
            logger.info(f"👤 User {user_id} has no username and cannot be targeted.")

        roles_assigned = [role for role, users in roles.roles.items() if user_id in users and role != "role_masters"]

        if not roles_assigned:
            await message.reply_text("⚠️ You don't have a role assigned to use this bot.")
            logger.warning(f"⚠️ Unauthorized access attempt by user {user_id}.")
            return ConversationHandler.END

        logger.info(f"📥 Received message from user {user_id} with roles '{roles_assigned}'")

        if len(roles_assigned) > 1:
            # User has multiple roles, prompt to choose one
            context.bot_data['pending_message'] = message
            keyboard = []
            for role in roles_assigned:
                display_name = role.replace('_', ' ').title()
                callback_data = f"role:{role}"
                keyboard.append([InlineKeyboardButton(display_name, callback_data=callback_data)])
            # Add a Cancel button
            keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data='cancel_role_selection')])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await message.reply_text(
                "🔀 You have multiple roles. Please choose which role you want to use to send this message:",
                reply_markup=reply_markup
            )
            logger.info(f"User {user_id} has multiple roles and is prompted to select one.")
            return SELECT_ROLE
        else:
            # User has a single role, proceed to confirmation
            selected_role = roles_assigned[0]
            context.bot_data['sender_role'] = selected_role

            # Determine target roles: user's own role and Tara Team
            target_roles = SENDING_ROLE_TARGETS.get(selected_role, [])

            # Determine target user IDs
            target_ids = set()
            for role in target_roles:
                target_ids.update(list_users_with_role(role))
            target_ids.discard(user_id)  # Prevent sending to self if necessary

            logger.debug(f"🔑 Selected role '{selected_role}' targets user IDs: {target_ids}")

            if not target_ids:
                await message.reply_text("⚠️ No recipients found to send your message.")
                logger.warning(f"⚠️ No recipients found for user {user_id} with role '{selected_role}'.")
                return ConversationHandler.END

            # Store the message and targets for confirmation
            messages_to_send = [message]
            target_ids = list(target_ids)
            sender_role = selected_role

            # Send confirmation using UUID
            await send_confirmation(messages_to_send, context, sender_role, target_ids, target_roles=target_roles)
            logger.info(f"📤 User {user_id} is sending a message to roles {target_roles}.")

            return CONFIRMATION

    except Exception as e:
        logger.error(f"❌ Error in handle_general_message: {e}")
        await message.reply_text("❌ An error occurred. Please try again later.")
        return ConversationHandler.END

# ------------------ Command Handlers ------------------

@role_master_only
async def add_role_master_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Assign a Role Master to a user."""
    try:
        args = context.args
        if len(args) != 1:
            await update.message.reply_text("ℹ️ Usage: /add_role_master <user_id>")
            return

        target_user_id = int(args[0])

        if target_user_id in roles.roles.get("role_masters", set()):
            await update.message.reply_text(f"ℹ️ User ID {target_user_id} is already a Role Master.")
            logger.info(f"Role Master attempted to reassign existing Role Master {target_user_id}.")
            return

        # Add Role Master
        success = add_role_master_func(target_user_id)

        if success:
            target_username = get_username(target_user_id)
            if target_username:
                await update.message.reply_text(f"✅ User `{target_username}` (ID: {target_user_id}) has been promoted to Role Master.", parse_mode='Markdown')
            else:
                await update.message.reply_text(f"✅ User ID {target_user_id} has been promoted to Role Master.")
            logger.info(f"✅ User ID {target_user_id} promoted to Role Master by {update.effective_user.id}.")
        else:
            await update.message.reply_text(f"ℹ️ User ID {target_user_id} is already a Role Master.")
    except ValueError:
        await update.message.reply_text("⚠️ Please provide a valid numerical user ID.")
    except Exception as e:
        logger.error(f"❌ Error in add_role_master_command: {e}")
        await update.message.reply_text("❌ An error occurred while promoting the user. Please try again later.")

@role_master_only
async def remove_role_master_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Revoke Role Master from a user."""
    try:
        args = context.args
        if len(args) != 1:
            await update.message.reply_text("ℹ️ Usage: /remove_role_master <user_id>")
            return

        target_user_id = int(args[0])

        if target_user_id == 6177929931 and len(roles.roles.get("role_masters", set())) == 1:
            await update.message.reply_text("⚠️ You cannot revoke your own Role Master status as you are the only Role Master.")
            logger.warning(f"Role Master {6177929931} attempted to revoke their own status while being the sole Role Master.")
            return

        # Remove Role Master
        success = remove_role_master_func(target_user_id)

        if success:
            target_username = get_username(target_user_id)
            if target_username:
                await update.message.reply_text(f"✅ User `{target_username}` (ID: {target_user_id}) has been demoted from Role Master.", parse_mode='Markdown')
            else:
                await update.message.reply_text(f"✅ User ID {target_user_id} has been demoted from Role Master.")
            logger.info(f"✅ User ID {target_user_id} demoted from Role Master by {update.effective_user.id}.")
        else:
            # Check if the removal was denied due to being the last Role Master
            if target_user_id in list_role_masters_func():
                await update.message.reply_text("⚠️ Cannot remove the last Role Master to prevent lockout.")
                logger.warning(f"⚠️ Attempt to remove the last Role Master {target_user_id} by {update.effective_user.id}.")
            else:
                await update.message.reply_text(f"ℹ️ User ID {target_user_id} is not a Role Master.")
    except ValueError:
        await update.message.reply_text("⚠️ Please provide a valid numerical user ID.")
    except Exception as e:
        logger.error(f"❌ Error in remove_role_master_command: {e}")
        await update.message.reply_text("❌ An error occurred while demoting the user. Please try again later.")

@role_master_only
async def list_role_masters_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all current Role Masters."""
    try:
        role_masters_list = list_role_masters_func()

        if not role_masters_list:
            await update.message.reply_text("ℹ️ There are currently no Role Masters.")
            return

        role_masters_text = "\n".join([f"User ID: {uid}" for uid in role_masters_list])
        await update.message.reply_text(f"**🔰 Current Role Masters:**\n{role_masters_text}", parse_mode='Markdown')
        logger.info(f"🔰 Role Master {update.effective_user.id} requested the list of Role Masters.")
    except Exception as e:
        logger.error(f"❌ Error in list_role_masters_command: {e}")
        await update.message.reply_text("❌ An error occurred while listing Role Masters. Please try again later.")

@role_master_only
async def add_role_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Assign a role to a user."""
    try:
        args = context.args
        if len(args) != 2:
            await update.message.reply_text("ℹ️ Usage: /addrole <user_id> <role>")
            return

        target_user_id = int(args[0])
        role = args[1].lower()

        # Define allowed roles
        allowed_roles = ['writer', 'mcqs_team', 'checker_team', 'word_team', 'design_team', 'king_team', 'mind_map_form_creator', 'tara_team']

        if role not in allowed_roles:
            await update.message.reply_text(f"⚠️ Invalid role. Allowed roles: {', '.join(allowed_roles)}")
            return

        # Assign role
        success = add_role(target_user_id, role)

        if success:
            target_username = get_username(target_user_id)
            if target_username:
                await update.message.reply_text(f"✅ Role '{role}' has been assigned to user `{target_username}` (ID: {target_user_id}).", parse_mode='Markdown')
            else:
                await update.message.reply_text(f"✅ Role '{role}' has been assigned to user ID {target_user_id}.")
            logger.info(f"✅ Role '{role}' assigned to user ID {target_user_id} by {update.effective_user.id}.")
        else:
            await update.message.reply_text(f"ℹ️ User ID {target_user_id} already has the role '{role}'.")
    except ValueError:
        await update.message.reply_text("⚠️ Please provide a valid numerical user ID.")
    except Exception as e:
        logger.error(f"❌ Error in add_role_command: {e}")
        await update.message.reply_text("❌ An error occurred while assigning the role. Please try again later.")

@role_master_only
async def remove_role_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a role from a user."""
    try:
        args = context.args
        if len(args) != 2:
            await update.message.reply_text("ℹ️ Usage: /removerole <user_id> <role>")
            return

        target_user_id = int(args[0])
        role = args[1].lower()

        # Define allowed roles
        allowed_roles = ['writer', 'mcqs_team', 'checker_team', 'word_team', 'design_team', 'king_team', 'mind_map_form_creator', 'tara_team']

        if role not in allowed_roles:
            await update.message.reply_text(f"⚠️ Invalid role. Allowed roles: {', '.join(allowed_roles)}")
            return

        # Remove role
        success = remove_role(target_user_id, role)

        if success:
            target_username = get_username(target_user_id)
            if target_username:
                await update.message.reply_text(f"✅ Role '{role}' has been removed from user `{target_username}` (ID: {target_user_id}).", parse_mode='Markdown')
            else:
                await update.message.reply_text(f"✅ Role '{role}' has been removed from user ID {target_user_id}.")
            logger.info(f"✅ Role '{role}' removed from user ID {target_user_id} by {update.effective_user.id}.")
        else:
            await update.message.reply_text(f"ℹ️ User ID {target_user_id} does not have the role '{role}'.")
    except ValueError:
        await update.message.reply_text("⚠️ Please provide a valid numerical user ID.")
    except Exception as e:
        logger.error(f"❌ Error in remove_role_command: {e}")
        await update.message.reply_text("❌ An error occurred while removing the role. Please try again later.")

# ------------------ Mute Command Handlers ------------------

@role_master_only
async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /mute command for Role Masters."""
    try:
        user_id = update.message.from_user.id

        # Mute self or another user
        if len(context.args) == 0:
            target_user_id = user_id
        elif len(context.args) == 1:
            try:
                target_user_id = int(context.args[0])
            except ValueError:
                await update.message.reply_text("⚠️ Please provide a valid numerical user ID.")
                return
        else:
            await update.message.reply_text("ℹ️ Usage: /mute [user_id]")
            return

        if target_user_id in roles.roles.get("muted_users", set()):
            if target_user_id == user_id:
                await update.message.reply_text("ℹ️ You are already muted.")
            else:
                await update.message.reply_text("ℹ️ This user is already muted.")
            logger.info(f"🔇 Attempt to mute already muted user {target_user_id} by {user_id}.")
            return

        # Add to muted_users
        if "muted_users" not in roles.roles:
            roles.roles["muted_users"] = set()
        roles.roles["muted_users"].add(target_user_id)
        roles.save_roles(roles.roles)

        if target_user_id == user_id:
            await update.message.reply_text("🔇 You have been muted and can no longer send messages through this bot.")
            logger.info(f"🔇 User {user_id} has muted themselves.")
        else:
            # Attempt to get the username of the target user
            target_username = get_username(target_user_id)
            if target_username:
                await update.message.reply_text(f"✅ User `{target_username}` has been muted.", parse_mode='Markdown')
                logger.info(f"🔇 User {user_id} has muted user {target_user_id} (@{target_username}).")
            else:
                await update.message.reply_text(f"✅ User ID {target_user_id} has been muted.")
                logger.info(f"🔇 User {user_id} has muted user {target_user_id}.")
    except Exception as e:
        logger.error(f"❌ Error in mute_command handler: {e}")
        await update.message.reply_text("❌ An error occurred while muting the user. Please try again later.")

@role_master_only
async def mute_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /muteid command for Role Masters."""
    await mute_command(update, context)

@role_master_only
async def unmute_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /unmuteid command for Role Masters."""
    try:
        user_id = update.message.from_user.id

        if len(context.args) != 1:
            await update.message.reply_text("ℹ️ Usage: /unmuteid <user_id>")
            return

        try:
            target_user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("⚠️ Please provide a valid numerical user ID.")
            return

        if "muted_users" not in roles.roles or target_user_id not in roles.roles["muted_users"]:
            await update.message.reply_text(f"ℹ️ User ID {target_user_id} is not muted.")
            logger.warning(f"⚠️ Attempt to unmute user {target_user_id} who is not muted by user {user_id}.")
            return

        # Remove from muted_users
        roles.roles["muted_users"].remove(target_user_id)
        roles.save_roles(roles.roles)

        # Attempt to get the username of the target user
        target_username = get_username(target_user_id)

        if target_username:
            await update.message.reply_text(f"✅ User `{target_username}` has been unmuted.", parse_mode='Markdown')
            logger.info(f"🔈 User {user_id} has unmuted user {target_user_id} (@{target_username}).")
        else:
            await update.message.reply_text(f"✅ User ID {target_user_id} has been unmuted.")
            logger.info(f"🔈 User {user_id} has unmuted user {target_user_id}.")

    except Exception as e:
        logger.error(f"❌ Error in unmute_id_command handler: {e}")
        await update.message.reply_text("❌ An error occurred while unmuting the user. Please try again later.")

@role_master_only
async def list_muted_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /listmuted command for Role Masters."""
    try:
        muted_users_list = list(roles.roles.get("muted_users", set()))

        if not muted_users_list:
            await update.message.reply_text("ℹ️ No users are currently muted.")
            return

        muted_list = []
        for uid in muted_users_list:
            # Retrieve username from username_mapping
            username = get_username(uid)
            if username:
                muted_list.append(f"{username} (ID: {uid})")
            else:
                muted_list.append(f"User ID {uid}")

        muted_users_text = "\n".join(muted_list)
        await update.message.reply_text(f"**🔇 Muted Users:**\n{muted_users_text}", parse_mode='Markdown')
        logger.info(f"🔇 User {update.effective_user.id} requested the list of muted users.")
    except Exception as e:
        logger.error(f"❌ Error in list_muted_command handler: {e}")
        await update.message.reply_text("❌ An error occurred while listing muted users. Please try again later.")

# ------------------ Help Command ------------------

@role_master_only
async def help_master_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provide help information exclusive to Role Masters."""
    try:
        help_text = (
            "📘 *Role Master Commands:*\n\n"
            "/add_role_master <user_id> - Promote a user to Role Master.\n"
            "/remove_role_master <user_id> - Demote a user from Role Master.\n"
            "/list_role_masters - List all current Role Masters.\n"
            "/addrole <user_id> <role> - Assign a role to a user.\n"
            "/removerole <user_id> <role> - Remove a role from a user.\n"
            "/mute [user_id] - Mute yourself or another user.\n"
            "/muteid <user_id> - Mute a specific user by their User ID.\n"
            "/unmuteid <user_id> - Unmute a specific user by their User ID.\n"
            "/listmuted - List all currently muted users.\n\n"
            "*🔧 Notes:*\n"
            "- Only Role Masters can manage roles and muting.\n"
            "- Roles include: writer, mcqs_team, checker_team, word_team, design_team, king_team, mind_map_form_creator, tara_team.\n"
            "- Use `/cancel` to cancel any ongoing operation."
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')
        logger.info(f"👓 Role Master {update.effective_user.id} accessed /help_master.")
    except Exception as e:
        logger.error(f"❌ Error in help_master_command handler: {e}")
        await update.message.reply_text("❌ An error occurred while providing help. Please try again later.")

# ------------------ Start Command ------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command."""
    try:
        user = update.effective_user
        if not user.username:
            await update.message.reply_text(
                "ℹ️ Please set a Telegram username in your profile to use specific commands like `-@username`.",
                parse_mode='Markdown'
            )
            logger.warning(f"⚠️ User {user.id} has no username and cannot be targeted.")
            return

        # Add or update username mapping
        added = add_username(user.username, user.id)

        if user.id in roles.roles.get("role_masters", set()):
            await update.message.reply_text(
                f"🎉 You are a Role Master. You can manage roles and muting using the available commands.",
                parse_mode='Markdown'
            )
            logger.info(f"🔰 Role Master {user.id} started the bot.")
        else:
            await update.message.reply_text(
                f"👋 Hello, {get_display_name(user)}! Welcome to the Team Management Bot.\n\n"
                "Feel free to send messages using the available commands."
            )
            logger.info(f"👋 User {user.id} started the bot.")
    except Exception as e:
        logger.error(f"❌ Error in start_command handler: {e}")
        await update.message.reply_text("❌ An error occurred while starting the bot. Please try again later.")

# ------------------ General Help Command ------------------

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provide help information to users."""
    try:
        help_text = (
            "📘 *Available Commands:*\n\n"
            "/start - Initialize interaction with the bot.\n"
            "/help - Show this help message.\n"
            "/help_master - Show Role Master help (Role Masters only).\n\n"
            "*🔑 Message Sending Triggers:*\n"
            "`-team` - Send a message to your team and the Tara Team.\n"
            "`-t` - Send a message exclusively to the Tara Team.\n"
            "`-@username` - Send a message to a specific user.\n\n"
            "*🔧 Notes:*\n"
            "- Only Role Masters can manage roles and muting.\n"
            "- Roles include: writer, mcqs_team, checker_team, word_team, design_team, king_team, mind_map_form_creator, tara_team.\n"
            "- Use `/cancel` to cancel any ongoing operation."
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')
        logger.info(f"ℹ️ User {update.effective_user.id} requested help.")
    except Exception as e:
        logger.error(f"❌ Error in help_command handler: {e}")
        await update.message.reply_text("❌ An error occurred while providing help. Please try again later.")

# ------------------ Main Function ------------------

def main():
    """Main function to start the Telegram bot."""
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        logger.error("🚫 BOT_TOKEN is not set in environment variables.")
        return

    try:
        # Build the application
        application = ApplicationBuilder().token(BOT_TOKEN).build()

        # Add Command Handlers
        application.add_handler(CommandHandler('start', start_command))
        application.add_handler(CommandHandler('help', help_command))
        application.add_handler(CommandHandler('help_master', help_master_command))
        application.add_handler(CommandHandler('add_role_master', add_role_master_command))
        application.add_handler(CommandHandler('remove_role_master', remove_role_master_command))
        application.add_handler(CommandHandler('list_role_masters', list_role_masters_command))
        application.add_handler(CommandHandler('addrole', add_role_command))
        application.add_handler(CommandHandler('removerole', remove_role_command))
        application.add_handler(CommandHandler('mute', mute_command))
        application.add_handler(CommandHandler('muteid', mute_id_command))
        application.add_handler(CommandHandler('unmuteid', unmute_id_command))
        application.add_handler(CommandHandler('listmuted', list_muted_command))

        # Add Conversation Handlers
        specific_user_conv_handler = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex(re.compile(r'^\s*-\@([A-Za-z0-9_]{5,32})\s*$', re.IGNORECASE)), specific_user_trigger)],
            states={
                CONFIRMATION: [CallbackQueryHandler(confirmation_handler, pattern='^(confirm:|cancel:).*')],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
            allow_reentry=True,
            per_message=False,  # Set to False since entry_points use MessageHandler
        )

        specific_team_conv_handler = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex(re.compile(r'^-(w|e|mcq|d|de|mf|c)$', re.IGNORECASE)), specific_team_trigger)],
            states={
                CONFIRMATION: [CallbackQueryHandler(confirmation_handler, pattern='^(confirm:|cancel:).*')],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
            allow_reentry=True,
            per_message=False,  # Set to False since entry_points use MessageHandler
        )

        team_conv_handler = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex(re.compile(r'^-team$', re.IGNORECASE)), team_trigger)],
            states={
                SELECT_ROLE: [CallbackQueryHandler(select_role_handler, pattern='^role:.*$|^cancel_role_selection$')],
                CONFIRMATION: [CallbackQueryHandler(confirmation_handler, pattern='^(confirm:|cancel:).*')],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
            allow_reentry=True,
            per_message=False,  # Set to False since entry_points use MessageHandler
        )

        tara_conv_handler = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex(re.compile(r'^-t$', re.IGNORECASE)), tara_trigger)],
            states={
                CONFIRMATION: [CallbackQueryHandler(confirmation_handler, pattern='^(confirm:|cancel:).*')],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
            allow_reentry=True,
            per_message=False,  # Set to False since entry_points use MessageHandler
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
                SELECT_ROLE: [CallbackQueryHandler(select_role_handler, pattern='^role:.*$|^cancel_role_selection$')],
                CONFIRMATION: [CallbackQueryHandler(confirmation_handler, pattern='^(confirm:|cancel:).*')],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
            allow_reentry=True,
            per_message=False,  # Set to False since entry_points use MessageHandler
        )

        application.add_handler(specific_user_conv_handler)
        application.add_handler(specific_team_conv_handler)
        application.add_handler(team_conv_handler)
        application.add_handler(tara_conv_handler)
        application.add_handler(general_conv_handler)

        # Start the Bot using long polling
        logger.info("🤖 Bot started polling...")
        application.run_polling()
    except Exception as e:
        logger.error(f"🚫 Failed to start the bot: {e}")

if __name__ == '__main__':
    main()
