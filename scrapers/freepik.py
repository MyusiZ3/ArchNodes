"""
ArchNodes - Freepik & Magnific AI Downloader Scraper
Converts Freepik Premium / Magnific URLs to Direct Google Drive download links
with multi-account pool rotation, rate-limit tracking, and browser cache sync.
"""

import os
import re
import json
import time
import random
import requests
import cloudscraper
from typing import Dict, Optional, List, Tuple
from bs4 import BeautifulSoup

ACCOUNTS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "freepik_accounts.json")

RATE_LIMITED_ACCOUNTS: Dict[str, float] = {}
RATE_LIMIT_DURATION = 3600  # 1 hour cooldown per account limit

class FreepikRateLimitException(Exception):
    def __init__(self, message, reset_minutes=60, total_accounts=1):
        super().__init__(message)
        self.reset_minutes = reset_minutes
        self.total_accounts = total_accounts

def _load_accounts() -> List[Dict[str, str]]:
    if os.path.exists(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data
        except Exception:
            pass
    return []

def _save_accounts(accounts: List[Dict[str, str]]) -> bool:
    try:
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(accounts, f, indent=2)
        return True
    except Exception:
        return False

FREEPIK_ACCOUNTS: List[Dict[str, str]] = _load_accounts()

def add_account(email: str, password: str) -> Dict:
    accounts = _load_accounts()
    for acc in accounts:
        if acc["email"].lower() == email.lower():
            return {"success": False, "error": f"Account {email} is already in the pool"}
    
    try:
        scraper = FreepikScraper()
        if scraper._login_account(email, password):
            accounts.append({"email": email, "password": password})
            _save_accounts(accounts)
            FREEPIK_ACCOUNTS.clear()
            FREEPIK_ACCOUNTS.extend(accounts)
            return {"success": True, "message": f"Account {email} successfully added to the pool"}
        else:
            return {"success": False, "error": f"Login failed for {email}. Please verify your email and password."}
    except Exception as e:
        return {"success": False, "error": f"Error verifying login: {str(e)}"}

def batch_add_accounts(account_list: List[Dict[str, str]]) -> Dict:
    accounts = _load_accounts()
    existing_emails = {acc["email"].lower() for acc in accounts}
    
    added = []
    already_in_pool = []
    failed = []
    
    for item in account_list:
        email = (item.get("email") or "").strip()
        password = (item.get("password") or "").strip()
        if not email or not password:
            continue
            
        if email.lower() in existing_emails:
            already_in_pool.append(email)
            continue
            
        try:
            scraper = FreepikScraper()
            if scraper._login_account(email, password):
                accounts.append({"email": email, "password": password})
                existing_emails.add(email.lower())
                added.append(email)
            else:
                failed.append({"email": email, "reason": "Login failed (unregistered / unverified)"})
        except Exception as e:
            failed.append({"email": email, "reason": str(e)})
            
    if added:
        _save_accounts(accounts)
        FREEPIK_ACCOUNTS.clear()
        FREEPIK_ACCOUNTS.extend(accounts)
        
    return {
        "success": len(added) > 0 or len(already_in_pool) > 0,
        "added_count": len(added),
        "added_accounts": added,
        "already_in_pool": already_in_pool,
        "failed": failed,
        "total_in_pool": len(accounts),
        "accounts": accounts
    }

def remove_account(email: str) -> Dict:
    accounts = _load_accounts()
    filtered = [acc for acc in accounts if acc["email"].lower() != email.lower()]
    if len(filtered) == len(accounts):
        return {"success": False, "error": f"Account {email} not found"}
    _save_accounts(filtered)
    FREEPIK_ACCOUNTS.clear()
    FREEPIK_ACCOUNTS.extend(filtered)
    if email in RATE_LIMITED_ACCOUNTS:
        del RATE_LIMITED_ACCOUNTS[email]
    return {"success": True, "message": f"Account {email} removed from the pool"}

def auto_register_account() -> Dict:
    # Auto-register stub for 1-click temp mail account generation
    return {
        "success": False,
        "error": "Please use the Gmail Dot-Trick Generator or Add Manually to add accounts directly to your browser pool."
    }


class FreepikScraper:
    def __init__(self):
        self.base_url = "https://freepikdownloader.com"
        self.scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
        )
        self.csrf_token = ""
        self.is_logged_in = False
        self.current_account = None

    @classmethod
    def get_account_status(cls, custom_accounts: Optional[List[Dict[str, str]]] = None) -> Dict:
        now = time.time()
        pool = custom_accounts if (custom_accounts is not None and len(custom_accounts) > 0) else _load_accounts()
        total = len(pool)
        active = 0
        limited = 0
        min_reset = 999
        details = []

        for acc in pool:
            email = acc["email"]
            limit_expire = RATE_LIMITED_ACCOUNTS.get(email, 0)
            if limit_expire > now:
                limited += 1
                remaining_min = int((limit_expire - now) / 60) + 1
                if remaining_min < min_reset:
                    min_reset = remaining_min
                details.append({
                    "email": email,
                    "status": f"Limited (~{remaining_min}m remaining)",
                    "is_active": False,
                    "reset_minutes": remaining_min
                })
            else:
                active += 1
                details.append({
                    "email": email,
                    "status": "Ready / Active",
                    "is_active": True,
                    "reset_minutes": 0
                })

        if total == 0:
            summary = "0/0 Accounts (Pool Empty)"
            badge_text = "Freepik: Pool Empty"
            status_color = "#94A3B8"
        elif active > 0:
            summary = f"{active}/{total} Accounts Ready ({active} Active)"
            badge_text = f"Freepik Pool: {active}/{total} Ready"
            status_color = "#22C55E"
        else:
            summary = f"0/{total} Accounts Limited (Reset in ~{min_reset}m)"
            badge_text = f"Freepik Limit: 0/{total} (Reset in ~{min_reset}m)"
            status_color = "#F59E0B"

        return {
            "total_accounts": total,
            "active_accounts": active,
            "limited_accounts": limited,
            "reset_minutes": min_reset if limited > 0 else 0,
            "summary_text": summary,
            "badge_text": badge_text,
            "status_color": status_color,
            "accounts": details
        }

    def _login_account(self, email: str, password: str) -> bool:
        try:
            self.scraper.cookies.clear()
            home_res = self.scraper.get(self.base_url + "/")
            soup_home = BeautifulSoup(home_res.text, "html.parser")
            form_login = soup_home.find("form", id="form-login")
            if not form_login:
                return False
                
            self.csrf_token = form_login.find("input", {"name": "csrf_token"}).get("value", "")
            
            payload = {
                "csrf_token": self.csrf_token,
                "email": email,
                "password": password,
                "remember": "true"
            }
            
            headers = {
                "Referer": self.base_url + "/",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": self.base_url
            }
            
            login_res = self.scraper.post(
                self.base_url + "/action/login.php",
                data=payload,
                headers=headers
            )
            
            if "status" in login_res.text and "success" in login_res.text.lower():
                self.is_logged_in = True
                self.current_account = email
                return True
                
            dash_res = self.scraper.get(self.base_url + "/")
            if "logout" in dash_res.text.lower() or "user_id" in self.scraper.cookies.get_dict():
                self.is_logged_in = True
                self.current_account = email
                return True
                
            return False
        except Exception:
            return False

    def extract_gdrive_url(self, freepik_url: str, custom_accounts: Optional[List[Dict[str, str]]] = None) -> str:
        pool = custom_accounts if (custom_accounts is not None and len(custom_accounts) > 0) else _load_accounts()
        if not pool:
            raise Exception("No Freepik accounts in pool. Please add accounts in the Freepik modal.")
            
        now = time.time()
        available_accounts = [
            acc for acc in pool 
            if RATE_LIMITED_ACCOUNTS.get(acc.get("email", ""), 0) <= now
        ]

        if not available_accounts:
            status = self.get_account_status(pool)
            raise FreepikRateLimitException(
                f"Hourly download limit reached on all accounts ({status['total_accounts']}/{status['total_accounts']} Accounts Limited). Please try again in ~{status['reset_minutes']} minutes or add new accounts.",
                reset_minutes=status["reset_minutes"],
                total_accounts=status["total_accounts"]
            )

        last_error = ""

        for acc in available_accounts:
            email = acc["email"]
            password = acc["password"]
            
            try:
                if not self._login_account(email, password):
                    continue
                    
                home_res = self.scraper.get(self.base_url + "/")
                soup_home = BeautifulSoup(home_res.text, "html.parser")
                form_dl = soup_home.find("form", id="form-download")
                if not form_dl:
                    continue
                    
                dl_csrf = form_dl.find("input", {"name": "csrf_token"}).get("value", "")
                
                headers = {
                    "Referer": self.base_url + "/",
                    "X-Requested-With": "XMLHttpRequest",
                    "Origin": self.base_url
                }
                
                gen_res = self.scraper.post(
                    self.base_url + "/action/gen-link.php",
                    data={"csrf_token": dl_csrf, "url": freepik_url},
                    headers=headers
                )
                
                gen_data = gen_res.json()
                
                if gen_data.get("status") == "error":
                    msg = gen_data.get("message", "").lower()
                    if any(k in msg for k in ["limit", "hourly", "reached", "quota", "per hour", "1 hour"]):
                        RATE_LIMITED_ACCOUNTS[email] = time.time() + RATE_LIMIT_DURATION
                        last_error = gen_data.get("message")
                        continue
                    else:
                        raise Exception(f"FreepikDownloader: {gen_data.get('message')}")
                        
                file_id = gen_data.get("file_id") or gen_data.get("id") or gen_data.get("link")
                if not file_id:
                    raise Exception(f"Could not retrieve download ID from Freepik: {gen_res.text}")
                    
                if file_id.startswith("http"):
                    return file_id
                    
                learn_page_url = f"{self.base_url}/learn/{file_id}"
                learn_res = self.scraper.get(learn_page_url, headers={"Referer": self.base_url + "/"})
                
                match_dd = re.search(r'href=["\'](https?://[^"\']+/ddlink/[^"\']+)["\']', learn_res.text)
                if not match_dd:
                    match_dd = re.search(r'["\'](/ddlink/[^"\']+)["\']', learn_res.text)
                    if match_dd:
                        dd_url = self.base_url + match_dd.group(1)
                    else:
                        dd_url = f"{self.base_url}/ddlink/{file_id}"
                else:
                    dd_url = match_dd.group(1)
                    
                dd_res = self.scraper.get(dd_url, headers={"Referer": learn_page_url})
                
                match_gd = re.search(r'https://drive\.google\.com/uc\?export=download&id=[a-zA-Z0-9_-]+', dd_res.text)
                if match_gd:
                    return match_gd.group(0)
                    
                match_gd2 = re.search(r'https://drive\.google\.com/[^\s"\'<>]+', dd_res.text)
                if match_gd2:
                    return match_gd2.group(0)
                    
                match_direct = re.search(r'window\.location\.href\s*=\s*["\'](https?://[^"\']+)["\']', dd_res.text)
                if match_direct:
                    return match_direct.group(1)
                    
                raise Exception("Failed to parse Google Drive link from intermediate bypass page.")
                
            except FreepikRateLimitException:
                raise
            except Exception as e:
                last_error = str(e)
                continue

        status = self.get_account_status(pool)
        if status["active_accounts"] == 0:
            raise FreepikRateLimitException(
                f"Hourly limit reached on all pool accounts ({status['total_accounts']}/{status['total_accounts']} Limited). Reset in ~{status['reset_minutes']}m.",
                reset_minutes=status["reset_minutes"],
                total_accounts=status["total_accounts"]
            )
        raise Exception(f"Failed to generate Freepik download link: {last_error}")
