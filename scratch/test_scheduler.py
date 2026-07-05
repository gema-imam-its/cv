import sys
import os

# Tambahkan base path agar bisa import dari core
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.prayer_scheduler import get_current_prayer

# Skenario pengujian (Waktu WIB -> Sholat yang Diharapkan)
test_cases = [
    # Subuh (04:15, masuk waktu dari 03:45 s/d 06:00)
    ("03:44", "Isya"),   # Tepat 1 menit sebelum masuk subuh (masih Isya)
    ("03:45", "Subuh"),  # Masuk waktu Subuh minus 30 menit
    ("04:15", "Subuh"),  # Waktu Subuh asli
    ("05:59", "Subuh"),  # Menjelang akhir subuh
    
    # Siang / Dhuhur (11:45, masuk waktu dari 11:15 s/d 14:30)
    ("06:01", "Isya"),   # Waktu dhuha / pagi hari (tidak ada sholat wajib, default ke Isya)
    ("11:14", "Isya"),   # Menjelang dhuhur (masih Isya)
    ("11:15", "Dhuhur"), # Masuk waktu Dhuhur minus 30 menit
    ("12:00", "Dhuhur"),
    ("14:29", "Dhuhur"), # Menjelang ashar
    
    # Ashar (15:00, masuk waktu dari 14:30 s/d 17:15)
    ("14:30", "Ashar"),  # Masuk waktu Ashar minus 30 menit
    ("15:30", "Ashar"),
    ("17:14", "Ashar"),  # Menjelang maghrib
    
    # Maghrib (17:45, masuk waktu dari 17:15 s/d 18:30)
    ("17:15", "Maghrib"),# Masuk waktu Maghrib minus 30 menit
    ("18:00", "Maghrib"),
    ("18:29", "Maghrib"),# Menjelang isya
    
    # Isya (19:00, masuk waktu dari 18:30 s/d 03:44 keesokan harinya)
    ("18:30", "Isya"),   # Masuk waktu Isya minus 30 menit
    ("20:00", "Isya"),
    ("23:59", "Isya"),   # Menjelang tengah malam
    ("01:00", "Isya"),   # Dini hari
    ("03:00", "Isya"),   # Menjelang subuh
]

print("=" * 60)
print(" RUNNING UNIT TEST: prayer_scheduler.py")
print("=" * 60)

passed = 0
failed = 0

for t_str, expected in test_cases:
    result = get_current_prayer(test_time_str=t_str)
    if result == expected:
        print(f"[PASS] Waktu: {t_str} WIB ➔ Terdeteksi: {result:<8} (Diharapkan: {expected})")
        passed += 1
    else:
        print(f"[FAIL] Waktu: {t_str} WIB ➔ Terdeteksi: {result:<8} (Diharapkan: {expected})  ❌")
        failed += 1

print("-" * 60)
print(f"Hasil: {passed} Uji Coba Lulus, {failed} Uji Coba Gagal.")
print("=" * 60)

if failed > 0:
    sys.exit(1)
else:
    sys.exit(0)
