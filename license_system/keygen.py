import base64, json, sys
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

def generate_keys():
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    print("🔒 SAVE THIS PRIVATE KEY (Never share this!):")
    print(base64.b64encode(private_key.private_bytes_raw()).decode())
    print("\n🔓 PUBLIC KEY (Paste this in license_check.py):")
    print(base64.b64encode(public_key.public_bytes_raw()).decode())

def generate_license(machine_id, private_key_b64):
    private_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key_b64))
    signature = private_key.sign(machine_id.encode())
    
    license_data = {
        "machine_id": machine_id,
        "license_key": base64.b64encode(signature).decode()
    }
    
    with open("license.json", "w") as f:
        json.dump(license_data, f)
    print(f"✅ License generated for {machine_id}. Send 'license.json' to the buyer.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        generate_keys()
    elif len(sys.argv) == 3:
        generate_license(sys.argv[1], sys.argv[2])
