"""
ArchNodes - Premium Asset Downloader
Main Flask Web Application
"""

import os
import sys
import json
import logging
from flask import Flask, render_template, request, jsonify, Response, redirect

# Ensure project root in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.normalizer import normalize_profile_url
from core.bypass import get_bypass_settings, save_bypass_settings
from core.proxy_manager import load_proxy_settings, save_proxy_settings, test_single_proxy, test_all_proxies, get_current_ip_info
from core.downloader import get_download_progress, stop_download
from scrapers.base import fetch_media_stream, HEADERS_FOR_REQUESTS
from scrapers.freepik import (
    FreepikScraper,
    _load_accounts as _load_freepik_accounts,
    add_account,
    remove_account,
    batch_add_accounts,
    verify_all_accounts as verify_all_freepik_accounts,
    test_freepik_login,
    fetch_freepik_referral_code,
    sync_all_freepik_referrals,
    track_freepik_referral_use,
    complete_freepik_profile,
    auto_farm_freepik_referral,
    auto_register_account,
    FreepikRateLimitException
)
from scrapers.vault import find_vault_item, add_vault_item, load_vault, save_vault, sync_all_accounts_history
from scrapers.envato import (
    get_envato_info,
    EnvatoScraper,
    _load_envato_accounts,
    _save_envato_accounts,
    add_account as add_envato_account,
    remove_account as remove_envato_account,
    batch_add_accounts as batch_add_envato_accounts,
    verify_all_accounts as verify_all_envato_accounts,
    test_envato_login,
    fetch_envato_referral_code,
    sync_all_envato_referrals,
    track_envato_referral_use,
    complete_envato_profile,
    auto_farm_envato_referral
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = Flask(__name__)
app.config['SECRET_KEY'] = 'archnodes-secret-2026'
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/check", methods=["POST"])
@app.route("/api/get-info", methods=["POST"])
def api_check():
    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"status": "error", "message": "Please enter a valid link"}), 400

    res_norm = normalize_profile_url(url)
    profile_url, asset_name, platform = res_norm[0], res_norm[1], res_norm[2]
    if not profile_url:
        return jsonify({"status": "error", "message": "Invalid URL format"}), 400

    if platform == "freepik":
        url_low = profile_url.lower()
        file_type = "PSD" if "psd" in url_low else "VECTOR" if "vector" in url_low else "PHOTO" if "photo" in url_low else "ZIP"
        return jsonify({
            "status": "success",
            "success": True,
            "model_name": asset_name,
            "platform": "freepik",
            "count": 1,
            "image_count": 1,
            "video_count": 0,
            "media_items": [{
                "index": 1,
                "type": file_type,
                "src": profile_url,
                "poster": "",
                "download_type": "freepik"
            }],
            "account_status": FreepikScraper.get_account_status()
        })

    if platform == "envato":
        url_low = profile_url.lower()
        file_type = "MOCKUP" if "mockup" in url_low else "TEMPLATE" if "template" in url_low else "PSD" if "psd" in url_low else "GRAPHIC" if "graphic" in url_low else "VIDEO" if "video" in url_low else "AUDIO" if "audio" in url_low else "FONT" if "font" in url_low else "ASSET"
        
        # Parse clean title from URL slug without triggering 403 on elements.envato.com
        slug = profile_url.split('#')[0].split('?')[0].rstrip('/').split('/')[-1]
        title = slug.replace('-', ' ').replace('_', ' ').title()
        
        return jsonify({
            "status": "success",
            "success": True,
            "model_name": title or asset_name,
            "platform": "envato",
            "count": 1,
            "image_count": 1,
            "video_count": 0,
            "media_items": [{
                "index": 1,
                "type": file_type,
                "src": profile_url,
                "poster": "",
                "download_type": "envato"
            }]
        })

    return jsonify({"status": "error", "message": "Unsupported platform"}), 400

@app.route("/api/get-freepik-link", methods=["POST", "GET"])
@app.route("/api/freepik-download", methods=["POST", "GET"])
def api_get_freepik_link():
    data = (request.json if request.is_json else request.args) or {}
    url = data.get("url", "").strip()
    custom_accounts = data.get("accounts") if isinstance(data.get("accounts"), list) else None

    if not url:
        return jsonify({"success": False, "error": "URL parameter is required"}), 400

    # 1. Check Cloud Vault Cache First (Instant 0-Quota Resolution)
    cached = find_vault_item(url)
    if cached and cached.get("download_url"):
        return jsonify({
            "success": True,
            "download_url": cached["download_url"],
            "title": cached.get("title", ""),
            "from_vault": True,
            "account_status": FreepikScraper.get_account_status(custom_accounts)
        })

    try:
        scraper_fp = FreepikScraper()
        gdrive_link = scraper_fp.extract_gdrive_url(url, custom_accounts=custom_accounts)
        # Auto-persist to Cloud Vault
        slug = url.split('#')[0].split('?')[0].rstrip('/').split('/')[-1]
        title = slug.replace('-', ' ').replace('_', ' ').replace('.htm', '').title()
        add_vault_item(url, title, gdrive_link, "freepik")
        return jsonify({
            "success": True,
            "download_url": gdrive_link,
            "from_vault": False,
            "account_status": FreepikScraper.get_account_status(custom_accounts)
        })
    except FreepikRateLimitException as e:
        status = FreepikScraper.get_account_status(custom_accounts)
        return jsonify({"success": False, "error": str(e), "rate_limited": True, "account_status": status}), 429
    except Exception as e:
        status = FreepikScraper.get_account_status(custom_accounts)
        return jsonify({"success": False, "error": str(e), "account_status": status}), 500

@app.route("/api/download-stream")
def api_download_stream():
    url = request.args.get("url", "").strip()
    index = int(request.args.get("index", 1))

    if not url:
        return "URL parameter is missing", 400

    res_norm = normalize_profile_url(url)
    profile_url, asset_name, platform = res_norm[0], res_norm[1], res_norm[2]

    if platform == "freepik":
        try:
            cached = find_vault_item(profile_url)
            if cached and cached.get("download_url"):
                gdrive_link = cached["download_url"]
            else:
                scraper_fp = FreepikScraper()
                gdrive_link = scraper_fp.extract_gdrive_url(profile_url)
                slug = profile_url.split('#')[0].split('?')[0].rstrip('/').split('/')[-1]
                title = slug.replace('-', ' ').replace('_', ' ').replace('.htm', '').title()
                add_vault_item(profile_url, title, gdrive_link, "freepik")
                
            if request.args.get("mode") == "json":
                return jsonify({"success": True, "download_url": gdrive_link})
            return redirect(gdrive_link)
        except Exception as e:
            return f"<h2>Freepik Resolution Error</h2><p>{str(e)}</p>", 500

    if platform == "envato":
        try:
            cached = find_vault_item(profile_url)
            if cached and cached.get("download_url"):
                gdrive_link = cached["download_url"]
            else:
                scraper_env = EnvatoScraper()
                gdrive_link = scraper_env.extract_gdrive_url(profile_url)
                slug = profile_url.split('#')[0].split('?')[0].rstrip('/').split('/')[-1]
                title = slug.replace('-', ' ').replace('_', ' ').title()
                add_vault_item(profile_url, title, gdrive_link, "envato")
                
            if request.args.get("mode") == "json":
                return jsonify({"success": True, "download_url": gdrive_link})
            return redirect(gdrive_link)
        except Exception as e:
            return f"<h2>Envato Resolution Error</h2><p>{str(e)}</p>", 500

    return "Unsupported platform", 400

@app.route("/api/reset-cooldowns", methods=["POST"])
def api_reset_cooldowns():
    from scrapers.freepik import RATE_LIMITED_ACCOUNTS
    from scrapers.envato import RATE_LIMITED_ENVATO_ACCOUNTS
    RATE_LIMITED_ACCOUNTS.clear()
    RATE_LIMITED_ENVATO_ACCOUNTS.clear()
    return jsonify({"success": True, "message": "All account cooldowns have been reset."})

@app.route("/api/freepik-status", methods=["GET", "POST"])
def api_freepik_status():
    data = (request.json if request.is_json else request.args) or {}
    custom_accounts = data.get("accounts") if isinstance(data.get("accounts"), list) else None
    return jsonify({"success": True, "status": FreepikScraper.get_account_status(custom_accounts)})

@app.route("/api/freepik-batch-add", methods=["POST"])
def api_freepik_batch_add():
    data = request.json or {}
    accounts = data.get("accounts", [])
    if not accounts:
        return jsonify({"success": False, "error": "Account list is empty"}), 400
    result = batch_add_accounts(accounts)
    return jsonify(result)

@app.route("/api/get-envato-link", methods=["POST", "GET"])
def api_get_envato_link():
    data = (request.json if request.is_json else request.args) or {}
    url = data.get("url", "").strip()
    custom_accounts = data.get("accounts") if isinstance(data.get("accounts"), list) else None

    if not url:
        return jsonify({"success": False, "error": "URL parameter is required"}), 400

    # Check Cloud Vault First
    cached = find_vault_item(url)
    if cached and cached.get("download_url"):
        return jsonify({
            "success": True,
            "download_url": cached["download_url"],
            "title": cached.get("title", ""),
            "from_vault": True
        })

    try:
        scraper_env = EnvatoScraper()
        gdrive_link = scraper_env.extract_gdrive_url(url, custom_accounts=custom_accounts)
        slug = url.split('#')[0].split('?')[0].rstrip('/').split('/')[-1]
        title = slug.replace('-', ' ').replace('_', ' ').title()
        add_vault_item(url, title, gdrive_link, "envato")
        return jsonify({
            "success": True,
            "download_url": gdrive_link,
            "from_vault": False
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/freepik-auto-register", methods=["POST"])
def api_freepik_auto_register():
    result = auto_register_account()
    if not result.get("account_status"):
        result["account_status"] = FreepikScraper.get_account_status()
    return jsonify(result)

@app.route("/api/freepik-accounts", methods=["GET", "POST", "DELETE"])
def api_freepik_accounts():
    if request.method == "GET":
        data = (request.json if request.is_json else request.args) or {}
        custom_accounts = data.get("accounts") if isinstance(data.get("accounts"), list) else None
        return jsonify({"success": True, "status": FreepikScraper.get_account_status(custom_accounts)})
    
    if request.method == "POST":
        data = request.json or {}
        email = data.get("email", "").strip()
        password = data.get("password", "").strip()
        if not email or not password:
            return jsonify({"success": False, "error": "Email and password are required"}), 400
        result = add_account(email, password)
        if result.get("success"):
            result["account_status"] = FreepikScraper.get_account_status()
        return jsonify(result)
    
    if request.method == "DELETE":
        data = request.json or {}
        email = data.get("email", "").strip()
        if not email:
            return jsonify({"success": False, "error": "Email is required"}), 400
        result = remove_account(email)
        if result.get("success"):
            result["account_status"] = FreepikScraper.get_account_status()
        return jsonify(result)

@app.route("/api/freepik-sync-referrals", methods=["POST"])
def api_freepik_sync_referrals():
    result = sync_all_freepik_referrals()
    result["status"] = FreepikScraper.get_account_status()
    return jsonify(result)

@app.route("/api/freepik-verify", methods=["POST"])
def api_freepik_verify():
    data = request.json or {}
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    if not email:
        return jsonify({"success": False, "error": "Email is required"}), 400
    if not password:
        accounts = _load_freepik_accounts()
        for a in accounts:
            if a.get("email", "").lower() == email.lower():
                password = a.get("password", "")
                break
    ok, msg, credits = test_freepik_login(email, password)
    if ok:
        accounts = _load_freepik_accounts()
        for a in accounts:
            if a.get("email", "").lower() == email.lower():
                a["verified"] = True
                a["credits"] = credits
                a["status"] = f"Ready ({credits} Credits)" if credits > 0 else "0 Credits (No balance)"
                break
        from scrapers.freepik import _save_accounts
        _save_accounts(accounts)
    return jsonify({
        "success": ok,
        "message": msg,
        "credits": credits,
        "status": FreepikScraper.get_account_status()
    })

@app.route("/api/freepik-verify-all", methods=["POST"])
def api_freepik_verify_all():
    data = request.json or {}
    custom_accounts = data.get("accounts") if isinstance(data.get("accounts"), list) else None
    result = verify_all_freepik_accounts(custom_accounts)
    result["status"] = FreepikScraper.get_account_status()
    return jsonify(result)

@app.route("/api/freepik-fetch-ref", methods=["POST"])
def api_freepik_fetch_single_ref():
    data = request.json or {}
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    if not email:
        return jsonify({"success": False, "error": "Email is required"}), 400
    if not password:
        accounts = _load_freepik_accounts()
        for a in accounts:
            if a.get("email", "").lower() == email.lower():
                password = a.get("password", "")
                break
    if not password:
        return jsonify({"success": False, "error": "Password not found for account"}), 400

    result = fetch_freepik_referral_code(email, password, save_to_pool=True)
    result["status"] = FreepikScraper.get_account_status()
    return jsonify(result)

@app.route("/api/freepik-track-referral", methods=["POST"])
def api_freepik_track_referral():
    data = request.json or {}
    email = data.get("email", "").strip()
    if not email:
        return jsonify({"success": False, "error": "Email is required"}), 400
    result = track_freepik_referral_use(email)
    result["status"] = FreepikScraper.get_account_status()
    return jsonify(result)

@app.route("/api/freepik-complete-profile", methods=["POST"])
def api_freepik_complete_profile():
    data = request.json or {}
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    profile = data.get("profile") if isinstance(data.get("profile"), dict) else None
    if not email or not password:
        return jsonify({"success": False, "error": "Email and password are required"}), 400
    result = complete_freepik_profile(email, password, custom_profile=profile)
    result["status"] = FreepikScraper.get_account_status()
    return jsonify(result)

@app.route("/api/freepik-auto-farm", methods=["POST"])
def api_freepik_auto_farm():
    data = request.json or {}
    master_ref = data.get("referral_code", "").strip()
    master_email = data.get("master_email", "").strip()
    mode = data.get("mode", "tempmail").strip()
    gmail_user = data.get("gmail_user", "").strip()
    gmail_pass = data.get("gmail_app_password", "").strip()
    custom_email = data.get("custom_email", "").strip()
    custom_password = data.get("custom_password", "").strip()

    if not master_ref:
        return jsonify({"success": False, "error": "Master referral code is required to farm credits"}), 400

    result = auto_farm_freepik_referral(
        master_ref_code=master_ref,
        master_email=master_email,
        mode=mode,
        gmail_user=gmail_user,
        gmail_app_password=gmail_pass,
        custom_email=custom_email,
        custom_password=custom_password
    )
    result["account_status"] = FreepikScraper.get_account_status()
    return jsonify(result)


@app.route("/api/bypass-settings", methods=["GET", "POST"])
def api_bypass_settings():
    if request.method == "GET":
        return jsonify({"success": True, "settings": get_bypass_settings()})
    data = request.json or {}
    success = save_bypass_settings(data)
    return jsonify({"success": success, "settings": get_bypass_settings()})

@app.route("/api/progress")
def api_progress():
    return jsonify(get_download_progress())

@app.route("/api/stop", methods=["POST"])
def api_stop():
    stop_download()
    return jsonify({"success": True})

@app.route("/api/envato-status", methods=["GET", "POST"])
def api_envato_status():
    data = (request.json if request.is_json else request.args) or {}
    custom_accounts = data.get("accounts") if isinstance(data.get("accounts"), list) else None
    return jsonify({"success": True, "status": EnvatoScraper.get_account_status(custom_accounts)})

@app.route("/api/envato-sync-referrals", methods=["POST"])
def api_envato_sync_referrals():
    result = sync_all_envato_referrals()
    result["status"] = EnvatoScraper.get_account_status()
    return jsonify(result)

@app.route("/api/envato-track-referral", methods=["POST"])
def api_envato_track_referral():
    data = request.json or {}
    email = data.get("email", "").strip()
    if not email:
        return jsonify({"success": False, "error": "Email is required"}), 400
    result = track_envato_referral_use(email)
    result["status"] = EnvatoScraper.get_account_status()
    return jsonify(result)

@app.route("/api/envato-complete-profile", methods=["POST"])
def api_envato_complete_profile():
    data = request.json or {}
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    profile = data.get("profile") if isinstance(data.get("profile"), dict) else None
    if not email or not password:
        return jsonify({"success": False, "error": "Email and password are required"}), 400
    result = complete_envato_profile(email, password, custom_profile=profile)
    result["status"] = EnvatoScraper.get_account_status()
    return jsonify(result)

@app.route("/api/envato-auto-farm", methods=["POST"])
def api_envato_auto_farm():
    data = request.json or {}
    master_ref_code = data.get("master_ref_code", "").strip()
    master_email = data.get("master_email", "").strip()
    mode = data.get("mode", "imap").strip()
    gmail_user = data.get("gmail_user", "").strip()
    gmail_app_password = data.get("gmail_app_password", "").strip()
    
    if not master_ref_code:
        return jsonify({"success": False, "error": "Master Referral Code is required"}), 400
    if mode == "imap" and (not gmail_user or not gmail_app_password):
        return jsonify({"success": False, "error": "Gmail Email and App Password are required for IMAP mode"}), 400

    result = auto_farm_envato_referral(
        master_ref_code=master_ref_code,
        master_email=master_email,
        mode=mode,
        gmail_user=gmail_user,
        gmail_app_password=gmail_app_password
    )
    result["status"] = EnvatoScraper.get_account_status()
    return jsonify(result)

@app.route("/api/envato-auto-register", methods=["POST"])
def api_envato_auto_register():
    data = request.json or {}
    master_ref = data.get("referral_code", "")
    result = auto_farm_envato_referral(master_ref_code=master_ref, mode="tempmail")
    result["account_status"] = EnvatoScraper.get_account_status()
    return jsonify(result)

@app.route("/api/envato-accounts", methods=["GET", "POST", "DELETE"])
def api_envato_accounts():
    if request.method == "GET":
        data = (request.json if request.is_json else request.args) or {}
        custom_accounts = data.get("accounts") if isinstance(data.get("accounts"), list) else None
        return jsonify({"success": True, "status": EnvatoScraper.get_account_status(custom_accounts)})
    
    if request.method == "POST":
        data = request.json or {}
        email = data.get("email", "").strip()
        password = data.get("password", "").strip()
        verify = data.get("verify", True)
        if not email or not password:
            return jsonify({"success": False, "error": "Email and password are required"}), 400
        result = add_envato_account(email, password, verify=verify)
        if result.get("success"):
            result["account_status"] = EnvatoScraper.get_account_status()
        return jsonify(result)
        
    if request.method == "DELETE":
        data = request.json or {}
        email = data.get("email", "").strip()
        if not email:
            return jsonify({"success": False, "error": "Email is required"}), 400
        result = remove_envato_account(email)
        if result.get("success"):
            result["account_status"] = EnvatoScraper.get_account_status()
        return jsonify(result)

@app.route("/api/envato-batch-add", methods=["POST"])
def api_envato_batch_add():
    data = request.json or {}
    accounts = data.get("accounts", [])
    if not accounts:
        return jsonify({"success": False, "error": "Account list is empty"}), 400
    result = batch_add_envato_accounts(accounts)
    result["account_status"] = EnvatoScraper.get_account_status()
    return jsonify(result)

@app.route("/api/envato-verify-all", methods=["POST"])
def api_envato_verify_all():
    data = request.json or {}
    custom_accounts = data.get("accounts") if isinstance(data.get("accounts"), list) and len(data.get("accounts")) > 0 else None
    result = verify_all_envato_accounts(custom_accounts)
    status = EnvatoScraper.get_account_status()
    result["status"] = status
    result["account_status"] = status
    return jsonify(result)

@app.route("/api/envato-verify", methods=["POST"])
def api_envato_verify_single():
    data = request.json or {}
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    if not email:
        return jsonify({"success": False, "error": "Email is required"}), 400
    
    if not password:
        accounts = _load_envato_accounts()
        for a in accounts:
            if a.get("email", "").lower() == email.lower():
                password = a.get("password", "")
                break
                
    if not password:
        return jsonify({"success": False, "error": "Password not found for account"}), 400

    ok, msg, credits = test_envato_login(email, password, check_credits=True)
    
    accounts = _load_envato_accounts()
    updated = False
    for a in accounts:
        if a.get("email", "").lower() == email.lower():
            a["verified"] = ok
            a["credits"] = credits
            a["remaining_daily"] = credits
            a["rate_limited"] = (credits == 0)
            a["status"] = "Ready" if (ok and credits > 0) else ("Quota Limit Reached (0/2)" if ok else "Invalid credentials")
            updated = True
            break
    if updated:
        _save_envato_accounts(accounts)

    return jsonify({
        "success": ok,
        "message": msg,
        "verified": ok,
        "credits": credits,
        "remaining_daily": credits,
        "rate_limited": (credits == 0),
        "status": "Ready" if (ok and credits > 0) else ("Quota Limit Reached (0/2)" if ok else "Invalid credentials"),
        "account_status": EnvatoScraper.get_account_status()
    })

@app.route("/api/vault-stats", methods=["GET"])
def api_vault_stats():
    items = load_vault()
    freepik_count = sum(1 for x in items if x.get("platform") == "freepik")
    envato_count = sum(1 for x in items if x.get("platform") == "envato")
    return jsonify({
        "success": True,
        "total_items": len(items),
        "freepik_items": freepik_count,
        "envato_items": envato_count
    })

@app.route("/api/vault-items", methods=["GET"])
def api_vault_items():
    items = load_vault()
    return jsonify({"success": True, "items": items, "count": len(items)})

@app.route("/api/vault-clear", methods=["POST"])
def api_vault_clear():
    save_vault([])
    return jsonify({"success": True, "message": "Vault cache cleared successfully."})

@app.route("/api/sync-pool-vault", methods=["POST"])
def api_sync_pool_vault():
    res = sync_all_accounts_history()
    return jsonify(res)


@app.route("/api/proxy-settings", methods=["GET", "POST"])
def api_proxy_settings():
    if request.method == "GET":
        settings = load_proxy_settings()
        ip_info = get_current_ip_info()
        return jsonify({"success": True, "settings": settings, "ip_info": ip_info})
    
    data = request.json or {}
    success = save_proxy_settings(data)
    return jsonify({"success": success, "settings": load_proxy_settings()})

@app.route("/api/proxy-test", methods=["POST"])
def api_proxy_test():
    data = request.json or {}
    proxy_str = data.get("proxy", "").strip()
    if proxy_str:
        result = test_single_proxy(proxy_str)
        return jsonify({"success": True, "result": result})
    else:
        results = test_all_proxies()
        return jsonify({"success": True, "results": results})

@app.route("/api/current-ip", methods=["GET"])
def api_current_ip():
    return jsonify(get_current_ip_info())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"[ArchNodes] Engine running on http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
