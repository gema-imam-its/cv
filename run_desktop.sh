#!/bin/bash
# ============================================================
# GEMA Imam — Desktop Runner Script
# Dijalankan oleh xfce4-terminal saat autostart XFCE.
# Berbeda dari run_systemd.sh: script ini mengaktifkan venv
# lalu menjalankan program dalam jendela terminal yang terbuka.
# ============================================================

# Direktori project GEMA Imam
PROJECT_DIR="/home/orangepi/Downloads/cv"

# Aktifkan virtual environment
source "$PROJECT_DIR/venv/bin/activate"

# Pindah ke direktori project
cd "$PROJECT_DIR"

echo "=================================================="
echo "  GEMA Imam — Sholat Tracking System"
echo "  Memulai program... Tekan Ctrl+C untuk keluar."
echo "=================================================="

# Jalankan program utama
python core/main.py
