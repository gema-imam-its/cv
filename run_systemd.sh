#!/bin/bash
# ============================================================
# GEMA Imam — Sholat Tracking System
# run_systemd.sh — Runner script untuk Systemd Service
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Aktifkan virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "[ERROR] Virtual environment 'venv' tidak ditemukan!"
    exit 1
fi

# Jalankan program utama
python core/main.py
