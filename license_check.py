import json, base64, subprocess, secrets
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

BASE_DIR = Path(__file__).resolve().parent
PUB_KEY_PATH = BASE_DIR / "public_key.pem"
LICENSE_FILE = BASE_DIR / "license.json"

def get_device_id():
    try:
        res = subprocess.run(["termux-telephony-deviceinfo"], capture_output=True, text=True)
        if res.returncode == 0:
            dev_id = json.loads(res.stdout).get("device_id")
            if dev_id and dev_id != "null": return str(dev_id)
    except: pass
    try:
        with open("/sys/class/net/wlan0/address", "r") as f:
            mac = f.read().strip().replace(":", "")
            if mac: return mac
    except: pass
    device_file = Path.home() / ".ghostreels_device_id"
    if device_file.exists(): return device_file.read_text().strip()
    else:
        new_id = secrets.token_hex(8).upper()
        device_file.write_text(new_id)
        return new_id

def verify_license():
    if not PUB_KEY_PATH.exists():
        print("[!] public_key.pem missing! Cannot verify license.")
        return False
    if not LICENSE_FILE.exists():
        print("\n[!] LICENSE REQUIRED: license.json not found.")
        return False
    try:
        data = json.loads(LICENSE_FILE.read_text())
        payload = data["payload"]
        signature = base64.b64decode(data["signature"])
        public_key = serialization.load_pem_public_key(PUB_KEY_PATH.read_bytes())
        payload_bytes = json.dumps(payload, sort_keys=True).encode()
        public_key.verify(signature, payload_bytes)
        
        current_device = get_device_id()
        if payload.get("device_id") and payload.get("device_id") != current_device:
            print("\n[!] LICENSE ERROR: Locked to a different device.")
            return False
        return True
    except InvalidSignature:
        print("\n[!] LICENSE ERROR: Invalid Signature (Tampered).")
        return False
    except Exception as e:
        print(f"\n[!] LICENSE ERROR: {e}")
        return False
