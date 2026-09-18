# ArchNodes

**ArchNodes** is a high-performance digital asset resolution engine and multi-account pool manager for creative platforms (including Freepik and Envato Elements). It provides direct high-speed asset resolution, multi-account quota rotation, integrated DNS-over-HTTPS (DoH) routing, and persistent cloud vault storage.

---

## Features

- **Studio Asset Resolver**: Extract and stream full-resolution media assets directly without browser extensions or manual scraping friction.
- **Multi-Account Quota Rotation**: Automatically balances download quotas across configured Freepik and Envato account pools with cooldown protection and status monitoring.
- **Integrated DNS-over-HTTPS (DoH)**: Built-in encrypted DNS resolution supporting Cloudflare, Google, Quad9, and AdGuard DNS to bypass ISP censorship and regional filtering.
- **Proxy Pool Management**: Supports HTTP and SOCKS5 proxy lists with live latency ping testing, automatic fallback, and user-agent randomization.
- **Persistent Cloud Vault**: Synchronize extracted assets with permanent Google Drive cloud storage backups for durable access.
- **Modern Bento UI**: Built with a sleek glassmorphic interface, dark/light mode toggle, custom confirmation modals, and responsive layout.

---

## Tech Stack

- **Backend**: Python 3.10+, Flask, Requests, Cloudscraper, Beautiful Soup 4, Gunicorn
- **Frontend**: Vanilla HTML5, Modern CSS Design System (Glassmorphism & Bento UI), Vanilla JavaScript
- **Security & Privacy**: Client-side memory pools, local session storage, encrypted DoH querying

---

## Project Structure

```text
ArchNodes/
├── app.py                      # Main Flask application & API routes
├── requirements.txt            # Python dependencies
├── core/
│   ├── bypass.py               # DNS-over-HTTPS (DoH) resolution engine
│   ├── downloader.py           # Stream downloader & media pipeline
│   ├── normalizer.py           # URL canonicalization & platform detector
│   └── proxy_manager.py        # Proxy rotator, ping tester, & UA header engine
├── scrapers/
│   ├── base.py                 # Base scraper abstraction
│   ├── envato.py               # Envato Elements resolver & account pool manager
│   ├── freepik.py              # Freepik resolver & token pool manager
│   └── vault.py                # Cloud Vault cache & GDrive sync engine
├── static/
│   ├── logo.png                # App branding logo
│   └── favicon.png             # Browser favicon
├── templates/
│   └── index.html              # Main application single-page interface
├── .env.example                # Sample environment configuration
├── accounts.example.json       # Sample Freepik account pool structure
├── envato_accounts.example.json# Sample Envato account pool structure
├── .gitignore                  # Sensitive credential & cache exclusion
└── LICENSE                     # GNU General Public License v3.0
```

---

## Getting Started

### Prerequisites

- **Python 3.10** or higher
- **pip** package manager

### 1. Clone the Repository

```bash
git clone https://github.com/MyusiZ3/ArchNodes.git
cd ArchNodes
```

### 2. Create and Activate a Virtual Environment

```bash
# Linux / macOS
python3 -m venv venv
source venv/bin/activate

# Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configuration

Copy the example configuration files:

```bash
# Environment variables (Optional)
cp .env.example .env

# Freepik Account Pool (Optional)
cp accounts.example.json accounts.json

# Envato Account Pool (Optional)
cp envato_accounts.example.json envato_accounts.json
```

---

## Running the Application

### Development Server

```bash
python app.py
```

Once running, open your web browser and navigate to:
```text
http://127.0.0.1:5050
```

### Production Deployment (Gunicorn / Linux VPS)

```bash
gunicorn -w 4 -b 0.0.0.0:5050 app:app
```

---

## Usage Guide

1. **Extracting Assets (Studio)**:
   - Navigate to the **Studio** tab.
   - Paste a supported asset URL (Freepik or Envato Elements).
   - Click **Extract** to resolve the download streams and metadata.
2. **Accessing Vault (History)**:
   - Switch to the **History** tab to view your current session downloads.
   - Click **Cloud Pool Vault** to view permanent assets backed up to Google Drive.
3. **Bypassing ISP Restrictions (Network)**:
   - Open the **Network** tab to toggle DNS-over-HTTPS (DoH) providers (Cloudflare, Google, Quad9).
   - Paste your proxy list into the **Proxy Pool** box and click **Test & Ping Proxies** to verify online latency.
4. **Managing Account Pools (Accounts)**:
   - Add new session cookies or accounts under the **Accounts** tab to distribute quotas evenly.

---

## Disclaimer & Legal Notice

> **IMPORTANT**: This software is developed strictly for educational, research, and personal workflow automation purposes.
>
> - ArchNodes is **not affiliated with, endorsed by, or associated with** Freepik Company S.L., Envato Pty Ltd, or any third-party asset providers.
> - Users are solely responsible for ensuring that their usage complies with all applicable laws, terms of service, and licensing agreements of the respective third-party platforms.
> - The developers and contributors assume **no liability** for any account bans, data loss, rate limiting, or damages arising from the use of this software.

---

## License

This project is licensed under the **GNU General Public License v3.0 (GPL-3.0)**.

- You are free to run, study, and modify the software.
- If you distribute or convey modified versions of this software, you **must** provide the complete corresponding source code under the same GPL-3.0 license and preserve the original copyright notices.
- See the [LICENSE](LICENSE) file for complete terms and conditions.

**Author**: Muhamad Sidik ([@MyusiZ3](https://github.com/MyusiZ3))  
**Contact**: [muhamadsidik.work.id@gmail.com](mailto:muhamadsidik.work.id@gmail.com)
