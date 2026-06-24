from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DEFAULT_KEY_DIR = Path(__file__).resolve().parents[1] / "keys"
DEFAULT_PRIVATE_KEY_PATH = DEFAULT_KEY_DIR / "whatsapp_flow_private.pem"


def _load_private_key_pem() -> bytes | None:
    inline = os.getenv("WHATSAPP_FLOW_PRIVATE_KEY", "").strip()
    if inline:
        return inline.replace("\\n", "\n").encode("utf-8")

    key_path = Path(os.getenv("WHATSAPP_FLOW_PRIVATE_KEY_PATH", str(DEFAULT_PRIVATE_KEY_PATH)))
    if key_path.exists():
        return key_path.read_bytes()
    return None


def ensure_flow_keypair() -> tuple[bytes, bytes]:
    pem = _load_private_key_pem()
    if pem:
        private_key = serialization.load_pem_private_key(pem, password=None)
    else:
        DEFAULT_KEY_DIR.mkdir(parents=True, exist_ok=True)
        private_key = generate_private_key(public_exponent=65537, key_size=2048)
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        DEFAULT_PRIVATE_KEY_PATH.write_bytes(pem)

    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return pem, public_pem


def get_flow_public_key_pem() -> str:
    _, public_pem = ensure_flow_keypair()
    return public_pem.decode("utf-8")


def decrypt_flow_request(body: dict[str, Any]) -> tuple[dict[str, Any], bytes, bytes]:
    pem = _load_private_key_pem()
    if not pem:
        raise ValueError("WhatsApp Flow private key is not configured.")

    private_key = serialization.load_pem_private_key(pem, password=None)
    encrypted_aes_key = base64.b64decode(body["encrypted_aes_key"])
    encrypted_flow_data = base64.b64decode(body["encrypted_flow_data"])
    iv = base64.b64decode(body["initial_vector"])

    aes_key = private_key.decrypt(
        encrypted_aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    decrypted = AESGCM(aes_key).decrypt(iv, encrypted_flow_data, None)
    payload = json.loads(decrypted.decode("utf-8"))
    return payload, aes_key, iv


def encrypt_flow_response(response: dict[str, Any], aes_key: bytes, iv: bytes) -> str:
    flipped_iv = bytes(byte ^ 0xFF for byte in iv)
    encrypted = AESGCM(aes_key).encrypt(flipped_iv, json.dumps(response).encode("utf-8"), None)
    return base64.b64encode(encrypted).decode("utf-8")
