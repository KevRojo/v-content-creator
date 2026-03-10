# 🎬 V-Content Creator

**AI-powered viral video content factory** — Generate narrated story videos with AI text, AI voice, AI images, and automatic editing. One command, full video.

<p align="center">
  <img src="https://img.shields.io/badge/python-3.9+-blue" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey" alt="Platform">
</p>

## ✨ What it does

```
Idea → AI Story → AI Voice → AI Images → Subtitles → Final Video
```

V-Content Creator automates the **entire** video production pipeline:

1. **📝 Story Generation** — AI writes viral stories with hooks, escalation, and twists (Gemini or Moonshot/Kimi)
2. **🎙️ Voice Narration** — Natural TTS voice (Gemini TTS or ElevenLabs)
3. **🖼️ Scene Images** — AI-generated images synced to the narration (SDXL local GPU or Gemini Web)
4. **📝 Subtitles** — Automatic transcription with faster-whisper
5. **🎬 Video Assembly** — FFmpeg with zoompan effects, per-image timing from AI timestamps
6. **📊 YouTube Metadata** — Auto-generated title, description, tags, and SEO

## 🎯 Content Niches

Built-in viral content templates:

| Niche | Style |
|-------|-------|
| 🔍 Misterio Real | True Crime, investigative |
| 🤫 Confesiones | Intimate, confessional |
| 😱 Suspenso Cotidiano | Everyday situations gone wrong |
| 🤖 Ciencia Ficción | Black Mirror-style sci-fi |
| 💔 Drama Humano | Emotional storytelling |
| 🧠 Terror Psicológico | Psychological horror |
| 🌿 Folklore Latam | Latin American legends |
| ⚖️ Venganza | Revenge / poetic justice |
| 🏔️ Supervivencia | Survival stories |
| 💻 Misterio Digital | Internet creepy |

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/YOUR_USERNAME/v-content-creator.git
cd v-content-creator
pip install -r requirements.txt
```

### 2. Configure API Keys

```bash
cp .env.example .env
# Edit .env with your API keys
```

**Required:** At least one of:
- `GEMINI_API_KEY` — [Get it here](https://aistudio.google.com/apikey) (free tier available)
- `MOONSHOT_API_KEY` — [Get it here](https://platform.moonshot.cn/)

**Optional:**
- `ELEVENLABS_API_KEY` — For premium voice quality
- `CHANNEL_NAME` — Your channel name for metadata

### 3. Install FFmpeg

FFmpeg is required for video assembly:

- **Windows:** `winget install ffmpeg` or download from [ffmpeg.org](https://ffmpeg.org/download.html)
- **Linux:** `sudo apt install ffmpeg`
- **Mac:** `brew install ffmpeg`

### 4. Generate a Video

```bash
# Basic — auto niche, auto duration
python vcontent_creator.py

# Specify a niche and duration
python vcontent_creator.py --niche terror_psicologico --duration 3

# Short format (9:16 vertical, 60s)
python vcontent_creator.py --short

# Use ElevenLabs voice
python vcontent_creator.py --eleven

# Full control
python vcontent_creator.py --count 3 --niche venganza --duration 5 --voice Fenrir --quality high
```

### 5. GUI Mode (optional)

```bash
pip install PyQt5
python gui.py
```

## 🖼️ Image Generation Options

### Option A: SDXL Local (GPU required)

Requires an NVIDIA GPU with ~8GB VRAM.

```bash
pip install torch diffusers transformers accelerate
```

Download an SDXL model and place it in:
```
stable-diffusion-webui-master/models/Stable-diffusion/
```

**Recommended models** (download one):

| Model | Type | Link |
|-------|------|------|
| RealVisXL V5.0 Baked VAE | Photorealistic (best) | [CivitAI](https://civitai.com/models/139562/realvisxl-v50) |
| RealVisXL V5.0 Lightning | Fast photorealistic | [CivitAI](https://civitai.com/models/139562/realvisxl-v50) |
| Juggernaut XL v11 | Multi-purpose premium | [CivitAI](https://civitai.com/models/133005/juggernaut-xl) |
| SDXL Base 1.0 | Official base | [HuggingFace](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0) |

### Option B: Gemini Web (no GPU needed)

Uses your Gemini Premium subscription via browser automation:

```bash
pip install playwright
playwright install chromium
python vcontent_creator.py --gemini-images
```

## ⚙️ CLI Reference

| Flag | Description |
|------|-------------|
| `--count N` | Number of stories to generate (default: 1) |
| `--niche NAME` | Content niche (use `--list-niches` to see all) |
| `--duration N` | Target duration in minutes |
| `--voice NAME` | TTS voice: Charon, Fenrir, Kore, Orus, etc. |
| `--quality LEVEL` | Video quality: high, medium, low, minimal |
| `--short` | Short format (9:16 vertical, ≤60s) |
| `--model ENGINE` | Text model: gemini (default) or kimi |
| `--eleven` | Use ElevenLabs TTS instead of Gemini |
| `--gemini-images` | Use Gemini Web for image generation |
| `--gemini-web-story` | Use Gemini Web for story generation |
| `--list-niches` | Show all available niches |
| `--context TEXT` | Creative direction for the story |

## 📁 Project Structure

```
v-content-creator/
├── vcontent_creator.py    # Main engine (text → audio → images → video)
├── gui.py                 # PyQt5 GUI (optional)
├── .env                   # Your API keys (not tracked by git)
├── .env.example           # Template for API keys
├── requirements.txt       # Python dependencies
├── sounds/                # SFX audio files (rain, steps, door)
├── stable-diffusion-webui-master/
│   └── models/
│       └── Stable-diffusion/  # Place SDXL .safetensors models here
├── output/                # Generated videos (auto-created)
└── temp/                  # Working files (auto-created)
```

## 🔧 How It Works

1. **Story Generation** — The AI receives a detailed prompt with the selected niche's tone, hooks, clichés to avoid, and format rules. It generates the story AND image prompts with timestamps.

2. **Audio** — The story text is split into chunks, synthesized with TTS, and crossfaded into a seamless narration.

3. **Images** — Each image prompt is generated with a specific timestamp (e.g., `IMG1 0:00`, `IMG2 0:12`). Images are resized to match the video format.

4. **Video Assembly** — Each image becomes a clip with its own zoompan animation matching its specific duration from the AI timestamps. Clips are concatenated with the audio and burned-in subtitles.

## 📄 License

MIT License — use it, modify it, share it.

## 🤝 Contributing

Pull requests welcome! Areas that could use help:
- More content niches
- Support for more TTS engines
- Multi-language support
- Thumbnail generation
- Auto-upload to YouTube/TikTok
