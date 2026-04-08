# Infoglut

An interactive art installation where audience messages are projected onto physical surfaces in real time, with AI-generated reactions and Arduino-controlled pneumatic responses.

> **Platform: macOS / Windows.** Use `start.sh` on macOS and `start.bat` on Windows.

## Architecture

```
Audience (phone) → Flask Server (server.py) → UDP → Projector × 2 (projector.py)
                                             ↓
                                         Arduino (pump / valve)
                                             ↓
                                         AI thought (GPT-4o-mini)
```

- **server.py** — Flask web server (port 8080). Receives audience text, classifies it (normal / harmful), sends UDP messages to both projectors, triggers the Arduino, and generates an AI reaction.
- **projector.py** — Pygame fullscreen display. Receives UDP messages and renders floating text on a Coons-patch warped surface. Run one instance per projector.
- **tunnel_qr.py** — Opens a Cloudflare tunnel to expose the local server, then generates and opens a QR code for audience access.

## Environment Setup

### 1. Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.11+ | 3.14 used in development |
| Node.js | 18+ | Required for `npx cloudflared` |
| Arduino IDE | any | Only needed to flash the firmware |

**macOS** — install via [Homebrew](https://brew.sh)

```bash
brew install python node
```

**Windows** — install via [winget](https://learn.microsoft.com/en-us/windows/package-manager/)

```powershell
winget install Python.Python.3 OpenJS.NodeJS
```

---

### 2. Python virtual environment

**macOS**
```bash
cd /path/to/Infoglut
python3 -m venv venv
source venv/bin/activate
```

**Windows**
```powershell
cd C:\path\to\Infoglut
python -m venv venv
venv\Scripts\activate
```

> Every time you open a new terminal, activate the venv before starting the project.

---

### 3. Install Python dependencies

```bash
pip install flask pygame-ce numpy pyserial openai python-dotenv safetext
```

Key packages:

| Package | Purpose |
|---------|---------|
| `flask` | Web server for audience input page |
| `pygame-ce` | Projector rendering (community edition) |
| `numpy` | Coons-patch surface math |
| `pyserial` | Arduino serial communication |
| `openai` | GPT-4o-mini AI reactions |
| `python-dotenv` | Load `.env` config |
| `safetext` | English profanity detection |

---

### 4. Cloudflare tunnel

```bash
# Install once globally (requires Node.js)
npm install -g cloudflared

# Verify
cloudflared --version
```

If `npx cloudflared` fails, you can also install the binary directly from [cloudflare.com/products/tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).

---

### 5. OpenAI API key

Create a `.env` file in the project root:

**macOS**
```bash
echo "OPENAI_API_KEY=sk-..." > .env
```

**Windows**
```powershell
"OPENAI_API_KEY=sk-..." | Out-File .env -Encoding utf8
```

Or just create `.env` manually with any text editor and paste in:
```
OPENAI_API_KEY=sk-...
```

Without this key the server still works — AI reactions fall back to `"I kept thinking about that."`.

---

### 6. Arduino

- Connect the Arduino via USB before starting the server.
- The port is detected automatically (looks for `usbmodem` or `arduino` in port descriptions).
- If detection fails, the server logs all available ports at startup — update `find_arduino_port()` in `server.py` if needed.
- Baud rate: **9600**

---

### 7. First run

**macOS**
```bash
chmod +x start.sh
source venv/bin/activate
./start.sh
```
Opens four Terminal tabs automatically via AppleScript.

**Windows**
```powershell
venv\Scripts\activate
start.bat
```
Opens four Command Prompt windows automatically.

---

## Quick Start

**macOS**
```bash
source venv/bin/activate
python3 projector.py 12345   # Terminal 1 — Projector 1
python3 projector.py 12346   # Terminal 2 — Projector 2
python3 server.py            # Terminal 3 — Server
python3 tunnel_qr.py         # Terminal 4 — Tunnel + QR code
```

**Windows**
```powershell
venv\Scripts\activate
python projector.py 12345    # Terminal 1 — Projector 1
python projector.py 12346    # Terminal 2 — Projector 2
python server.py             # Terminal 3 — Server
python tunnel_qr.py          # Terminal 4 — Tunnel + QR code
```

Audience scans the QR code that pops up and opens the input page on their phone.

Arduino is detected automatically. If not found, messages are still projected but no physical response occurs.

## Projector Controls

| Key | Action |
|-----|--------|
| `F` | Toggle fullscreen / windowed |
| `C` | Show / hide editor overlay |
| `S` | Print current control point coordinates |
| `H` | Horizontal mirror |
| `V` | Vertical mirror |
| `[` / `]` | Increase / decrease strip width (precision vs. CPU) |
| `ESC` | Quit |

Drag the blue control points in the editor overlay to warp the projected image to fit your physical surface.

## Message Behavior

- **Normal message** → white floating text on a random projector + pump pulse (duration scales with message length)
- **Harmful message** → red shaking text + valve release (longer for longer messages)
- **AI reaction** → GPT-4o-mini generates a blunt, short response displayed in the "THOUGHT" box on both projectors

---

© 2026 Yijie Ding. All rights reserved.
For viewing purposes only. Not for reuse or distribution.

