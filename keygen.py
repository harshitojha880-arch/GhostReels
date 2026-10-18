import os, json, base64, sys
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

# 1. Generate Keys (Run only once)
if not os.path.exists("private_key.pem"):
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    with open("private_key.pem", "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))
    with open("public_key.pem", "wb") as f:
        f.write(public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))
    print("[OK] Keys Generated! Keep private_key.pem safe.")

def generate_key(device_id):
    with open("private_key.pem", "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)
        
    payload = {"device_id": device_id, "product": "GhostReels"}
    payload_bytes = json.dumps(payload, sort_keys=True).encode()
    signature = private_key.sign(payload_bytes)
    
    # Encode as a single string
    part1 = base64.b64encode(payload_bytes).decode()
    part2 = base64.b64encode(signature).decode()
    
    return f"{part1}.{part2}"

if __name__ == "__main__":
    print("====================================")
    print("  GHOSTREELS KEY GENERATOR (SELLER)")
    print("====================================")
    dev_id = input("Enter Buyer's Device ID: ").strip()
    if dev_id:
        key = generate_key(dev_id)
        print("\n" + "="*50)
        print(" ✅ LICENSE KEY GENERATED (Copy this to buyer):")
        print("="*50)
        print(f"\n{key}\n")
        print("="*50)
        print("Send this text to the buyer. Do NOT share private_key.pem.")
