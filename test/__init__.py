"""Test package defaults; never use production credentials in tests."""

import os

os.environ.setdefault("CHATGPT2API_AUTH_KEY", "test-auth")
