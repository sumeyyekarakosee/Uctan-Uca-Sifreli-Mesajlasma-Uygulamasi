import os
from typing import Tuple

def read_file_as_bytes(file_path: str) -> Tuple[str, bytes]:
    filename = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        data = f.read()
    return filename, data

def save_received_file(filename: str, data: bytes, folder: str = "received_files") -> str:
    os.makedirs(folder, exist_ok=True)
    save_path = os.path.join(folder, filename)

    base, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(save_path):
        save_path = os.path.join(folder, f"{base}_{counter}{ext}")
        counter += 1

    with open(save_path, "wb") as f:
        f.write(data)

    return save_path