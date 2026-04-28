import base64
import json
import sys
import time
import urllib.request
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT_DIR / "data" / "output"
BASE_URL = "http://127.0.0.1:8000"

# `python -m unittest discover -s test` puts the test directory before the
# repository root on sys.path. If this helper is imported as top-level `utils`,
# expose the real project utils package path so `utils.helper` still resolves.
if __name__ == "utils":
    __path__ = [str(ROOT_DIR / "utils")]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def load_auth_key() -> str:
    return json.loads((ROOT_DIR / "config.json").read_text(encoding="utf-8"))["auth-key"]


def post_json(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        BASE_URL + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {load_auth_key()}"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode())


def detect_ext(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return ".webp"
    if image_bytes.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    return ".png"


def save_image(image_b64: str, name: str) -> Path:
    image_bytes = base64.b64decode(image_b64)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{name}_{int(time.time())}{detect_ext(image_bytes)}"
    path.write_bytes(image_bytes)
    return path
