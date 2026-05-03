import socket
import threading
import logging
import os
import base64

from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes

import protocol
import auth_utils

HOST = "0.0.0.0"
PORT = 9999
BUFFER_SIZE = 65536
RAM_WARN_MB = 256
KEYS_DIR = "keys"
LOG_FILE = "server.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("server")

active_users: dict[str, socket.socket] = {}
active_users_lock = threading.Lock()

server_private_key = None
server_public_key_pem = ""


def _get_ram_mb() -> float:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except FileNotFoundError:
        pass
    return 0.0


def check_ram(context: str = ""):
    mb = _get_ram_mb()
    if mb == 0:
        return
    label = f"[{context}] " if context else ""
    if mb >= RAM_WARN_MB:
        log.warning(f"{label}RAM kullanımı yüksek: {mb:.1f} MB (eşik: {RAM_WARN_MB} MB)")
    else:
        log.debug(f"{label}RAM: {mb:.1f} MB")


def generate_or_load_server_keys():
    global server_private_key, server_public_key_pem

    os.makedirs(KEYS_DIR, exist_ok=True)
    priv_path = os.path.join(KEYS_DIR, "server_private.pem")
    pub_path = os.path.join(KEYS_DIR, "server_public.pem")

    if os.path.exists(priv_path) and os.path.exists(pub_path):
        with open(priv_path, "rb") as f:
            server_private_key = serialization.load_pem_private_key(f.read(), password=None)
        with open(pub_path, "rb") as f:
            server_public_key_pem = f.read().decode("utf-8")
        log.info("Sunucu RSA anahtarları diskten yüklendi.")
    else:
        server_private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        priv_bytes = server_private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption()
        )
        pub_bytes = server_private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo
        )
        with open(priv_path, "wb") as f:
            f.write(priv_bytes)
        with open(pub_path, "wb") as f:
            f.write(pub_bytes)
        server_public_key_pem = pub_bytes.decode("utf-8")
        log.info("Yeni sunucu RSA anahtarları üretildi ve kaydedildi.")


def decrypt_with_server_key(encrypted_b64: str) -> str | None:
    try:
        encrypted_bytes = base64.b64decode(encrypted_b64)
        plaintext = server_private_key.decrypt(
            encrypted_bytes,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        return plaintext.decode("utf-8")
    except Exception as e:
        log.warning(f"RSA çözme hatası: {e}")
        return None


def broadcast_user_list():
    with active_users_lock:
        users = list(active_users.keys())
        packet = protocol.encode(protocol.make_user_list(users))
        dead = []
        for uname, sock in active_users.items():
            try:
                sock.sendall(packet)
            except Exception:
                dead.append(uname)
        for uname in dead:
            _remove_user(uname)


def _remove_user(username: str):
    if username in active_users:
        del active_users[username]
        log.info(f"Kullanıcı listeden çıkarıldı: {username}")


def send_to(username: str, packet: dict) -> bool:
    with active_users_lock:
        sock = active_users.get(username)
    if sock is None:
        return False
    try:
        data = protocol.encode(packet)
        sock.sendall(data)
        return True
    except (BrokenPipeError, ConnectionResetError, OSError) as e:
        log.warning(f"Gönderme hatası ({username}): {e}")
        return False


def handle_client(conn: socket.socket, addr: tuple):
    log.info(f"Yeni bağlantı: {addr}")
    current_user: str | None = None
    buffer = b""

    try:
        while True:
            chunk = conn.recv(BUFFER_SIZE)
            if not chunk:
                break
            buffer += chunk

            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if not line.strip():
                    continue
                packet = protocol.decode(line)
                if packet is None:
                    log.warning(f"Geçersiz paket ({addr}): {line[:80]}")
                    continue

                ptype = packet.get("type")

                if ptype == "get_server_key":
                    resp = protocol.make_server_key(server_public_key_pem)
                    conn.sendall(protocol.encode(resp))

                elif ptype == "signup":
                    username = packet.get("username", "").strip().lower()
                    enc_pass = packet.get("password", "")
                    plaintext_pass = decrypt_with_server_key(enc_pass)

                    if plaintext_pass is None:
                        result = protocol.make_auth_result(False, "Şifre çözülemedi.")
                    else:
                        ok, msg = auth_utils.register_user(username, plaintext_pass)
                        result = protocol.make_auth_result(ok, msg)
                        if ok:
                            log.info(f"Yeni kayıt: {username}")

                    conn.sendall(protocol.encode(result))

                elif ptype == "login":
                    username = packet.get("username", "").strip().lower()
                    enc_pass = packet.get("password", "")
                    plaintext_pass = decrypt_with_server_key(enc_pass)

                    if plaintext_pass is None:
                        result = protocol.make_auth_result(False, "Şifre çözülemedi.")
                    else:
                        with active_users_lock:
                            already_online = username in active_users
                        if already_online:
                            result = protocol.make_auth_result(
                                False, protocol.ErrorMsg.ALREADY_ONLINE
                            )
                        else:
                            ok, msg = auth_utils.verify_user(username, plaintext_pass)
                            result = protocol.make_auth_result(ok, msg)
                            if ok:
                                log.info(f"Giriş başarılı: {username}")

                    conn.sendall(protocol.encode(result))

                elif ptype == "register_session":
                    username = packet.get("username", "").strip().lower()
                    if not username:
                        continue
                    with active_users_lock:
                        if username in active_users:
                            conn.sendall(protocol.encode(
                                protocol.make_status(protocol.ErrorMsg.ALREADY_ONLINE)
                            ))
                            continue
                        active_users[username] = conn
                        current_user = username
                    log.info(f"Aktif kullanıcı eklendi: {username}")
                    broadcast_user_list()

                elif ptype in ("public_key", "aes_key", "message", "message_delivered", "message_seen", "file_info", "file_data", "file_chunk", "file_end", "file_delivered", "file_seen"):
                    to_user = packet.get("to")
                    if not to_user:
                        log.warning(f"'to' alanı eksik paket: {ptype}")
                        continue

                    if ptype == "file_info":
                        fname = packet.get("filename", "?")
                        fsize = packet.get("filesize", 0)
                        tchunks = packet.get("total_chunks", 1)
                        log.info(
                            f"Dosya transferi başladı: {current_user} → {to_user} | '{fname}' {fsize} bayt, {tchunks} chunk"
                        )
                        check_ram("file_info")

                    elif ptype == "file_chunk":
                        idx = packet.get("chunk_index", 0)
                        total = packet.get("total_chunks", 1)
                        if idx == 0 or (idx + 1) % 10 == 0 or idx + 1 == total:
                            log.debug(
                                f"Chunk yönlendiriliyor: {current_user} → {to_user} [{idx + 1}/{total}]"
                            )

                    elif ptype == "file_end":
                        fname = packet.get("filename", "?")
                        log.info(
                            f"Dosya transferi tamamlandı: {current_user} → {to_user} | '{fname}'"
                        )
                        check_ram("file_end")

                    if not send_to(to_user, packet):
                        if current_user:
                            send_to(current_user, protocol.make_status(
                                f"{to_user} şu anda çevrimdışı."
                            ))
                        log.warning(f"Yönlendirme başarısız: {ptype} → {to_user}")

                elif ptype == "disconnect":
                    username = packet.get("username", current_user)
                    log.info(f"Bağlantı kapatma isteği: {username}")
                    break

                else:
                    log.warning(f"Bilinmeyen paket türü: {ptype} ({addr})")

    except ConnectionResetError:
        log.warning(f"Bağlantı koptu: {addr}")
    except Exception as e:
        log.error(f"İstemci hatası ({addr}): {e}", exc_info=True)
    finally:
        conn.close()
        if current_user:
            with active_users_lock:
                _remove_user(current_user)
            log.info(f"Kullanıcı ayrıldı: {current_user}")
            broadcast_user_list()
        else:
            log.info(f"Bağlantı kapandı: {addr}")


def start_server():
    generate_or_load_server_keys()

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(50)

    log.info(f"Sunucu başlatıldı → {HOST}:{PORT}")
    log.info("Bağlantılar bekleniyor...")

    try:
        while True:
            conn, addr = server_sock.accept()
            t = threading.Thread(
                target=handle_client,
                args=(conn, addr),
                daemon=True
            )
            t.start()
    except KeyboardInterrupt:
        log.info("Sunucu kapatılıyor...")
    finally:
        server_sock.close()


if __name__ == "__main__":
    start_server()