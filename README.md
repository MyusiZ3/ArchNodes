# ArchNodes

Creative asset extraction and downloader tool for digital designers, video editors, and production workflows.

---

## Overview

ArchNodes provides a streamlined interface to extract, resolve, and download media assets from creative asset platforms (including Freepik and Envato Elements) with high-speed streaming and multi-account pool rotation.

### Key Capabilities

- **Freepik & Magnific Integration**: Multi-account pool rotation with automatic rate-limit cooldown handling.
- **Envato Elements Resolver**: Metadata extraction, video footage streams, preview images, and audio tracks.
- **Zero Server-Side Storage**: User accounts and credentials reside exclusively in the client browser (`localStorage`), eliminating credential exposure on public deployments.
- **Integrated DNS-over-HTTPS (DoH)**: Built-in DNS resolution support (Cloudflare, Google, AdGuard, Quad9) and proxy routing.
- **Modern Interface**: Clean, lightweight web interface with responsive layout, dark/light theme, and local history tracking.

---

## Quick Start

### Prerequisites
- Python 3.9 or higher

### Installation

```bash
# Clone the repository
git clone https://github.com/your-username/ArchNodes.git
cd ArchNodes

# Install dependencies
pip install -r requirements.txt
```

### Running Locally

```bash
python app.py
```

Open your browser and navigate to: `http://127.0.0.1:5050`

---

## Production Deployment

### Standard WSGI (Gunicorn / Render / Railway / VPS)

```bash
gunicorn app:app --bind 0.0.0.0:$PORT --workers 4
```

### Environment Variables

| Variable | Description | Default |
|---|---|---|
| `PORT` | Web server listening port | `5050` |
| `SECRET_KEY` | Flask session signing secret | `archnodes-default-secret` |

---

## License

MIT License - see the LICENSE file for details.
