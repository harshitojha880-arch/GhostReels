import os, json, base64, sys, time
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

if not os.path.exists("private_key.pem"):
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    with open("private_key.pem", "wb") as f:
        f.write(private_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    with open("public_key.pem", "wb") as f:
        f.write(public_key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    print("[OK] Keys Generated.")

def generate_key(device_id, trial_hours=0):
    with open("private_key.pem", "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)
    payload = {"device_id": device_id, "product": "GhostReels"}
    if trial_hours > 0:
        payload["expires_at"] = int(time.time() + (trial_hours * 3600))
    payload_bytes = json.dumps(payload, sort_keys=True).encode()
    signature = private_key.sign(payload_bytes)
    return f"{base64.b64encode(payload_bytes).decode()}.{base64.b64encode(signature).decode()}"

if __name__ == "__main__":
    print("=== GHOSTREELS KEY GENERATOR ===")
    print("1. Permanent Key")
    print("2. Trial Key (3 Hours)")
    choice = input("Select option (1/2): ").strip()
    dev_id = input("Enter Buyer's Device ID: ").strip()
    if dev_id:
        if choice == "2":
            print(f"\n✅ 3-HOUR TRIAL KEY:\n{generate_key(dev_id, trial_hours=3)}\n")
        else:
            print(f"\n✅ PERMANENT KEY:\n{generate_key(dev_id, trial_hours=0)}\n")
