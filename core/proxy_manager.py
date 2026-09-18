"""
ArchNodes - Network & Proxy Rotation Manager
Manages rotating proxies (HTTP, HTTPS, SOCKS4, SOCKS5), User-Agent randomization, and IP spoofing defenses.
"""

import os
import json
import random
import time
import requests
import cloudscraper
from typing import Dict, List, Optional, Tuple

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "proxy_settings.json")

DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.3; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
]

_ROUND_ROBIN_INDEX = 0

def load_proxy_settings() -> Dict:
    """Load proxy settings from proxy_settings.json"""
    default_settings = {
        "enabled": False,
        "rotation_mode": "random",  # "random" or "round-robin"
        "proxies": [],
        "rotate_user_agents": True,
        "timeout_sec": 12,
        "last_tested": 0
    }
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_settings.update(data)
    except Exception as e:
        print(f"[ProxyManager] Error reading proxy settings: {e}")
    return default_settings

def save_proxy_settings(settings: Dict) -> bool:
    """Save proxy settings to proxy_settings.json"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception as e:
        print(f"[ProxyManager] Error saving proxy settings: {e}")
        return False

def get_random_user_agent() -> str:
    """Return a randomized modern desktop user agent"""
    return random.choice(DEFAULT_USER_AGENTS)

def format_proxy_url(proxy_str: str) -> Optional[Dict[str, str]]:
    """Format raw proxy string into standard requests/cloudscraper proxy dict"""
    if not proxy_str:
        return None
    raw = proxy_str.strip()
    if not raw:
        return None
    
    # If already has scheme (http://, https://, socks5://, socks4://)
    if "://" in raw:
        scheme = raw.split("://")[0].lower()
        return {"http": raw, "https": raw}
    
    # Default to http://
    return {"http": f"http://{raw}", "https": f"http://{raw}"}

def get_next_proxy() -> Optional[Dict[str, str]]:
    """Get the next active proxy based on configured rotation mode"""
    global _ROUND_ROBIN_INDEX
    settings = load_proxy_settings()
    if not settings.get("enabled"):
        return None
        
    proxies = settings.get("proxies", [])
    if not proxies:
        return None
        
    valid_proxies = [p.strip() for p in proxies if p and p.strip()]
    if not valid_proxies:
        return None
        
    mode = settings.get("rotation_mode", "random")
    if mode == "round-robin":
        _ROUND_ROBIN_INDEX = (_ROUND_ROBIN_INDEX + 1) % len(valid_proxies)
        selected = valid_proxies[_ROUND_ROBIN_INDEX]
    else:
        selected = random.choice(valid_proxies)
        
    return format_proxy_url(selected)

def apply_network_settings(scraper_or_session) -> None:
    """Apply current proxy and randomized headers to a cloudscraper or requests session"""
    settings = load_proxy_settings()
    
    # 1. User Agent Randomization
    if settings.get("rotate_user_agents", True):
        ua = get_random_user_agent()
        scraper_or_session.headers.update({"User-Agent": ua})
        
    # 2. Proxy Application
    if settings.get("enabled"):
        proxy_dict = get_next_proxy()
        if proxy_dict:
            scraper_or_session.proxies = proxy_dict
    else:
        scraper_or_session.proxies = {}

def create_configured_scraper(browser_options: Optional[Dict] = None):
    """Factory function to create a ready-to-use cloudscraper with network settings pre-applied"""
    opts = browser_options or {'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    scraper = cloudscraper.create_scraper(browser=opts)
    apply_network_settings(scraper)
    return scraper

def test_single_proxy(proxy_str: str, timeout: int = 10) -> Dict:
    """Test latency and outgoing IP of a single proxy"""
    formatted = format_proxy_url(proxy_str)
    if not formatted:
        return {"proxy": proxy_str, "status": "invalid", "error": "Invalid format"}
        
    start_t = time.time()
    try:
        res = requests.get(
            "https://api.ipify.org?format=json",
            proxies=formatted,
            timeout=timeout,
            headers={"User-Agent": get_random_user_agent()}
        )
        latency_ms = int((time.time() - start_t) * 1000)
        if res.status_code == 200:
            ip = res.json().get("ip", "unknown")
            return {
                "proxy": proxy_str,
                "status": "active",
                "latency_ms": latency_ms,
                "ip": ip,
                "error": None
            }
        else:
            return {
                "proxy": proxy_str,
                "status": "failed",
                "latency_ms": latency_ms,
                "error": f"HTTP {res.status_code}"
            }
    except Exception as e:
        latency_ms = int((time.time() - start_t) * 1000)
        return {
            "proxy": proxy_str,
            "status": "failed",
            "latency_ms": latency_ms,
            "error": str(e)
        }

def test_all_proxies(timeout: int = 8) -> Dict:
    """Test all configured proxies in parallel or sequence"""
    settings = load_proxy_settings()
    proxies = settings.get("proxies", [])
    results = []
    active_count = 0
    
    for p in proxies:
        p_str = p.strip()
        if not p_str:
            continue
        res = test_single_proxy(p_str, timeout=timeout)
        if res.get("status") == "active":
            active_count += 1
        results.append(res)
        
    # Update last_tested timestamp
    settings["last_tested"] = time.time()
    save_proxy_settings(settings)
    
    return {
        "total": len(results),
        "active_count": active_count,
        "results": results
    }

def get_current_ip_info() -> Dict:
    """Fetch current direct external IP without proxy"""
    try:
        start_t = time.time()
        res = requests.get("https://api.ipify.org?format=json", timeout=8)
        lat = int((time.time() - start_t) * 1000)
        if res.status_code == 200:
            return {"ip": res.json().get("ip", "Unknown"), "latency_ms": lat, "direct": True}
    except Exception as e:
        return {"ip": "Offline / Error", "error": str(e), "direct": True}
    return {"ip": "Unknown", "direct": True}
