# role_master.py

import json
import logging
from pathlib import Path

# Setup Logging
logger = logging.getLogger(__name__)

# File to store user roles
USER_ROLES_FILE = Path('user_roles.json')

# File to store Role Masters
ROLE_MASTERS_FILE = Path('role_masters.json')

# Load existing user roles or initialize an empty dictionary
if USER_ROLES_FILE.exists():
    try:
        with open(USER_ROLES_FILE, 'r') as f:
            user_roles = json.load(f)
            # Convert keys to integers for user IDs
            user_roles = {int(k): v for k, v in user_roles.items()}
            logger.info("Loaded existing user roles from user_roles.json.")
    except json.JSONDecodeError:
        user_roles = {}
        logger.error("user_roles.json is not a valid JSON file. Starting with an empty role store.")
else:
    user_roles = {}

# Load existing Role Masters or initialize an empty list
if ROLE_MASTERS_FILE.exists():
    try:
        with open(ROLE_MASTERS_FILE, 'r') as f:
            role_masters = set(json.load(f))
            logger.info("Loaded existing Role Masters from role_masters.json.")
    except json.JSONDecodeError:
        role_masters = set()
        logger.error("role_masters.json is not a valid JSON file. Starting with an empty Role Masters set.")
else:
    role_masters = set()

def save_user_roles():
    """Save the user_roles dictionary to a JSON file."""
    try:
        with open(USER_ROLES_FILE, 'w') as f:
            # Convert keys to strings for JSON serialization
            json.dump({str(k): v for k, v in user_roles.items()}, f, indent=4)
            logger.info("Saved user roles to user_roles.json.")
    except Exception as e:
        logger.error(f"Failed to save user roles: {e}")

def save_role_masters():
    """Save the role_masters set to a JSON file."""
    try:
        with open(ROLE_MASTERS_FILE, 'w') as f:
            json.dump(list(role_masters), f, indent=4)
            logger.info("Saved Role Masters to role_masters.json.")
    except Exception as e:
        logger.error(f"Failed to save Role Masters: {e}")

def add_role(user_id, role):
    """Add a role to a user."""
    roles = user_roles.get(user_id, [])
    if role not in roles:
        roles.append(role)
        user_roles[user_id] = roles
        save_user_roles()
        logger.info(f"Added role '{role}' to user ID {user_id}.")
        return True
    logger.info(f"User ID {user_id} already has role '{role}'.")
    return False

def remove_role(user_id, role):
    """Remove a role from a user."""
    roles = user_roles.get(user_id, [])
    if role in roles:
        roles.remove(role)
        user_roles[user_id] = roles
        save_user_roles()
        logger.info(f"Removed role '{role}' from user ID {user_id}.")
        return True
    logger.info(f"User ID {user_id} does not have role '{role}'.")
    return False

def get_roles(user_id):
    """Retrieve all roles assigned to a user."""
    return user_roles.get(user_id, [])

def list_users_with_role(role):
    """List all user IDs that have a specific role."""
    users = [user_id for user_id, roles in user_roles.items() if role in roles]
    return users

def assign_roles(user_id, roles):
    """Assign multiple roles to a user."""
    updated = False
    for role in roles:
        if add_role(user_id, role):
            updated = True
    return updated

def remove_roles(user_id, roles):
    """Remove multiple roles from a user."""
    updated = False
    for role in roles:
        if remove_role(user_id, role):
            updated = True
    return updated

# Role Master Management Functions

def add_role_master(user_id):
    """Add a user as a Role Master."""
    if user_id not in role_masters:
        role_masters.add(user_id)
        save_role_masters()
        logger.info(f"User ID {user_id} has been added as a Role Master.")
        return True
    logger.info(f"User ID {user_id} is already a Role Master.")
    return False

def remove_role_master(user_id):
    """Remove a user from Role Masters."""
    if user_id in role_masters:
        role_masters.remove(user_id)
        save_role_masters()
        logger.info(f"User ID {user_id} has been removed from Role Masters.")
        return True
    logger.info(f"User ID {user_id} is not a Role Master.")
    return False

def get_role_masters():
    """Retrieve all Role Masters."""
    return role_masters

def is_role_master(user_id):
    """Check if a user is a Role Master."""
    return user_id in role_masters
