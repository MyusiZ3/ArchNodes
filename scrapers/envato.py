from core.proxy_manager import apply_network_settings
import os
import re
import time
import json
import random
import string
import imaplib
import email
from email.header import decode_header
import cloudscraper
import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Tuple
from datetime import datetime

ENVATO_ACCOUNTS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "envato_accounts.json")
RATE_LIMITED_ENVATO_ACCOUNTS: Dict[str, float] = {}

def _get_today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def _load_envato_accounts() -> List[Dict]:
    if not os.path.exists(ENVATO_ACCOUNTS_FILE):
        return []
    try:
        with open(ENVATO_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            accounts = json.load(f)
            
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
                
        if updated:
            _save_envato_accounts(accounts)
        return accounts
    except Exception:
        return []

def _save_envato_accounts(accounts: List[Dict]) -> None:
    try:
        with open(ENVATO_ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(accounts, f, indent=2)
    except Exception as e:
        print(f"[Envato] Error saving accounts: {e}")

def check_envato_credits(scraper, csrf_token: str) -> Tuple[bool, int, str]:
    """Check if account has remaining credits on envato-downloader.com via probe"""
    try:
        payload = {
            "csrf_token": csrf_token,
            "url": "https://elements.envato.com/corporate-flyer-P9C8Y6N",
            "type": "envato_downloader",
            "tokens": "1",
            "osuyk": "",
            "sysLangId": "1"
        }
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://envato-downloader.com/envato-downloader"
        }
        res = scraper.post("https://envato-downloader.com/AjaxController/envato_downloader", data=payload, headers=headers, timeout=15)
        text = res.text.lower()
        if "doesn't have any credits" in text or "buy credits" in text or "no credits" in text:
            return True, 0, "No credits remaining (0 credits)"
        return True, 2, "Credits available"
    except Exception as e:
        return True, 2, str(e)

def test_envato_login(email: str, password: str, check_credits: bool = True) -> Tuple[bool, str, int]:
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    try:
        home_res = scraper.get("https://envato-downloader.com/", timeout=15)
        soup_home = BeautifulSoup(home_res.text, "html.parser")
        form_login = soup_home.find("form", id="form-login")
        if not form_login:
            return False, "Could not find login form on envato-downloader.com", 0
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
            credits = 2
            msg = "Login successful"
            if check_credits:
                _, credits, cmsg = check_envato_credits(scraper, csrf_token)
                msg = f"Login successful ({cmsg})"
            return True, msg, credits
        msg = res_json.get("error_message") or res_json.get("message") or "Invalid credentials"
        clean_msg = re.sub(r'<[^>]+>', ' ', str(msg)).strip()
        return False, clean_msg or "Login failed", 0
    except Exception as e:
        return False, str(e), 0

def add_account(email: str, password: str, verify: bool = True) -> Dict:
    accounts = _load_envato_accounts()
    for acc in accounts:
        if acc.get("email", "").lower() == email.lower():
            if password and acc.get("password") != password:
                acc["password"] = password
            if verify:
                ok, msg, _ = test_envato_login(email, password, check_credits=False)
                acc["verified"] = ok
            _save_envato_accounts(accounts)
            return {"success": True, "message": f"Account {email} is already in the pool", "already_in_pool": True, "account": acc}
            
    is_valid = True
    msg = "Account added"
    if verify:
        is_valid, msg, _ = test_envato_login(email, password, check_credits=False)
        if not is_valid:
            return {"success": False, "error": f"Verification failed: {msg}"}
            
    today = _get_today_str()
    new_acc = {
        "email": email,
        "password": password,
        "verified": is_valid,
        "referral_code": "",
        "referral_url": "",
        "daily_used": 0,
        "remaining_daily": 2,
        "rate_limited": False,
        "status": "Ready",
        "last_used_date": today,
        "added_at": time.time()
    }
    
    # Auto fetch referral code if login valid
    if is_valid:
        try:
            ref_info = fetch_envato_referral_code(email, password, save_to_pool=False)
            if ref_info.get("success"):
                new_acc["referral_code"] = ref_info.get("referral_code", "")
                new_acc["referral_url"] = ref_info.get("referral_url", "")
        except Exception:
            pass

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
    today = _get_today_str()
    for item in acc_list:
        em = item.get("email", "").strip()
        pw = item.get("password", "").strip()
        if em and pw and em.lower() not in existing_emails:
            accounts.append({
                "email": em,
                "password": pw,
                "verified": False,
                "referral_code": "",
                "referral_url": "",
                "daily_used": 0,
                "remaining_daily": 2,
                "rate_limited": False,
                "status": "Unverified",
                "last_used_date": today,
                "added_at": time.time()
            })
            existing_emails.add(em.lower())
            added_count += 1
    _save_envato_accounts(accounts)
    return {"success": True, "added": added_count, "total": len(accounts)}

def verify_all_accounts(custom_accounts: Optional[List[Dict]] = None) -> Dict:
    accounts = custom_accounts if (custom_accounts is not None and len(custom_accounts) > 0) else _load_envato_accounts()
    results = []
    valid_count = 0
    now = time.time()
    today = _get_today_str()
    for acc in accounts:
        em = acc.get("email", "")
        pw = acc.get("password", "")
        ok, msg, _ = test_envato_login(em, pw, check_credits=False)
        acc["verified"] = ok
        if ok:
            valid_count += 1
            if acc.get("last_used_date") != today:
                acc["daily_used"] = 0
                acc["last_used_date"] = today
            acc["remaining_daily"] = max(0, 2 - acc.get("daily_used", 0))
            if acc["remaining_daily"] > 0:
                acc["rate_limited"] = False
                acc["status"] = "Ready"
                RATE_LIMITED_ENVATO_ACCOUNTS.pop(em, None)
            else:
                acc["rate_limited"] = True
                acc["status"] = "Quota Limit Reached (0/2)"
        else:
            acc["status"] = "Invalid credentials"
        acc["last_used_date"] = today
        results.append({"email": em, "success": ok, "message": msg})
    if len(accounts) > 0:
        _save_envato_accounts(accounts)
    return {"success": True, "valid_count": valid_count, "total": len(accounts), "details": results}

def fetch_envato_referral_code(email: str, password: str, save_to_pool: bool = True) -> Dict:
    """Log in to envato-downloader.com, scrape /get-credits, and extract referral code & link"""
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    try:
        home_res = scraper.get("https://envato-downloader.com/", timeout=15)
        soup_home = BeautifulSoup(home_res.text, "html.parser")
        form_login = soup_home.find("form", id="form-login")
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
            "Referer": "https://envato-downloader.com/"
        }
        res = scraper.post("https://envato-downloader.com/AuthController/loginPost", data=payload, headers=headers, timeout=15)
        if res.status_code != 200 or res.json().get("result") != 1:
            return {"success": False, "error": "Login failed for account"}

        r_credits = scraper.get("https://envato-downloader.com/get-credits", timeout=15)
        soup_cred = BeautifulSoup(r_credits.text, "html.parser")
        
        ref_code = ""
        ref_url = ""
        
        # 1. Look for span.code
        ref_span = soup_cred.find("span", class_="code")
        if ref_span:
            ref_code = ref_span.get_text(strip=True)
            
        # 2. Look for referblock onclick
        referblock = soup_cred.find("div", class_=re.compile(r"referblock"))
        if referblock and referblock.get("onclick"):
            onclick_txt = referblock.get("onclick", "")
            m = re.search(r'https?://envato-downloader\.com/register\?ref=([A-Za-z0-9_-]+)', onclick_txt)
            if m:
                ref_url = m.group(0)
                if not ref_code:
                    ref_code = m.group(1)
                    
        # 3. Fallback regex in full page
        if not ref_code:
            m_full = re.search(r'register\?ref=([A-Za-z0-9_-]+)', r_credits.text)
            if m_full:
                ref_code = m_full.group(1)
                ref_url = f"https://envato-downloader.com/register?ref={ref_code}"

        if not ref_url and ref_code:
            ref_url = f"https://envato-downloader.com/register?ref={ref_code}"

        if not ref_code:
            return {"success": False, "error": "Referral code not found on /get-credits page"}

        if save_to_pool:
            accounts = _load_envato_accounts()
            for acc in accounts:
                if acc.get("email", "").lower() == email.lower():
                    acc["referral_code"] = ref_code
                    acc["referral_url"] = ref_url
                    break
            _save_envato_accounts(accounts)

        return {
            "success": True,
            "email": email,
            "referral_code": ref_code,
            "referral_url": ref_url
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def sync_all_envato_referrals() -> Dict:
    """Sync/fetch referral codes for all verified accounts in pool"""
    accounts = _load_envato_accounts()
    synced_count = 0
    results = []
    
    for acc in accounts:
        em = acc.get("email", "")
        pw = acc.get("password", "")
        if not em or not pw:
            continue
            
        res = fetch_envato_referral_code(em, pw, save_to_pool=True)
        if res.get("success"):
            synced_count += 1
            results.append({"email": em, "success": True, "referral_code": res.get("referral_code")})
        else:
            results.append({"email": em, "success": False, "error": res.get("error")})
            
    return {"success": True, "synced_count": synced_count, "total": len(accounts), "details": results}

def track_envato_referral_use(email: str) -> Dict:
    """Increment the daily referral use/copy counter for an account (Max 2 per day)"""
    accounts = _load_envato_accounts()
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
            _save_envato_accounts(accounts)
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

def complete_envato_profile(email: str, password: str, custom_profile: Optional[Dict] = None) -> Dict:
    """Auto-submit profile completion form on envato-downloader.com"""
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    try:
        # 1. Login
        home_res = scraper.get("https://envato-downloader.com/", timeout=15)
        soup_home = BeautifulSoup(home_res.text, "html.parser")
        form_login = soup_home.find("form", id="form-login")
        if not form_login:
            return {"success": False, "error": "Login form not found"}
        csrf_token = form_login.find("input", {"name": "csrf_token"}).get("value", "")
        
        l_res = scraper.post("https://envato-downloader.com/AuthController/loginPost", data={
            "csrf_token": csrf_token,
            "email": email,
            "password": password,
            "sys_lang_id": "1"
        }, headers={"X-Requested-With": "XMLHttpRequest", "Referer": "https://envato-downloader.com/"}, timeout=15)
        
        if l_res.status_code != 200 or l_res.json().get("result") != 1:
            return {"success": False, "error": "Login failed for profile update"}

        # 2. Get Profile Page CSRF
        r_prof = scraper.get("https://envato-downloader.com/profile", timeout=15)
        soup_prof = BeautifulSoup(r_prof.text, "html.parser")
        csrf_prof_inp = soup_prof.find("input", {"name": "csrf_token"})
        csrf_prof = csrf_prof_inp.get("value", "") if csrf_prof_inp else csrf_token

        # 3. Generate Profile Payload
        first_names = ["Alex", "Jordan", "Taylor", "Morgan", "Reza", "Dimas", "Aditya", "Fajar", "Kevin", "Budi"]
        last_names = ["Pratama", "Wijaya", "Kusuma", "Santoso", "Saputra", "Nugroho", "Setiawan", "Hidayat", "Siregar"]
        cities = ["Jakarta", "Surabaya", "Bandung", "Medan", "Semarang", "Yogyakarta"]
        
        fname = (custom_profile or {}).get("first_name") or random.choice(first_names)
        lname = (custom_profile or {}).get("last_name") or random.choice(last_names)
        city = random.choice(cities)
        
        prof_payload = {
            "csrf_token": csrf_prof,
            "back_url": "https://envato-downloader.com/profile",
            "first_name": fname,
            "last_name": lname,
            "country_code": "62",
            "phone_number": f"812{random.randint(1000000, 9999999)}",
            "address": f"Cyber Creative Studio Jl. {city} No. {random.randint(10, 199)}",
            "country_id": "1",
            "state_id": "1",
            "city_id": "1",
            "zipcode": str(random.randint(10000, 99999))
        }

        # 4. Post Profile Update
        res_p = scraper.post("https://envato-downloader.com/complete-profile-post", data=prof_payload, headers={"Referer": "https://envato-downloader.com/profile"}, timeout=20)
        if res_p.status_code in [200, 302]:
            accounts = _load_envato_accounts()
            for acc in accounts:
                if acc.get("email", "").lower() == email.lower():
                    acc["profile_completed"] = True
                    break
            _save_envato_accounts(accounts)
            return {"success": True, "message": f"Profile completed successfully for {email}", "profile": prof_payload}
        else:
            return {"success": False, "error": f"Profile update returned status {res_p.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _poll_imap_for_verification(gmail_user: str, gmail_app_pass: str, max_wait_sec: int = 50) -> Optional[str]:
    """Poll Gmail inbox via IMAP to auto-retrieve activation link"""
    start = time.time()
    while time.time() - start < max_wait_sec:
        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
            mail.login(gmail_user, gmail_app_pass)
            mail.select("INBOX")
            
            # Search unread or latest messages
            status, messages = mail.search(None, 'UNSEEN')
            msg_ids = messages[0].split() if status == 'OK' and messages[0] else []
            if not msg_ids:
                status, messages = mail.search(None, 'ALL')
                all_ids = messages[0].split() if status == 'OK' and messages[0] else []
                msg_ids = all_ids[-6:]
                
            for msg_id in reversed(msg_ids):
                res, data = mail.fetch(msg_id, '(RFC822)')
                if res != 'OK':
                    continue
                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)
                
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() in ["text/plain", "text/html"]:
                            payload = part.get_payload(decode=True)
                            if payload:
                                body += payload.decode(errors="ignore")
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body = payload.decode(errors="ignore")
                        
                if "envato-downloader" in body.lower() or "confirm" in body.lower() or "verify" in body.lower():
                    links = re.findall(r'https?://envato-downloader\.com/[^\s"\'<>]+', body)
                    for lk in links:
                        if any(k in lk.lower() for k in ["verify", "confirm", "token=", "code=", "activate"]):
                            mail.logout()
                            return lk
            mail.logout()
        except Exception as e:
            print(f"[IMAP Poll] Notice: {e}")
        time.sleep(4)
    return None

def auto_farm_envato_referral(
    master_ref_code: str,
    master_email: str = "",
    mode: str = "imap",
    gmail_user: str = "",
    gmail_app_password: str = "",
    custom_email: str = "",
    custom_password: str = ""
) -> Dict:
    """Full Automation Engine: Register with referral code -> Confirm Email -> Complete Profile -> Add to Pool"""
    steps = []
    try:
        steps.append("Initializing referral automation session...")
        sess = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "mobile": False})
        sess.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        
        # 1. Determine Target Registration Email
        target_email = ""
        target_password = custom_password or ("EnvatoAuto@" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8)))
        mail_tm_token = None
        
        if mode == "imap" and gmail_user:
            # Generate plus-alias or dot-trick from gmail_user
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
            r_acc = requests.post("https://api.mail.tm/accounts", json={"address": target_email, "password": target_password}, timeout=15)
            r_tok = requests.post("https://api.mail.tm/token", json={"address": target_email, "password": target_password}, timeout=15)
            mail_tm_token = r_tok.json().get("token", "")
            steps.append(f"Created Temp-Mail: {target_email}")
        else:
            target_email = custom_email
            if not target_email:
                raise Exception("No registration email provided")

        # 2. Get Register CSRF
        steps.append("Fetching register page & CSRF token...")
        reg_page = sess.get("https://envato-downloader.com/register", timeout=20)
        soup = BeautifulSoup(reg_page.text, "html.parser")
        csrf_inp = soup.find("input", {"name": re.compile(r"csrf", re.I)})
        csrf = csrf_inp.get("value") if csrf_inp else ""

        # 3. Post Registration with Referral Code
        steps.append(f"Submitting registration with Referral Code [{master_ref_code}]...")
        username_val = re.sub(r'[^a-zA-Z0-9]', '', target_email.split('@')[0])[:12] or "user" + ''.join(random.choices(string.digits, k=5))
        reg_data = {
            "csrf_token": csrf,
            "sys_lang_id": "1",
            "username": username_val,
            "email": target_email,
            "password": target_password,
            "confirm_password": target_password,
            "referral_code": master_ref_code,
            "terms_conditions": "1"
        }
        reg_resp = sess.post("https://envato-downloader.com/register-post", data=reg_data, headers={"X-Requested-With": "XMLHttpRequest"}, timeout=20)
        steps.append(f"Registration response status: {reg_resp.status_code}")

        # Strict Validation & Anti-Bot Alert Detection
        soup_resp = BeautifulSoup(reg_resp.text, "html.parser")
        alert_danger = soup_resp.find(class_=re.compile(r"alert-danger|alert-warning|error", re.I))
        if alert_danger:
            err_text = alert_danger.get_text(strip=True)
            if "robot" in err_text.lower() or "captcha" in err_text.lower():
                raise Exception(f'Registration blocked by Anti-Bot protection: "{err_text}". CAPTCHA challenge is enforced on registration form.')
            raise Exception(f"Registration error from server: {err_text}")

        # 4. Email Confirmation
        vlink = None
        if mode == "imap" and gmail_user and gmail_app_password:
            steps.append("Polling Gmail IMAP for activation link (max 50s)...")
            vlink = _poll_imap_for_verification(gmail_user, gmail_app_password, max_wait_sec=50)
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
                        lks = re.findall(r'https?://envato-downloader\.com/[^\s"\'<>]+', b_text)
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

        # 5. Auto Complete Profile
        steps.append("Auto-completing user profile (name, address, phone)... ")
        prof_res = complete_envato_profile(target_email, target_password)
        if prof_res.get("success"):
            steps.append("Profile completed & activated!")

        # 6. Add new account to Pool & Fetch its own Ref Code
        add_account(target_email, target_password, verify=False)
        try:
            ref_res = fetch_envato_referral_code(target_email, target_password, save_to_pool=True)
            if ref_res.get("success"):
                steps.append(f"Generated new account referral code: {ref_res.get('referral_code')}")
        except Exception:
            pass

        # 7. Track referral quota on master account
        if master_email:
            track_envato_referral_use(master_email)
            steps.append(f"Updated daily referral counter for master account {master_email}")

        return {
            "success": True,
            "email": target_email,
            "password": target_password,
            "referral_code": master_ref_code,
            "message": f"Successfully automated referral for {target_email}! Credits added to master.",
            "steps": steps,
            "account_status": EnvatoScraper.get_account_status()
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Auto-farm error: {str(e)}",
            "steps": steps
        }

class EnvatoScraper:
    def __init__(self):
        self.base_url = "https://envato-downloader.com"
        self.scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
        )
        apply_network_settings(self.scraper)
        self.csrf_token = ""
        self.is_logged_in = False
        self.current_email = None

    @staticmethod
    def get_account_status(custom_accounts: Optional[List[Dict[str, str]]] = None) -> Dict:
        pool = custom_accounts if (custom_accounts is not None and len(custom_accounts) > 0) else _load_envato_accounts()
        now = time.time()
        today = _get_today_str()
        accounts_info = []
        ready_count = 0
        rate_limited_count = 0

        for acc in pool:
            em = acc.get("email", "")
            is_limited = RATE_LIMITED_ENVATO_ACCOUNTS.get(em, 0) > now
            daily_used = acc.get("daily_used", 0) if acc.get("last_used_date") == today else 0
            remaining = max(0, 2 - daily_used)

            if not acc.get("verified", True):
                status_str = "Unverified"
            elif is_limited:
                status_str = "Rate-Limited (1h cooldown)"
                rate_limited_count += 1
            elif remaining == 0:
                status_str = "Quota Reached (0/2)"
                rate_limited_count += 1
            else:
                status_str = "Ready"
                ready_count += 1

            accounts_info.append({
                "email": em,
                "password": acc.get("password", ""),
                "status": status_str,
                "rate_limited": is_limited or (remaining == 0),
                "verified": acc.get("verified", True),
                "referral_code": acc.get("referral_code", ""),
                "referral_url": acc.get("referral_url", ""),
                "daily_used": daily_used,
                "remaining_daily": remaining,
                "profile_completed": acc.get("profile_completed", False),
                "added_at": acc.get("added_at", time.time())
            })

        total = len(pool)
        return {
            "total_accounts": total,
            "active_accounts": ready_count,
            "ready_accounts": ready_count,
            "limited_accounts": rate_limited_count,
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

    def _check_downloads_history(self, target_url: str) -> Optional[str]:
        """Check the /downloads page for an already-generated link for this asset"""
        try:
            r = self.scraper.get(f"{self.base_url}/downloads", timeout=15)
            if r.status_code != 200:
                return None
            soup = BeautifulSoup(r.text, "html.parser")
            
            clean_target = target_url.split('#')[0].split('?')[0].rstrip('/')
            target_slug = clean_target.split('/')[-1].replace('-', ' ').replace('_', ' ').lower()
            
            rows = soup.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if not cols or len(cols) < 3:
                    continue
                row_text = row.get_text().lower()
                
                # Check for direct download link in row
                dl_btn = row.find("a", href=re.compile(r"generate-link|download-file|drive\.google\.com|elements\.envato", re.I))
                if not dl_btn:
                    dl_btn = row.find("a", class_=re.compile(r"btn", re.I))
                    
                if dl_btn and dl_btn.get("href"):
                    href = dl_btn.get("href")
                    # Strict match: must match target slug or relevant title
                    if target_slug in row_text or any(w in row_text for w in target_slug.split() if len(w) > 4):
                        return href
            return None
        except Exception as e:
            print(f"[EnvatoScraper] History check error: {e}")
            return None

    def _process_extraction(self, envato_url: str) -> str:
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{self.base_url}/envato-downloader",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        home_after = self.scraper.get(f"{self.base_url}/envato-downloader", timeout=15)
        soup_after = BeautifulSoup(home_after.text, "html.parser")
        form_dl = soup_after.find("form", id="envatodownloader")
        csrf_inp = form_dl.find("input", {"name": "csrf_token"}) if form_dl else soup_after.find("input", {"name": "csrf_token"})
        csrf_val = csrf_inp.get("value") if csrf_inp else self.csrf_token

        clean_url = envato_url.strip().split('#')[0].split('?')[0]
        m_slug = re.search(r'elements\.envato\.com/(?:[^/]+/)?([^/?#]+)', clean_url)
        target_sub_url = f"https://elements.envato.com/{m_slug.group(1)}" if m_slug else clean_url

        ajax_payload = {
            "csrf_token": csrf_val,
            "url": target_sub_url,
            "type": "envato_downloader",
            "tokens": "1",
            "osuyk": "",
            "sysLangId": "1"
        }
        res = self.scraper.post(f"{self.base_url}/AjaxController/envato_downloader", data=ajax_payload, headers=headers, timeout=20)
        try:
            res_json = res.json()
        except:
            res_json = {}

        gen_url = res_json.get("token")
        if not gen_url:
            print("[EnvatoScraper] Direct AJAX token not returned. Checking /downloads history for ready link...")
            history_url = self._check_downloads_history(clean_url)
            if history_url:
                print(f"[EnvatoScraper] Found ready download link in account history: {history_url}")
                gen_url = history_url

        if not gen_url:
            msg = res_json.get("message", "Failed to generate link")
            clean_msg = re.sub(r'<[^>]+>', ' ', str(msg)).strip()
            clean_msg = ' '.join(clean_msg.split())
            if any(k in clean_msg.lower() for k in ["credit", "limit", "buy credits", "exhausted"]):
                if self.current_email:
                    RATE_LIMITED_ENVATO_ACCOUNTS[self.current_email] = time.time() + 86400
            raise Exception(clean_msg)

        return self._resolve_gen_url_to_gdrive(gen_url, headers, csrf_val)

    def _resolve_gen_url_to_gdrive(self, gen_url: str, headers: dict, fallback_csrf: str = "") -> str:
        """Resolve a generate-link token URL all the way to a direct Google Drive link"""
        if "drive.google.com" in gen_url or "google.com" in gen_url:
            return gen_url

        gen_resp = self.scraper.get(gen_url, timeout=20)
        soup_gen = BeautifulSoup(gen_resp.text, "html.parser")
        btn = soup_gen.find(id="btnCounter")
        next_url = btn.get("href") if btn else None
        
        if not next_url:
            raise Exception("Could not find btnCounter href on Envato generate page")
            
        if "download-file" in next_url:
            dl_file_url = next_url
        else:
            proc_resp = self.scraper.get(next_url, timeout=20)
            soup_proc = BeautifulSoup(proc_resp.text, "html.parser")
            dl_link = soup_proc.find("a", href=re.compile(r"download-file"))
            dl_file_url = dl_link.get("href") if dl_link else None
            
        if not dl_file_url:
            raise Exception("Could not find download-file URL")
            
        df_resp = self.scraper.get(dl_file_url, timeout=20)
        soup_df = BeautifulSoup(df_resp.text, "html.parser")
        link_a = soup_df.find("a", href=re.compile(r"links"))
        links_url = link_a.get("href") if link_a else None
        
        if not links_url:
            raise Exception("Could not find links URL")
            
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
            
        learn_resp = self.scraper.get(learn_target_url, timeout=20)
        learn_soup = BeautifulSoup(learn_resp.text, "html.parser")
        
        gen_dl_token = ""
        for s in learn_soup.find_all("script"):
            t = s.string or ""
            m = re.search(r'generatedownload\(["\']([a-f0-9]{32,64})["\']\)', t)
            if m:
                gen_dl_token = m.group(1)
                break
                
        ddlink_slug = ""
        for a in learn_soup.find_all("a"):
            h = a.get("href", "")
            if "/ddlink/" in h:
                ddlink_slug = h.split("/ddlink/")[-1].split("?")[0].strip()
                break
                
        if not ddlink_slug and not gen_dl_token:
            for a in learn_soup.find_all("a"):
                h = a.get("href", "")
                if "drive.google.com" in h:
                    return h
            raise Exception("Could not extract generatedownload token or ddlink from learn page")
            
        csrf_learn_inp = learn_soup.find("input", {"name": "csrf_token"})
        csrf_learn = csrf_learn_inp.get("value") if csrf_learn_inp else fallback_csrf
        
        gen_payload = {
            "token": gen_dl_token or ddlink_slug,
            "csrf_token": csrf_learn
        }
        gen_post_resp = self.scraper.post(
            f"{self.base_url}/AjaxController/generatedownload",
            data=gen_payload,
            headers={"X-Requested-With": "XMLHttpRequest", "Referer": learn_target_url},
            timeout=20
        )
        
        try:
            gen_data = gen_post_resp.json()
            if gen_data.get("url"):
                return gen_data["url"]
        except Exception:
            pass
            
        if ddlink_slug:
            dd_resp = self.scraper.get(f"{self.base_url}/ddlink/{ddlink_slug}", timeout=20)
            dd_soup = BeautifulSoup(dd_resp.text, "html.parser")
            for a in dd_soup.find_all("a"):
                h = a.get("href", "")
                if "drive.google.com" in h:
                    return h
                    
        raise Exception("Failed to resolve final direct Google Drive download link")

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
    """Wrapper for legacy calls"""
    return auto_farm_envato_referral(master_ref_code="", mode="tempmail")
