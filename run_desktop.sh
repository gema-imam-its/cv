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

# Baca MAC Address Bluetooth Speaker dari file .env (jika ada)
BT_MAC=""
if [ -f "$PROJECT_DIR/.env" ]; then
    BT_MAC=$(grep "^BLUETOOTH_SPEAKER_MAC=" "$PROJECT_DIR/.env" | cut -d'=' -f2 | tr -d '"' | tr -d ' ')
fi

# Auto-connect ke Bluetooth Speaker (jika MAC dikonfigurasi)
if [ -n "$BT_MAC" ]; then
    echo ""
    echo "  [BT] Menghubungkan ke speaker Bluetooth: $BT_MAC ..."
    
    BT_CONNECTED=false
    for i in $(seq 1 10); do
        # Cek apakah sudah terhubung
        STATUS=$(bluetoothctl info "$BT_MAC" 2>/dev/null | grep "Connected: yes")
        if [ -n "$STATUS" ]; then
            echo "  [BT] ✅ Speaker Bluetooth sudah terhubung!"
            BT_CONNECTED=true
            break
        fi
        
        # Coba connect
        bluetoothctl connect "$BT_MAC" >/dev/null 2>&1
        sleep 2
        
        # Cek lagi setelah connect
        STATUS=$(bluetoothctl info "$BT_MAC" 2>/dev/null | grep "Connected: yes")
        if [ -n "$STATUS" ]; then
            echo "  [BT] ✅ Speaker Bluetooth berhasil terhubung (percobaan ke-$i)!"
            BT_CONNECTED=true
            break
        fi
        
        echo "  [BT] ⏳ Percobaan $i/10 gagal, mencoba lagi..."
    done
    
    if [ "$BT_CONNECTED" = false ]; then
        echo "  [BT] ⚠️  Speaker Bluetooth tidak tersedia. Menggunakan audio jack sebagai fallback."
    fi
    
    # Beri jeda agar sistem audio (PulseAudio) selesai mendaftarkan sink Bluetooth
    sleep 1
else
    echo "  [BT] INFO: BLUETOOTH_SPEAKER_MAC tidak dikonfigurasi di .env — melewati auto-connect."
fi

echo ""

# Jalankan program utama
python core/main.py

echo ""
echo "=================================================="
echo "  Program selesai atau dihentikan."
echo "  Ketik perintah berikut untuk menjalankan kembali:"
echo ""
echo "    python core/main.py"
echo ""
echo "  Atau ketik 'exit' untuk menutup terminal ini."
echo "=================================================="

# Buka shell interaktif agar terminal tidak langsung tertutup
# dan user bisa mengetik perintah kembali
exec bash
