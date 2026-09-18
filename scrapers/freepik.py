from core.proxy_manager import apply_network_settings
"""
Freepik Premium Scraper via FreepikDownloader.com
Fully programmatic (CloudScraper + BeautifulSoup)
Multi-account pool support with auto-rotation, referral credit engine, profile completion, and GDrive link extraction.
Accounts stored in accounts.json for persistence. Auto-register & auto-farm via mail.tm temp mail & Gmail IMAP dot-trick.
"""

import os
import re
import json
import time
import random
import string
import imaplib
import email as email_lib
from datetime import datetime
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
RATE_LIMITED_ACCOUNTS: Dict[str, float] = {}

def _get_today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def _load_accounts() -> List[Dict]:
    """Load accounts from accounts.json with daily reset and field normalization"""
    if not os.path.exists(ACCOUNTS_FILE):
        return []
    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            accounts = data.get("accounts", []) if isinstance(data, dict) else data

        today = _get_today_str()
        updated = False
        for acc in accounts:
            if "daily_used" not in acc:
                acc["daily_used"] = 0
                acc["last_used_date"] = today
                updated = True
            elif acc.get("last_used_date") != today:
                acc["daily_used"] = 0
                acc["last_used_date"] = today
                updated = True
            if "referral_code" not in acc:
                acc["referral_code"] = ""
                updated = True
            if "referral_url" not in acc:
                acc["referral_url"] = f"https://freepikdownloader.com/register?ref={acc['referral_code']}" if acc.get("referral_code") else ""
                updated = True
            if "verified" not in acc:
                acc["verified"] = True
                updated = True
            if "profile_completed" not in acc:
                acc["profile_completed"] = False
                updated = True
            if "added_at" not in acc:
                acc["added_at"] = time.time()
                updated = True

        if updated:
            _save_accounts(accounts)
        return accounts
    except Exception as e:
        print(f"[FreepikScraper] Error loading accounts.json: {e}")
        return []

def _save_accounts(accounts: List[Dict]):
    """Save accounts to accounts.json"""
    try:
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump({"accounts": accounts}, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[FreepikScraper] Error saving accounts.json: {e}")

def test_freepik_login(email: str, password: str) -> Tuple[bool, str, int]:
    """Test logging into freepikdownloader.com and scrape live credit balance"""
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    apply_network_settings(scraper)
    try:
        home_res = scraper.get("https://freepikdownloader.com/", timeout=15)
        soup_home = BeautifulSoup(home_res.text, "html.parser")
        form_login = soup_home.find("form", id="form-login") or soup_home.find("form")
        if not form_login:
            return False, "Login form not found", 0
        csrf_token = form_login.find("input", {"name": "csrf_token"}).get("value", "")
        payload = {
            "csrf_token": csrf_token,
            "email": email,
            "password": password,
            "sys_lang_id": "1"
        }
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://freepikdownloader.com/"
        }
        res = scraper.post("https://freepikdownloader.com/AuthController/loginPost", data=payload, headers=headers, timeout=15)
        if res.status_code == 200:
            res_json = res.json()
            if res_json.get("result") == 1:
                credits = 0
                try:
                    r_home = scraper.get("https://freepikdownloader.com/", timeout=15)
                    soup_after = BeautifulSoup(r_home.text, "html.parser")
                    for a in soup_after.find_all(["a", "button", "span", "div"]):
                        txt = a.get_text(strip=True)
                        m = re.search(r'(\d+)\s*credits?', txt, re.I)
                        if m and "earn" not in txt.lower():
                            credits = int(m.group(1))
                            break
                except Exception:
                    pass
                return True, "Login successful", credits
            else:
                return False, res_json.get("message", "Invalid credentials or account unverified"), 0
        return False, f"HTTP Error {res.status_code}", 0
    except Exception as e:
        return False, str(e), 0

def add_account(email: str, password: str, verify: bool = True) -> Dict:
    """Add account to pool after optional login check & auto-fetch referral code and credits"""
    accounts = _load_accounts()
    for acc in accounts:
        if acc.get("email", "").lower() == email.lower():
            if password and acc.get("password") != password:
                acc["password"] = password
            if verify:
                ok, msg, creds = test_freepik_login(email, password)
                acc["verified"] = ok
                acc["credits"] = creds
            _save_accounts(accounts)
            return {"success": True, "message": f"Account {email} is already in the pool", "already_in_pool": True, "account": acc}

    is_valid = True
    credits = 0
    if verify:
        is_valid, msg, credits = test_freepik_login(email, password)
        if not is_valid:
            return {"success": False, "error": f"Login failed: {msg}"}

    today = _get_today_str()
    new_acc = {
        "email": email,
        "password": password,
        "verified": is_valid,
        "credits": credits,
        "referral_code": "",
        "referral_url": "",
        "daily_used": 0,
        "remaining_daily": 2,
        "last_used_date": today,
        "profile_completed": False,
        "added_at": time.time()
    }

    if is_valid:
        try:
            ref_info = fetch_freepik_referral_code(email, password, save_to_pool=False)
            if ref_info.get("success"):
                new_acc["referral_code"] = ref_info.get("referral_code", "")
                new_acc["referral_url"] = ref_info.get("referral_url", "")
        except Exception:
            pass

    accounts.append(new_acc)
    _save_accounts(accounts)
    return {"success": True, "message": "Account added to pool", "account": new_acc}

def remove_account(email: str) -> Dict:
    accounts = _load_accounts()
    filtered = [acc for acc in accounts if acc.get("email", "").lower() != email.lower()]
    if len(filtered) == len(accounts):
        return {"success": False, "error": f"Account {email} not found"}
    _save_accounts(filtered)
    RATE_LIMITED_ACCOUNTS.pop(email, None)
    return {"success": True, "message": f"Account {email} removed from pool"}

def batch_add_accounts(acc_list: List[Dict[str, str]]) -> Dict:
    accounts = _load_accounts()
    existing_emails = {acc.get("email", "").lower() for acc in accounts}
    added_count = 0
    today = _get_today_str()
    for item in acc_list:
        em = item.get("email", "").strip()
        pw = item.get("password", "").strip()
        if em and pw and em.lower() not in existing_emails:
            accounts.append({
                "email": em,
                "password": pw,
                "verified": False,
                "credits": 0,
                "referral_code": "",
                "referral_url": "",
                "daily_used": 0,
                "remaining_daily": 2,
                "last_used_date": today,
                "profile_completed": False,
                "added_at": time.time()
            })
            existing_emails.add(em.lower())
            added_count += 1
    _save_accounts(accounts)
    return {"success": True, "added": added_count, "total": len(accounts)}

def verify_all_accounts(custom_accounts: Optional[List[Dict]] = None) -> Dict:
    accounts = custom_accounts if (custom_accounts is not None and len(custom_accounts) > 0) else _load_accounts()
    results = []
    valid_count = 0
    total_credits = 0
    for acc in accounts:
        em = acc.get("email", "")
        pw = acc.get("password", "")
        ok, msg, creds = test_freepik_login(em, pw)
        acc["verified"] = ok
        acc["credits"] = creds
        if ok:
            valid_count += 1
            total_credits += creds
            if creds == 0:
                acc["status"] = "No Credits (0 Bal)"
            else:
                acc["status"] = "Ready"
        else:
            acc["status"] = "Invalid credentials"
        results.append({"email": em, "success": ok, "message": msg, "credits": creds})
    if len(accounts) > 0:
        _save_accounts(accounts)
    return {"success": True, "valid_count": valid_count, "total_credits": total_credits, "total": len(accounts), "details": results}

def fetch_freepik_referral_code(email: str, password: str, save_to_pool: bool = True) -> Dict:
    """Log in to freepikdownloader.com, scrape /get-credits, and extract referral code & link"""
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    apply_network_settings(scraper)
    try:
        home_res = scraper.get("https://freepikdownloader.com/", timeout=15)
        soup_home = BeautifulSoup(home_res.text, "html.parser")
        form_login = soup_home.find("form", id="form-login") or soup_home.find("form")
        if not form_login:
            return {"success": False, "error": "Could not find login form"}
            
        csrf_token = form_login.find("input", {"name": "csrf_token"}).get("value", "")
        payload = {
            "csrf_token": csrf_token,
            "email": email,
            "password": password,
            "sys_lang_id": "1"
        }
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://freepikdownloader.com/"
        }
        res = scraper.post("https://freepikdownloader.com/AuthController/loginPost", data=payload, headers=headers, timeout=15)
        if res.status_code != 200 or res.json().get("result") != 1:
            return {"success": False, "error": "Login failed for account"}

        r_credits = scraper.get("https://freepikdownloader.com/get-credits", timeout=15)
        soup_cred = BeautifulSoup(r_credits.text, "html.parser")
        
        ref_code = ""
        ref_url = ""
        
        ref_span = soup_cred.find("span", class_="code")
        if ref_span:
            ref_code = ref_span.get_text(strip=True)
            
        referblock = soup_cred.find("div", class_=re.compile(r"referblock"))
        if referblock and referblock.get("onclick"):
            onclick_txt = referblock.get("onclick", "")
            m = re.search(r'https?://freepikdownloader\.com/register\?ref=([A-Za-z0-9_-]+)', onclick_txt)
            if m:
                ref_url = m.group(0)
                if not ref_code:
                    ref_code = m.group(1)
                    
        if not ref_code:
            m_full = re.search(r'Referral\s*Code\s*:\s*([A-Za-z0-9_-]+)', r_credits.text, re.I)
            if m_full:
                ref_code = m_full.group(1).replace("(Click", "").replace("(", "").strip()
            else:
                m_full2 = re.search(r'Referral\s*Code\s*Here\s*:\s*([A-Za-z0-9_-]+)', r_credits.text, re.I)
                if m_full2:
                    ref_code = m_full2.group(1).strip()
                else:
                    m_reg = re.search(r'register\?ref=([A-Za-z0-9_-]+)', r_credits.text)
                    if m_reg:
                        ref_code = m_reg.group(1)

        if ref_code and not ref_url:
            ref_url = f"https://freepikdownloader.com/register?ref={ref_code}"

        if not ref_code:
            return {"success": False, "error": "Referral code not found on /get-credits page"}

        if save_to_pool:
            accounts = _load_accounts()
            for acc in accounts:
                if acc.get("email", "").lower() == email.lower():
                    acc["referral_code"] = ref_code
                    acc["referral_url"] = ref_url
                    break
            _save_accounts(accounts)

        return {
            "success": True,
            "email": email,
            "referral_code": ref_code,
            "referral_url": ref_url
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def sync_all_freepik_referrals() -> Dict:
    """Sync/fetch referral codes for all verified accounts in pool"""
    accounts = _load_accounts()
    synced_count = 0
    results = []
    
    for acc in accounts:
        em = acc.get("email", "")
        pw = acc.get("password", "")
        if not em or not pw:
            continue
            
        res = fetch_freepik_referral_code(em, pw, save_to_pool=True)
        if res.get("success"):
            synced_count += 1
            results.append({"email": em, "success": True, "referral_code": res.get("referral_code")})
        else:
            results.append({"email": em, "success": False, "error": res.get("error")})
            
    return {"success": True, "synced_count": synced_count, "total": len(accounts), "details": results}

def track_freepik_referral_use(email: str) -> Dict:
    """Increment referral use counter for an account"""
    accounts = _load_accounts()
    today = _get_today_str()
    for acc in accounts:
        if acc.get("email", "").lower() == email.lower():
            if acc.get("last_used_date") != today:
                acc["daily_used"] = 0
                acc["last_used_date"] = today
                
            current_used = acc.get("daily_used", 0)
            if current_used >= 2:
                return {
                    "success": False,
                    "error": "Maximum daily referral limit reached for this account (2/2 used today).",
                    "daily_used": 2,
                    "remaining": 0,
                    "cooldown": True
                }
                
            acc["daily_used"] = current_used + 1
            _save_accounts(accounts)
            remaining = 2 - acc["daily_used"]
            return {
                "success": True,
                "email": email,
                "referral_code": acc.get("referral_code", ""),
                "referral_url": acc.get("referral_url", ""),
                "daily_used": acc["daily_used"],
                "remaining": remaining,
                "cooldown": remaining <= 0
            }
            
    return {"success": False, "error": "Account not found"}

def complete_freepik_profile(email: str, password: str, custom_profile: Optional[Dict] = None) -> Dict:
    """Auto-submit profile completion form on freepikdownloader.com"""
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    apply_network_settings(scraper)
    try:
        home_res = scraper.get("https://freepikdownloader.com/", timeout=15)
        soup_home = BeautifulSoup(home_res.text, "html.parser")
        form_login = soup_home.find("form", id="form-login") or soup_home.find("form")
        if not form_login:
            return {"success": False, "error": "Login form not found"}
        csrf_token = form_login.find("input", {"name": "csrf_token"}).get("value", "")
        
        l_res = scraper.post("https://freepikdownloader.com/AuthController/loginPost", data={
            "csrf_token": csrf_token,
            "email": email,
            "password": password,
            "sys_lang_id": "1"
        }, headers={"X-Requested-With": "XMLHttpRequest", "Referer": "https://freepikdownloader.com/"}, timeout=15)
        
        if l_res.status_code != 200 or l_res.json().get("result") != 1:
            return {"success": False, "error": "Login failed for profile update"}

        r_prof = scraper.get("https://freepikdownloader.com/profile", timeout=15)
        soup_prof = BeautifulSoup(r_prof.text, "html.parser")
        csrf_prof_inp = soup_prof.find("input", {"name": "csrf_token"})
        csrf_prof = csrf_prof_inp.get("value", "") if csrf_prof_inp else csrf_token

        first_names = ["Alex", "Jordan", "Taylor", "Morgan", "Reza", "Dimas", "Aditya", "Fajar", "Kevin", "Budi"]
        last_names = ["Pratama", "Wijaya", "Kusuma", "Santoso", "Saputra", "Nugroho", "Setiawan", "Hidayat", "Siregar"]
        cities = ["Jakarta", "Surabaya", "Bandung", "Medan", "Semarang", "Yogyakarta"]
        
        fname = (custom_profile or {}).get("first_name") or random.choice(first_names)
        lname = (custom_profile or {}).get("last_name") or random.choice(last_names)
        city = random.choice(cities)
        
        prof_payload = {
            "csrf_token": csrf_prof,
            "back_url": "https://freepikdownloader.com/profile",
            "first_name": fname,
            "last_name": lname,
            "phone_number": f"812{random.randint(1000000, 9999999)}",
            "address": f"Studio Visual Kreatif Jl. {city} No. {random.randint(10, 199)}",
            "country_id": "1",
            "state_id": "1",
            "city_id": "1",
            "zipcode": str(random.randint(10000, 99999))
        }

        res_p = scraper.post("https://freepikdownloader.com/complete-profile-post", data=prof_payload, headers={"Referer": "https://freepikdownloader.com/profile"}, timeout=20)
        if res_p.status_code in [200, 302]:
            accounts = _load_accounts()
            for acc in accounts:
                if acc.get("email", "").lower() == email.lower():
                    acc["profile_completed"] = True
                    break
            _save_accounts(accounts)
            return {"success": True, "message": f"Profile completed successfully for {email}", "profile": prof_payload}
        else:
            return {"success": False, "error": f"Profile update returned status {res_p.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _poll_imap_for_freepik_verification(gmail_user: str, gmail_app_pass: str, max_wait_sec: int = 50) -> Optional[str]:
    """Poll Gmail inbox via IMAP to auto-retrieve Freepik activation link"""
    start = time.time()
    while time.time() - start < max_wait_sec:
        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
            mail.login(gmail_user, gmail_app_pass)
            mail.select("inbox")
            status, messages = mail.search(None, '(UNSEEN FROM "freepikdownloader.com")')
            if status != "OK" or not messages[0]:
                status, messages = mail.search(None, '(FROM "freepikdownloader.com")')
                
            if status == "OK" and messages[0]:
                msg_ids = messages[0].split()
                latest_id = msg_ids[-1]
                res_f, data = mail.fetch(latest_id, "(RFC822)")
                if res_f == "OK":
                    raw_email = data[0][1]
                    msg = email_lib.message_from_bytes(raw_email)
                    body_content = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() in ["text/html", "text/plain"]:
                                body_content += part.get_payload(decode=True).decode(errors="ignore")
                    else:
                        body_content = msg.get_payload(decode=True).decode(errors="ignore")
                        
                    links = re.findall(r'https?://freepikdownloader\.com/[^\s"\'<>]+', body_content)
                    for lk in links:
                        if "activate" in lk or "verify" in lk or "confirm" in lk or "token" in lk:
                            mail.logout()
                            return lk
                    if links:
                        mail.logout()
                        return links[0]
            mail.logout()
        except Exception:
            pass
        time.sleep(4)
    return None

def auto_farm_freepik_referral(
    master_ref_code: str,
    master_email: str = "",
    mode: str = "tempmail",
    gmail_user: str = "",
    gmail_app_password: str = "",
    custom_email: str = "",
    custom_password: str = ""
) -> Dict:
    """Full Automation Engine: Register with referral code -> Confirm Email -> Complete Profile -> Add to Pool"""
    steps = []
    try:
        steps.append("Initializing Freepik referral automation session...")
        sess = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "mobile": False})
        apply_network_settings(sess)
        sess.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        
        target_email = ""
        target_password = custom_password or ("FreepikAuto@" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8)))
        mail_tm_token = None
        
        if mode == "imap" and gmail_user:
            user_part, domain_part = gmail_user.split("@", 1)
            rand_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
            target_email = f"{user_part}+{rand_suffix}@{domain_part}"
            steps.append(f"Generated Gmail Alias: {target_email}")
        elif mode == "tempmail":
            steps.append("Fetching mail.tm temporary domain...")
            r_dom = requests.get("https://api.mail.tm/domains", timeout=15)
            members = r_dom.json().get("hydra:member", [])
            domain = next((m["domain"] for m in members if m.get("isActive")), None)
            if not domain:
                raise Exception("No active temp-mail domain available")
            uname = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            target_email = f"{uname}@{domain}"
            requests.post("https://api.mail.tm/accounts", json={"address": target_email, "password": target_password}, timeout=15)
            r_tok = requests.post("https://api.mail.tm/token", json={"address": target_email, "password": target_password}, timeout=15)
            mail_tm_token = r_tok.json().get("token", "")
            steps.append(f"Created Temp-Mail: {target_email}")
        else:
            target_email = custom_email
            if not target_email:
                raise Exception("No registration email provided")

        steps.append("Fetching register page & CSRF token...")
        reg_page = sess.get("https://freepikdownloader.com/register", timeout=20)
        soup = BeautifulSoup(reg_page.text, "html.parser")
        csrf_inp = soup.find("input", {"name": re.compile(r"csrf", re.I)})
        csrf = csrf_inp.get("value") if csrf_inp else ""

        steps.append(f"Submitting registration with Referral Code [{master_ref_code}]...")
        reg_data = {
            "csrf_token": csrf,
            "sys_lang_id": "1",
            "email": target_email,
            "password": target_password,
            "confirm_password": target_password,
            "referral_code": master_ref_code,
            "terms_conditions": "1"
        }
        reg_resp = sess.post("https://freepikdownloader.com/register-post", data=reg_data, headers={"X-Requested-With": "XMLHttpRequest"}, timeout=20)
        steps.append(f"Registration response status: {reg_resp.status_code}")

        soup_resp = BeautifulSoup(reg_resp.text, "html.parser")
        alert_danger = soup_resp.find(class_=re.compile(r"alert-danger|alert-warning|error", re.I))
        if alert_danger:
            err_text = alert_danger.get_text(strip=True)
            if "robot" in err_text.lower() or "captcha" in err_text.lower():
                raise Exception(f'Registration blocked by Anti-Bot protection: "{err_text}". CAPTCHA challenge is enforced on registration form.')
            raise Exception(f"Registration error from server: {err_text}")

        vlink = None
        if mode == "imap" and gmail_user and gmail_app_password:
            steps.append("Polling Gmail IMAP for activation link (max 50s)...")
            vlink = _poll_imap_for_freepik_verification(gmail_user, gmail_app_password, max_wait_sec=50)
        elif mode == "tempmail" and mail_tm_token:
            steps.append("Polling mail.tm inbox for activation link...")
            h_tm = {"Authorization": f"Bearer {mail_tm_token}"}
            start_tm = time.time()
            while time.time() - start_tm < 40:
                time.sleep(3)
                r_in = requests.get("https://api.mail.tm/messages", headers=h_tm, timeout=15)
                if r_in.status_code == 200:
                    for msg in r_in.json().get("hydra:member", []):
                        r_m = requests.get(f"https://api.mail.tm/messages/{msg['id']}", headers=h_tm, timeout=15)
                        b_text = str(r_m.json().get("html", "")) + str(r_m.json().get("text", ""))
                        lks = re.findall(r'https?://freepikdownloader\.com/[^\s"\'<>]+', b_text)
                        if lks:
                            vlink = lks[0]
                            break
                if vlink:
                    break

        if vlink:
            steps.append(f"Activating account via confirmation link: {vlink}...")
            sess.get(vlink, timeout=20)
            steps.append("Account successfully verified!")
        else:
            steps.append("No confirmation link received or manual activation pending.")

        steps.append("Auto-completing user profile (name, address, phone)... ")
        prof_res = complete_freepik_profile(target_email, target_password)
        if prof_res.get("success"):
            steps.append("Profile completed & activated!")

        add_account(target_email, target_password, verify=False)
        try:
            ref_res = fetch_freepik_referral_code(target_email, target_password, save_to_pool=True)
            if ref_res.get("success"):
                steps.append(f"Generated new account referral code: {ref_res.get('referral_code')}")
        except Exception:
            pass

        if master_email:
            track_freepik_referral_use(master_email)
            steps.append(f"Updated daily referral counter for master account {master_email}")

        return {
            "success": True,
            "email": target_email,
            "password": target_password,
            "referral_code": master_ref_code,
            "message": f"Successfully automated referral for {target_email}! 5 Credits added.",
            "steps": steps,
            "account_status": FreepikScraper.get_account_status()
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "steps": steps
        }

def auto_register_account() -> Dict:
    """Legacy wrapper for 1-click temp account creation"""
    accounts = _load_accounts()
    master_ref = accounts[0].get("referral_code", "") if accounts else ""
    return auto_farm_freepik_referral(master_ref_code=master_ref, mode="tempmail")

# ── Global account pool state (loaded from JSON) ────────────────────────────
FREEPIK_ACCOUNTS: List[Dict] = _load_accounts()

class FreepikScraper:
    def __init__(self):
        self.base_url = "https://freepikdownloader.com"
        self.scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
        )
        apply_network_settings(self.scraper)
        self.csrf_token = ""
        self.current_email = ""

    @staticmethod
    def get_account_status(custom_accounts: Optional[List[Dict[str, str]]] = None) -> Dict:
        pool = custom_accounts if (custom_accounts is not None and len(custom_accounts) > 0) else _load_accounts()
        now = time.time()
        today = _get_today_str()
        accounts_info = []
        ready_count = 0
        rate_limited_count = 0

        total_credits = 0
        accounts_with_credits = 0

        for acc in pool:
            em = acc.get("email", "")
            creds = acc.get("credits", 0)
            total_credits += creds
            is_limited = RATE_LIMITED_ACCOUNTS.get(em, 0) > now
            daily_used = acc.get("daily_used", 0) if acc.get("last_used_date") == today else 0
            remaining = max(0, 2 - daily_used)

            if not acc.get("verified", True):
                status_str = "Unverified"
            elif is_limited:
                status_str = "Rate-Limited (1h cooldown)"
                rate_limited_count += 1
            elif creds == 0:
                status_str = "0 Credits (No balance)"
            else:
                status_str = f"Ready ({creds} Credits)"
                ready_count += 1
                accounts_with_credits += 1

            accounts_info.append({
                "email": em,
                "password": acc.get("password", ""),
                "status": status_str,
                "credits": creds,
                "rate_limited": is_limited or (remaining == 0 and creds == 0),
                "verified": acc.get("verified", True),
                "referral_code": acc.get("referral_code", ""),
                "referral_url": acc.get("referral_url", ""),
                "daily_used": daily_used,
                "remaining_daily": remaining,
                "profile_completed": acc.get("profile_completed", False),
                "added_at": acc.get("added_at", time.time())
            })

        total = len(pool)
        min_reset = 60 if rate_limited_count > 0 else 0

        if total == 0:
            summary = "0/0 Accounts (Pool Empty)"
            badge_text = "Freepik: Pool Empty"
            status_color = "#94A3B8"
        elif accounts_with_credits > 0:
            summary = f"{accounts_with_credits}/{total} Accounts with Credits ({total_credits} Credits Total)"
            badge_text = f"Freepik Pool: {accounts_with_credits}/{total} Ready ({total_credits} Credits)"
            status_color = "#22C55E"
        else:
            summary = f"0/{total} Accounts with Credits (0 Credits Total)"
            badge_text = f"Freepik: 0/{total} with Credits"
            status_color = "#F59E0B"

        return {
            "total_accounts": total,
            "active_accounts": accounts_with_credits,
            "ready_accounts": accounts_with_credits,
            "accounts_with_credits": accounts_with_credits,
            "total_credits": total_credits,
            "limited_accounts": rate_limited_count,
            "rate_limited_accounts": rate_limited_count,
            "reset_minutes": min_reset,
            "summary_text": summary,
            "badge_text": badge_text,
            "status_color": status_color,
            "accounts": accounts_info
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
                err_low = err_text.lower()
                if any(k in err_low for k in ["limit", "quota", "maximum", "exceeded", "too many"]):
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

    def _resolve_gen_url_to_gdrive(self, gen_url: str, headers: dict, fallback_csrf: str = "") -> str:
        """Resolve a generate-link token URL all the way to a direct Google Drive link"""
        # 3. Access generate-link page
        gen_resp = self.scraper.get(gen_url)
        soup_gen = BeautifulSoup(gen_resp.text, "html.parser")
        btn = soup_gen.find(id="btnCounter")
        next_url = btn.get("href") if btn else None
        
        if not next_url:
            raise Exception("Could not find btnCounter href on generate page")
            
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
        csrf_learn_val = csrf_learn.get("value") if csrf_learn else fallback_csrf
        
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
            print(f"[FreepikScraper] History check error: {e}")
        return None

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
        clean_req_url = freepik_url.strip().split("#")[0].split("?")[0] if ".htm" in freepik_url else freepik_url.strip().split("#")[0]
        ajax_payload = {
            "csrf_token": csrf_val,
            "url": clean_req_url,
            "sys_lang_id": "1",
            "g-recaptcha-response": ""
        }
        res = self.scraper.post(f"{self.base_url}/AjaxController/freepik_downloader", data=ajax_payload, headers=headers)
        try:
            res_json = res.json()
        except:
            res_json = {}

        gen_url = res_json.get("token")
        if not gen_url:
            # Smart Fallback: Check if the file was queued and is already available in /downloads history!
            print("[FreepikScraper] Direct AJAX token not returned. Checking /downloads history for ready link...")
            history_url = self._check_downloads_history(clean_req_url)
            if history_url:
                print(f"[FreepikScraper] Found ready download link in account history: {history_url}")
                gen_url = history_url

        if not gen_url:
            msg = res_json.get("message", "Failed to generate link")
            clean_msg = re.sub(r'<[^>]+>', ' ', msg).strip()
            clean_msg = ' '.join(clean_msg.split())
            raise Exception(clean_msg)

        return self._resolve_gen_url_to_gdrive(gen_url, headers, csrf_val)

if __name__ == "__main__":
    pass
