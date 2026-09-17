"""
ArchNodes - Pool Cloud Vault & Multi-Account Downloads Aggregator
Persistently manages and syncs generated download links across all accounts in the pool.
"""

import os
import json
import time
import re
from typing import List, Dict, Optional, Tuple
from bs4 import BeautifulSoup
import cloudscraper

VAULT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vault_cache.json")
ACCOUNTS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "accounts.json")
ENVATO_ACCOUNTS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "envato_accounts.json")


def load_vault() -> List[Dict]:
    """Load cached download items from vault_cache.json"""
    try:
        if os.path.exists(VAULT_FILE):
            with open(VAULT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("items", []) if isinstance(data, dict) else data
    except Exception as e:
        print(f"[Vault] Error loading vault_cache.json: {e}")
    return []


def save_vault(items: List[Dict]) -> None:
    """Save download items to vault_cache.json"""
    try:
        with open(VAULT_FILE, "w", encoding="utf-8") as f:
            json.dump({"items": items, "last_updated": time.time()}, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Vault] Error saving vault_cache.json: {e}")


def _extract_slug(url: str) -> str:
    """Normalize asset URL to clean slug identifier"""
    if not url:
        return ""
    clean = url.split('#')[0].split('?')[0].rstrip('/')
    slug = clean.split('/')[-1]
    slug = re.sub(r'_\d+\.htm.*', '', slug).lower()
    return slug


def find_vault_item(url: str) -> Optional[Dict]:
    """Find a cached download item by URL or matching slug"""
    if not url:
        return None
    slug = _extract_slug(url)
    items = load_vault()
    for item in items:
        cached_url = item.get("url", "")
        cached_slug = item.get("slug", "") or _extract_slug(cached_url)
        if url.strip().lower() == cached_url.strip().lower():
            return item
        if slug and slug == cached_slug:
            return item
    return None


def add_vault_item(url: str, title: str, gdrive_url: str, platform: str, account_email: str = "") -> Dict:
    """Add or update an item in the persistent vault"""
    items = load_vault()
    slug = _extract_slug(url)
    
    # Check if existing item needs update
    for item in items:
        cached_slug = item.get("slug", "") or _extract_slug(item.get("url", ""))
        if (url and url == item.get("url")) or (slug and slug == cached_slug):
            item["download_url"] = gdrive_url
            item["title"] = title or item.get("title", "Creative Asset")
            item["updated_at"] = time.time()
            if account_email:
                item["account"] = account_email
            save_vault(items)
            return item

    # New item
    new_item = {
        "id": f"vault_{int(time.time()*1000)}",
        "url": url,
        "slug": slug,
        "title": title or "Creative Asset",
        "download_url": gdrive_url,
        "platform": platform,
        "account": account_email,
        "created_at": time.time(),
        "updated_at": time.time()
    }
    items.insert(0, new_item)
    save_vault(items)
    return new_item


def sync_all_accounts_history() -> Dict:
    """
    Login to all Freepik & Envato accounts, scrape their /downloads tables,
    resolve valid tokens to Google Drive URLs, and save them to vault_cache.json.
    """
    from scrapers.freepik import FreepikScraper, _load_accounts
    from scrapers.envato import EnvatoScraper, _load_envato_accounts

    vault_items = load_vault()
    existing_gdrive_urls = {item.get("download_url") for item in vault_items if item.get("download_url")}
    existing_slugs = {item.get("slug") for item in vault_items if item.get("slug")}

    synced_count = 0
    errors = []

    # 1. Sync Freepik Accounts
    fp_accounts = _load_accounts()
    fp_scraper = FreepikScraper()
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://freepikdownloader.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    for acc in fp_accounts:
        email = acc.get("email", "").strip()
        pwd = acc.get("password", "").strip()
        if not email or not pwd:
            continue

        try:
            if not fp_scraper._login_account(email, pwd):
                continue

            dl_page = fp_scraper.scraper.get(f"{fp_scraper.base_url}/downloads", timeout=15)
            soup = BeautifulSoup(dl_page.text, "html.parser")
            table = soup.find("table")
            if not table:
                continue

            for tr in table.find_all("tr"):
                cells = [td.get_text().strip() for td in tr.find_all(["td", "th"])]
                links = [a.get("href") for a in tr.find_all("a") if "/generate-link/" in a.get("href", "")]
                if not links:
                    continue

                gen_url = links[0]
                raw_title = cells[-1] if len(cells) >= 2 else "Freepik Asset"
                clean_title = raw_title.split("\n")[0].replace("Premium PSD", "").replace("Premium", "").replace("|", "").strip()
                slug = re.sub(r'[^a-zA-Z0-9]+', '-', clean_title).strip('-').lower()

                if slug in existing_slugs:
                    continue

                try:
                    gdrive_url = fp_scraper._resolve_gen_url_to_gdrive(gen_url, headers)
                    if gdrive_url and gdrive_url not in existing_gdrive_urls:
                        new_item = {
                            "id": f"vault_{int(time.time()*1000)}_{synced_count}",
                            "url": f"https://www.freepik.com/premium-psd/{slug}",
                            "slug": slug,
                            "title": clean_title or "Freepik Asset",
                            "download_url": gdrive_url,
                            "platform": "freepik",
                            "account": email,
                            "created_at": time.time(),
                            "updated_at": time.time()
                        }
                        vault_items.insert(0, new_item)
                        existing_gdrive_urls.add(gdrive_url)
                        existing_slugs.add(slug)
                        synced_count += 1
                except Exception as exc:
                    pass
        except Exception as e:
            errors.append(f"Freepik {email}: {str(e)}")

    # 2. Sync Envato Accounts
    env_accounts = _load_envato_accounts()
    env_scraper = EnvatoScraper()
    headers_env = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://envato-downloader.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    for acc in env_accounts:
        email = acc.get("email", "").strip()
        pwd = acc.get("password", "").strip()
        if not email or not pwd:
            continue

        try:
            if not env_scraper._login_account(email, pwd):
                continue

            dl_page = env_scraper.scraper.get(f"{env_scraper.base_url}/downloads", timeout=15)
            soup = BeautifulSoup(dl_page.text, "html.parser")
            table = soup.find("table")
            if not table:
                continue

            for tr in table.find_all("tr"):
                cells = [td.get_text().strip() for td in tr.find_all(["td", "th"])]
                links = [a.get("href") for a in tr.find_all("a") if "/generate-link/" in a.get("href", "")]
                if not links:
                    continue

                gen_url = links[0]
                raw_title = cells[-1] if len(cells) >= 2 else "Envato Asset"
                clean_title = raw_title.split("\n")[0].replace("|", "").strip()
                slug = re.sub(r'[^a-zA-Z0-9]+', '-', clean_title).strip('-').lower()

                if slug in existing_slugs:
                    continue

                try:
                    gdrive_url = env_scraper._resolve_gen_url_to_gdrive(gen_url, headers_env)
                    if gdrive_url and gdrive_url not in existing_gdrive_urls:
                        new_item = {
                            "id": f"vault_{int(time.time()*1000)}_{synced_count}",
                            "url": f"https://elements.envato.com/{slug}",
                            "slug": slug,
                            "title": clean_title or "Envato Asset",
                            "download_url": gdrive_url,
                            "platform": "envato",
                            "account": email,
                            "created_at": time.time(),
                            "updated_at": time.time()
                        }
                        vault_items.insert(0, new_item)
                        existing_gdrive_urls.add(gdrive_url)
                        existing_slugs.add(slug)
                        synced_count += 1
                except Exception as exc:
                    pass
        except Exception as e:
            errors.append(f"Envato {email}: {str(e)}")

    save_vault(vault_items)

    return {
        "success": True,
        "synced_count": synced_count,
        "total_items": len(vault_items),
        "items": vault_items,
        "errors": errors
    }
