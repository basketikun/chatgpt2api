"""Cloudflare Tunnel manager — auto-start/stop cloudflared subprocess.

Paste your Cloudflare Tunnel token in Settings UI → tunnel auto-starts.
Auto-restarts on crash (monitored every 30s).
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time

from services.config import config

logger = logging.getLogger(__name__)

_tunnel_process: subprocess.Popen | None = None
_lock = threading.Lock()
_monitor_started = False


def _token() -> str:
    return str(config.get().get("cloudflare_tunnel_token", "")).strip()


def is_running() -> bool:
    with _lock:
        return _tunnel_process is not None and _tunnel_process.poll() is None


def start_tunnel() -> bool:
    global _tunnel_process
    token = _token()
    if not token:
        return False

    with _lock:
        if _tunnel_process is not None and _tunnel_process.poll() is None:
            return True
        try:
            _tunnel_process = subprocess.Popen(
                ["cloudflared", "tunnel", "--no-autoupdate", "run", "--token", token],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            time.sleep(2)
            if _tunnel_process.poll() is not None:
                stderr = _tunnel_process.stderr.read() if _tunnel_process.stderr else ""
                logger.error("Cloudflare Tunnel failed: %s", stderr[:300])
                _tunnel_process = None
                return False
            logger.info("Cloudflare Tunnel started (PID %d)", _tunnel_process.pid)
            return True
        except FileNotFoundError:
            logger.warning("cloudflared not installed")
            return False
        except Exception as exc:
            logger.error("Tunnel start error: %s", exc)
            return False


def stop_tunnel() -> bool:
    global _tunnel_process
    with _lock:
        if _tunnel_process is None:
            return True
        try:
            _tunnel_process.terminate()
            _tunnel_process.wait(timeout=10)
            _tunnel_process = None
            return True
        except Exception:
            try:
                _tunnel_process.kill()
                _tunnel_process.wait(timeout=5)
            except Exception:
                pass
            _tunnel_process = None
            return True


def restart_tunnel() -> bool:
    stop_tunnel()
    return start_tunnel()


def _monitor_loop() -> None:
    while True:
        time.sleep(30)
        try:
            token = _token()
            if not token:
                continue
            with _lock:
                if _tunnel_process is not None and _tunnel_process.poll() is not None:
                    logger.warning("Tunnel crashed (exit %d), restarting", _tunnel_process.returncode)
                    _tunnel_process = None
            if not is_running() and token:
                start_tunnel()
        except Exception:
            pass


def start_monitor() -> None:
    global _monitor_started
    if _monitor_started:
        return
    _monitor_started = True
    t = threading.Thread(target=_monitor_loop, daemon=True, name="cf-monitor")
    t.start()


def get_status() -> dict:
    return {"running": is_running(), "token_configured": bool(_token())}
