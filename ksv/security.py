import base64
from django.conf import settings
from cryptography.fernet import Fernet

# Default fallback key for development if ENCRYPTION_KEY is not defined in settings.py
# Must be a 32-byte url-safe base64 key.
FALLBACK_KEY = b'uFj6n9Hwz4-1QJ0vV8_7x-3U-yF6WkLw_y5Zq8E9r-Q='

def get_fernet():
    key = getattr(settings, 'ENCRYPTION_KEY', None)
    if not key:
        key = FALLBACK_KEY
    if isinstance(key, str):
        key = key.encode('utf-8')
    return Fernet(key)

def encrypt_data(plain_text: str) -> str:
    """Encrypts a plaintext string and returns a base64 encoded ciphertext string."""
    if not plain_text:
        return ""
    f = get_fernet()
    cipher_bytes = f.encrypt(plain_text.encode('utf-8'))
    return cipher_bytes.decode('utf-8')

def decrypt_data(cipher_text: str) -> str:
    """Decrypts a base64 encoded ciphertext string and returns plaintext."""
    if not cipher_text:
        return ""
    f = get_fernet()
    try:
        decrypted_bytes = f.decrypt(cipher_text.encode('utf-8'))
        return decrypted_bytes.decode('utf-8')
    except Exception as e:
        # Fallback in case of decryption failures
        return f"[Decryption Error: {str(e)}]"
