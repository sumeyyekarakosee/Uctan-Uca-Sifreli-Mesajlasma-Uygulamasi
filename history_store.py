import json
import os
from datetime import datetime, timezone, timedelta

# Geçmiş dosyalarının tutulacağı klasör
HISTORY_DIR = "chat_history"

# Kaç günden eski kayıtlar silinecek
HISTORY_DAYS = 7

def _now_iso() -> str:
    """Şimdiki UTC zamanı ISO-8601 formatında döner."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _now_hhmm() -> str:
    """Yerel saatle HH:MM döner (görüntüleme için)."""
    return datetime.now().strftime("%H:%M")


def _cutoff_dt() -> datetime:
    """7 gün öncesinin UTC datetime nesnesi."""
    return datetime.now(timezone.utc) - timedelta(days=HISTORY_DAYS)


def _parse_ts(ts_str: str) -> datetime | None:
    """ISO-8601 string'i timezone-aware datetime'a çevirir. Hatalıysa None."""
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _history_path(username: str) -> str:
    os.makedirs(HISTORY_DIR, exist_ok=True)
    safe = username.strip().lower().replace("/", "_").replace("\\", "_")
    return os.path.join(HISTORY_DIR, f"{safe}.json")


def load_history(username: str) -> dict[str, list]:
    path = _history_path(username)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        return {}
    except (json.JSONDecodeError, IOError):
        return {}


def _save_history(username: str, data: dict[str, list]) -> None:
    """Geçmişi diske yazar. I/O hatalarını yutar (geçmiş kritik değil)."""
    path = _history_path(username)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError:
        pass


def prune_old_entries(username: str) -> int:
    """
    7 günden eski tüm kayıtları siler.
    Döner: silinen kayıt sayısı.

    Uygulama başında bir kez çağrılır.
    """
    data = load_history(username)
    cutoff = _cutoff_dt()
    total_removed = 0

    for peer in list(data.keys()):
        before = len(data[peer])
        data[peer] = [
            e for e in data[peer]
            if _parse_ts(e.get("timestamp", "")) and
               _parse_ts(e["timestamp"]) >= cutoff
        ]
        total_removed += before - len(data[peer])

        # Boş konuşmayı kaldır
        if not data[peer]:
            del data[peer]

    if total_removed > 0:
        _save_history(username, data)

    return total_removed


def append_message(username: str, peer: str,
                   sender: str, content: str,
                   message_id: str | None = None,
                   status: str | None = None) -> None:
    data = load_history(username)
    if peer not in data:
        data[peer] = []

    entry = {
        "type":      "text",
        "sender":    sender,
        "content":   content,
        "timestamp": _now_iso(),
        "time":      _now_hhmm(),
    }

    if message_id:
        entry["message_id"] = message_id
    if status:
        entry["status"] = status

    data[peer].append(entry)
    _save_history(username, data)


def append_file(username: str, peer: str,
                sender: str, filename: str,
                path: str | None = None,
                transfer_id: str | None = None,
                status: str | None = None) -> None:
    data = load_history(username)
    if peer not in data:
        data[peer] = []

    entry: dict = {
        "type": "file",
        "sender": sender,
        "filename": filename,
        "timestamp": _now_iso(),
        "time": _now_hhmm(),
        "progress": 100,
        "status": status or "done",
    }

    if path:
        entry["path"] = path
    if transfer_id:
        entry["transfer_id"] = transfer_id

    data[peer].append(entry)
    _save_history(username, data)



def get_conversation(username: str, peer: str) -> list[dict]:
    """
    username ile peer arasındaki son 7 günlük konuşmayı döner.
    Her eleman GUI'nin chat_histories formatıyla uyumludur.
    """
    data = load_history(username)
    cutoff = _cutoff_dt()
    raw = data.get(peer, [])
    result = []
    for e in raw:
        ts = _parse_ts(e.get("timestamp", ""))
        if ts is None or ts < cutoff:
            continue
        # GUI item formatına dönüştür
        item: dict = {
            "type":      e["type"],
            "sender":    e["sender"],
            "time":      e.get("time", ""),
            "timestamp": e.get("timestamp", ""),
        }
        if e["type"] == "text":
            item["content"] = e.get("content", "")
            item["message_id"] = e.get("message_id")
            item["status"] = e.get("status")
        else:
            item["filename"] = e.get("filename", "")
            item["path"] = e.get("path")
            item["progress"] = e.get("progress", 100)
            item["status"] = e.get("status", "done")
            item["transfer_id"] = e.get("transfer_id")
        result.append(item)
    return result


def get_peers_with_history(username: str) -> list[str]:
    """
    Son 7 gün içinde en az bir mesajı olan peer listesini döner.
    Bu kullanıcılar çevrimdışı olsa da listede gösterilir.
    """
    data = load_history(username)
    cutoff = _cutoff_dt()
    peers = []
    for peer, entries in data.items():
        if any(
            _parse_ts(e.get("timestamp", "")) and
            _parse_ts(e["timestamp"]) >= cutoff
            for e in entries
        ):
            peers.append(peer)
    return peers

def update_message_status(username: str, peer: str,
                          message_id: str, status: str) -> None:
    data = load_history(username)
    if peer not in data:
        return

    updated = False
    for entry in reversed(data[peer]):
        if (
            entry.get("type") == "text"
            and entry.get("message_id") == message_id
            and entry.get("sender") == "Ben"
        ):
            entry["status"] = status
            updated = True
            break

    if updated:
        _save_history(username, data)

def update_file_status(username: str, peer: str,
                       transfer_id: str, status: str) -> None:
    data = load_history(username)
    if peer not in data:
        return

    updated = False
    for entry in reversed(data[peer]):
        if (
            entry.get("type") == "file"
            and entry.get("transfer_id") == transfer_id
            and entry.get("sender") == "Ben"
        ):
            entry["status"] = status
            updated = True
            break

    if updated:
        _save_history(username, data)