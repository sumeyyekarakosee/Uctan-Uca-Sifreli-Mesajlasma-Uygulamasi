import os
import json
import math
import socket
import threading
import uuid
from typing import Callable, Dict, Optional

from crypto_utils import (
    generate_rsa_keypair,
    serialize_public_key,
    rsa_encrypt_with_public_key,
    rsa_decrypt_with_private_key,
    generate_aes_key,
    aes_encrypt,
    aes_decrypt,
)
from file_utils import save_received_file
from protocol import (
    CHUNK_PAYLOAD_SIZE,
    create_get_server_key_packet,
    create_signup_packet,
    create_login_packet,
    create_register_session_packet,
    create_public_key_packet,
    create_aes_key_packet,
    create_message_packet,
    create_file_info_packet,
    create_file_chunk_packet,
    create_file_end_packet,
    create_disconnect_packet,
    create_message_delivered_packet,
    create_message_seen_packet,
    create_file_delivered_packet,
    create_file_seen_packet,
)


class ChatClient:
    def __init__(self):
        self.sock: Optional[socket.socket] = None
        self.connected = False
        self.username: Optional[str] = None

        self.private_key, self.public_key = generate_rsa_keypair()
        self.public_key_pem = serialize_public_key(self.public_key)

        self.server_public_key: Optional[str] = None
        self.peer_public_keys: Dict[str, str] = {}
        self.session_keys: Dict[str, str] = {}

        # Thread-safety icin lock
        self._key_lock = threading.Lock()

        self.pending_messages: Dict[str, list] = {}
        self.pending_files: Dict[str, list] = {}
        self.incoming_files: Dict[str, dict] = {}

        self.on_status: Optional[Callable[[str], None]] = None
        self.on_message: Optional[Callable[[str, str], None]] = None
        self.on_message_status: Optional[Callable[[str, str, str], None]] = None
        self.on_user_list: Optional[Callable[[list], None]] = None
        self.on_auth_result: Optional[Callable[[bool, str], None]] = None
        self.on_file_received: Optional[Callable[[str, str], None]] = None
        self.on_file_progress: Optional[Callable[[str, str, int, bool], None]] = None
        self.on_file_status: Optional[Callable[[str, str, str], None]] = None

        self.raw_chunk_size = 24 * 1024

    def set_callbacks(self, on_status=None, on_message=None, on_user_list=None,
                      on_auth_result=None, on_file_received=None, on_file_progress=None,
                      on_message_status=None, on_file_status=None):
        self.on_status = on_status
        self.on_message = on_message
        self.on_user_list = on_user_list
        self.on_auth_result = on_auth_result
        self.on_file_received = on_file_received
        self.on_file_progress = on_file_progress
        self.on_message_status = on_message_status
        self.on_file_status = on_file_status

    # Temel ağ islemleri

    def _send_packet(self, packet: dict):
        if not self.sock:
            return
        try:
            data = json.dumps(packet).encode("utf-8") + b"\n"
            self.sock.sendall(data)
        except Exception as e:
            if self.on_status:
                self.on_status(f"Paket gonderme hatasi: {e}")

    def connect(self, host: str, port: int):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, port))
        self.connected = True
        threading.Thread(target=self._receive_loop, daemon=True).start()
        if self.on_status:
            self.on_status("Sunucuya baglanildi.")
        self._send_packet(create_get_server_key_packet())

    def signup(self, username: str, password: str):
        if not self.server_public_key:
            if self.on_status:
                self.on_status("Sunucu public key henuz alinmadi.")
            return
        enc = rsa_encrypt_with_public_key(self.server_public_key, password)
        self._send_packet(create_signup_packet(username, enc))

    def login(self, username: str, password: str):
        if not self.server_public_key:
            if self.on_status:
                self.on_status("Sunucu public key henuz alinmadi.")
            return
        enc = rsa_encrypt_with_public_key(self.server_public_key, password)
        self._send_packet(create_login_packet(username, enc))

    def register_session(self, username: str):
        self.username = username.strip().lower()
        self._send_packet(create_register_session_packet(self.username))

    def disconnect(self):
        if self.connected and self.username:
            self._send_packet(create_disconnect_packet(self.username))
        self.connected = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None


    def _is_initiator(self, peer: str) -> bool:
        #Alfabetik olarak kucuk olan kullanici AES key uretir.
        return (self.username or "") <= peer

    def _try_establish_key(self, peer: str):
        with self._key_lock:
            if peer in self.session_keys:
                return
            if peer not in self.peer_public_keys:
                return
            if not self._is_initiator(peer):
                # Biz responder'iz, karsinin aes_key gondermesini bekliyoruz
                return

            # AES key uret ve gonder
            aes_key = generate_aes_key()
            self.session_keys[peer] = aes_key
            encrypted_aes_key = rsa_encrypt_with_public_key(
                self.peer_public_keys[peer], aes_key
            )

        # Lock disinda gonder (deadlock onleme)
        self._send_packet(create_aes_key_packet(self.username, peer, encrypted_aes_key))
        if self.on_status:
            self.on_status(f"{peer} ile AES oturum anahtari kuruldu (initiator).")

    def _ensure_handshake_started(self, peer: str) -> bool:
        with self._key_lock:
            if peer in self.session_keys:
                return True

        # Public key'imizi gonder — bu hem aktif hem pasif taraf icin gerekli
        self._send_packet(create_public_key_packet(self.username, peer, self.public_key_pem))

        # Karsinin public key'i elimizde varsa hemen key kurulumuna gec
        self._try_establish_key(peer)

        with self._key_lock:
            return peer in self.session_keys

    # Mesaj / Dosya gonderme

    def _flush_pending_for_user(self, username: str):
        with self._key_lock:
            has_key = username in self.session_keys
        if not has_key:
            return

        msgs = self.pending_messages.pop(username, [])
        for message_id, msg in msgs:
            self._send_encrypted_message_now(username, msg, message_id)

        files = self.pending_files.pop(username, [])
        for filename, file_bytes, transfer_id in files:
            self._start_file_transfer_thread(username, filename, file_bytes, transfer_id)

    def _send_encrypted_message_now(self, to_user: str, message_text: str, message_id: str):
        encrypted_payload = aes_encrypt(
            self.session_keys[to_user],
            message_text.encode("utf-8")
        )
        self._send_packet(create_message_packet(self.username, to_user, encrypted_payload, message_id))

    def send_message(self, to_user: str, message_text: str) -> str | None:
        if not self.username:
            return None

        to_user = to_user.strip().lower()
        message_id = str(uuid.uuid4())

        with self._key_lock:
            has_key = to_user in self.session_keys

        if has_key:
            self._send_encrypted_message_now(to_user, message_text, message_id)
            return message_id

        self.pending_messages.setdefault(to_user, []).append((message_id, message_text))
        ready = self._ensure_handshake_started(to_user)
        if ready:
            self._flush_pending_for_user(to_user)
        else:
            if self.on_status:
                self.on_status("İlk mesaj için güvenli anahtar kuruluyor. Mesaj otomatik gönderilecek.")
        return message_id

    def send_file(self, to_user: str, filename: str, file_bytes: bytes) -> str | None:
        if not self.username:
            return None

        to_user = to_user.strip().lower()
        transfer_id = str(uuid.uuid4())

        with self._key_lock:
            has_key = to_user in self.session_keys

        if has_key:
            self._start_file_transfer_thread(to_user, filename, file_bytes, transfer_id)
            return transfer_id

        self.pending_files.setdefault(to_user, []).append((filename, file_bytes, transfer_id))
        ready = self._ensure_handshake_started(to_user)
        if ready:
            self._flush_pending_for_user(to_user)
        else:
            if self.on_status:
                self.on_status("Ilk dosya icin guvenli anahtar kuruluyor. Dosya otomatik gonderilecek.")
        return transfer_id

    def send_seen(self, to_user: str, message_ids: list[str]):
        if not self.username:
            return
        to_user = to_user.strip().lower()
        for message_id in message_ids:
            self._send_packet(create_message_seen_packet(self.username, to_user, message_id))

    # Dosya transferi

    def _start_file_transfer_thread(self, to_user: str, filename: str, file_bytes: bytes, transfer_id: str):
        threading.Thread(
            target=self._send_file_in_chunks,
            args=(to_user, filename, file_bytes, transfer_id),
            daemon=True
        ).start()

    def _send_file_in_chunks(self, to_user: str, filename: str, file_bytes: bytes, transfer_id: str):
        if not self.username or to_user not in self.session_keys:
            return

        total_chunks = max(1, math.ceil(len(file_bytes) / self.raw_chunk_size))

        self._send_packet(create_file_info_packet(
            self.username, to_user, filename, len(file_bytes), total_chunks, transfer_id
        ))

        for i in range(total_chunks):
            raw_chunk = file_bytes[i * self.raw_chunk_size:(i + 1) * self.raw_chunk_size]
            encrypted_payload = aes_encrypt(self.session_keys[to_user], raw_chunk)

            if len(encrypted_payload.encode("utf-8")) > CHUNK_PAYLOAD_SIZE * 2:
                if self.on_status:
                    self.on_status("Dosya parcasi beklenenden buyuk olusstu.")
                return

            self._send_packet(create_file_chunk_packet(
                self.username, to_user, filename, i, total_chunks, encrypted_payload, transfer_id
            ))

            percent = int(((i + 1) / total_chunks) * 100)
            if self.on_file_progress:
                self.on_file_progress(to_user, transfer_id, percent, False)

        self._send_packet(create_file_end_packet(
            self.username, to_user, filename, total_chunks, transfer_id
        ))

        if self.on_file_progress:
            self.on_file_progress(to_user, transfer_id, 100, True)

    def send_file_seen(self, to_user: str, transfer_ids: list[str]):
        if not self.username:
            return

        to_user = to_user.strip().lower()
        for transfer_id in transfer_ids:
            self._send_packet(create_file_seen_packet(self.username, to_user, transfer_id))

    # Receive loop & paket isleme

    def _receive_loop(self):
        buffer = b""
        try:
            while self.connected and self.sock:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    raw_packet, buffer = buffer.split(b"\n", 1)
                    if not raw_packet.strip():
                        continue
                    try:
                        packet = json.loads(raw_packet.decode("utf-8"))
                        self._handle_packet(packet)
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            if self.on_status:
                self.on_status(f"Baglanti hatasi: {e}")
        finally:
            self.connected = False
            if self.on_status:
                self.on_status("Sunucu baglantisi kapandi.")

    def _handle_packet(self, packet: dict):
        ptype = packet.get("type")

        if ptype == "server_key":
            self.server_public_key = packet.get("key")
            if self.on_status:
                self.on_status("Sunucu public key alindi.")

        elif ptype == "auth_result":
            if self.on_auth_result:
                self.on_auth_result(packet.get("success", False), packet.get("message", ""))

        elif ptype == "user_list":
            if self.on_user_list:
                self.on_user_list(packet.get("users", []))

        elif ptype == "public_key":
            from_user = (packet.get("from") or "").strip().lower()
            key = packet.get("key")
            if not (from_user and key):
                return

            # Karsi tarafin public key'ini kaydet
            self.peer_public_keys[from_user] = key
            if self.on_status:
                self.on_status(f"{from_user} kullanicisinin public key'i alindi.")

            # Karsi tarafa bizim public key'imizi de gonder
            # (pasif taraf aktife cevap vermeli ki her iki taraf da birbirinin key'ini bilsin)
            self._send_packet(create_public_key_packet(self.username, from_user, self.public_key_pem))

            # Initiator isek AES key kur
            self._try_establish_key(from_user)

            # Bekleyen mesaj/dosya varsa gonder
            self._flush_pending_for_user(from_user)

        elif ptype == "aes_key":
            from_user = (packet.get("from") or "").strip().lower()
            encrypted_aes = packet.get("key")
            if not (from_user and encrypted_aes):
                return

            with self._key_lock:
                if from_user in self.session_keys:
                    # Zaten key var (biz initiator'dik), bu paketi yoksay
                    return

                # Biz responder'iz — karsinin urettigi key'i kabul et
                try:
                    aes_key = rsa_decrypt_with_private_key(self.private_key, encrypted_aes)
                    self.session_keys[from_user] = aes_key
                except Exception as e:
                    if self.on_status:
                        self.on_status(f"AES key cozme hatasi: {e}")
                    return

            if self.on_status:
                self.on_status(f"{from_user} ile guvenli oturum anahtari kuruldu (responder).")

            self._flush_pending_for_user(from_user)

        elif ptype == "message":
            from_user = (packet.get("from") or "").strip().lower()
            encrypted_payload = packet.get("payload")
            message_id = packet.get("message_id")
            if not (from_user and encrypted_payload and from_user in self.session_keys and message_id):
                return
            try:
                plaintext = aes_decrypt(
                    self.session_keys[from_user],
                    encrypted_payload
                ).decode("utf-8")
                if self.on_message:
                    self.on_message(from_user, plaintext, message_id)
                self._send_packet(
                    create_message_delivered_packet(
                        self.username,
                        from_user,
                        message_id
                    )
                )
            except Exception as e:
                if self.on_status:
                    self.on_status(f"Mesaj cozme hatasi: {e}")

        elif ptype == "message_delivered":
            from_user = (packet.get("from") or "").strip().lower()
            message_id = packet.get("message_id")
            if from_user and message_id and self.on_message_status:
                self.on_message_status(from_user, message_id, "delivered")

        elif ptype == "message_seen":
            from_user = (packet.get("from") or "").strip().lower()
            message_id = packet.get("message_id")
            if from_user and message_id and self.on_message_status:
                self.on_message_status(from_user, message_id, "seen")

        elif ptype == "file_info":
            from_user = (packet.get("from") or "").strip().lower()
            filename = packet.get("filename")
            transfer_id = packet.get("transfer_id") or f"{from_user}:{filename}"
            self.incoming_files[transfer_id] = {
                "from_user": from_user,
                "filename": filename,
                "filesize": packet.get("filesize"),
                "total_chunks": packet.get("total_chunks", 1),
                "chunks": {}
            }
            if self.on_status and from_user and filename:
                self.on_status(f"{from_user} dosya gonderiyor: {filename} ({packet.get('filesize')} bayt)")

        elif ptype == "file_chunk":
            from_user =(packet.get("from") or "").strip().lower()
            filename = packet.get("filename")
            encrypted_payload = packet.get("payload")
            chunk_index = packet.get("chunk_index", 0)
            transfer_id = packet.get("transfer_id") or f"{from_user}:{filename}"

            if not (from_user and filename and encrypted_payload and from_user in self.session_keys):
                return
            try:
                file_chunk = aes_decrypt(self.session_keys[from_user], encrypted_payload)
                if transfer_id not in self.incoming_files:
                    self.incoming_files[transfer_id] = {
                        "from_user": from_user, "filename": filename,
                        "filesize": 0,
                        "total_chunks": packet.get("total_chunks", 1),
                        "chunks": {}
                    }
                self.incoming_files[transfer_id]["chunks"][chunk_index] = file_chunk
            except Exception as e:
                if self.on_status:
                    self.on_status(f"Dosya parcasi cozme hatasi: {e}")

        elif ptype == "file_end":
            from_user = (packet.get("from") or "").strip().lower()
            filename = packet.get("filename")
            total_chunks = packet.get("total_chunks", 1)
            transfer_id = packet.get("transfer_id") or f"{from_user}:{filename}"

            if transfer_id not in self.incoming_files:
                return

            try:
                file_info = self.incoming_files[transfer_id]
                chunks = file_info["chunks"]
                missing = [i for i in range(total_chunks) if i not in chunks]

                if missing:
                    if self.on_status:
                        self.on_status(f"Dosya eksik parca: {filename}")
                    del self.incoming_files[transfer_id]
                    return

                full_bytes = b"".join(chunks[i] for i in range(total_chunks))
                user_folder = self.username or "unknown_user"
                saved_path = save_received_file(
                    filename,
                    full_bytes,
                    folder=os.path.join("received_files", user_folder)
                )

                if self.on_file_received:
                    self.on_file_received(from_user, saved_path, transfer_id)

                self._send_packet(
                    create_file_delivered_packet(
                        self.username,
                        from_user,
                        transfer_id
                    )
                )

                if self.on_status:
                    self.on_status(f"{from_user} kullanicisinden dosya alindi: {filename}")

                del self.incoming_files[transfer_id]

            except Exception as e:
                if self.on_status:
                    self.on_status(f"Dosya birlestirme hatasi: {e}")

        elif ptype == "file_delivered":
            from_user = (packet.get("from") or "").strip().lower()
            transfer_id = packet.get("transfer_id")

            if from_user and transfer_id and self.on_file_status:
                self.on_file_status(from_user, transfer_id, "delivered")

        elif ptype == "file_seen":
            from_user = (packet.get("from") or "").strip().lower()
            transfer_id = packet.get("transfer_id")

            if from_user and transfer_id and self.on_file_status:
                self.on_file_status(from_user, transfer_id, "seen")