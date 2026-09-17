"""
Freepik Premium Scraper via FreepikDownloader.com
Fully programmatic (CloudScraper + BeautifulSoup)
Multi-account pool support with auto-rotation, rate limit status tracking, and GDrive link extraction.
Accounts stored in accounts.json for persistence. Auto-register via mail.tm temp mail.
"""

import os
import re
import json
import time
import random
import string
import requests
import cloudscraper
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Tuple

class FreepikRateLimitException(Exception):
    def __init__(self, message: str, reset_minutes: int = 45, total_accounts: int = 1):
        super().__init__(message)
        self.reset_minutes = reset_minutes
        self.total_accounts = total_accounts

# ── Account JSON Storage ─────────────────────────────────────────────────────
ACCOUNTS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "accounts.json")

def _load_accounts() -> List[Dict[str, str]]:
    """Load accounts from accounts.json"""
    try:
        if os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("accounts", [])
    except Exception as e:
        print(f"[FreepikScraper] Error loading accounts.json: {e}")
    return []

def _save_accounts(accounts: List[Dict[str, str]]):
    """Save accounts to accounts.json"""
    try:
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump({"accounts": accounts}, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[FreepikScraper] Error saving accounts.json: {e}")

def add_account(email: str, password: str) -> Dict:
    """Add account to pool after verifying login works"""
    accounts = _load_accounts()
    # Check duplicate
    for acc in accounts:
        if acc["email"].lower() == email.lower():
            return {"success": False, "error": f"Account {email} is already in the pool"}
    
    # Verify login works
    try:
        scraper = FreepikScraper()
        if scraper._login_account(email, password):
            accounts.append({"email": email, "password": password})
            _save_accounts(accounts)
            # Update global list
            FREEPIK_ACCOUNTS.clear()
            FREEPIK_ACCOUNTS.extend(accounts)
            return {"success": True, "message": f"Account {email} successfully added to the pool"}
        else:
            return {"success": False, "error": f"Login failed for {email}. Please ensure email & password are correct and the account is verified on freepikdownloader.com"}
    except Exception as e:
        return {"success": False, "error": f"Error verifying login: {str(e)}"}

def batch_add_accounts(account_list: List[Dict[str, str]]) -> Dict:
    """Verify and add multiple accounts to the pool at once"""
    accounts = _load_accounts()
    existing_emails = {acc["email"].lower() for acc in accounts}
    
    added = []
    failed = []
    already_in_pool = []
    
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
                failed.append({"email": email, "reason": "Login failed / account not activated on Freepik"})
        except Exception as e:
            failed.append({"email": email, "reason": str(e)})
            
    if added:
        _save_accounts(accounts)
        FREEPIK_ACCOUNTS.clear()
        FREEPIK_ACCOUNTS.extend(accounts)
        
    return {
        "success": len(added) > 0 or len(already_in_pool) > 0,
        "added_count": len(added),
        "added": added,
        "failed": failed,
        "already_in_pool": already_in_pool,
        "accounts": accounts,
        "account_status": FreepikScraper.get_account_status(accounts)
    }

def remove_account(email: str) -> Dict:
    """Remove account from pool"""
    accounts = _load_accounts()
    new_accounts = [acc for acc in accounts if acc["email"].lower() != email.lower()]
    if len(new_accounts) == len(accounts):
        return {"success": False, "error": f"Account {email} not found in pool"}
    _save_accounts(new_accounts)
    FREEPIK_ACCOUNTS.clear()
    FREEPIK_ACCOUNTS.extend(new_accounts)
    # Also remove from rate limit tracking
    RATE_LIMITED_ACCOUNTS.pop(email, None)
    return {"success": True, "message": f"Account {email} successfully removed from pool"}

def reload_accounts():
    """Reload accounts from JSON file into global list"""
    accounts = _load_accounts()
    FREEPIK_ACCOUNTS.clear()
    FREEPIK_ACCOUNTS.extend(accounts)

# ── Auto-Register via mail.tm ────────────────────────────────────────────────
MAILTM_API = "https://api.mail.tm"
FREEPIK_DL_BASE = "https://freepikdownloader.com"
DEFAULT_PASSWORD = "@Qwerty2003"

def _get_mailtm_domain() -> str:
    """Get active mail.tm domain"""
    r = requests.get(f"{MAILTM_API}/domains", timeout=15)
    r.raise_for_status()
    data = r.json()
    members = data.get("hydra:member", [])
    for m in members:
        if m.get("isActive"):
            return m["domain"]
    raise Exception("No active mail.tm domain found")

def _create_mailtm_account(domain: str) -> Dict:
    """Create a mail.tm account and return credentials + token"""
    username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
    email = f"{username}@{domain}"
    password = "TempPass@" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    
    r = requests.post(f"{MAILTM_API}/accounts", json={"address": email, "password": password}, timeout=15)
    if r.status_code not in [200, 201]:
        raise Exception(f"mail.tm account creation failed: {r.status_code} {r.text[:200]}")
    
    # Get auth token
    r_token = requests.post(f"{MAILTM_API}/token", json={"address": email, "password": password}, timeout=15)
    if r_token.status_code != 200:
        raise Exception(f"mail.tm token failed: {r_token.status_code}")
    token = r_token.json().get("token", "")
    
    return {"email": email, "password": password, "token": token}

def _poll_mailtm_inbox(token: str, max_wait: int = 25) -> Optional[str]:
    """Poll mail.tm inbox for verification link from freepikdownloader"""
    headers = {"Authorization": f"Bearer {token}"}
    start = time.time()
    while time.time() - start < max_wait:
        time.sleep(5)
        try:
            r = requests.get(f"{MAILTM_API}/messages", headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                messages = data.get("hydra:member", [])
                for msg in messages:
                    msg_id = msg.get("id", "")
                    # Fetch full message
                    r_msg = requests.get(f"{MAILTM_API}/messages/{msg_id}", headers=headers, timeout=15)
                    if r_msg.status_code == 200:
                        body = r_msg.json().get("html", [])
                        body_text = "".join(body) if isinstance(body, list) else str(body)
                        if not body_text:
                            body_text = r_msg.json().get("text", "")
                        links = re.findall(r'https?://freepikdownloader\.com/[^\s"<>\']+', body_text)
                        if links:
                            return links[0]
        except Exception as e:
            print(f"[AutoRegister] Inbox poll error: {e}")
    return None

def auto_register_account() -> Dict:
    """Fully automated: create temp email → register → verify → add to pool"""
    steps = []
    try:
        # Step 1: Get mail.tm domain
        steps.append("Fetching temp mail domain...")
        domain = _get_mailtm_domain()
        steps.append(f"Domain: {domain}")
        
        # Step 2: Create mail.tm account
        steps.append("Creating temporary email account...")
        mailtm = _create_mailtm_account(domain)
        temp_email = mailtm["email"]
        temp_token = mailtm["token"]
        steps.append(f"Email: {temp_email}")
        
        # Step 3: Register on freepikdownloader.com
        steps.append("Registering on freepikdownloader.com...")
        sess = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "mobile": False})
        sess.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"})
        
        # Get CSRF from register page
        reg_page = sess.get(f"{FREEPIK_DL_BASE}/register", timeout=20)
        soup = BeautifulSoup(reg_page.text, "html.parser")
        csrf_inp = soup.find("input", {"name": re.compile(r"csrf", re.I)})
        csrf = csrf_inp.get("value") if csrf_inp else ""
        
        if not csrf:
            meta = soup.find("meta", {"name": "X-CSRF-TOKEN"})
            csrf = meta.get("content") if meta else ""
        
        reg_data = {
            "csrf_token": csrf,
            "sys_lang_id": "1",
            "email": temp_email,
            "password": DEFAULT_PASSWORD,
            "confirm_password": DEFAULT_PASSWORD,
            "terms_conditions": "1",
            "referral_code": ""
        }
        reg_resp = sess.post(f"{FREEPIK_DL_BASE}/register-post", data=reg_data,
                            headers={"X-Requested-With": "XMLHttpRequest"}, timeout=20, allow_redirects=True)
        steps.append(f"Register status: {reg_resp.status_code}")
        
        # Step 4: Try login immediately (some sites don't need email verification)
        steps.append("Testing login without verification...")
        csrf2_page = sess.get(f"{FREEPIK_DL_BASE}/freepik-downloader", timeout=20)
        soup2 = BeautifulSoup(csrf2_page.text, "html.parser")
        csrf2_inp = soup2.find("input", {"name": "csrf_token"})
        csrf2 = csrf2_inp.get("value") if csrf2_inp else csrf
        
        login_data = {"email": temp_email, "password": DEFAULT_PASSWORD, "sysLangId": "1", "csrf_token": csrf2}
        login_resp = sess.post(f"{FREEPIK_DL_BASE}/AuthController/loginPost", data=login_data,
                              headers={"X-Requested-With": "XMLHttpRequest"}, timeout=20)
        try:
            login_json = login_resp.json()
        except:
            login_json = {}
        
        if login_json.get("result") == 1:
            steps.append("Login successful without email verification!")
            # Add to pool
            accounts = _load_accounts()
            accounts.append({"email": temp_email, "password": DEFAULT_PASSWORD})
            _save_accounts(accounts)
            FREEPIK_ACCOUNTS.clear()
            FREEPIK_ACCOUNTS.extend(accounts)
            return {
                "success": True,
                "email": temp_email,
                "password": DEFAULT_PASSWORD,
                "message": f"Account {temp_email} created and added to pool successfully!",
                "steps": steps,
                "account_status": FreepikScraper.get_account_status()
            }
        
        # Step 5: Poll for verification email
        steps.append("Waiting for verification email (max 25s)...")
        vlink = _poll_mailtm_inbox(temp_token, max_wait=90)
        
        if not vlink:
            steps.append("Verification email not received. Retrying login...")
            # Try login one more time
            login_resp2 = sess.post(f"{FREEPIK_DL_BASE}/AuthController/loginPost", data=login_data,
                                   headers={"X-Requested-With": "XMLHttpRequest"}, timeout=20)
            try:
                lr2 = login_resp2.json()
            except:
                lr2 = {}
            if lr2.get("result") == 1:
                steps.append("Login successful!")
                accounts = _load_accounts()
                accounts.append({"email": temp_email, "password": DEFAULT_PASSWORD})
                _save_accounts(accounts)
                FREEPIK_ACCOUNTS.clear()
                FREEPIK_ACCOUNTS.extend(accounts)
                return {
                    "success": True,
                    "email": temp_email,
                    "password": DEFAULT_PASSWORD,
                    "message": f"Account {temp_email} created successfully!",
                    "steps": steps,
                    "account_status": FreepikScraper.get_account_status()
                }
            return {
                "success": False,
                "error": f"Temp mail domain ({domain}) is blocked by FreepikDownloader. Please use the Gmail Dot-Trick tab for 100% reliable account registration.",
                "steps": steps
            }
        
        # Step 6: Click verification link
        steps.append(f"Clicking verification link...")
        sess.get(vlink, timeout=20)
        
        # Step 7: Final login test
        steps.append("Logging in after verification...")
        csrf3_page = sess.get(f"{FREEPIK_DL_BASE}/freepik-downloader", timeout=20)
        soup3 = BeautifulSoup(csrf3_page.text, "html.parser")
        csrf3_inp = soup3.find("input", {"name": "csrf_token"})
        csrf3 = csrf3_inp.get("value") if csrf3_inp else csrf2
        
        login_data3 = {"email": temp_email, "password": DEFAULT_PASSWORD, "sysLangId": "1", "csrf_token": csrf3}
        login_resp3 = sess.post(f"{FREEPIK_DL_BASE}/AuthController/loginPost", data=login_data3,
                               headers={"X-Requested-With": "XMLHttpRequest"}, timeout=20)
        try:
            lr3 = login_resp3.json()
        except:
            lr3 = {}
        
        if lr3.get("result") == 1:
            steps.append("Login successful after verification!")
            accounts = _load_accounts()
            accounts.append({"email": temp_email, "password": DEFAULT_PASSWORD})
            _save_accounts(accounts)
            FREEPIK_ACCOUNTS.clear()
            FREEPIK_ACCOUNTS.extend(accounts)
            return {
                "success": True,
                "email": temp_email,
                "password": DEFAULT_PASSWORD,
                "message": f"Account {temp_email} created and verified successfully!",
                "steps": steps,
                "account_status": FreepikScraper.get_account_status()
            }
        else:
            return {
                "success": False,
                "error": f"Verification completed but login still failed: {lr3}",
                "steps": steps
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Auto-register error: {str(e)}",
            "steps": steps
        }

# ── Global account pool state (loaded from JSON) ────────────────────────────
FREEPIK_ACCOUNTS: List[Dict[str, str]] = _load_accounts()

# Track rate limited accounts: {email: timestamp_limited_until}
RATE_LIMITED_ACCOUNTS: Dict[str, float] = {}

class FreepikScraper:
    def __init__(self):
        self.base_url = "https://freepikdownloader.com"
        self.scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
        )
        self.csrf_token = ""
        self.current_email = ""

    @staticmethod
    def get_account_status(accounts: Optional[List[Dict[str, str]]] = None) -> Dict:
        """Returns rate limit status and quota summary across all accounts in the pool"""
        if accounts is None:
            accounts = _load_accounts()
            FREEPIK_ACCOUNTS.clear()
            FREEPIK_ACCOUNTS.extend(accounts)
        
        now = time.time()
        total = len(accounts)
        active = 0
        limited = 0
        min_reset = 60
        details = []

        for acc in accounts:
            email = acc.get("email", "")
            if not email:
                continue
            limited_until = RATE_LIMITED_ACCOUNTS.get(email, 0)
            if limited_until > now:
                limited += 1
                remaining_min = int((limited_until - now) / 60) + 1
                min_reset = min(min_reset, remaining_min)
                details.append({
                    "email": email,
                    "status": f"Hourly Limit (Reset in ~{remaining_min}m)",
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
        """Authenticate specific account on freepikdownloader.com"""
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
                "sys_lang_id": "1"
            }
            headers = {
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.base_url + "/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            res = self.scraper.post(f"{self.base_url}/AuthController/loginPost", data=payload, headers=headers)
            if res.status_code == 200 and res.json().get("result") == 1:
                self.current_email = email
                return True
            return False
        except Exception as e:
            print(f"[FreepikScraper] Login error for {email}: {e}")
            return False

    def extract_gdrive_url(self, freepik_url: str, custom_accounts: Optional[List[Dict[str, str]]] = None) -> str:
        """Convert a Freepik Premium URL to a Direct Google Drive download link with smart auto-switching across pool accounts"""
        pool = custom_accounts if (custom_accounts is not None and len(custom_accounts) > 0) else _load_accounts()
        if not pool:
            raise Exception("No Freepik accounts in pool. Please add accounts in the Freepik modal.")

        # Clean URL to ensure FreepikDownloader accepts it
        clean_url = freepik_url.strip().split('#')[0]
        if ".htm" in clean_url:
            clean_url = clean_url.split('?')[0]
        if "magnific.com" in clean_url or "magnific.ai" in clean_url:
            clean_url = clean_url.replace("www.magnific.com", "www.freepik.com").replace("magnific.com", "freepik.com").replace("www.magnific.ai", "www.freepik.com").replace("magnific.ai", "freepik.com")
            
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
        attempted_count = 0

        # Try every available account in the pool sequentially
        for acc in available_accounts:
            email = acc.get("email", "").strip()
            password = acc.get("password", "").strip()
            if not email or not password:
                continue

            attempted_count += 1
            print(f"[FreepikScraper] Attempting extraction with account #{attempted_count}: {email}")
            
            # 1. Attempt login
            if not self._login_account(email, password):
                print(f"[FreepikScraper] Login failed for {email}. Auto-switching to next account...")
                last_error = f"Login failed for {email}"
                continue

            # 2. Attempt link extraction
            try:
                gdrive_link = self._process_extraction(clean_url)
                if gdrive_link:
                    print(f"[FreepikScraper] Successfully extracted GDrive link using {email}")
                    return gdrive_link
            except Exception as exc:
                err_text = str(exc)
                print(f"[FreepikScraper] Account {email} extraction error: {err_text}. Switching to next account...")
                RATE_LIMITED_ACCOUNTS[email] = time.time() + 3600
                last_error = err_text
                continue

        # If all accounts in pool failed
        status = self.get_account_status(pool)
        if last_error:
            raise Exception(f"{last_error} (tried {attempted_count} pool accounts)")
        else:
            raise FreepikRateLimitException(
                f"All {len(pool)} pool accounts are currently rate-limited or unverified. Please add a fresh account.",
                reset_minutes=status.get("reset_minutes", 60),
                total_accounts=len(pool)
            )

    def _process_extraction(self, freepik_url: str) -> str:
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": self.base_url + "/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # 1. Fetch homepage to get fresh CSRF
        home_after = self.scraper.get(self.base_url + "/")
        soup_after = BeautifulSoup(home_after.text, "html.parser")
        csrf_inp = soup_after.find("input", {"name": "csrf_token"})
        csrf_val = csrf_inp.get("value") if csrf_inp else self.csrf_token

        # 2. Submit link generator AJAX
        ajax_payload = {
            "csrf_token": csrf_val,
            "url": freepik_url.strip().split("#")[0].split("?")[0] if ".htm" in freepik_url else freepik_url.strip().split("#")[0],
            "sys_lang_id": "1",
            "g-recaptcha-response": ""
        }
        res = self.scraper.post(f"{self.base_url}/AjaxController/freepik_downloader", data=ajax_payload, headers=headers)
        res_json = res.json()

        if res_json.get("code") != 1:
            msg = res_json.get("message", "Failed to generate link")
            clean_msg = re.sub(r'<[^>]+>', ' ', msg).strip()
            clean_msg = ' '.join(clean_msg.split())
            raise Exception(clean_msg)

        gen_url = res_json.get("token")
        
        # 3. Access generate-link page
        gen_resp = self.scraper.get(gen_url)
        soup_gen = BeautifulSoup(gen_resp.text, "html.parser")
        btn = soup_gen.find(id="btnCounter")
        next_url = btn.get("href") if btn else None
        
        if not next_url:
            raise Exception("Could not find btnCounter href")
            
        # 4. Access download-file page
        if "download-file" in next_url:
            dl_file_url = next_url
        else:
            proc_resp = self.scraper.get(next_url)
            soup_proc = BeautifulSoup(proc_resp.text, "html.parser")
            dl_link = soup_proc.find("a", href=re.compile(r"download-file"))
            dl_file_url = dl_link.get("href") if dl_link else None
            
        if not dl_file_url:
            raise Exception("Could not find download-file URL")
            
        # 5. Access /links?t= page
        df_resp = self.scraper.get(dl_file_url)
        soup_df = BeautifulSoup(df_resp.text, "html.parser")
        link_a = soup_df.find("a", href=re.compile(r"links"))
        links_url = link_a.get("href") if link_a else None
        
        if not links_url:
            raise Exception("Could not find links URL")
            
        # 6. Access /learn/ page with token
        l_resp = self.scraper.get(links_url)
        l_soup = BeautifulSoup(l_resp.text, "html.parser")
        
        learn_target_url = None
        for a in l_soup.find_all("a"):
            h = a.get("href", "")
            if "/learn/" in h:
                learn_target_url = h
                break
                
        if not learn_target_url:
            raise Exception("Could not find learn target URL on links page")
            
        # 7. Extract generatedownload token and first ddlink slug
        learn_resp = self.scraper.get(learn_target_url)
        learn_soup = BeautifulSoup(learn_resp.text, "html.parser")
        
        gen_tok = None
        ddlink = None
        for s in learn_soup.find_all("script"):
            st = s.string or ""
            m1 = re.search(r"'generatedownload'\s*:\s*'([^']+)'", st)
            if m1:
                gen_tok = m1.group(1)
            m2 = re.search(r"var\s+ddlink\s*=\s*'([^']+)'", st)
            if m2:
                ddlink = m2.group(1)
                
        if not gen_tok or not ddlink:
            raise Exception("Could not extract generatedownload token or ddlink")
            
        # 8. Post to /aaaaaaaaa to authorize cookies
        csrf_learn = learn_soup.find("input", {"name": "csrf_token"})
        csrf_learn_val = csrf_learn.get("value") if csrf_learn else csrf_val
        
        a_payload = {
            "csrf_token": csrf_learn_val,
            "generatedownload": gen_tok,
            "sys_lang_id": "1"
        }
        self.scraper.post(f"{self.base_url}/aaaaaaaaa", data=a_payload, headers=headers)
        
        # 9. Fetch final learn page
        final_dl_url = f"{self.base_url}/learn/{ddlink}" if not ddlink.startswith("http") else ddlink
        f_resp = self.scraper.get(final_dl_url)
        
        # 10. Extract direct GDrive URL from the final page JS logic
        match = re.search(r"var\s+ddlink\s*=\s*'([^']+)'", f_resp.text)
        if match:
            gdrive_url = match.group(1)
            return gdrive_url
            
        raise Exception("Google Drive URL regex match failed on final page")

if __name__ == "__main__":
    print("Testing FreepikScraper E2E...")
    scraper = FreepikScraper()
    print("Account Status:", scraper.get_account_status())
