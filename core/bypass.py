"""
ArchNodes - Core Bypass & Anti-Block Engine
Provides DNS-over-HTTPS (Cloudflare, Google, AdGuard, Quad9) resolution and HTTP/HTTPS/SOCKS5 proxy routing.
"""

import os
import json
import socket
import requests
from typing import Dict, Any, Optional

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bypass_settings.json")

DOH_ENDPOINTS = {
    "cloudflare": "https://1.1.1.1/dns-query",
    "google": "https://dns.google/resolve",
    "adguard": "https://dns.adguard-dns.com/dns-query",
    "quad9": "https://dns.quad9.net/dns-query"
}

_doh_dns_cache = {}

def get_bypass_settings() -> Dict[str, Any]:
    default_settings = {
        "enabled": True,
        "mode": "doh",
        "doh_provider": "cloudflare",
        "custom_doh_url": "",
        "proxy_url": ""
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                default_settings.update(saved)
        except Exception:
            pass
    return default_settings

def save_bypass_settings(settings: Dict[str, Any]) -> bool:
    try:
        current = get_bypass_settings()
        current.update(settings)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
        _doh_dns_cache.clear()
        return True
    except Exception:
        return False

def resolve_ip_via_doh(domain: str, provider: str = "cloudflare", custom_url: str = "") -> Optional[str]:
    if not domain:
        return None
    if domain in _doh_dns_cache:
        return _doh_dns_cache[domain]

    endpoint = custom_url.strip() if provider == "custom" and custom_url else DOH_ENDPOINTS.get(provider, DOH_ENDPOINTS["cloudflare"])

    try:
        if "cloudflare" in endpoint or "adguard" in endpoint or "quad9" in endpoint:
            headers = {"Accept": "application/dns-json", "User-Agent": "ArchNodes/1.0"}
            params = {"name": domain, "type": "A"}
            r = requests.get(endpoint, headers=headers, params=params, timeout=5, verify=False)
            if r.status_code == 200:
                data = r.json()
                answers = data.get("Answer", [])
                for ans in answers:
                    if ans.get("type") == 1 and ans.get("data"):
                        ip = ans["data"]
                        _doh_dns_cache[domain] = ip
                        return ip
        elif "google" in endpoint:
            headers = {"Accept": "application/json", "User-Agent": "ArchNodes/1.0"}
            params = {"name": domain, "type": "A"}
            r = requests.get(endpoint, headers=headers, params=params, timeout=5, verify=False)
            if r.status_code == 200:
                data = r.json()
                answers = data.get("Answer", [])
                for ans in answers:
                    if ans.get("type") == 1 and ans.get("data"):
                        ip = ans["data"]
                        _doh_dns_cache[domain] = ip
                        return ip
    except Exception:
        pass
    return None

_orig_getaddrinfo = socket.getaddrinfo

def custom_doh_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    settings = get_bypass_settings()
    if settings.get("enabled") and settings.get("mode") in ["doh", "both"]:
        if isinstance(host, str) and not host.replace('.', '').isdigit() and ':' not in host:
            resolved_ip = resolve_ip_via_doh(
                host, 
                provider=settings.get("doh_provider", "cloudflare"),
                custom_url=settings.get("custom_doh_url", "")
            )
            if resolved_ip:
                host = resolved_ip
    return _orig_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = custom_doh_getaddrinfo

def get_request_proxies() -> Dict[str, str]:
    settings = get_bypass_settings()
    if settings.get("enabled") and settings.get("mode") in ["proxy", "both"]:
        p_url = settings.get("proxy_url", "").strip()
        if p_url:
            return {"http": p_url, "https": p_url}
    return {}
