#!/data/data/com.termux/files/usr/bin/bash
# Prevent Android OOM killer from terminating our processes.

pkill -f survival_guard.sh 2>/dev/null
sleep 1

while true; do
    for pid in $(pgrep -f "python3.*run.py" 2>/dev/null); do
        echo -500 > /proc/$pid/oom_score_adj 2>/dev/null
    done
    for pid in $(pgrep -f "llama-server" 2>/dev/null); do
        echo -500 > /proc/$pid/oom_score_adj 2>/dev/null
    done
    sleep 30
done
