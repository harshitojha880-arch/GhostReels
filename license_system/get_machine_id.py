import uuid, hashlib
mac = str(uuid.getnode())
print(f"YOUR MACHINE ID: {hashlib.sha256(f'{mac}-GhostReels'.encode()).hexdigest()[:16].upper()}")
