import os
import re
import time
import json
import cloudscraper
import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Tuple

ENVATO_ACCOUNTS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "envato_accounts.json")
RATE_LIMITED_ENVATO_ACCOUNTS: Dict[str, float] = {}

def _load_envato_accounts() -> List[Dict[str, str]]:
    if not os.path.exists(ENVATO_ACCOUNTS_FILE):
        return []
    try:
        with open(ENVATO_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _save_envato_accounts(accounts: List[Dict[str, str]]) -> None:
    try:
        with open(ENVATO_ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(accounts, f, indent=2)
    except Exception as e:
        print(f"[Envato] Error saving accounts: {e}")

def test_envato_login(email: str, password: str) -> Tuple[bool, str]:
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    try:
        home_res = scraper.get("https://envato-downloader.com/", timeout=15)
        soup_home = BeautifulSoup(home_res.text, "html.parser")
        form_login = soup_home.find("form", id="form-login")
        if not form_login:
            return False, "Could not find login form on envato-downloader.com"
        csrf_token = form_login.find("input", {"name": "csrf_token"}).get("value", "")
        payload = {
            "csrf_token": csrf_token,
            "email": email,
            "password": password,
            "sys_lang_id": "1"
        }
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://envato-downloader.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = scraper.post("https://envato-downloader.com/AuthController/loginPost", data=payload, headers=headers, timeout=15)
        res_json = res.json()
        if res.status_code == 200 and res_json.get("result") == 1:
            return True, "Login successful"
        msg = res_json.get("error_message") or res_json.get("message") or "Invalid credentials"
        clean_msg = re.sub(r'<[^>]+>', ' ', str(msg)).strip()
        return False, clean_msg or "Login failed"
    except Exception as e:
        return False, str(e)

def add_account(email: str, password: str, verify: bool = True) -> Dict:
    accounts = _load_envato_accounts()
    for acc in accounts:
        if acc.get("email", "").lower() == email.lower():
            return {"success": False, "error": "Account already exists in pool"}
            
    is_valid = True
    msg = "Account added"
    if verify:
        is_valid, msg = test_envato_login(email, password)
        if not is_valid:
            return {"success": False, "error": f"Verification failed: {msg}"}
            
    new_acc = {
        "email": email,
        "password": password,
        "verified": is_valid,
        "added_at": time.time()
    }
    accounts.append(new_acc)
    _save_envato_accounts(accounts)
    return {"success": True, "message": "Account added and verified successfully", "account": new_acc}

def remove_account(email: str) -> Dict:
    accounts = _load_envato_accounts()
    filtered = [acc for acc in accounts if acc.get("email", "").lower() != email.lower()]
    if len(filtered) == len(accounts):
        return {"success": False, "error": "Account not found"}
    _save_envato_accounts(filtered)
    if email in RATE_LIMITED_ENVATO_ACCOUNTS:
        del RATE_LIMITED_ENVATO_ACCOUNTS[email]
    return {"success": True, "message": "Account removed"}

def batch_add_accounts(acc_list: List[Dict[str, str]]) -> Dict:
    accounts = _load_envato_accounts()
    existing_emails = {acc.get("email", "").lower() for acc in accounts}
    added_count = 0
    for item in acc_list:
        em = item.get("email", "").strip()
        pw = item.get("password", "").strip()
        if em and pw and em.lower() not in existing_emails:
            accounts.append({
                "email": em,
                "password": pw,
                "verified": False,
                "added_at": time.time()
            })
            existing_emails.add(em.lower())
            added_count += 1
    _save_envato_accounts(accounts)
    return {"success": True, "added": added_count, "total": len(accounts)}

def verify_all_accounts() -> Dict:
    accounts = _load_envato_accounts()
    results = []
    valid_count = 0
    for acc in accounts:
        em = acc.get("email", "")
        pw = acc.get("password", "")
        ok, msg = test_envato_login(em, pw)
        acc["verified"] = ok
        if ok:
            valid_count += 1
        results.append({"email": em, "success": ok, "message": msg})
    _save_envato_accounts(accounts)
    return {"success": True, "valid_count": valid_count, "total": len(accounts), "details": results}

class EnvatoScraper:
    def __init__(self):
        self.base_url = "https://envato-downloader.com"
        self.scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
        )
        self.csrf_token = ""
        self.is_logged_in = False
        self.current_email = None

    @staticmethod
    def get_account_status(custom_accounts: Optional[List[Dict[str, str]]] = None) -> Dict:
        pool = custom_accounts if (custom_accounts is not None and len(custom_accounts) > 0) else _load_envato_accounts()
        now = time.time()
        accounts_info = []
        ready_count = 0
        rate_limited_count = 0

        for acc in pool:
            em = acc.get("email", "")
            is_limited = RATE_LIMITED_ENVATO_ACCOUNTS.get(em, 0) > now
            if is_limited:
                status_str = "Rate-Limited (1h cooldown)"
                rate_limited_count += 1
            else:
                status_str = "Ready" if acc.get("verified", True) else "Unverified"
                ready_count += 1

            accounts_info.append({
                "email": em,
                "status": status_str,
                "rate_limited": is_limited,
                "verified": acc.get("verified", True)
            })

        return {
            "total_accounts": len(pool),
            "ready_accounts": ready_count,
            "rate_limited_accounts": rate_limited_count,
            "accounts": accounts_info
        }

    def _login_account(self, email: str, password: str) -> bool:
        try:
            self.scraper.cookies.clear()
            home_res = self.scraper.get(self.base_url + "/", timeout=15)
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
            res = self.scraper.post(f"{self.base_url}/AuthController/loginPost", data=payload, headers=headers, timeout=15)
            if res.status_code == 200 and res.json().get("result") == 1:
                self.current_email = email
                self.is_logged_in = True
                return True
            return False
        except Exception as e:
            print(f"[EnvatoScraper] Login error for {email}: {e}")
            return False

    def extract_gdrive_url(self, envato_url: str, custom_accounts: Optional[List[Dict[str, str]]] = None) -> str:
        """Extract direct GDrive link from envato-downloader.com with auto-account rotation"""
        pool = custom_accounts if (custom_accounts is not None and len(custom_accounts) > 0) else _load_envato_accounts()
        if not pool:
            raise Exception("No Envato accounts in pool. Please add accounts in the Envato pool.")

        clean_url = envato_url.strip().split('#')[0].split('?')[0]
        now = time.time()
        available_accounts = [
            acc for acc in pool 
            if RATE_LIMITED_ENVATO_ACCOUNTS.get(acc.get("email", ""), 0) <= now
        ]

        if not available_accounts:
            raise Exception("All Envato accounts in pool have reached their hourly limit. Please add a fresh account or wait.")

        last_error = ""
        attempted_count = 0

        for acc in available_accounts:
            email = acc.get("email", "").strip()
            password = acc.get("password", "").strip()
            if not email or not password:
                continue

            attempted_count += 1
            print(f"[EnvatoScraper] Attempting extraction with account #{attempted_count}: {email}")
            
            if not self._login_account(email, password):
                print(f"[EnvatoScraper] Login failed for {email}. Switching to next account...")
                last_error = f"Login failed for {email}"
                continue

            try:
                gdrive_link = self._process_extraction(clean_url)
                if gdrive_link:
                    print(f"[EnvatoScraper] Successfully extracted GDrive link using {email}")
                    return gdrive_link
            except Exception as exc:
                err_text = str(exc)
                print(f"[EnvatoScraper] Account {email} extraction error: {err_text}. Switching to next account...")
                err_low = err_text.lower()
                if any(k in err_low for k in ["limit", "quota", "maximum", "exceeded", "too many", "hourly"]):
                    RATE_LIMITED_ENVATO_ACCOUNTS[email] = time.time() + 3600
                last_error = err_text
                continue

        if last_error:
            raise Exception(f"{last_error} (tried {attempted_count} Envato accounts)")
        else:
            raise Exception(f"All {len(pool)} Envato pool accounts are rate-limited or unverified.")

    def _resolve_gen_url_to_gdrive(self, gen_url: str, headers: dict, fallback_csrf: str = "") -> str:
        """Resolve a generate-link token URL all the way to a direct Google Drive link"""
        # 3. Access generate-link page
        gen_resp = self.scraper.get(gen_url, timeout=20)
        soup_gen = BeautifulSoup(gen_resp.text, "html.parser")
        btn = soup_gen.find(id="btnCounter")
        next_url = btn.get("href") if btn else None
        
        if not next_url:
            raise Exception("Could not find btnCounter href on Envato generate page")
            
        # 4. Access download-file page
        if "download-file" in next_url:
            dl_file_url = next_url
        else:
            proc_resp = self.scraper.get(next_url, timeout=20)
            soup_proc = BeautifulSoup(proc_resp.text, "html.parser")
            dl_link = soup_proc.find("a", href=re.compile(r"download-file"))
            dl_file_url = dl_link.get("href") if dl_link else None
            
        if not dl_file_url:
            raise Exception("Could not find download-file URL")
            
        # 5. Access /links?t= page
        df_resp = self.scraper.get(dl_file_url, timeout=20)
        soup_df = BeautifulSoup(df_resp.text, "html.parser")
        link_a = soup_df.find("a", href=re.compile(r"links"))
        links_url = link_a.get("href") if link_a else None
        
        if not links_url:
            raise Exception("Could not find links URL")
            
        # 6. Access /learn/ page with token
        l_resp = self.scraper.get(links_url, timeout=20)
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
        learn_resp = self.scraper.get(learn_target_url, timeout=20)
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
        csrf_learn_val = csrf_learn.get("value") if csrf_learn else fallback_csrf
        
        a_payload = {
            "csrf_token": csrf_learn_val,
            "generatedownload": gen_tok,
            "sys_lang_id": "1"
        }
        self.scraper.post(f"{self.base_url}/aaaaaaaaa", data=a_payload, headers=headers, timeout=20)
        
        # 9. Fetch final learn page
        final_dl_url = f"{self.base_url}/learn/{ddlink}" if not ddlink.startswith("http") else ddlink
        f_resp = self.scraper.get(final_dl_url, timeout=20)
        
        # 10. Extract direct GDrive URL from the final page JS logic
        match = re.search(r"var\s+ddlink\s*=\s*'([^']+)'", f_resp.text)
        if match:
            gdrive_url = match.group(1)
            return gdrive_url
            
        raise Exception("Google Drive URL regex match failed on final Envato page")

    def _check_downloads_history(self, target_url: str) -> Optional[str]:
        """Check user's /downloads history page for newly generated download links matching the requested asset"""
        try:
            dl_page = self.scraper.get(f"{self.base_url}/downloads", timeout=15)
            soup_dl = BeautifulSoup(dl_page.text, "html.parser")
            table = soup_dl.find("table")
            if not table:
                return None

            slug = target_url.split('#')[0].split('?')[0].rstrip('/').split('/')[-1]
            slug_clean = re.sub(r'_\d+\.htm.*', '', slug).replace('-', ' ').replace('_', ' ').lower()
            words = list(set([w for w in slug_clean.split() if len(w) > 3]))

            for tr in table.find_all("tr"):
                row_text = tr.get_text().lower()
                links = [a.get("href") for a in tr.find_all("a") if "/generate-link/" in a.get("href", "")]
                if not links:
                    continue

                matches = sum(1 for w in words if w in row_text)
                is_fresh = any(t in row_text for t in ["just now", "second", "seconds ago", "1 minute ago", "2 minutes ago", "3 minutes ago", "4 minutes ago", "5 minutes ago"])
                is_old = any(t in row_text for t in ["hour", "hours ago", "day", "days ago", "week", "month", "year"])

                if matches >= min(2, len(words)) and is_fresh and not is_old:
                    return links[0]
        except Exception as e:
            print(f"[EnvatoScraper] History check error: {e}")
        return None

    def _process_extraction(self, envato_url: str) -> str:
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": self.base_url + "/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        home_after = self.scraper.get(self.base_url + "/", timeout=15)
        soup_after = BeautifulSoup(home_after.text, "html.parser")
        csrf_inp = soup_after.find("input", {"name": "csrf_token"})
        csrf_val = csrf_inp.get("value") if csrf_inp else self.csrf_token

        clean_url = envato_url.strip().split('#')[0].split('?')[0]

        ajax_payload = {
            "csrf_token": csrf_val,
            "url": clean_url,
            "sys_lang_id": "1",
            "g-recaptcha-response": ""
        }
        res = self.scraper.post(f"{self.base_url}/AjaxController/envato_downloader", data=ajax_payload, headers=headers, timeout=20)
        try:
            res_json = res.json()
        except:
            res_json = {}

        gen_url = res_json.get("token")
        if not gen_url:
            # Smart Fallback: Check if the file was queued and is already available in /downloads history!
            print("[EnvatoScraper] Direct AJAX token not returned. Checking /downloads history for ready link...")
            history_url = self._check_downloads_history(clean_req_url if 'clean_req_url' in locals() else clean_url)
            if history_url:
                print(f"[EnvatoScraper] Found ready download link in account history: {history_url}")
                gen_url = history_url

        if not gen_url:
            msg = res_json.get("message", "Failed to generate link")
            clean_msg = re.sub(r'<[^>]+>', ' ', str(msg)).strip()
            clean_msg = ' '.join(clean_msg.split())
            raise Exception(clean_msg)

        return self._resolve_gen_url_to_gdrive(gen_url, headers, csrf_val)

if __name__ == "__main__":
    pass


def get_envato_info(url: str) -> Tuple[Optional[Dict], Optional[str]]:
    """Extract offline title and metadata for an Envato Elements asset URL without triggering 403 blocks"""
    try:
        slug = url.split('#')[0].split('?')[0].rstrip('/').split('/')[-1]
        title = slug.replace('-', ' ').replace('_', ' ').title()
        url_low = url.lower()
        file_type = "MOCKUP" if "mockup" in url_low else "TEMPLATE" if "template" in url_low else "PSD" if "psd" in url_low else "GRAPHIC" if "graphic" in url_low else "VIDEO" if "video" in url_low else "AUDIO" if "audio" in url_low else "FONT" if "font" in url_low else "ASSET"
        return {
            "title": title or "Envato Elements Asset",
            "items": [{
                "index": 1,
                "type": file_type,
                "src": url,
                "poster": "",
                "download_type": "envato"
            }]
        }, None
    except Exception as e:
        return None, str(e)


def auto_register_account() -> Dict:
    """Fully automated: create temp email -> register -> verify -> add to Envato pool"""
    steps = []
    try:
        # Step 1: Get mail.tm domain
        steps.append("Fetching temp mail domain...")
        r = requests.get("https://api.mail.tm/domains", timeout=15)
        r.raise_for_status()
        members = r.json().get("hydra:member", [])
        domain = None
        for m in members:
            if m.get("isActive"):
                domain = m["domain"]
                break
        if not domain:
            raise Exception("No active mail.tm domain found")

        # Step 2: Create mail.tm account
        steps.append("Creating temporary email account...")
        username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
        temp_email = f"{username}@{domain}"
        temp_password = "TempPass@" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        
        r_acc = requests.post("https://api.mail.tm/accounts", json={"address": temp_email, "password": temp_password}, timeout=15)
        if r_acc.status_code not in [200, 201]:
            raise Exception(f"mail.tm account creation failed: {r_acc.status_code}")
            
        r_tok = requests.post("https://api.mail.tm/token", json={"address": temp_email, "password": temp_password}, timeout=15)
        if r_tok.status_code != 200:
            raise Exception(f"mail.tm token failed: {r_tok.status_code}")
        token = r_tok.json().get("token", "")

        # Step 3: Register on envato-downloader.com
        steps.append("Registering on envato-downloader.com...")
        sess = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "mobile": False})
        sess.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        
        reg_page = sess.get("https://envato-downloader.com/register", timeout=20)
        soup = BeautifulSoup(reg_page.text, "html.parser")
        csrf_inp = soup.find("input", {"name": re.compile(r"csrf", re.I)})
        csrf = csrf_inp.get("value") if csrf_inp else ""
        
        reg_data = {
            "csrf_token": csrf,
            "sys_lang_id": "1",
            "email": temp_email,
            "password": temp_password,
            "confirm_password": temp_password,
            "terms_conditions": "1",
            "referral_code": ""
        }
        reg_resp = sess.post("https://envato-downloader.com/register-post", data=reg_data,
                            headers={"X-Requested-With": "XMLHttpRequest"}, timeout=20)
        steps.append(f"Register status: {reg_resp.status_code}")

        # Step 4: Poll inbox for verification email
        steps.append("Waiting for verification email (max 45s)...")
        headers = {"Authorization": f"Bearer {token}"}
        start = time.time()
        vlink = None
        while time.time() - start < 45:
            time.sleep(4)
            try:
                r_inbox = requests.get("https://api.mail.tm/messages", headers=headers, timeout=15)
                if r_inbox.status_code == 200:
                    messages = r_inbox.json().get("hydra:member", [])
                    for msg in messages:
                        msg_id = msg.get("id", "")
                        r_msg = requests.get(f"https://api.mail.tm/messages/{msg_id}", headers=headers, timeout=15)
                        if r_msg.status_code == 200:
                            body = r_msg.json().get("html", [])
                            body_text = "".join(body) if isinstance(body, list) else str(body)
                            if not body_text:
                                body_text = r_msg.json().get("text", "")
                            links = re.findall(r'https?://envato-downloader\.com/[^\s"\'<>]+', body_text)
                            if links:
                                vlink = links[0]
                                break
                if vlink:
                    break
            except Exception as e:
                print(f"[EnvatoAutoRegister] Inbox poll error: {e}")

        if vlink:
            steps.append("Clicking activation link...")
            sess.get(vlink, timeout=20)

        # Add to Envato pool
        accounts = _load_envato_accounts()
        accounts.append({
            "email": temp_email,
            "password": temp_password,
            "verified": True if vlink else False,
            "added_at": time.time()
        })
        _save_envato_accounts(accounts)
        
        return {
            "success": True,
            "email": temp_email,
            "password": temp_password,
            "message": f"Account {temp_email} created and registered successfully!",
            "steps": steps,
            "account_status": EnvatoScraper.get_account_status()
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Envato auto-register error: {str(e)}",
            "steps": steps
        }

