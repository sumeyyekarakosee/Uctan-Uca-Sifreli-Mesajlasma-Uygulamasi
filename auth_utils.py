import json
import hashlib
import secrets
import os

USERS_FILE = "users.json"


def load_users() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_users(users: dict) -> None:
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


def hash_password(password: str, salt: str) -> str:
    combined = salt + password
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def register_user(username: str, password: str) -> tuple[bool, str]:
    if not username or not username.strip():
        return False, "Kullanıcı adı boş olamaz."
    if not password:
        return False, "Şifre boş olamaz."

    username = username.strip().lower()
    users = load_users()

    if username in users:
        return False, "Bu kullanıcı adı zaten kayıtlı."

    salt = secrets.token_hex(32)
    password_hash = hash_password(password, salt)

    users[username] = {
        "salt": salt,
        "password_hash": password_hash
    }
    save_users(users)
    return True, "Kayıt başarılı."


def verify_user(username: str, password: str) -> tuple[bool, str]:
    if not username or not username.strip():
        return False, "Kullanıcı adı boş olamaz."
    if not password:
        return False, "Şifre boş olamaz."

    username = username.strip().lower()
    users = load_users()

    if username not in users:
        return False, "Kullanıcı adı veya şifre hatalı."

    stored = users[username]
    computed_hash = hash_password(password, stored["salt"])

    if computed_hash != stored["password_hash"]:
        return False, "Kullanıcı adı veya şifre hatalı."

    return True, "Giriş başarılı."


def user_exists(username: str) -> bool:
    username = username.strip().lower()
    users = load_users()
    return username in users