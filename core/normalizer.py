"""
ArchNodes - URL Normalizer & Platform Classifier
Exclusively processes and classifies creative assets and design stock platforms.
"""

import re
from typing import Tuple

def normalize_profile_url(url: str) -> Tuple[str, str, str]:
    """
    Normalizes a creative asset URL and extracts (normalized_url, asset_name, platform).
    Returns (url, asset_name, platform) on success or ("", "", "") if unsupported.
    """
    if not url or not isinstance(url, str):
        return "", "", ""
        
    clean_url = url.strip()
    clean_url = re.sub(r'[\r\n\t]+', '', clean_url)
    clean_url = clean_url.strip('"\'')
    
    if clean_url.startswith("http://"):
        clean_url = "https://" + clean_url[7:]
    elif not clean_url.startswith("https://"):
        clean_url = "https://" + clean_url
        
    url_lower = clean_url.lower()

    # 1. Freepik / Magnific AI
    if "freepik.com" in url_lower:
        match = re.search(r'freepik\.com/(?:[^/]+/)?(?:free-|premium-)?(?:photo|vector|psd|icon|video|ai-image|template)?[^/]*_(\d+)', clean_url)
        if not match:
            match = re.search(r'freepik\.com/.*[_-](\d{6,})', clean_url)
        asset_id = match.group(1) if match else "freepik_asset"
        return clean_url, f"freepik_{asset_id}", "freepik"

    if "magnific.ai" in url_lower or "magnific.com" in url_lower:
        return clean_url, "magnific_ai_asset", "freepik"

    # 2. Envato Elements
    if "elements.envato.com" in url_lower:
        # e.g. https://elements.envato.com/clean-modern-corporate-presentation-ABC1234
        slug_match = re.search(r'elements\.envato\.com/([^/?#]+)', clean_url)
        slug = slug_match.group(1) if slug_match else "envato_asset"
        slug_clean = re.sub(r'[^a-zA-Z0-9_-]', '_', slug)[:60]
        return clean_url, f"envato_{slug_clean}", "envato"

    # 3. Motion Array
    if "motionarray.com" in url_lower:
        slug_match = re.search(r'motionarray\.com/[^/]+/([^/?#]+)', clean_url)
        slug = slug_match.group(1) if slug_match else "motionarray_asset"
        slug_clean = re.sub(r'[^a-zA-Z0-9_-]', '_', slug)[:60]
        return clean_url, f"motionarray_{slug_clean}", "motionarray"

    # 4. Vecteezy
    if "vecteezy.com" in url_lower:
        slug_match = re.search(r'vecteezy\.com/[^/]+/([^/?#]+)', clean_url)
        slug = slug_match.group(1) if slug_match else "vecteezy_asset"
        slug_clean = re.sub(r'[^a-zA-Z0-9_-]', '_', slug)[:60]
        return clean_url, f"vecteezy_{slug_clean}", "vecteezy"

    # 5. Shutterstock
    if "shutterstock.com" in url_lower:
        match = re.search(r'shutterstock\.com/(?:[^/]+/)?(?:image-photo|image-vector|video|image-illustration)/[^/?#]+-(\d+)', clean_url)
        asset_id = match.group(1) if match else "shutterstock_asset"
        return clean_url, f"shutterstock_{asset_id}", "shutterstock"

    # Default fallback for generic creative URLs
    domain_match = re.search(r'https?://(?:www\.)?([^/]+)', clean_url)
    domain = domain_match.group(1).split('.')[0] if domain_match else "asset"
    return clean_url, f"{domain}_asset", domain
