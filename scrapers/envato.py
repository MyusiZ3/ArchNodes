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
                RATE_LIMITED_ENVATO_ACCOUNTS[email] = time.time() + 3600
                last_error = err_text
                continue

        if last_error:
            raise Exception(f"{last_error} (tried {attempted_count} Envato accounts)")
        else:
            raise Exception(f"All {len(pool)} Envato pool accounts are rate-limited or unverified.")

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
        res_json = res.json()

        if res_json.get("code") != 1:
            msg = res_json.get("message", "Failed to generate link")
            clean_msg = re.sub(r'<[^>]+>', ' ', str(msg)).strip()
            clean_msg = ' '.join(clean_msg.split())
            raise Exception(clean_msg)

        gen_url = res_json.get("token")
        
        # 3. Access generate-link page
        gen_resp = self.scraper.get(gen_url, timeout=20)
        soup_gen = BeautifulSoup(gen_resp.text, "html.parser")
        btn = soup_gen.find(id="btnCounter")
        next_url = btn.get("href") if btn else None
        
        if not next_url:
            raise Exception("Could not find btnCounter href")
            
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
            
        # 8. Post to /aaaaaaaaa
        csrf_learn = learn_soup.find("input", {"name": "csrf_token"})
        csrf_learn_val = csrf_learn.get("value") if csrf_learn else csrf_val
        
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
            return match.group(1)
            
        raise Exception("Google Drive URL regex match failed on final page")

def get_envato_info(url: str) -> Tuple[Optional[Dict], Optional[str]]:
    """Fetch info from elements.envato.com with robust offline fallback to avoid Cloudflare 403"""
    title = "Envato Elements Asset"
    try:
        parts = [p for p in url.split('?')[0].split('#')[0].split('/') if p]
        if parts:
            slug = parts[-1]
            slug = re.sub(r'-[A-Z0-9]{5,}$', '', slug)
            cleaned_title = slug.replace('-', ' ').title()
            if cleaned_title:
                title = cleaned_title
    except Exception:
        pass

    try:
        scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        r = scraper.get(url, headers=headers, timeout=8)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            title_el = soup.find("h1") or soup.find("title")
            if title_el:
                t = title_el.get_text(strip=True)
                title = re.sub(r'\s*\|\s*Envato Elements.*', '', t)
            
            items = []
            video_tag = soup.find("video")
            if video_tag:
                src = video_tag.get("src") or (video_tag.find("source").get("src") if video_tag.find("source") else "")
                poster = video_tag.get("poster", "")
                if src:
                    items.append({"index": 1, "type": "video", "src": src, "poster": poster})
                    
            audio_tag = soup.find("audio")
            if audio_tag and not items:
                src = audio_tag.get("src") or (audio_tag.find("source").get("src") if audio_tag.find("source") else "")
                if src:
                    items.append({"index": 1, "type": "audio", "src": src, "poster": ""})

            if not items:
                meta_img = soup.find("meta", property="og:image")
                img_src = meta_img.get("content") if meta_img else ""
                items.append({"index": 1, "type": "package", "src": url, "poster": img_src})

            return {"title": title, "items": items}, None
    except Exception:
        pass

    return {
        "title": title,
        "items": [{
            "index": 1,
            "type": "package",
            "src": url,
            "poster": ""
        }]
    }, None


def _get_mailtm_domain() -> Optional[str]:
    try:
        r = requests.get("https://api.mail.tm/domains", timeout=8)
        if r.status_code == 200:
            domains = r.json().get("hydra:member", [])
            if domains:
                return domains[0].get("domain")
    except Exception:
        pass
    return None

def _create_mailtm_account(email: str, password: str) -> bool:
    try:
        r = requests.post(
            "https://api.mail.tm/accounts",
            json={"address": email, "password": password},
            timeout=8
        )
        return r.status_code in [200, 201]
    except Exception:
        return False

def auto_register_account() -> Dict:
    import random
    import string
    domain = _get_mailtm_domain()
    if not domain:
        return {"success": False, "error": "Could not connect to tempmail domain service"}
        
    username = "env_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    email = f"{username}@{domain}"
    password = "Env_" + "".join(random.choices(string.ascii_letters + string.digits, k=8)) + "!"
    
    if not _create_mailtm_account(email, password):
        return {"success": False, "error": "Failed to provision temporary email"}
        
    return {
        "success": True,
        "email": email,
        "password": password,
        "register_url": "https://envato-downloader.com/register",
        "message": "Temporary email generated! Complete registration on envato-downloader.com then click Verify & Add."
    }
