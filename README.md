👻 GhostReels Studio

Welcome to **GhostReels Studio**, the ultimate 24/7 autonomous Faceless Video Generation Pipeline. 

Designed to run seamlessly on Android (via Termux) or a Linux VPS, GhostReels takes a single topic and handles the entire production line: writing a cinematic script, generating AI images, creating a realistic voiceover, adding cinematic motion, burning perfectly synced subtitles, and packaging it with SEO titles & thumbnails — completely hands-free.

Whether you run a **Dark Psychology** channel, a **True Crime** documentary page, or a **Finance** automation channel, GhostReels builds the videos while you sleep. 

---

## 📑 Table of Contents
1. [Key Features](#-key-features)
2. [Prerequisites](#-prerequisites)
3. [Step 1: Get Your API Keys](#-step-1-get-your-api-keys)
4. [Step 2: Installation](#-step-2-installation)
5. [Step 3: License Activation](#-step-3-license-activation)
6. [Step 4: Running the Factory](#-step-4-running-the-factory)
7. [Understanding the Output](#-understanding-the-output)
8. [Pro-Tips for 24/7 Running](#-pro-tips-for-247-running)
9. [Troubleshooting & FAQ](#-troubleshooting--faq)

---

## ✨ Key Features
- **Multi-Niche Engine:** Choose between Dark Psychology, True Crime, Finance, and more. The AI adapts its tone, script, and visuals to your chosen niche.
- **100% Autonomous:** Runs in an infinite loop. Generates 5-10 high-quality videos daily without human intervention.
- **Crash-Resume Technology:** If your phone dies, restarts, or loses internet, simply restart the system. It resumes exactly where it left off.
- **Thermal & RAM Safe:** Built-in guards pause the pipeline if your device exceeds 45°C, preventing hardware damage.
- **Ultra-Secure Licensing:** Device-locked activation. Your purchase is protected, and the software cannot be copied to other devices.

---

## 🛠️ Prerequisites
Before starting, ensure you have:
1. **Android Phone** (Minimum 4GB RAM recommended) OR a Linux VPS.
2. **Termux App:** Download strictly from [F-Droid](https://f-droid.org/en/packages/com.termux/). *(Do NOT use the Play Store version, as it is outdated and broken).*
3. **Stable Internet:** Required for fetching images, voices, and scripts from the cloud.

---

## 🔑 Step 1: Get Your API Keys (100% Free)

GhostReels uses a smart 4-layer fallback system to ensure you never hit rate limits. You need 4 free keys:

1. **Groq (Primary Script Engine):**
   - Go to [console.groq.com](https://console.groq.com)
   - Sign Up / Login.
   - Go to "API Keys" -> Click "Create API Key".
   - Copy the key (starts with `gsk_...`).

2. **Gemini (Fallback Script Engine):**
   - Go to [aistudio.google.com](https://aistudio.google.com)
   - Click "Get API Key" -> Create API Key.
   - Copy the key (starts with `AIza...` or `AQ...`).

3. **NVIDIA (Secondary Fallback Script):**
   - Go to [build.nvidia.com](https://build.nvidia.com)
   - Sign Up -> Get API Key.
   - Copy the key (starts with `nvapi-...`).

4. **Agnes AI (Image Generator):**
   - Go to [platform.agnes-ai.com](https://platform.agnes-ai.com)
   - Sign Up -> Create Secret Key.
   - Copy the key (starts with `sk-...`).

---

## 🚀 Step 2: Installation

Open Termux and paste the following commands one by one. 

**1. Update Termux and install Git:**
```bash
pkg update -y && pkg install git -y
```

2. Download GhostReels:

```bash
git clone https://github.com/harshitojha880-arch/GhostReels.git
cd GhostReels
```

3. Run the Auto-Installer:

```bash
bash install.sh
```

The installer will automatically download Python, FFmpeg, and all required libraries. It will then ask for your keys one by one:

· Paste GROQ_API_KEY: -> Paste your Groq key, press Enter.
· Paste GEMINI_API_KEY: -> Paste your Gemini key, press Enter.
· Paste NVIDIA_API_KEY: -> Paste your NVIDIA key, press Enter.
· Paste AGNES_API_KEY: -> Paste your Agnes key, press Enter.

The installation is now complete.

---

🎬 Step 3: License Activation

Because GhostReels is premium software, it is locked to your specific device to prevent piracy.

1. In Termux, type:

```bash
ghostreels
```

2. The screen will show a Device ID (e.g., 6C3EBDBCC811CCF4).
3. Copy this Device ID and send it to the seller (the person you bought this from).
4. The seller will reply with a License Key (a long text code).
5. Paste that License Key into Termux and press Enter.
6. You will see: [OK] License Activated Successfully!

(Note: You only need to do this once. The system will remember your device forever).

---

🏭 Step 4: Running the Factory

Once activated, you will see a menu:

```text
1. Dark Psychology
2. True Crime & Mystery
3. Finance & Wealth
Enter category number (1): 
```

Type the number of your chosen niche (e.g., 1) and press Enter.

The system will now boot up the GHOSTREELS STUDIO dashboard. You will see live progress bars for:

· Writing Script
· Splitting Scenes
· Generating Prompts
· Rendering Images
· Synthesizing Voice
· Building Motion Clips
· Assembling Video
· Packaging SEO

Leave it running. The system will automatically start generating videos in a loop.

---

📁 Understanding the Output

When a video is completed, it will save automatically to your phone's gallery:
/storage/emulated/0/GhostReels/

Inside, you will find:

· video_1.mp4 -> The final video (ready to upload).
· seo/1/ -> A folder containing:
  · title.txt (Viral Title)
  · description.txt (SEO Description)
  · thumbnail.png (Custom AI Thumbnail)

---

💡 Pro-Tips for 24/7 Running

· Power: Keep the phone plugged into a charger at all times.
· Screen Off: You can turn off the screen. ghostreels automatically enables termux-wake-lock so it won't die in the background.
· Stopping: To stop the system, press Ctrl + C in Termux.
· Restarting: Just type ghostreels again. It will skip completed stages and resume from where it crashed.
· Heat: If the phone gets too hot, the system auto-pauses. Let it cool down and it will resume automatically.

---

🛠️ Troubleshooting & FAQ

Q: My images stopped generating?
A: You may have hit the free Agnes API limit. Wait 15 minutes, or generate a new key from their dashboard.

Q: Error: "Rate limit exceeded"?
A: GhostReels automatically rotates between Groq, Gemini, and NVIDIA. If all three hit limits, just wait 5-10 minutes. It will resume.

Q: License Error: "Locked to a different device"?
A: You are trying to use a license key on a different phone. Send your new Device ID to the seller.

Q: FFmpeg is stuck at 99%?
A: This is a rare Termux issue. Press Ctrl + C and type ghostreels again. It will resume instantly.

Q: Can I use this on PC?
A: Yes, if you know Linux. Run the same commands in Ubuntu/Debian terminal.

---

Copyright © 2026 GhostReels. Licensed for personal/commercial use. Redistribution or reselling the source code is strictly prohibited.

