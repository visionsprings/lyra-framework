# lyra-framework
A local, persistent, embodied AI companion framework (non-commercial)
# Lyra Framework

A local, persistent, embodied AI companion framework.

**Non-commercial, personal, and research use only** — see [LICENSE](#license) for details.

## Current Status (January 2026)

This is a **working, local-only** AI companion system built around a 4-bit quantized Mistral-7B-Instruct-v0.2 model.

### What's Working
- **Local web chat interface** (Flask) at http://127.0.0.1:5001
- **GPU-accelerated inference** (RTX 3090/4090 optimized, ~12–14GB VRAM)
- **SQLite persistence** — all messages saved with timestamps
- **Emotion analysis** — quantized RoBERTa model running on separate FastAPI server (auto-started)
- **Robust file-based IPC** using `message.json` + portalocker
- **Database manager** — full table view + row delete at `/db-manager`
- **Chat history loading** — last 10 messages on page load
- **Clean, responsive UI** with fade effect for older messages

### Architecture
- `app.py` — Flask web server + orchestrator
- `inference_engine.py` — pure model loading and generation
- `distilbert_emotion_server.py` — emotion analysis (FastAPI)
- `db.py` — SQLite wrapper
- `templates/chat.html` — main chat interface
- `templates/db_manager.html` — database inspection tool

### Planned / In Progress
- Full prompt builder with:
  - Core identity injection
  - Situated awareness (world state, body, time)
  - Long-term memory activation
  - Hormonal/physiological influence
- Persistent world simulation
- Internal thinking, dreaming, diary
- Value system drift

## Quick Start

```bash
# Clone and enter
git clone https://github.com/visionsprings/lyra-framework.git
cd lyra-framework

# Create and activate venv
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run
python app.py


Open http://127.0.0.1:5001 in your browser.
Hardware Requirements

NVIDIA GPU with ≥24GB VRAM (3090/4090 recommended)
32GB+ system RAM
Linux (WSL2 works perfectly)

License
This project is released under the Hippocratic License — allowing free personal, educational, and research use, but prohibiting commercial exploitation without explicit permission.
See LICENSE for full terms.
Contributing
This is a personal passion project. Contributions are welcome via issues and pull requests, but the core vision remains non-commercial.
Built with care — for depth, continuity, and privacy.
— Paul (visionsprings)