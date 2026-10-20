# local_gemma_server.py
# Persistent local Gemma-3-1B llama-server controller.
# - Binds to 127.0.0.1 only
# - Conservative context (4096), 4 threads
# - Idempotent start (won't double-launch)
# - Readiness probe with bounded retries
# - Logs to local_gemma_server.log

import os
import sys
import time
import json
import socket
import signal
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = Path.home() / "SCRIPTFORGE" / "models" / "qwen2.5-1.5b" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"
LOG_FILE = BASE_DIR / "local_gemma_server.log"
PID_FILE = BASE_DIR / "local_gemma_server.pid"

HOST = "127.0.0.1"
PORT = 8089
CTX_SIZE = 4096
THREADS = 2
BATCH_SIZE = 128
READY_TIMEOUT = 90   # seconds to wait for /health OK
READY_POLL_INTERVAL = 1.0


def _log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _port_in_use(host, port):
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def _http_get(path, timeout=3):
    url = f"http://{HOST}:{PORT}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception:
        return None, b""


def is_server_ready():
    """Return True if /health returns OK."""
    code, body = _http_get("/health", timeout=2)
    if code != 200:
        return False
    try:
        data = json.loads(body.decode("utf-8", errors="ignore") or "{}")
    except Exception:
        return False
    # Accept {"status":"ok"} or {"status":"loading model"} as not-ready
    return str(data.get("status", "")).lower() in ("ok", "ready")


def read_pid():
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except Exception:
        return None


def pid_alive(pid):
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def stop_server():
    pid = read_pid()
    if not pid_alive(pid):
        # Try pkill by name as fallback
        try:
            subprocess.run(["pkill", "-f", "llama-server"], timeout=5)
        except Exception:
            pass
        try:
            PID_FILE.unlink()
        except Exception:
            pass
        _log("stop_server: no running instance")
        return True

    _log(f"stop_server: terminating PID {pid}")
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception:
        pass

    # Wait up to 15s for graceful exit
    for _ in range(30):
        if not pid_alive(pid):
            break
        time.sleep(0.5)

    if pid_alive(pid):
        _log("stop_server: SIGKILL after timeout")
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass

    try:
        PID_FILE.unlink()
    except Exception:
        pass
    return True


def start_server(force=False):
    """Idempotent: starts server if not already running & ready."""
    if is_server_ready():
        _log("start_server: already running and ready — reusing")
        return True

    if _port_in_use(HOST, PORT) and not force:
        _log(f"start_server: port {PORT} in use but /health not OK — waiting")
        # Might be mid-boot
        if wait_ready(timeout=READY_TIMEOUT):
            _log("start_server: existing instance became ready")
            return True
        _log("start_server: existing instance not responding — killing")
        stop_server()
        time.sleep(2)

    if not MODEL_PATH.exists():
        raise Exception(f"[X] Model not found: {MODEL_PATH}")

    cmd = [
        "llama-server",
        "-m", str(MODEL_PATH),
        "-c", str(CTX_SIZE),
        "-t", str(THREADS),
        "-b", str(BATCH_SIZE),
        "--host", HOST,
        "--port", str(PORT),
        "--no-webui",
        "--log-disable",   # quieter; falls back if unsupported
    ]

    # Some builds don't support --log-disable / --no-webui.
    # Retry without them if start fails immediately.
    fallback_cmd = [
        "llama-server",
        "-m", str(MODEL_PATH),
        "-c", str(CTX_SIZE),
        "-t", str(THREADS),
        "-b", str(BATCH_SIZE),
        "--host", HOST,
        "--port", str(PORT),
    ]

    _log(f"start_server: launching llama-server on {HOST}:{PORT}")
    _log(f"  model: {MODEL_PATH}")
    _log(f"  ctx: {CTX_SIZE} | threads: {THREADS} | batch: {BATCH_SIZE}")

    # Open log file for stdout/stderr append
    log_fp = open(LOG_FILE, "ab", buffering=0)

    def _try_launch(c):
        try:
            proc = subprocess.Popen(
                c,
                cwd=str(BASE_DIR),
                stdout=log_fp,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
            return proc
        except FileNotFoundError:
            raise Exception("[X] llama-server not found in PATH")
        except Exception as e:
            _log(f"  launch failed: {e}")
            return None

    proc = _try_launch(cmd)
    if proc is None:
        _log("start_server: primary launch failed — trying fallback flags")
        proc = _try_launch(fallback_cmd)

    if proc is None:
        raise Exception("[X] Could not launch llama-server")

    PID_FILE.write_text(str(proc.pid))
    _log(f"start_server: PID {proc.pid}")

    # Probe for readiness
    if wait_ready(timeout=READY_TIMEOUT):
        _log("start_server: ready")
        return True

    # Not ready — check if process died
    if proc.poll() is not None:
        _log(f"start_server: process exited code {proc.returncode}")
        raise Exception(f"llama-server died (exit {proc.returncode}) — see {LOG_FILE.name}")

    _log("start_server: not ready within timeout")
    raise Exception(f"llama-server not ready in {READY_TIMEOUT}s")


def wait_ready(timeout=READY_TIMEOUT):
    t0 = time.time()
    last_state = None
    while time.time() - t0 < timeout:
        if is_server_ready():
            return True
        # If port not open at all yet, keep waiting
        state = "port_open" if _port_in_use(HOST, PORT) else "port_closed"
        if state != last_state:
            _log(f"  probe: {state}")
            last_state = state
        time.sleep(READY_POLL_INTERVAL)
    return False


def ensure_server():
    """Public entry: guarantee a running, ready server."""
    if is_server_ready():
        return True
    return start_server()


def pause_server():
    """Freeze llama-server with SIGSTOP — CPU 0%, RAM kept, no state loss."""
    pid = read_pid()
    if not pid_alive(pid):
        return False
    try:
        os.kill(pid, signal.SIGSTOP)
        _log(f"pause_server: PID {pid} paused (SIGSTOP)")
        return True
    except Exception as e:
        _log(f"pause_server failed: {e}")
        return False


def resume_server():
    """Resume frozen llama-server with SIGCONT."""
    pid = read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGCONT)
        _log(f"resume_server: PID {pid} resumed (SIGCONT)")
        return True
    except Exception as e:
        _log(f"resume_server failed: {e}")
        return False


def is_paused():
    """Check if process is in stopped state."""
    pid = read_pid()
    if pid is None:
        return False
    try:
        with open(f"/proc/{pid}/stat") as f:
            stat = f.read().split()
        state = stat[2]  # 3rd field is state
        return state == "T"  # T = stopped
    except Exception:
        return False


def clear_kv_cache():
    """Ask llama-server to clear its KV cache (frees context RAM)."""
    try:
        # llama-server exposes /slots; erase resets context
        req = urllib.request.Request(
            f"http://{HOST}:{PORT}/slots?action=erase",
            method="POST",
            data=b"",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            _log(f"clear_kv_cache: HTTP {r.status}")
            return True
    except Exception as e:
        # Endpoint may not exist; non-fatal
        _log(f"clear_kv_cache: {e}")
        return False


def status():
    pid = read_pid()
    ready = is_server_ready()
    port_open = _port_in_use(HOST, PORT)
    return {
        "pid": pid,
        "pid_alive": pid_alive(pid),
        "port_open": port_open,
        "ready": ready,
        "port": PORT,
        "model": str(MODEL_PATH),
    }


# ============================================================
# CLI
# ============================================================
def _cmd_status():
    st = status()
    print(json.dumps(st, indent=2))


def _cmd_start():
    start_server()


def _cmd_stop():
    stop_server()


def _cmd_restart():
    stop_server()
    time.sleep(2)
    start_server()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "start":
        _cmd_start()
    elif cmd == "stop":
        _cmd_stop()
    elif cmd == "restart":
        _cmd_restart()
    elif cmd == "status":
        _cmd_status()
    elif cmd == "ensure":
        ok = ensure_server()
        print("ready" if ok else "not-ready")
    elif cmd == "pause":
        print("paused" if pause_server() else "not-running")
    elif cmd == "resume":
        print("resumed" if resume_server() else "not-running")
    elif cmd == "clear":
        print("cleared" if clear_kv_cache() else "no-slots-endpoint")
    else:
        print("Usage: python3 local_gemma_server.py {start|stop|restart|status|ensure|pause|resume|clear}")
