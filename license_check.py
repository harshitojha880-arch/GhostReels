import json, base64, subprocess, secrets, sys, time
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
    new_id = secrets.token_hex(8).upper()
    device_file.write_text(new_id)
    return new_id

def verify_license():
    time_file = BASE_DIR / ".last_run_time"
    
    if not LICENSE_FILE.exists():
        print("
" + "="*50 + "
 🔒 GHOSTREELS IS LOCKED
" + "="*50)
        print(f" Your Device ID: [1;33m{get_device_id()}[0m")
        print(" Send this ID to the seller for your License Key.")
        key_input = input("
 Paste License Key here: ").strip()
        try:
            part1, part2 = key_input.split(".")
            payload = json.loads(base64.b64decode(part1).decode())
            signature = base64.b64decode(part2)
            public_key = serialization.load_pem_public_key(PUB_KEY_PATH.read_bytes())
            public_key.verify(signature, json.dumps(payload, sort_keys=True).encode())
            if payload.get("device_id") != get_device_id():
                print("
[X] ERROR: License key is for a different device.")
                return False
            LICENSE_FILE.write_text(json.dumps({"payload": payload, "signature": base64.b64encode(signature).decode()}, indent=2))
            
            # Save current time when license is first activated
            time_file.write_text(str(time.time()))
            
            print("
[OK] License Activated Successfully!")
            return True
        except Exception:
            print("
[X] Invalid License Key.")
            return False

    try:
        data = json.loads(LICENSE_FILE.read_text())
        public_key = serialization.load_pem_public_key(PUB_KEY_PATH.read_bytes())
        public_key.verify(base64.b64decode(data["signature"]), json.dumps(data["payload"], sort_keys=True).encode())
        if data["payload"].get("device_id") != get_device_id(): return False
        
        current_time = time.time()
        
        # --- ANTI-TAMPER CHECK ---
        if time_file.exists():
            last_run = float(time_file.read_text())
            if current_time < last_run - 300: # 5 min tolerance for clock sync
                print("
[!] SYSTEM TIME TAMPERING DETECTED. Software Locked.")
                return False
            time_file.write_text(str(current_time))
        else:
            time_file.write_text(str(current_time))

        # --- EXPIRY CHECK ---
        if "expires_at" in data["payload"]:
            if current_time > data["payload"]["expires_at"]:
                print("
[!] YOUR 3-HOUR TRIAL HAS EXPIRED.")
                print("Please contact the seller to buy the full version.")
                return False
                
        return True
    except:
        return False


