#!/data/data/com.termux/files/usr/bin/bash
# thermal_guard.sh — pauses pipeline if phone gets hot
# Checks thermal zone every 60s, SIGSTOPs python if overheated

SESSION="darkpsych"
CHECK_INTERVAL=60
HOT_THRESHOLD=65000  # millidegrees = 65°C
COOL_THRESHOLD=50000 # 50°C

get_temp() {
    # Try common Android thermal zones
    for zone in /sys/class/thermal/thermal_zone*/temp; do
        if [ -r "$zone" ]; then
            cat "$zone" 2>/dev/null
            return
        fi
    done
    echo "0"
}

paused=0

while true; do
    if ! tmux has-session -t "$SESSION" 2>/dev/null; then
        echo "[GUARD] Session not running, exiting"
        break
    fi

    temp=$(get_temp)

    if [ "$temp" -gt "$HOT_THRESHOLD" ] && [ "$paused" -eq 0 ]; then
        echo "[GUARD] HOT ($temp) — pausing pipeline"
        pkill -STOP -f "orchestrator.py" 2>/dev/null
        paused=1
    elif [ "$temp" -lt "$COOL_THRESHOLD" ] && [ "$paused" -eq 1 ]; then
        echo "[GUARD] COOL ($temp) — resuming pipeline"
        pkill -CONT -f "orchestrator.py" 2>/dev/null
        paused=0
    fi

    sleep $CHECK_INTERVAL
done
