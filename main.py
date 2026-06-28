"""
============================================================
GEMA Imam — Sholat Movement Tracking
main.py — Loop Utama & Pipeline Koordinasi (Entry Point)
============================================================
"""

import os
import sys
import time
import json
import csv
from datetime import datetime
import cv2
import mediapipe as mp

from config import (
    ACTIVE_PROFILE,
    PLATFORM,
    SHOLAT_CONFIG,
    SHOLAT_KEY_MAP,
    THRESHOLDS,
    POSE,
    LANDMARK,
    CALIBRATION_FILE,
    LOGS_DIR,
    KEY_QUIT,
    KEY_RESET,
    KEY_DEBUG,
    KEY_PAUSE,
    KEY_CALIBRATE
)
from pose_utils import get_coords
from pose_classifier import classify_pose, get_pose_features
from state_machine import SholatStateMachine
import visualizer

# Cek support display GUI
HAS_DISPLAY = "DISPLAY" in os.environ or os.name == "nt"

class GemaImamApp:
    def __init__(self):
        self.active_prayer = "Subuh"
        self.state_machine = SholatStateMachine(self.active_prayer)
        self.debug_mode = False
        self.paused = False
        
        # Inisialisasi MediaPipe Pose
        self.mp_pose = mp.solutions.pose
        self.pose_detector = self.mp_pose.Pose(
            model_complexity=ACTIVE_PROFILE["model_complexity"],
            min_detection_confidence=ACTIVE_PROFILE["min_detection_conf"],
            min_tracking_confidence=ACTIVE_PROFILE["min_tracking_conf"],
        )
        
        # Setup Kalibrasi
        self.calibrating = False
        self.calibration_start_time = 0
        self.calibration_samples = []
        self.load_calibration()
        
        # Data logger
        self.start_timestamp = None

    def load_calibration(self):
        """Memuat data kalibrasi dari file jika tersedia."""
        if os.path.exists(CALIBRATION_FILE):
            try:
                with open(CALIBRATION_FILE, "r") as f:
                    data = json.load(f)
                    if data.get("calibrated", False):
                        print(f"[CALIBRATION] Berhasil memuat kalibrasi dari {datetime.fromtimestamp(data['calibrated_at'])}")
                        # Di sini Anda bisa meng-override threshold berbasis Y menggunakan data kalibrasi jika diinginkan
            except Exception as e:
                print(f"[WARNING] Gagal membaca file kalibrasi: {e}")

    def save_calibration(self, shoulder_y, hip_y, knee_y):
        """Menyimpan hasil kalibrasi berdiri tegak."""
        data = {
            "calibrated": True,
            "calibrated_at": time.time(),
            "platform": PLATFORM,
            "shoulder_y": float(shoulder_y),
            "hip_y": float(hip_y),
            "knee_y": float(knee_y)
        }
        try:
            with open(CALIBRATION_FILE, "w") as f:
                json.dump(data, f, indent=2)
            print("[CALIBRATION] Hasil kalibrasi berhasil disimpan!")
        except Exception as e:
            print(f"[ERROR] Gagal menulis file kalibrasi: {e}")

    def start_session_logging(self):
        """Memulai pencatatan log waktu mulai sesi sholat."""
        self.start_timestamp = datetime.now()

    def save_session_logs(self, force_cancel=False):
        """Menyimpan log transisi gerakan (CSV) dan ringkasan sesi (JSON)."""
        if not self.start_timestamp:
            return
            
        timestamp_str = self.start_timestamp.strftime("%Y%m%d_%H%M%S")
        status_str = "Dibatalkan" if force_cancel else "Selesai"
        duration = (datetime.now() - self.start_timestamp).total_seconds()
        
        # 1. Simpan CSV (Detail Gerakan Rakaat demi Rakaat)
        csv_filename = os.path.join(LOGS_DIR, f"sholat_{self.active_prayer}_{timestamp_str}.csv")
        try:
            with open(csv_filename, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Rakaat", "State/Pose", "Sujud_Ke", "Waktu"])
                for step in self.state_machine.completed_steps:
                    writer.writerow([
                        step["rakaat"],
                        step["state"],
                        step["sujud_index"] if step["sujud_index"] is not None else "",
                        datetime.now().strftime("%H:%M:%S")
                    ])
            print(f"[LOGGER] Log CSV detail disimpan di: {csv_filename}")
        except Exception as e:
            print(f"[ERROR] Gagal menyimpan log CSV: {e}")
            
        # 2. Simpan JSON (Ringkasan Sesi)
        json_filename = os.path.join(LOGS_DIR, f"sholat_{self.active_prayer}_{timestamp_str}.json")
        summary = {
            "sholat": self.active_prayer,
            "tanggal": self.start_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "durasi_detik": round(duration, 1),
            "status": status_str,
            "total_rakaat_dilewati": self.state_machine.rakaat_count,
            "log_transisi": self.state_machine.completed_steps
        }
        try:
            with open(json_filename, "w") as f:
                json.dump(summary, f, indent=2)
            print(f"[LOGGER] Ringkasan JSON disimpan di: {json_filename}")
        except Exception as e:
            print(f"[ERROR] Gagal menyimpan log JSON: {e}")

    def run(self):
        camera_index = ACTIVE_PROFILE["camera_index"]
        backend_str = ACTIVE_PROFILE.get("camera_backend", None)
        skip_frame_rate = ACTIVE_PROFILE.get("skip_frame", 0)
        
        is_stream = isinstance(camera_index, str) and (camera_index.startswith("http://") or camera_index.startswith("https://"))
        
        print("\n[STEP 4/4] Membuka kamera...")
        if is_stream:
            cap = cv2.VideoCapture(camera_index)
            print(f"      Menggunakan stream URL: {camera_index}")
        else:
            if backend_str == "v4l2":
                cap = cv2.VideoCapture(camera_index, cv2.CAP_V4L2)
                print("      Menggunakan backend: V4L2")
            else:
                cap = cv2.VideoCapture(camera_index)
                print("      Menggunakan backend: Auto")
                
        if not cap.isOpened():
            print(f"❌ GAGAL: Tidak bisa membuka kamera/stream: {camera_index}")
            if is_stream:
                print("Pastikan server stream di Windows sudah berjalan.")
            sys.exit(1)
            
        # Set resolusi jika kamera lokal
        if not is_stream:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, ACTIVE_PROFILE["camera_width"])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, ACTIVE_PROFILE["camera_height"])
            cap.set(cv2.CAP_PROP_BUFFERSIZE, ACTIVE_PROFILE["buffer_size"])
            
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"✅ Kamera siap! Resolusi: {actual_w}x{actual_h}")
        
        # Mulai sesi logging
        self.start_session_logging()
        
        frame_count = 0
        fps = 0.0
        start_time = time.time()
        
        # Variabel cache pose untuk frame skipping
        last_results = None
        last_classified_pose = POSE.UNKNOWN
        last_features = {}
        
        print("\n" + "=" * 55)
        if HAS_DISPLAY:
            print(" GEMA IMAM RUNNING (Mode GUI)")
            print(" Shortcuts:")
            print("   1-5 : Ganti Sholat (Subuh, Dhuhur, Ashar, Maghrib, Isya)")
            print("   r   : Reset State Machine")
            print("   d   : Toggle Debug Overlay (Tampilkan Sudut)")
            print("   c   : Mulai Kalibrasi Tinggi Badan (Berdiri Tegak)")
            print("   p   : Pause / Resume")
            print("   q   : Keluar & Simpan Log Sesi")
        else:
            print(" GEMA IMAM RUNNING (Mode Headless/SSH)")
            print(" Menjalankan benchmark... Tekan Ctrl+C untuk keluar.")
        print("=" * 55 + "\n")
        
        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    print("[WARNING] Gagal mengambil frame.")
                    break
                    
                frame_count += 1
                
                # Jeda jika aplikasi di-pause
                if self.paused:
                    if HAS_DISPLAY:
                        cv2.putText(frame, "PAUSED", (actual_w // 2 - 80, actual_h // 2),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3, cv2.LINE_AA)
                        cv2.imshow("GEMA Imam", frame)
                        if cv2.waitKey(30) & 0xFF == ord('p'):
                            self.paused = False
                    continue
                
                # Mirror frame
                frame = cv2.flip(frame, 1)
                
                # Frame skipping logic (sangat penting untuk Orange Pi)
                should_process = (frame_count % (skip_frame_rate + 1)) == 0
                
                if should_process:
                    img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    last_results = self.pose_detector.process(img_rgb)
                    
                    if last_results.pose_landmarks:
                        # 1. Klasifikasi pose saat ini
                        last_classified_pose = classify_pose(last_results.pose_landmarks)
                        
                        # 2. Update state machine sholat
                        if not self.calibrating:
                            self.state_machine.update(last_classified_pose)
                        
                        # 3. Hitung fitur untuk debug sudut
                        last_features = get_pose_features(last_results.pose_landmarks)
                        
                        # Logika Kalibrasi Tinggi Badan
                        if self.calibrating:
                            elapsed_cal = time.time() - self.calibration_start_time
                            if elapsed_cal < 5.0:
                                # Kumpulkan sampel koordinat bahu, pinggul, lutut
                                sh_l = get_coords(last_results.pose_landmarks, LANDMARK.LEFT_SHOULDER)
                                sh_r = get_coords(last_results.pose_landmarks, LANDMARK.RIGHT_SHOULDER)
                                hip_l = get_coords(last_results.pose_landmarks, LANDMARK.LEFT_HIP)
                                hip_r = get_coords(last_results.pose_landmarks, LANDMARK.RIGHT_HIP)
                                knee_l = get_coords(last_results.pose_landmarks, LANDMARK.LEFT_KNEE)
                                knee_r = get_coords(last_results.pose_landmarks, LANDMARK.RIGHT_KNEE)
                                
                                self.calibration_samples.append((
                                    (sh_l[1] + sh_r[1]) / 2.0,
                                    (hip_l[1] + hip_r[1]) / 2.0,
                                    (knee_l[1] + knee_r[1]) / 2.0
                                ))
                            else:
                                # Proses hasil kalibrasi
                                if self.calibration_samples:
                                    avg_sh_y = np.mean([s[0] for s in self.calibration_samples])
                                    avg_hip_y = np.mean([s[1] for s in self.calibration_samples])
                                    avg_knee_y = np.mean([s[2] for s in self.calibration_samples])
                                    self.save_calibration(avg_sh_y, avg_hip_y, avg_knee_y)
                                self.calibrating = False
                                self.calibration_samples = []
                                print("[CALIBRATION] Selesai!")
                
                # Hitung FPS
                elapsed = time.time() - start_time
                fps = frame_count / elapsed if elapsed > 0 else 0.0
                
                # UI Rendering
                if HAS_DISPLAY:
                    if last_results and last_results.pose_landmarks:
                        # Draw skeleton
                        visualizer.draw_skeleton(frame, last_results.pose_landmarks)
                        
                        # Draw debug overlay sudut
                        if self.debug_mode and last_features:
                            visualizer.draw_debug_angles(frame, last_results.pose_landmarks, last_features)
                            
                    # Draw HUD
                    visualizer.draw_hud(
                        frame,
                        self.state_machine.current_state,
                        self.active_prayer,
                        self.state_machine.rakaat_count,
                        fps,
                        self.state_machine.hold_counter,
                        self.state_machine.max_hold_frames
                    )
                    
                    # Rendering info kalibrasi jika sedang berjalan
                    if self.calibrating:
                        elapsed_cal = time.time() - self.calibration_start_time
                        remaining = max(0.0, 5.0 - elapsed_cal)
                        cv2.rectangle(frame, (10, actual_h - 60), (450, actual_h - 10), (0, 0, 0), -1)
                        cv2.putText(frame, f"KALIBRASI: Berdiri Tegak ({remaining:.1f}s)", 
                                    (20, actual_h - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2, cv2.LINE_AA)
                    
                    cv2.imshow("GEMA Imam", frame)
                    
                    # Keyboard shortcuts
                    key = cv2.waitKey(1) & 0xFF
                    if key == KEY_QUIT:
                        print("[INFO] Menutup program via keyboard shortcut.")
                        self.save_session_logs(force_cancel=True)
                        break
                    elif key == KEY_RESET:
                        self.state_machine.reset()
                    elif key == KEY_DEBUG:
                        self.debug_mode = not self.debug_mode
                        print(f"[INFO] Debug mode: {'AKTIF' if self.debug_mode else 'NONAKTIF'}")
                    elif key == KEY_PAUSE:
                        self.paused = True
                        print("[INFO] Sesi di-pause.")
                    elif key == KEY_CALIBRATE:
                        if not self.calibrating:
                            print("[CALIBRATION] Mulai... Harap berdiri tegak menghadap kamera!")
                            self.calibrating = True
                            self.calibration_start_time = time.time()
                            self.calibration_samples = []
                    elif key in SHOLAT_KEY_MAP:
                        new_prayer = SHOLAT_KEY_MAP[key]
                        if new_prayer != self.active_prayer:
                            self.active_prayer = new_prayer
                            self.state_machine = SholatStateMachine(new_prayer)
                            self.start_session_logging()
                else:
                    # Headless Mode console logs
                    if frame_count % 30 == 0:
                        print(f"[Headless] Frame: {frame_count} | FPS: {fps:.1f} | Pose: {last_classified_pose} | State: {self.state_machine.current_state} (Rakaat {self.state_machine.rakaat_count})")
                    
                    # Otomatis berhenti setelah 500 frame di headless mode (untuk benchmark)
                    if frame_count >= 500:
                        print("[Headless] Benchmark 500 frame selesai.")
                        break
                        
        except KeyboardInterrupt:
            print("\n[INFO] Program dihentikan via KeyboardInterrupt.")
            self.save_session_logs(force_cancel=True)
        finally:
            cap.release()
            if HAS_DISPLAY:
                cv2.destroyAllWindows()
            
            # Jika program selesai normal tanpa dicancel ditengah sholat
            if self.state_machine.current_state == POSE.SELESAI:
                self.save_session_logs(force_cancel=False)
                
            print(f"\nSesi selesai. Rata-rata FPS: {fps:.1f}")

if __name__ == '__main__':
    print("=" * 55)
    print(" GEMA Imam — Sholat Tracking System")
    print("=" * 55)
    app = GemaImamApp()
    app.run()
