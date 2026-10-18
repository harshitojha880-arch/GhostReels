import json, base64, subprocess, secrets, sys
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
    # Agar license.json nahi hai, toh lock screen dikhao
    if not LICENSE_FILE.exists():
        dev_id = get_device_id()
        print("\n" + "="*50)
        print(" 🔒 GHOSTREELS IS LOCKED")
        print("="*50)
        print(f" Your Device ID: \033[1;33m{dev_id}\033[0m")
        print(" Please send this ID to the seller to get your License Key.")
        print("="*50)
        
        key_input = input("\n Paste License Key here: ").strip()
        
        try:
            part1, part2 = key_input.split(".")
            payload = json.loads(base64.b64decode(part1).decode())
            signature = base64.b64decode(part2)
            
            public_key = serialization.load_pem_public_key(PUB_KEY_PATH.read_bytes())
            public_key.verify(signature, json.dumps(payload, sort_keys=True).encode())
            
            if payload.get("device_id") != dev_id:
                print("\n[X] ERROR: This license key is for a different device.")
                return False
                
            license_data = {
                "payload": payload,
                "signature": base64.b64encode(signature).decode()
            }
            LICENSE_FILE.write_text(json.dumps(license_data, indent=2))
            print("\n[OK] License Activated Successfully! Starting GhostReels...")
            return True
        except Exception as e:
            print(f"\n[X] Invalid License Key. Please check and try again.")
            return False
            
    # Agar file hai, toh verify karo
    try:
        data = json.loads(LICENSE_FILE.read_text())
        payload = data["payload"]
        signature = base64.b64decode(data["signature"])
        public_key = serialization.load_pem_public_key(PUB_KEY_PATH.read_bytes())
        public_key.verify(signature, json.dumps(payload, sort_keys=True).encode())
        
        if payload.get("device_id") != get_device_id():
            print("\n[!] LICENSE ERROR: Locked to a different device.")
            return False
        return True
    except InvalidSignature:
        print("\n[!] LICENSE ERROR: Invalid Signature.")
        return False
    except Exception as e:
        print(f"\n[!] LICENSE ERROR: {e}")
        return False
