"""
ArchNodes - Envato Elements Asset Resolver
Fetches preview streams, high-resolution media, audio demos, video footage,
and template metadata from elements.envato.com links.
"""

import re
import json
from typing import Dict, Tuple, Optional
from bs4 import BeautifulSoup
from scrapers.base import scraper, HEADERS_FOR_REQUESTS
from core.bypass import get_request_proxies

_envato_cache = {}

def get_envato_info(url: str, force_fresh: bool = False) -> Tuple[Optional[Dict], str]:
    global _envato_cache
    if not force_fresh and url in _envato_cache:
        return _envato_cache[url], ""

    req_headers = dict(HEADERS_FOR_REQUESTS)
    req_headers["Referer"] = "https://elements.envato.com/"
    
    try:
        res = scraper.get(url, headers=req_headers, timeout=12, verify=False, proxies=get_request_proxies())
        if res.status_code != 200:
            return None, f"Failed to access Envato Elements (HTTP {res.status_code})"

        soup = BeautifulSoup(res.text, "html.parser")
        
        # Title Extraction
        title_el = soup.find("h1") or soup.find("title")
        title = title_el.get_text(strip=True) if title_el else "Envato Elements Asset"
        title = title.replace(" - Envato Elements", "").strip()

        media_items = []
        poster = ""

        # 1. Look for Video Previews (mp4/webm)
        for video_tag in soup.find_all("video"):
            src = video_tag.get("src")
            v_poster = video_tag.get("poster")
            if not src:
                source_tag = video_tag.find("source")
                if source_tag:
                    src = source_tag.get("src")
            if src and src.startswith("http"):
                media_items.append({
                    "type": "video",
                    "src": src,
                    "poster": v_poster or "",
                    "index": len(media_items) + 1
                })
                if not poster and v_poster:
                    poster = v_poster

        # 2. Look for Audio Previews (mp3/wav)
        for audio_tag in soup.find_all("audio"):
            src = audio_tag.get("src")
            if not src:
                source_tag = audio_tag.find("source")
                if source_tag:
                    src = source_tag.get("src")
            if src and src.startswith("http"):
                media_items.append({
                    "type": "audio",
                    "src": src,
                    "poster": poster or "https://elements.envato.com/favicon.ico",
                    "index": len(media_items) + 1
                })

        # 3. Look for High-Res Preview Images / Slides
        img_tags = soup.find_all("img")
        for img in img_tags:
            src = img.get("data-src") or img.get("src") or img.get("srcset", "").split(" ")[0]
            if src and "elements-cover-images" in src or "elements-preview-images" in src or "elements-video-cover-images" in src:
                if src not in [m["src"] for m in media_items]:
                    media_items.append({
                        "type": "image",
                        "src": src,
                        "poster": src,
                        "index": len(media_items) + 1
                    })
                    if not poster:
                        poster = src

        # 4. JSON-LD Embedded metadata
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    if not poster and data.get("image"):
                        img_val = data["image"]
                        poster = img_val if isinstance(img_val, str) else img_val[0] if isinstance(img_val, list) else ""
                    if not media_items and data.get("contentUrl"):
                        media_items.append({
                            "type": "file",
                            "src": data["contentUrl"],
                            "poster": poster,
                            "index": 1
                        })
            except Exception:
                pass

        if not poster and media_items:
            poster = media_items[0].get("poster") or media_items[0].get("src")

        if not media_items and poster:
            media_items.append({
                "type": "image",
                "src": poster,
                "poster": poster,
                "index": 1
            })

        if not media_items:
            return None, "No preview media found on this Envato Elements page."

        info = {
            "title": title,
            "poster": poster,
            "items": media_items,
            "total_items": len(media_items)
        }
        _envato_cache[url] = info
        return info, ""
        
    except Exception as e:
        return None, f"Error fetching Envato Elements info: {str(e)}"
