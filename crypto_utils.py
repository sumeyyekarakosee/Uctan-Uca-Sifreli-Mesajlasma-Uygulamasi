import os
import base64
from typing import Tuple

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def b64_encode(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")

def b64_decode(data: str) -> bytes:
    return base64.b64decode(data.encode("utf-8"))

def generate_rsa_keypair() -> Tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    public_key = private_key.public_key()
    return private_key, public_key

def serialize_public_key(public_key: rsa.RSAPublicKey) -> str:
    pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return pem.decode("utf-8")

def serialize_private_key(private_key: rsa.RSAPrivateKey) -> str:
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    return pem.decode("utf-8")

def load_public_key(pem_data: str) -> rsa.RSAPublicKey:
    return serialization.load_pem_public_key(pem_data.encode("utf-8"))

def load_private_key(pem_data: str) -> rsa.RSAPrivateKey:
    return serialization.load_pem_private_key(
        pem_data.encode("utf-8"),
        password=None
    )

def rsa_encrypt_with_public_key(public_key_pem: str, plaintext: str) -> str:
    public_key = load_public_key(public_key_pem)
    ciphertext = public_key.encrypt(
        plaintext.encode("utf-8"),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    return b64_encode(ciphertext)

def rsa_decrypt_with_private_key(private_key, ciphertext_b64: str) -> str:
    ciphertext = b64_decode(ciphertext_b64)
    plaintext = private_key.decrypt(
        ciphertext,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    return plaintext.decode("utf-8")

def generate_aes_key() -> str:
    key = AESGCM.generate_key(bit_length=256)
    return b64_encode(key)

def aes_encrypt(aes_key_b64: str, plaintext: bytes) -> str:
    key = b64_decode(aes_key_b64)
    aesgcm = AESGCM(key)

    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    combined = nonce + ciphertext
    return b64_encode(combined)

def aes_decrypt(aes_key_b64: str, encrypted_b64: str) -> bytes:
    key = b64_decode(aes_key_b64)
    aesgcm = AESGCM(key)

    combined = b64_decode(encrypted_b64)
    nonce = combined[:12]
    ciphertext = combined[12:]

    return aesgcm.decrypt(nonce, ciphertext, None)