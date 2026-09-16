"""
ArchNodes - High-Speed Download Stream Manager
Handles streaming downloads with progress tracking and abort signals.
"""

import os
import time
import requests
from typing import Dict, Any
from core.normalizer import normalize_profile_url
from scrapers.base import fetch_media_stream, HEADERS_FOR_REQUESTS

download_state: Dict[str, Any] = {
    "is_running": False,
    "current": 0,
    "total": 0,
    "percentage": 0,
    "status_text": "Ready",
    "stop_flag": False
}

def get_download_progress() -> Dict[str, Any]:
    return dict(download_state)

def stop_download():
    download_state["stop_flag"] = True
    download_state["is_running"] = False
    download_state["status_text"] = "Download stopped."
