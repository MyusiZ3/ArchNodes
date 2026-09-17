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
from core.downloader import get_download_progress, stop_download
from scrapers.base import fetch_media_stream, HEADERS_FOR_REQUESTS
from scrapers.freepik import (
    FreepikScraper,
    add_account,
    remove_account,
    batch_add_accounts,
    auto_register_account,
    FreepikRateLimitException
)
from scrapers.envato import (
    get_envato_info,
    EnvatoScraper,
    add_account as add_envato_account,
    remove_account as remove_envato_account,
    batch_add_accounts as batch_add_envato_accounts,
    verify_all_accounts as verify_all_envato_accounts,
    auto_register_account as auto_register_envato_account,
    test_envato_login
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

    try:
        scraper_fp = FreepikScraper()
        gdrive_link = scraper_fp.extract_gdrive_url(url, custom_accounts=custom_accounts)
        return jsonify({
            "success": True,
            "download_url": gdrive_link,
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
            scraper_fp = FreepikScraper()
            gdrive_link = scraper_fp.extract_gdrive_url(profile_url)
            if request.args.get("mode") == "json":
                return jsonify({"success": True, "download_url": gdrive_link})
            return redirect(gdrive_link)
        except Exception as e:
            return f"<h2>Freepik Resolution Error</h2><p>{str(e)}</p>", 500

    if platform == "envato":
        info, err = get_envato_info(profile_url)
        if not info or not info.get("items"):
            return err or "Asset not found", 404
        items = info["items"]
        target_idx = (index - 1) if (0 <= index - 1 < len(items)) else 0
        target_item = items[target_idx]
        target_url = target_item["src"]
        file_type = target_item["type"]
        ext = "mp4" if file_type == "video" else "mp3" if file_type == "audio" else "jpg"
        filename = f"{asset_name}_{index}.{ext}"
        
        req_headers = dict(HEADERS_FOR_REQUESTS)
        req_headers["Referer"] = "https://elements.envato.com/"
        r_stream = fetch_media_stream(target_url, req_headers)
        if r_stream.status_code in [200, 206]:
            res_headers = {
                "Content-Type": r_stream.headers.get("Content-Type", "application/octet-stream"),
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Access-Control-Allow-Origin": "*"
            }
            return Response(r_stream.iter_content(chunk_size=262144), status=r_stream.status_code, headers=res_headers)
        return "Failed to stream media from Envato CDN", 502

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

    try:
        scraper_env = EnvatoScraper()
        gdrive_link = scraper_env.extract_gdrive_url(url, custom_accounts=custom_accounts)
        return jsonify({
            "success": True,
            "download_url": gdrive_link
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


@app.route("/api/envato-auto-register", methods=["POST"])
def api_envato_auto_register():
    result = auto_register_envato_account()
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
    result = verify_all_envato_accounts()
    result["account_status"] = EnvatoScraper.get_account_status()
    return jsonify(result)

@app.route("/api/envato-verify", methods=["POST"])
def api_envato_verify_single():
    data = request.json or {}
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    if not email or not password:
        return jsonify({"success": False, "error": "Email and password are required"}), 400
    ok, msg = test_envato_login(email, password)
    return jsonify({"success": ok, "message": msg, "verified": ok})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"[ArchNodes] Engine running on http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
