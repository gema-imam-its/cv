"""
============================================================
GEMA Imam — Sholat Tracking System
prayer_scheduler.py — Otomatisasi penentuan waktu sholat aktif
============================================================
"""

from datetime import datetime, timezone, timedelta
import os
import sys

# Tambahkan base path agar bisa import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PRAYER_OFFSET_MINUTES

def get_current_prayer(test_time_str=None):
    """
    Menghitung sholat mana yang sedang aktif saat ini berdasarkan waktu lokal WIB (GMT+7).
    Mendukung offset masuk waktu sholat (default: 30 menit lebih awal).
    
    Args:
        test_time_str (str): Untuk keperluan testing unit, format "HH:MM".
        
    Returns:
        str: Nama sholat ("Subuh", "Dhuhur", "Ashar", "Maghrib", "Isya")
    """
    # 1. Set zona waktu WIB (GMT+7) secara manual agar konsisten
    wib_tz = timezone(timedelta(hours=7))
    
    if test_time_str:
        now = datetime.strptime(test_time_str, "%H:%M").replace(tzinfo=wib_tz)
    else:
        now = datetime.now(wib_tz)
        
    current_minutes = now.hour * 60 + now.minute
    
    # 2. Waktu Sholat Dasar Rata-rata Indonesia (Jakarta/Surabaya) dalam menit dari tengah malam
    base_times = {
        "Subuh":   4 * 60 + 15,   # 04:15
        "Dhuhur":  11 * 60 + 45,  # 11:45
        "Ashar":   15 * 60 + 0,   # 15:00
        "Maghrib": 17 * 60 + 45,  # 17:45
        "Isya":    19 * 60 + 0    # 19:00
    }
    
    # 3. Hitung batas mulai setiap sholat setelah dikurangi offset
    offset = PRAYER_OFFSET_MINUTES
    start_times = {name: (t - offset) for name, t in base_times.items()}
    
    subuh_start   = start_times["Subuh"]   # 03:45
    dhuhur_start  = start_times["Dhuhur"]  # 11:15
    ashar_start   = start_times["Ashar"]   # 14:30
    maghrib_start = start_times["Maghrib"] # 17:15
    isya_start    = start_times["Isya"]    # 18:30
    
    # 4. Tentukan sholat aktif berdasarkan slot waktu saat ini
    #    (Subuh berakhir sekitar jam 06:00 pagi saat matahari terbit/syuruq)
    if subuh_start <= current_minutes < 6 * 60:
        return "Subuh"
    elif dhuhur_start <= current_minutes < ashar_start:
        return "Dhuhur"
    elif ashar_start <= current_minutes < maghrib_start:
        return "Ashar"
    elif maghrib_start <= current_minutes < isya_start:
        return "Maghrib"
    else:
        # Waktu antara 18:30 malam s/d 03:44 pagi keesokan harinya adalah waktu Isya
        return "Isya"

if __name__ == "__main__":
    # Test deteksi jika dijalankan sebagai script mandiri
    p = get_current_prayer()
    wib_tz = timezone(timedelta(hours=7))
    now = datetime.now(wib_tz)
    print(f"[TEST] Waktu sistem (WIB): {now.strftime('%H:%M:%S')}")
    print(f"[TEST] Sholat aktif otomatis: {p}")
