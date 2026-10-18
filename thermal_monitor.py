# thermal_monitor.py v2
# Uses termux-api for battery. Falls back to sysfs if available.

import os
import glob
import json
import subprocess


def _run(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True,
                           text=True, timeout=5)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return None


def get_battery_temp():
    """Battery temp in °C via termux-api."""
    # Try termux-api first (most reliable on Android 16)
    out = _run("termux-battery-status")
    if out:
        try:
            data = json.loads(out)
            t = data.get("temperature")
            if t is not None:
                return float(t)
        except Exception:
            pass

    # Fallback: sysfs (usually blocked on OriginOS)
    for p in [
        "/sys/class/power_supply/battery/temp",
        "/sys/class/power_supply/bms/temp",
    ]:
        try:
            with open(p) as f:
                v = int(f.read().strip())
            return v / 1000.0 if v > 1000 else v / 10.0
        except Exception:
            pass

    return None


def get_max_thermal_temp():
    """Max thermal zone temp. Usually blocked, returns None."""
    max_c = None
    for p in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        try:
            with open(p) as f:
                v = int(f.read().strip())
            c = v / 1000.0 if v > 1000 else float(v)
            if 10 <= c <= 120:
                if max_c is None or c > max_c:
                    max_c = c
        except Exception:
            continue
    return max_c


def get_temp():
    b = get_battery_temp()
    if b is not None:
        return b
    return get_max_thermal_temp()


def is_too_hot():
    """Returns (too_hot, temp, reason)."""
    b = get_battery_temp()
    t = get_max_thermal_temp()

    if b is not None and b >= 40.0:
        return True, b, "battery"
    if t is not None and t >= 52.0:
        return True, t, "soc"
    return False, (b if b is not None else t), None


def is_cool_enough():
    b = get_battery_temp()
    t = get_max_thermal_temp()

    if b is not None and b >= 37.0:
        return False
    if t is not None and t >= 47.0:
        return False
    return True


def describe():
    b = get_battery_temp()
    t = get_max_thermal_temp()
    too_hot, temp, reason = is_too_hot()
    return {
        "battery_c": b,
        "soc_max_c": t,
        "too_hot": too_hot,
        "reason": reason,
        "cool": is_cool_enough(),
    }


if __name__ == "__main__":
    print(json.dumps(describe(), indent=2))
