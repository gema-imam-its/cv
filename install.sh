#!/bin/bash
# ============================================================
# GEMA Imam — Sholat Tracking System
# install.sh — Skrip Instalasi Otomatis untuk Orange Pi 4 Pro
# ============================================================
# Jalankan: bash install.sh
# ============================================================

set -e  # Hentikan jika ada error

# Warna output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "============================================================"
echo "  GEMA Imam — Instalasi Sistem Tracking Sholat"
echo "  Direktori: $INSTALL_DIR"
echo "============================================================"
echo ""

# ── STEP 1: Dependensi Sistem ────────────────────────────────
echo -e "${BLUE}[1/5] Menginstal dependensi sistem...${NC}"
sudo apt-get update -q
sudo apt-get install -y -q \
    python3-pip \
    python3-venv \
    libgl1-mesa-glx \
    libglib2.0-0 \
    alsa-utils \
    libsm6 \
    libxext6 \
    libxrender-dev
echo -e "${GREEN}    ✓ Dependensi sistem selesai.${NC}"

# ── STEP 2: Python Virtual Environment ──────────────────────
echo -e "${BLUE}[2/5] Membuat Python virtual environment...${NC}"
if [ ! -d "$INSTALL_DIR/venv" ]; then
    python3 -m venv "$INSTALL_DIR/venv"
    echo -e "${GREEN}    ✓ Virtual environment dibuat.${NC}"
else
    echo -e "${YELLOW}    ⚠ Virtual environment sudah ada, dilewati.${NC}"
fi

source "$INSTALL_DIR/venv/bin/activate"

# ── STEP 3: Install Python packages ─────────────────────────
echo -e "${BLUE}[3/5] Menginstal Python packages...${NC}"
pip install --upgrade pip -q
pip install -r "$INSTALL_DIR/requirements.txt" -q
echo -e "${GREEN}    ✓ Python packages selesai.${NC}"

# ── STEP 4: Setup konfigurasi rahasia ───────────────────────
echo -e "${BLUE}[4/5] Mengatur konfigurasi...${NC}"
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    echo -e "${YELLOW}    ⚠ Berkas .env dibuat dari template."
    echo -e "      Isi TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID di berkas:${NC}"
    echo -e "      ${YELLOW}$INSTALL_DIR/.env${NC}"
else
    echo -e "${GREEN}    ✓ Berkas .env sudah ada.${NC}"
fi

# ── STEP 5: Buat folder yang diperlukan ─────────────────────
echo -e "${BLUE}[5/5] Membuat folder yang diperlukan...${NC}"
mkdir -p "$INSTALL_DIR/logs"
touch "$INSTALL_DIR/logs/.gitkeep"
echo -e "${GREEN}    ✓ Folder logs siap.${NC}"

# ── SELESAI ──────────────────────────────────────────────────
echo ""
echo "============================================================"
echo -e "${GREEN}  INSTALASI SELESAI!${NC}"
echo "============================================================"
echo ""
echo "Langkah selanjutnya:"
echo ""
echo "  1. Isi kredensial Telegram di berkas .env:"
echo "     nano $INSTALL_DIR/.env"
echo ""
echo "  2. Uji kamera:"
echo "     source $INSTALL_DIR/venv/bin/activate"
echo "     python $INSTALL_DIR/test_camera.py"
echo ""
echo "  3. Jalankan program:"
echo "     python $INSTALL_DIR/core/main.py"
echo ""
echo "  4. (Opsional) Aktifkan autostart saat boot (Systemd):"
echo "     sudo cp $INSTALL_DIR/gema-imam.service /etc/systemd/system/"
echo "     sudo systemctl daemon-reload"
echo "     sudo systemctl enable gema-imam.service"
echo "     sudo systemctl start gema-imam.service"
echo ""
