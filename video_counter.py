# video_counter.py — Persistent unique video numbering (1 to 1000)
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
COUNTER_FILE = BASE_DIR / "video_counter.json"

DEFAULT = {
    "next_number": 1,
    "max_number": 1000,
    "completed": [],
}


def load_counter():
    if not COUNTER_FILE.exists():
        return dict(DEFAULT)
    try:
        with open(COUNTER_FILE, encoding="utf-8") as f:
            data = json.load(f)
        # Ensure all keys
        for k, v in DEFAULT.items():
            data.setdefault(k, v)
        return data
    except Exception:
        return dict(DEFAULT)


def save_counter(data):
    tmp = str(COUNTER_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, COUNTER_FILE)


def get_next_number():
    """Get next number without incrementing."""
    data = load_counter()
    return data["next_number"]


def claim_number():
    """
    Claim the next available number. Increments for next call.
    Cycles 1-1000 (skips completed).
    Returns the claimed number as int.
    """
    data = load_counter()
    max_n = data["max_number"]
    completed = set(data.get("completed", []))

    # Find next available number
    n = data["next_number"]
    tries = 0
    while tries < max_n:
        if n not in completed and 1 <= n <= max_n:
            break
        n += 1
        if n > max_n:
            n = 1
        tries += 1
    else:
        # All 1000 used — reset (or extend)
        print("[COUNTER] All 1000 used — resetting cycle")
        completed.clear()
        n = 1

    # Mark as in-progress (add to next position)
    data["next_number"] = n + 1 if n < max_n else 1
    save_counter(data)
    print(f"[COUNTER] Claimed video number: #{n:04d}")
    return n


def mark_complete(number):
    """Mark a video number as completed."""
    data = load_counter()
    completed = list(data.get("completed", []))
    if number not in completed:
        completed.append(number)
    data["completed"] = sorted(completed)
    save_counter(data)
    print(f"[COUNTER] Video #{number:04d} marked complete")
    return number


def get_padded(number):
    """Return string without padding (e.g., '42')."""
    return str(number)


def status():
    data = load_counter()
    return {
        "next_number": data["next_number"],
        "completed_count": len(data.get("completed", [])),
        "max_number": data["max_number"],
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "next":
            print(get_next_number())
        elif cmd == "claim":
            n = claim_number()
            print(f"Claimed: #{n:04d}")
        elif cmd == "complete":
            if len(sys.argv) > 2:
                mark_complete(int(sys.argv[2]))
        elif cmd == "status":
            print(json.dumps(status(), indent=2))
    else:
        print(json.dumps(status(), indent=2))
