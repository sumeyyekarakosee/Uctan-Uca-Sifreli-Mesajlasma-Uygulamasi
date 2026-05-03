import json

CHUNK_PAYLOAD_SIZE = 48 * 1024


def make_get_server_key() -> dict:
    return {"type": "get_server_key"}

def make_server_key(public_key: str) -> dict:
    return {"type": "server_key", "key": public_key}

def make_signup(username: str, encrypted_password: str) -> dict:
    return {"type": "signup", "username": username.strip().lower(), "password": encrypted_password}

def make_login(username: str, encrypted_password: str) -> dict:
    return {"type": "login", "username": username.strip().lower(), "password": encrypted_password}

def make_auth_result(success: bool, message: str) -> dict:
    return {"type": "auth_result", "success": success, "message": message}

def make_register_session(username: str) -> dict:
    return {"type": "register_session", "username": username.strip().lower()}

def make_user_list(users: list) -> dict:
    return {"type": "user_list", "users": users}

def make_public_key(from_user: str, to_user: str, key: str) -> dict:
    return {"type": "public_key", "from": from_user, "to": to_user, "key": key}

def make_aes_key(from_user: str, to_user: str, encrypted_key: str) -> dict:
    return {"type": "aes_key", "from": from_user, "to": to_user, "key": encrypted_key}

def make_message(from_user: str, to_user: str, payload: str, message_id: str) -> dict:
    return {
        "type": "message",
        "from": from_user,
        "to": to_user,
        "payload": payload,
        "message_id": message_id
    }

def make_message_delivered(from_user: str, to_user: str, message_id: str) -> dict:
    return {
        "type": "message_delivered",
        "from": from_user,
        "to": to_user,
        "message_id": message_id
    }

def make_message_seen(from_user: str, to_user: str, message_id: str) -> dict:
    return {
        "type": "message_seen",
        "from": from_user,
        "to": to_user,
        "message_id": message_id
    }

def make_file_info(from_user: str, to_user: str, filename: str, filesize: int,
                   total_chunks: int = 1, transfer_id: str | None = None) -> dict:
    p = {"type": "file_info", "from": from_user, "to": to_user,
         "filename": filename, "filesize": filesize, "total_chunks": total_chunks}
    if transfer_id is not None:
        p["transfer_id"] = transfer_id
    return p

def make_file_data(from_user: str, to_user: str, filename: str, payload: str,
                   transfer_id: str | None = None) -> dict:
    p = {"type": "file_data", "from": from_user, "to": to_user,
         "filename": filename, "payload": payload}
    if transfer_id is not None:
        p["transfer_id"] = transfer_id
    return p

def make_file_chunk(from_user: str, to_user: str, filename: str,
                    chunk_index: int, total_chunks: int, payload: str,
                    transfer_id: str | None = None) -> dict:
    p = {"type": "file_chunk", "from": from_user, "to": to_user,
         "filename": filename, "chunk_index": chunk_index,
         "total_chunks": total_chunks, "payload": payload}
    if transfer_id is not None:
        p["transfer_id"] = transfer_id
    return p

def make_file_end(from_user: str, to_user: str, filename: str, total_chunks: int,
                  transfer_id: str | None = None) -> dict:
    p = {"type": "file_end", "from": from_user, "to": to_user,
         "filename": filename, "total_chunks": total_chunks}
    if transfer_id is not None:
        p["transfer_id"] = transfer_id
    return p

def make_file_delivered(from_user: str, to_user: str, transfer_id: str) -> dict:
    return {
        "type": "file_delivered",
        "from": from_user,
        "to": to_user,
        "transfer_id": transfer_id
    }

def make_file_seen(from_user: str, to_user: str, transfer_id: str) -> dict:
    return {
        "type": "file_seen",
        "from": from_user,
        "to": to_user,
        "transfer_id": transfer_id
    }

def make_status(message: str) -> dict:
    return {"type": "status", "message": message}

def make_disconnect(username: str) -> dict:
    return {"type": "disconnect", "username": username}

def create_get_server_key_packet() -> dict:        return make_get_server_key()
def create_signup_packet(u, p) -> dict:            return make_signup(u, p)
def create_login_packet(u, p) -> dict:             return make_login(u, p)
def create_register_session_packet(u) -> dict:     return make_register_session(u)
def create_public_key_packet(f, t, k) -> dict:     return make_public_key(f, t, k)
def create_aes_key_packet(f, t, k) -> dict:        return make_aes_key(f, t, k)
def create_message_packet(f, t, p, mid) -> dict:   return make_message(f, t, p, mid)
def create_status_packet(m) -> dict:               return make_status(m)
def create_disconnect_packet(u) -> dict:           return make_disconnect(u)

def create_message_delivered_packet(f, t, mid) -> dict:
    return make_message_delivered(f, t, mid)

def create_message_seen_packet(f, t, mid) -> dict:
    return make_message_seen(f, t, mid)

def create_file_info_packet(f, t, fn, fs, tc=1, tid=None) -> dict:
    return make_file_info(f, t, fn, fs, tc, tid)

def create_file_data_packet(f, t, fn, pl, tid=None) -> dict:
    return make_file_data(f, t, fn, pl, tid)

def create_file_chunk_packet(f, t, fn, ci, tc, pl, tid=None) -> dict:
    return make_file_chunk(f, t, fn, ci, tc, pl, tid)

def create_file_end_packet(f, t, fn, tc, tid=None) -> dict:
    return make_file_end(f, t, fn, tc, tid)

def create_file_delivered_packet(f, t, tid) -> dict:
    return make_file_delivered(f, t, tid)

def create_file_seen_packet(f, t, tid) -> dict:
    return make_file_seen(f, t, tid)

def encode(packet: dict) -> bytes:
    return (json.dumps(packet, ensure_ascii=False) + "\n").encode("utf-8")

def decode(data: bytes) -> dict | None:
    try:
        return json.loads(data.decode("utf-8").strip())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

# Hata mesajları
class ErrorMsg:
    USERNAME_EMPTY     = "Kullanıcı adı boş olamaz."
    PASSWORD_EMPTY     = "Şifre boş olamaz."
    USERNAME_TAKEN     = "Bu kullanıcı adı zaten kayıtlı."
    WRONG_CREDENTIALS  = "Kullanıcı adı veya şifre hatalı."
    ALREADY_ONLINE     = "Bu kullanıcı zaten çevrimiçi."
    RECIPIENT_MISSING  = "Alıcı seçilmedi."
    MESSAGE_EMPTY      = "Mesaj boş olamaz."
    FILE_NOT_SELECTED  = "Dosya seçilmedi."
    CONNECTION_LOST    = "Bağlantı kesildi."
    DECRYPTION_FAILED  = "Şifre çözme başarısız."
    UNKNOWN_PACKET     = "Bilinmeyen paket türü."
    SERVER_ERROR       = "Sunucu hatası oluştu."
    FILE_CHUNK_MISSING = "Dosya parçası eksik, transfer iptal edildi."
    FILE_TRANSFER_FAIL = "Dosya transferi başarısız."
    RECIPIENT_OFFLINE  = "Alıcı çevrimdışı, dosya gönderilemedi."