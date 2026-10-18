# 👻 GhostReels Studio

**GhostReels** is a fully autonomous, 24/7 Faceless Video Generation Pipeline designed to run on Android (via Termux) or Linux. It takes a topic, writes a cinematic script, generates images, creates a realistic AI voiceover, edits the video with motion, burns subtitles, and packages it with SEO titles & thumbnails — completely hands-free.

## ✨ Features
- **Multi-Niche Support:** Switch between Dark Psychology, True Crime, Finance, etc.
- **100% Automated:** Runs in a loop. Wake up to new videos every day.
- **Crash-Resume:** If the phone restarts or network drops, it resumes exactly where it left off.
- **Thermal & RAM Safe:** Automatically pauses if the phone gets too hot.
- **SEO Ready:** Generates viral titles, descriptions, hashtags, and custom thumbnails.

---

## 🛠️ Prerequisites
1. An Android Phone (8GB RAM recommended) OR a Linux VPS.
2. **Termux App:** Download from F-Droid (Do NOT use Play Store version).
3. 4 Free API Keys (Instructions below).

---

## 🔑 Step 1: Get Your API Keys
You need to create 4 free accounts to get API keys. Copy these keys, you will need them during installation.

1. **Groq (For Script Writing):** Go to console.groq.com -> Sign Up -> API Keys -> Create Key.
2. **Gemini (Fallback for Script):** Go to aistudio.google.com -> Get API Key -> Create Key.
3. **NVIDIA (Fallback for Script):** Go to build.nvidia.com -> Sign Up -> Get API Key.
4. **Agnes AI (For Image Generation):** Go to platform.agnes-ai.com -> Sign Up -> Create Secret Key.

---

## 🚀 Step 2: Installation (1 Command)

Open Termux and paste the following commands. The installer will automatically ask for the 4 API keys you just created.

```bash
pkg update -y && pkg install git -y
git clone https://github.com/harshitojha880-arch/GhostReels.git
cd GhostReels
bash install.sh
