# ArchNodes

> **The Ultimate Creative & Stock Assets Downloader**  
> High-speed premium asset bypass and extractor for designers, video editors, and agencies.

---

## ✨ Features

- **Freepik & Magnific AI Bypass**: Direct Google Drive downloads with smart multi-account rotation and rate-limit cooldown handling.
- **Envato Elements Resolver**: Extract stock video footage, template previews, audio tracks, and graphic elements.
- **100% SFW & Hosting Ready**: Zero adult content, zero risk of hosting TOS bans (safe for Vercel, Render, Railway, HuggingFace, VPS).
- **Client-Side Account Security**: Accounts are stored in the user's local browser cache (`localStorage`) with JSON backup/restore, ensuring zero credential leaks on public servers.
- **Integrated DNS-over-HTTPS (DoH)**: Built-in Cloudflare, Google, AdGuard, and Quad9 anti-block bypass engine.
- **Modern Glassmorphism UI**: High-end responsive interface with dark/light mode and download history.

---

## 🚀 Quick Start (Local Run)

1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start ArchNodes:**
   ```bash
   python app.py
   ```

3. **Open Browser:**
   Navigate to `http://127.0.0.1:5050`

---

## ☁️ Deployment Guide

### Deploy on Render / Railway / VPS:
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT`

---

## 📄 License
MIT License © 2026 ArchNodes Team
