import re
from typing import Tuple

def normalize_profile_url(url: str) -> Tuple[str, str, str]:
    if not url or not isinstance(url, str):
        return "", "", ""
        
    clean_url = url.strip()
    clean_url = re.sub(r'[\r\n\t]+', '', clean_url)
    clean_url = clean_url.strip('"\'')
    
    # Strip hash fragments
    clean_url = clean_url.split('#')[0].strip()
    
    if clean_url.startswith("http://"):
        clean_url = "https://" + clean_url[7:]
    elif not clean_url.startswith("https://"):
        clean_url = "https://" + clean_url
        
    url_lower = clean_url.lower()

    # 1. Freepik / Magnific AI
    if "freepik.com" in url_lower or "magnific.ai" in url_lower or "magnific.com" in url_lower:
        if "magnific.com" in clean_url:
            clean_url = clean_url.replace("www.magnific.com", "www.freepik.com").replace("magnific.com", "freepik.com")
        elif "magnific.ai" in clean_url:
            clean_url = clean_url.replace("www.magnific.ai", "www.freepik.com").replace("magnific.ai", "freepik.com")

        # Strip query parameters for freepik htm URLs
        if ".htm" in clean_url:
            clean_url = clean_url.split('?')[0]

        match = re.search(r'freepik\.com/(?:[^/]+/)?(?:free-|premium-)?(?:photo|vector|psd|icon|video|ai-image|template)?/?([a-zA-Z0-9_-]+)_(\d+)', clean_url)
        if match:
            slug = match.group(1).replace('-', '_')
            asset_id = match.group(2)
            asset_name = f"freepik_{slug[:40]}_{asset_id}"
        else:
            match_id = re.search(r'[_-](\d{6,})', clean_url)
            asset_id = match_id.group(1) if match_id else "asset"
            asset_name = f"freepik_{asset_id}"

        return clean_url, asset_name, "freepik"

    # 2. Envato Elements
    if "elements.envato.com" in url_lower:
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

    domain_match = re.search(r'https?://(?:www\.)?([^/]+)', clean_url)
    domain = domain_match.group(1).split('.')[0] if domain_match else "asset"
    return clean_url, f"{domain}_asset", domain

def extract_thumbnail_url(url: str, platform: str = "") -> str:
    """Extract CDN thumbnail image URL for platforms like Freepik or direct images"""
    if not url or not isinstance(url, str):
        return ""
    clean_url = url.strip().split('#')[0].split('?')[0].rstrip('/')
    url_lower = clean_url.lower()

    # Freepik / Magnific AI
    if "freepik.com" in url_lower or platform == "freepik":
        m = re.search(r'freepik\.com/(?:[a-z]{2}(?:-[a-z]{2})?/)?([^/]+)/([^/?#]+)', clean_url, re.I)
        if m:
            cat = m.group(1)
            slug_id = m.group(2)
            if slug_id.lower().endswith('.htm'):
                slug_id = slug_id[:-4]
            return f"https://img.freepik.com/{cat}/{slug_id}.jpg?w=740"

    # Direct image URL
    if re.search(r'\.(png|jpe?g|webp|gif|avif)$', clean_url, re.I):
        return clean_url

    return ""
