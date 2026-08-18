"""Vercel WSGI entrypoint for the Flask API."""

from pathlib import Path
import sys

SERVER_DIR = Path(__file__).resolve().parent.parent / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from api import app  # noqa: E402
