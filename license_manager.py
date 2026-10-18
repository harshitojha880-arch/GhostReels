import hmac
import hashlib
import base64
import sys

# YE SECRET SALT SIRF TUMHARE PAAS HONA CHAHIYE
SECRET = "GHOSTREELS_SECRET_SALT_987654321"

def generate_key(email):
    msg = email.lower().strip().encode()
    sig = hmac.new(SECRET.encode(), msg, hashlib.sha256).digest()
    b32 = base64.b32encode(sig).decode().upper()
    raw = b32[:16]
    return f"GHOST-{raw[0:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:16]}"

if __name__ == "__main__":
    if len(sys.argv) > 1:
        email = sys.argv[1]
        print(f"Buyer Email: {email}")
        print(f"License Key: {generate_key(email)}")
    else:
        print("Usage: python3 license_manager.py buyer@email.com")
