"""
ArchNodes - Unified Scraper Hub
Resolves and extracts assets from supported creative stock & design platforms.
"""

from core.normalizer import normalize_profile_url
from scrapers.base import scraper, fetch_media_stream, HEADERS_FOR_REQUESTS
from scrapers.freepik import FreepikScraper, add_account, remove_account, batch_add_accounts, auto_register_account
from scrapers.envato import get_envato_info
from core.bypass import get_request_proxies

def get_media_files_count(url: str) -> tuple:
    """Universal media count resolver across supported creative platforms."""
    res_norm = normalize_profile_url(url)
    profile_url, asset_name, platform = res_norm[0], res_norm[1], res_norm[2]
    if not profile_url:
        return 0, "Invalid or unsupported creative asset URL"

    if platform == "freepik":
        return 1, ""

    if platform == "envato":
        info, err = get_envato_info(profile_url)
        if err:
            return -1, err
        if info and info.get("items"):
            return len(info["items"]), ""
        return 0, "Envato Elements asset not found."

    # Generic probe
    try:
        res = scraper.get(profile_url, timeout=10, verify=False, proxies=get_request_proxies())
        if res.status_code == 404:
            return 0, f"Asset '{asset_name}' not found (404 Not Found)."
        return 1, ""
    except Exception as err:
        return -1, f"Failed to connect: {str(err)}"
