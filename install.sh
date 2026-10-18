#!/data/data/com.termux/files/usr/bin/bash

echo "=========================================="
echo " 👻 Welcome to GhostReels Setup"
echo "=========================================="

# 1. Storage Permission
echo "[1/6] Setting up storage permissions..."
termux-setup-storage
sleep 2

# 2. System Dependencies
echo "[2/6] Installing system packages (Python, FFmpeg, Node)..."
pkg update -y
pkg install -y python nodejs-lts ffmpeg openssh termux-api git

# 3. Python Dependencies
echo "[3/6] Installing Python requirements..."
pip install --quiet -r requirements.txt

# 4. API Keys Setup
echo "[4/6] 🔑 API Keys Setup"
echo "You need 4 free API keys to run the system."
echo "Groq (console.groq.com) | Gemini (aistudio.google.com) | NVIDIA (build.nvidia.com) | Agnes (platform.agnes-ai.com)"
echo ""

read -p "Paste GROQ_API_KEY: " GROQ
read -p "Paste GEMINI_API_KEY: " GEMINI
read -p "Paste NVIDIA_API_KEY: " NVIDIA
read -p "Paste AGNES_API_KEY: " AGNES

# Save to secrets.env
cat > secrets.env << EOF
GROQ_API_KEY="$GROQ"
GEMINI_API_KEY="$GEMINI"
NVIDIA_API_KEY="$NVIDIA"
AGNES_API_KEY="$AGNES"
EOF

# 5. Command Alias Setup
echo "[5/6] Setting up command alias..."
sed -i '/alias ghostreels=/d' ~/.bashrc
echo 'alias ghostreels="termux-wake-lock; nice -n 19 ionice -c 3 python3 ~/GhostReels/run.py"' >> ~/.bashrc
source ~/.bashrc

# 6. Create Output Folders
echo "[6/6] Creating output folders..."
mkdir -p "/storage/emulated/0/GhostReels/seo"
mkdir -p "/storage/emulated/0/GhostReels/frames"
mkdir -p "/storage/emulated/0/GhostReels/clips"

echo ""
echo "=========================================="
echo " ✅ GhostReels Installed Successfully!"
echo "=========================================="
echo "To start the system, just type: ghostreels"
echo ""
