# memory_monitor.py
# Reads /proc/meminfo.

import json


def get_meminfo():
    out = {}
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) != 2:
                    continue
                key = parts[0].strip()
                val = parts[1].strip().split()
                if val:
                    try:
                        out[key] = int(val[0])
                    except Exception:
                        pass
    except Exception:
        pass
    return out


def free_mb():
    m = get_meminfo()
    return m.get("MemAvailable", 0) / 1024.0


def total_mb():
    m = get_meminfo()
    return m.get("MemTotal", 0) / 1024.0


def is_low(threshold_mb=400):
    return free_mb() < threshold_mb


def describe():
    m = get_meminfo()
    return {
        "total_mb": round(total_mb(), 0),
        "free_mb": round(free_mb(), 0),
        "swap_free_mb": round(m.get("SwapFree", 0) / 1024.0, 0),
        "low": is_low(),
    }


if __name__ == "__main__":
    print(json.dumps(describe(), indent=2))
