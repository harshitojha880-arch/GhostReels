import base64, json, uuid, hashlib, sys
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# 🔴 APNI PUBLIC KEY YAHAN PASTE KARNA (Jab aap keygen.py chalayenge)
PUBLIC_KEY_B64 = "YOUR_PUBLIC_KEY_HERE" 

def get_machine_id():
    # Har phone ka unique ID (MAC address + hardware based)
    mac = str(uuid.getnode())
    return hashlib.sha256(f"{mac}-GhostReels".encode()).hexdigest()[:16].upper()

def verify_license():
    license_file = Path.home() / ".ghostreels_license"
    
    if not license_file.exists():
        print("\n❌ [LICENSE ERROR] No license found!")
        print("👉 Please purchase GhostReels to get your license file.")
        print(f"📱 Send this Machine ID to Developer: {get_machine_id()}")
        sys.exit(1)
        
    try:
        with open(license_file, "r") as f:
            data = json.load(f)
            
        key_b64 = data.get("license_key")
        saved_machine_id = data.get("machine_id")
        
        # Check if license is for this device
        if saved_machine_id != get_machine_id():
            print("\n❌ [LICENSE ERROR] This license belongs to another device.")
            sys.exit(1)
            
        # Verify ED25519 Signature
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(PUBLIC_KEY_B64))
        public_key.verify(base64.b64decode(key_b64), saved_machine_id.encode())
        print("✅ GhostReels License Verified. Welcome!")
        return True
        
    except Exception as e:
        print(f"\n❌ [LICENSE ERROR] Invalid license or tampered files: {e}")
        sys.exit(1)
