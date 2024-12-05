# username_mapping.py

import json
import logging
from pathlib import Path

# Setup Logging
logger = logging.getLogger(__name__)

# File to store username to user ID mapping
USERNAME_MAPPING_FILE = Path('username_mapping.json')

# Load existing mapping or initialize empty
if USERNAME_MAPPING_FILE.exists():
    try:
        with open(USERNAME_MAPPING_FILE, 'r') as f:
            username_mapping = json.load(f)
            # Ensure keys are lowercase for consistency
            username_mapping = {k.lower(): int(v) for k, v in username_mapping.items()}
            logger.info("✅ Loaded existing username mapping from username_mapping.json.")
    except json.JSONDecodeError:
        username_mapping = {}
        logger.error("❌ username_mapping.json is not a valid JSON file. Starting with an empty mapping.")
else:
    username_mapping = {}
    logger.info("🔍 username_mapping.json not found. Starting with an empty mapping.")

def save_username_mapping():
    """Save the username_mapping dictionary to a JSON file."""
    try:
        with open(USERNAME_MAPPING_FILE, 'w') as f:
            json.dump(username_mapping, f, indent=4)
            logger.info("💾 Saved username mapping to username_mapping.json.")
    except Exception as e:
        logger.error(f"❌ Failed to save username mapping: {e}")

def add_username(username, user_id):
    """Add or update a username to the mapping."""
    username_lower = username.lower()
    if username_lower not in username_mapping:
        username_mapping[username_lower] = user_id
        save_username_mapping()
        logger.info(f"➕ Added username '{username_lower}' mapped to user ID {user_id}.")
        return True
    if username_mapping[username_lower] != user_id:
        # Update the mapping if user_id has changed
        username_mapping[username_lower] = user_id
        save_username_mapping()
        logger.info(f"🔄 Updated username '{username_lower}' to map to user ID {user_id}.")
        return True
    logger.info(f"ℹ️ Username '{username_lower}' is already mapped to user ID {user_id}.")
    return False

def get_user_id(username):
    """Retrieve the user ID by username."""
    return username_mapping.get(username.lower())

def get_username(user_id):
    """Retrieve the username by user ID."""
    for uname, uid in username_mapping.items():
        if uid == user_id:
            return f"@{uname}"
    return None
