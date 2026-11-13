"""Seed the egress proxy pool with the fixed mihomo node ports.

Run inside the app pod (or anywhere that can resolve the cluster Service). The port
count must match what ``script/build-egress-clash-config.py`` actually wrote into the
egress core; the default of 5 is the HK set that was verified CF-clean. Re-running is
idempotent: existing URLs are skipped, and enabling the pool is a settings write.

Usage:
    python script/seed-egress-pool.py [--count N] [--no-enable]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.proxy_pool_service import proxy_pool  # noqa: E402

SERVICE_HOST = "clash-egress-nodes.chatgpt2api-egress.svc.cluster.local"
PORT_START = 20001


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--no-enable", action="store_true", help="seed entries but leave the pool disabled")
    args = parser.parse_args()

    count = max(1, int(args.count))
    urls = [f"http://{SERVICE_HOST}:{PORT_START + index}" for index in range(count)]
    result = proxy_pool.add_entries(urls, source="manual")
    for entry in result["added"]:
        print(f"added {entry['id']} {entry['url']}")
    for url in result["skipped"]:
        print(f"exists {url}")
    for error in result["errors"]:
        print(f"error {error['url']}: {error['error']}")

    if not args.no_enable:
        proxy_pool.update_settings({"enabled": True})
        print("pool enabled")
    print(f"{len(result['added'])} added, {len(proxy_pool.list_entries())} total entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
