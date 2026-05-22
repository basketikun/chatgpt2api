"""Cloudflare Tunnel manager — auto-start/stop cloudflared subprocess.

The tunnel is started automatically on boot if cloudflare_tunnel_token is set
in data/studio/settings.json. The token can be configured via the Studio UI.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
import os

logger = logging.getLogger(__name__)

_tunnel_process: subprocess.Popen | None = None
_lock = threading.Lock()


def get_token() -> str:
    """Read Cloudflare tunnel token from settings."""
    from src.rag.settings import read
    return str(read().get("cloudflare_tunnel_token", "")).strip()


def is_running() -> bool:
    with _lock:
        return _tunnel_process is not None and _tunnel_process.poll() is None


def start_tunnel(token: str | None = None) -> bool:
    """Start cloudflared tunnel. Returns True if started successfully."""
    global _tunnel_process
    token = token or get_token()
    if not token:
        logger.info("Cloudflare Tunnel: no token configured, skipping")
        return False

    with _lock:
        if _tunnel_process is not None and _tunnel_process.poll() is None:
            logger.info("Cloudflare Tunnel: already running (PID %d)", _tunnel_process.pid)
            return True

        try:
            _tunnel_process = subprocess.Popen(
                ["cloudflared", "tunnel", "--no-autoupdate", "run", "--token", token],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            # Wait briefly to check if it started
            time.sleep(2)
            if _tunnel_process.poll() is not None:
                stderr = _tunnel_process.stderr.read() if _tunnel_process.stderr else ""
                logger.error("Cloudflare Tunnel failed to start: %s", stderr[:500])
                _tunnel_process = None
                return False
            logger.info("Cloudflare Tunnel started (PID %d)", _tunnel_process.pid)
            return True
        except FileNotFoundError:
            logger.warning("cloudflared binary not found — install cloudflared first")
            return False
        except Exception as exc:
            logger.error("Cloudflare Tunnel start error: %s", exc)
            return False


def stop_tunnel() -> bool:
    """Stop the running tunnel."""
    global _tunnel_process
    with _lock:
        if _tunnel_process is None:
            return True
        try:
            _tunnel_process.terminate()
            _tunnel_process.wait(timeout=10)
            logger.info("Cloudflare Tunnel stopped")
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
    """Restart the tunnel (e.g. after token change)."""
    stop_tunnel()
    return start_tunnel()


def _monitor_loop() -> None:
    """Background thread: restart tunnel if it crashes."""
    while True:
        time.sleep(30)
        try:
            token = get_token()
            if not token:
                time.sleep(60)
                continue
            with _lock:
                if _tunnel_process is not None and _tunnel_process.poll() is not None:
                    stderr = _tunnel_process.stderr.read() if _tunnel_process.stderr else ""
                    logger.warning("Cloudflare Tunnel crashed (exit %d), restarting...: %s",
                                 _tunnel_process.returncode, stderr[:200])
                    _tunnel_process = None
            if not is_running():
                start_tunnel(token)
        except Exception:
            pass


_monitor_started = False


def start_monitor() -> None:
    """Start background monitor thread (idempotent)."""
    global _monitor_started
    if _monitor_started:
        return
    _monitor_started = True
    t = threading.Thread(target=_monitor_loop, daemon=True, name="cf-tunnel-monitor")
    t.start()
    logger.info("Cloudflare Tunnel monitor started")
