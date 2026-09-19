"""
ArchNodes - IMAP Email Auto-Verification Engine
Scans Gmail inbox via IMAP to batch-retrieve and trigger activation links
for Freepik and Envato Downloader platforms.
"""

import imaplib
import email as email_lib
import re
import time
import logging
import cloudscraper
import requests
from typing import Dict, List, Optional
from core.proxy_manager import apply_network_settings

logger = logging.getLogger("archnodes.imap")

def batch_scan_and_activate_gmail_inbox(
    gmail_user: str,
    gmail_app_pass: str,
    platform: str = "all",
    max_scan_count: int = 25,
    timeout_sec: int = 20
) -> Dict:
    """
    Connects to Gmail IMAP, finds verification emails from freepikdownloader.com / envato-downloader.com,
    extracts confirmation links, executes GET requests to activate them, and returns activation report.
    """
    if not gmail_user or not gmail_app_pass:
        return {"success": False, "error": "Gmail user and Google App Password are required"}

    # Clean up app password (remove spaces)
    clean_pass = gmail_app_pass.replace(" ", "").strip()
    clean_user = gmail_user.strip()

    activated_items = []
    errors = []

    scraper = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "desktop": True})
    apply_network_settings(scraper)
    scraper.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    })

    mail = None
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(clean_user, clean_pass)
        mail.select("INBOX")

        # Define search queries based on platform
        search_terms = []
        if platform in ["freepik", "all"]:
            search_terms.append('(FROM "freepikdownloader.com")')
            search_terms.append('(BODY "freepikdownloader.com")')
        if platform in ["envato", "all"]:
            search_terms.append('(FROM "envato-downloader.com")')
            search_terms.append('(BODY "envato-downloader.com")')

        all_msg_ids = set()
        for term in search_terms:
            try:
                status, messages = mail.search(None, term)
                if status == "OK" and messages[0]:
                    for mid in messages[0].split():
                        all_msg_ids.add(mid)
            except Exception as e:
                logger.warning(f"IMAP search error with term {term}: {e}")

        # Also search latest 30 unseen emails in case FROM header was rewritten by ISP/provider
        try:
            status, unread_msgs = mail.search(None, "UNSEEN")
            if status == "OK" and unread_msgs[0]:
                for mid in unread_msgs[0].split():
                    all_msg_ids.add(mid)
        except Exception:
            pass

        if not all_msg_ids:
            # Fallback: check last 15 emails in general
            try:
                status, all_msgs = mail.search(None, "ALL")
                if status == "OK" and all_msgs[0]:
                    ids = all_msgs[0].split()
                    for mid in ids[-15:]:
                        all_msg_ids.add(mid)
            except Exception:
                pass

        # Sort message IDs in reverse to process newest first
        sorted_ids = sorted(list(all_msg_ids), key=lambda x: int(x) if x.isdigit() else 0, reverse=True)[:max_scan_count]

        found_links = set()

        for mid in sorted_ids:
            try:
                res_f, data = mail.fetch(mid, "(RFC822)")
                if res_f != "OK" or not data or not data[0]:
                    continue

                raw_email = data[0][1]
                msg = email_lib.message_from_bytes(raw_email)

                # Extract recipient & subject
                recipient = msg.get("To", "")
                subject = msg.get("Subject", "")

                body_content = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        if content_type in ["text/html", "text/plain"]:
                            payload = part.get_payload(decode=True)
                            if payload:
                                body_content += payload.decode(errors="ignore") + "\n"
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body_content = payload.decode(errors="ignore")

                # Look for Freepik & Envato activation URLs
                # Example: https://freepikdownloader.com/activate?token=xxx or https://freepikdownloader.com/confirm?token=xxx
                # Example: https://envato-downloader.com/activate.php?token=xxx or similar
                patterns = [
                    r'https?://freepikdownloader\.com/[^\s"\'<>]+(?:activate|verify|confirm|token)[^\s"\'<>]*',
                    r'https?://envato-downloader\.com/[^\s"\'<>]+(?:activate|verify|confirm|token)[^\s"\'<>]*',
                    r'https?://freepikdownloader\.com/auth/[^\s"\'<>]+',
                    r'https?://envato-downloader\.com/auth/[^\s"\'<>]+'
                ]

                links_in_msg = []
                for pat in patterns:
                    matches = re.findall(pat, body_content, re.IGNORECASE)
                    for m in matches:
                        # Clean HTML entities
                        clean_link = m.replace("&amp;", "&").rstrip(").,;")
                        if clean_link not in found_links:
                            found_links.add(clean_link)
                            links_in_msg.append(clean_link)

                # If no strict keyword match, find all links from the respective domains
                if not links_in_msg:
                    domain_links = re.findall(r'https?://(?:freepikdownloader\.com|envato-downloader\.com)/[^\s"\'<>]+', body_content)
                    for dl in domain_links:
                        clean_link = dl.replace("&amp;", "&").rstrip(").,;")
                        if any(k in clean_link.lower() for k in ["token", "code", "key", "act", "ver", "reg"]) and clean_link not in found_links:
                            found_links.add(clean_link)
                            links_in_msg.append(clean_link)

                # Activate links
                for link in links_in_msg:
                    plat = "freepik" if "freepik" in link else "envato" if "envato" in link else "unknown"
                    try:
                        act_res = scraper.get(link, timeout=12, allow_redirects=True)
                        activated_items.append({
                            "link": link,
                            "platform": plat,
                            "recipient": recipient,
                            "subject": subject,
                            "status_code": act_res.status_code,
                            "activated": act_res.status_code in [200, 302]
                        })
                    except Exception as act_err:
                        activated_items.append({
                            "link": link,
                            "platform": plat,
                            "recipient": recipient,
                            "status_code": 0,
                            "activated": False,
                            "error": str(act_err)
                        })

            except Exception as msg_err:
                errors.append(str(msg_err))

        return {
            "success": True,
            "scanned_count": len(sorted_ids),
            "activated_count": len(activated_items),
            "items": activated_items,
            "errors": errors if errors else None
        }

    except imaplib.IMAP4.error as imap_err:
        err_msg = str(imap_err)
        if "AUTHENTICATIONFAILED" in err_msg.upper() or "INVALID CREDENTIALS" in err_msg.upper():
            return {
                "success": False,
                "error": "Gmail Authentication Failed: Please make sure you are using a 16-character Google App Password (not your regular Gmail password). Generate one at: myaccount.google.com/apppasswords"
            }
        return {"success": False, "error": f"IMAP Error: {err_msg}"}
    except Exception as e:
        return {"success": False, "error": f"Connection Error: {str(e)}"}
    finally:
        if mail:
            try:
                mail.logout()
            except Exception:
                pass
