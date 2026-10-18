#!/data/data/com.termux/files/usr/bin/bash
# run_daemon.sh — starts orchestrator in tmux with low priority
# Usage: ./run_daemon.sh start | stop | status | attach | logs

SESSION="darkpsych"
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"

start_daemon() {
    # Wake lock so Termux survives screen off
    termux-wake-lock 2>/dev/null || true

    # Kill old session if exists
    tmux kill-session -t "$SESSION" 2>/dev/null || true

    # Start detached session
    tmux new-session -d -s "$SESSION" -c "$BASE_DIR" \
        "nice -n 19 ionice -c3 python3 orchestrator.py 2>&1 | tee -a pipeline.log"

    echo "[OK] Daemon started in tmux session: $SESSION"
    echo "     Attach: tmux attach -t $SESSION"
    echo "     Logs:   tail -f $BASE_DIR/pipeline.log"
}

stop_daemon() {
    tmux kill-session -t "$SESSION" 2>/dev/null && \
        echo "[OK] Stopped" || echo "[!] Not running"
    termux-wake-unlock 2>/dev/null || true
}

status_daemon() {
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        echo "[RUNNING] tmux session: $SESSION"
        tmux list-panes -t "$SESSION" -F "  pane #{pane_index}: #{pane_current_command}"
    else
        echo "[STOPPED]"
    fi
}

case "$1" in
    start)  start_daemon ;;
    stop)   stop_daemon ;;
    status) status_daemon ;;
    attach) tmux attach -t "$SESSION" ;;
    logs)   tail -f "$BASE_DIR/pipeline.log" ;;
    *)
        echo "Usage: $0 {start|stop|status|attach|logs}"
        exit 1
        ;;
esac
