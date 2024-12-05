# roles.py

import json
from pathlib import Path

ROLES_FILE = Path('roles.json')

def load_roles():
    """Load roles from the roles.json file."""
    if ROLES_FILE.exists():
        try:
            with open(ROLES_FILE, 'r') as f:
                data = json.load(f)
                # Convert lists to sets for efficient lookups
                roles = {role: set(user_ids) for role, user_ids in data.items() if role not in ["username_mapping", "muted_users"]}
                roles["username_mapping"] = {uname.lower(): uid for uname, uid in data.get("username_mapping", {}).items()}
                roles["muted_users"] = set(data.get("muted_users", []))
                return roles
        except json.JSONDecodeError:
            print("Error: roles.json is not a valid JSON file.")
    # Initialize with default roles if roles.json doesn't exist or is invalid
    return {
        "writer": set(),
        "mcqs_team": set(),
        "checker_team": set(),
        "word_team": set(),
        "design_team": set(),
        "king_team": set(),
        "tara_team": set(),
        "mind_map_form_creator": set(),
        "role_masters": set(),
        "username_mapping": {},
        "muted_users": set()
    }

def save_roles(roles):
    """Save roles to the roles.json file."""
    try:
        # Convert sets to lists for JSON serialization, except for username_mapping and muted_users
        data = {role: list(user_ids) for role, user_ids in roles.items() if role not in ["username_mapping", "muted_users"]}
        data["username_mapping"] = roles["username_mapping"]
        data["muted_users"] = list(roles["muted_users"])
        with open(ROLES_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        print("✅ Roles have been saved to roles.json.")
    except Exception as e:
        print(f"Error saving roles: {e}")

# Load roles at the start
roles = load_roles()
