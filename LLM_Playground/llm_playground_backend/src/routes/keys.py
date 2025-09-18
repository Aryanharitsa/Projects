from flask import Blueprint, request, jsonify
import os

KEYS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', '..', '.env')

bp = Blueprint('keys', __name__)

KEYS_LIST = [
    ("OPENAI_API_KEY", "OpenAI"),
    ("GEMINI_API_KEY", "Gemini"),
    ("CLAUDE_API_KEY", "Claude"),
    ("AUGUST_PKEY", "August PKEY"),
    ("AUGUST_PVARS", "August PVARS"),
]

def mask_key(keyval):
    """Mask key except first 4 and last 2 chars (for display)."""
    if not keyval or len(keyval) < 8:
        return "*" * (len(keyval) if keyval else 6)
    return f"{keyval[:4]}{'*'*(len(keyval)-6)}{keyval[-2:]}"

def read_env():
    """Read and return env as a dict."""
    env = {}
    if os.path.exists(KEYS_FILE):
        with open(KEYS_FILE, "r") as f:
            for line in f:
                if '=' in line:
                    k, v = line.strip().split('=', 1)
                    env[k] = v
    return env

def write_env(new_data):
    """Update .env file with new key-value pairs (rest untouched)."""
    import re
    env = read_env()
    env.update(new_data)
    # Keep order: all existing + any new keys at end
    with open(KEYS_FILE, "w") as f:
        for k, v in env.items():
            # If value contains any character except letters, digits, or underscores, quote it
            if re.search(r'[^A-Za-z0-9_]', v):
                safe_v = v.replace('"', '\\"')
                f.write(f'{k}="{safe_v}"\n')
            else:
                f.write(f"{k}={v}\n")

@bp.route('/api/key-status', methods=['GET'])
def key_status():
    """Return masked keys and whether they are set (not checking validity with providers)."""
    env = read_env()
    out = {}
    for envvar, label in KEYS_LIST:
        val = env.get(envvar, "")
        out[envvar] = {
            "label": label,
            "masked": mask_key(val),
            "active": bool(val)
        }
    return jsonify(out)

@bp.route('/api/save-keys', methods=['POST'])
def save_keys():
    """Update .env file with keys from user."""
    data = request.json
    # Only update provided keys (not blank strings)
    to_update = {}
    for envvar, label in KEYS_LIST:
        if envvar in data and data[envvar]:
            to_update[envvar] = data[envvar]
    if not to_update:
        return jsonify({"error": "No keys to update"}), 400
    try:
        write_env(to_update)
        from dotenv import load_dotenv
        load_dotenv(KEYS_FILE, override=True)
        os.environ.update(to_update)
        return jsonify({"success": True, "updated": list(to_update.keys())})
    except Exception as e:
        return jsonify({"error": str(e)}), 500