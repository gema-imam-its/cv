"""
============================================================
GEMA Imam — Fase 0: Test Kamera
test_camera.py

Jalankan ini SEBELUM memulai development untuk memastikan:
1. Kamera bisa dibuka
2. Frame bisa dibaca
3. MediaPipe bisa diimport
4. config.py bisa diimport

Cara jalankan:
    python test_camera.py

Tekan 'q' untuk keluar.
============================================================
"""

import sys
import os

print("=" * 55)
print(" GEMA Imam — Test Kamera & Environment")
print("=" * 55)

# ─── 1. Test import config ──────────────────────────────────
print("\n[1/4] Import config.py ...")
try:
    from config import ACTIVE_PROFILE, SHOLAT_CONFIG, THRESHOLDS, LANDMARK, POSE, PLATFORM
    print(f"      ✅ OK — Platform aktif: {PLATFORM}")
    print(f"      ✅ Profil: model_complexity={ACTIVE_PROFILE['model_complexity']}, "
          f"resolusi={ACTIVE_PROFILE['camera_width']}x{ACTIVE_PROFILE['camera_height']}")
except Exception as e:
    print(f"      ❌ GAGAL: {e}")
    sys.exit(1)

# ─── 2. Test import OpenCV ───────────────────────────────────
print("\n[2/4] Import OpenCV ...")
try:
    import cv2
    print(f"      ✅ OK — OpenCV versi: {cv2.__version__}")
except ImportError:
    print("      ❌ GAGAL: opencv-python belum terinstall.")
    print("         Jalankan: pip install -r requirements.txt")
    sys.exit(1)

# ─── 3. Test import MediaPipe ────────────────────────────────
print("\n[3/4] Import MediaPipe ...")
try:
    import mediapipe as mp
    print(f"      ✅ OK — MediaPipe versi: {mp.__version__}")
except ImportError:
    print("      ❌ GAGAL: mediapipe belum terinstall.")
    print("         Jalankan: pip install -r requirements.txt")
    sys.exit(1)

# ─── 4. Test buka kamera ────────────────────────────────────
print("\n[4/4] Test kamera ...")

camera_index  = ACTIVE_PROFILE["camera_index"]
camera_width  = ACTIVE_PROFILE["camera_width"]
camera_height = ACTIVE_PROFILE["camera_height"]
buffer_size   = ACTIVE_PROFILE["buffer_size"]
backend_str   = ACTIVE_PROFILE.get("camera_backend", None)

is_stream = isinstance(camera_index, str) and (camera_index.startswith("http://") or camera_index.startswith("https://"))

# Pilih backend
if is_stream:
    cap = cv2.VideoCapture(camera_index)
    print(f"      Menggunakan URL stream: {camera_index}")
else:
    if backend_str == "v4l2":
        cap = cv2.VideoCapture(camera_index, cv2.CAP_V4L2)
        print(f"      Menggunakan backend: V4L2")
    else:
        cap = cv2.VideoCapture(camera_index)
        print(f"      Menggunakan backend: Auto")

if not cap.isOpened():
    print(f"      ❌ GAGAL: Tidak bisa membuka kamera/stream: {camera_index}.")
    if is_stream:
        print("         Pastikan server streaming di Windows sudah dijalankan.")
    else:
        print("         Pastikan kamera terhubung dan tidak dipakai aplikasi lain.")
    sys.exit(1)

# Set resolusi & buffer (hanya jika menggunakan kamera fisik lokal)
if not is_stream:
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  camera_width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, camera_height)
    cap.set(cv2.CAP_PROP_BUFFERSIZE,   buffer_size)

actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

# Tukar lebar & tinggi jika rotasi vertikal aktif
rotation = ACTIVE_PROFILE.get("camera_rotation", None)
if rotation in [90, 270]:
    actual_w, actual_h = actual_h, actual_w

print(f"      ✅ Kamera terbuka — resolusi aktual: {actual_w}x{actual_h}")

# ─── Test live feed dengan MediaPipe ────────────────────────
# Cek apakah ada display GUI (X11) yang aktif
has_display = "DISPLAY" in os.environ or os.name == "nt"

print("\n" + "=" * 55)
if has_display:
    print(" Semua test OK! Menampilkan live feed + pose landmarks.")
    print(" Tekan 'q' untuk keluar.")
else:
    print(" ⚠️ Mode Headless aktif (tidak mendeteksi monitor/display GUI).")
    print(" Menjalankan benchmark kamera & pose selama 100 frame...")
print("=" * 55 + "\n")

mp_pose    = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

pose = mp_pose.Pose(
    model_complexity=ACTIVE_PROFILE["model_complexity"],
    min_detection_confidence=ACTIVE_PROFILE["min_detection_conf"],
    min_tracking_confidence=ACTIVE_PROFILE["min_tracking_conf"],
)

frame_count = 0
import time
start_time  = time.time()

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        print("PERINGATAN: Gagal membaca frame. Kamera mungkin terputus.")
        break

    # Rotasi frame jika diatur di profil
    rotation = ACTIVE_PROFILE.get("camera_rotation", None)
    if rotation == 90:
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    elif rotation == 180:
        frame = cv2.rotate(frame, cv2.ROTATE_180)
    elif rotation == 270:
        frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

    # Flip frame (opsional — agar tampak seperti cermin)
    frame = cv2.flip(frame, 1)

    # Proses dengan MediaPipe
    img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = pose.process(img_rgb)

    # Hitung FPS
    frame_count += 1
    elapsed = time.time() - start_time
    fps = frame_count / elapsed if elapsed > 0 else 0

    if has_display:
        # Gambar skeleton jika terdeteksi (hanya jika ada display GUI)
        if results.pose_landmarks:
            mp_drawing.draw_landmarks(
                frame,
                results.pose_landmarks,
                mp_pose.POSE_CONNECTIONS,
                mp_drawing.DrawingSpec(color=(0, 255, 100), thickness=2, circle_radius=3),
                mp_drawing.DrawingSpec(color=(255, 255, 255), thickness=2),
            )
            status_text = "Pose Terdeteksi ✓"
            status_color = (0, 220, 0)
        else:
            status_text = "Pose Tidak Terdeteksi"
            status_color = (0, 80, 255)

        # Overlay info
        cv2.putText(frame, status_text,
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, status_color, 2)
        cv2.putText(frame, f"FPS: {fps:.1f}",
                    (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
        cv2.putText(frame, f"Platform: {PLATFORM} | complexity={ACTIVE_PROFILE['model_complexity']}",
                    (20, actual_h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1)

        cv2.imshow("GEMA Imam — Test Kamera (tekan Q untuk keluar)", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    else:
        # Mode Headless: Tampilkan progres di console
        if frame_count % 10 == 0:
            pose_status = "Detected" if results.pose_landmarks else "Not Detected"
            print(f"  [Headless] Frame: {frame_count}/100 | FPS: {fps:.1f} | Pose: {pose_status}")
        
        # Berhenti setelah 100 frame
        if frame_count >= 100:
            break

cap.release()
if has_display:
    cv2.destroyAllWindows()

print(f"\nTest selesai. Total: {frame_count} frame dalam {elapsed:.1f} detik")
print(f"Rata-rata FPS: {fps:.1f}")
if PLATFORM == "laptop":
    print("\nJika FPS rendah di laptop, coba turunkan model_complexity di config.py")
else:
    print(f"\nBenchmark selesai untuk Orange Pi 4 Pro!")

