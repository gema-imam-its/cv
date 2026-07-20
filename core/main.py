"""
============================================================
GEMA Imam — Sholat Movement Tracking
main.py — Loop Utama & Pipeline Koordinasi (Entry Point)
============================================================
"""

import os
import sys

# Tambahkan direktori root project ke sys.path agar config.py bisa diimport
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import time
import json
import csv
from datetime import datetime
import cv2
import mediapipe as mp
import numpy as np
import queue
import subprocess
import threading
import requests

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
    AUDIO_DIR,
    AUDIO_STATE_MAP,
    AUDIO_TRANSITION_MAP,
    AUDIO_EXTRA,
    KEY_QUIT,
    KEY_RESET,
    KEY_DEBUG,
    KEY_PAUSE,
    KEY_CALIBRATE,
    USE_GPIO_BUTTON,
    GPIO_RESET_PIN,
    AUTO_DETECT_PRAYER,
    USE_TELEGRAM,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    WEB_LMS_URL,
    WEB_LMS_API_KEY
)
from pose_utils import get_coords
from pose_classifier import classify_pose, get_pose_features
from state_machine import SholatStateMachine
import visualizer

# Cek support display GUI
HAS_DISPLAY = "DISPLAY" in os.environ or os.name == "nt"

def get_cpu_temp():
    """Membaca suhu CPU Orange Pi (Linux). Mengembalikan derajat Celsius atau None."""
    try:
        temp_path = "/sys/class/thermal/thermal_zone0/temp"
        if os.path.exists(temp_path):
            with open(temp_path, "r") as f:
                temp_str = f.read().strip()
                return round(float(temp_str) / 1000.0, 1)
    except Exception:
        pass
    return None

# Daftar file audio bacaan sholat yang wajib/sunnah diselesaikan (jika terpotong dianggap kesalahan Imam)
READING_AUDIOS = {
    "alfatihah.WAV", "al-ikhlas.WAV", "ruku.WAV", "itidal.WAV",
    "sujud.WAV", "iftirasy.WAV", "tasyahud-awal.WAV", "tasyahud-akhir.WAV",
    "iftitah.WAV", "qunut.WAV", "niat-subuh.WAV"
}

class AudioPlayer:
    def __init__(self):
        self.queue = queue.Queue()
        self.active_process = None
        self.current_playing_file = None
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()
        
    def play(self, filename, delay=0.0):
        """Menambahkan file audio ke dalam antrean untuk diputar secara berurutan."""
        if not filename:
            return
        filepath = os.path.join(AUDIO_DIR, filename)
        if not os.path.exists(filepath):
            print(f"[AUDIO WARNING] Berkas tidak ditemukan: {filepath}")
            return
        self.queue.put((filepath, delay))
        
    def clear(self):
        """Mengosongkan antrean audio dan menghentikan audio yang sedang diputar.
           Mengembalikan daftar nama file audio yang terpotong/batal diputar."""
        interrupted = []
        if self.current_playing_file:
            interrupted.append(os.path.basename(self.current_playing_file))
            
        while not self.queue.empty():
            try:
                filepath, _ = self.queue.get_nowait()
                interrupted.append(os.path.basename(filepath))
            except queue.Empty:
                break
        if self.active_process:
            try:
                if sys.platform.startswith("win"):
                    import winsound
                    winsound.PlaySound(None, winsound.SND_PURGE)
                else:
                    self.active_process.terminate()
            except Exception:
                pass
            self.active_process = None
        
        self.current_playing_file = None
        return interrupted
                
    @staticmethod
    def _find_player():
        """Mencari audio player yang tersedia di sistem."""
        for player in ["aplay", "paplay", "ffplay", "mpg123"]:
            result = subprocess.run(["which", player], capture_output=True, text=True)
            if result.returncode == 0:
                return player.strip()
        return None

    def _worker(self):
        player = self._find_player()
        if player:
            print(f"[AUDIO] Menggunakan player: {player}")
        else:
            warn_msg = "[AUDIO WARNING] Tidak ada audio player yang ditemukan (aplay/paplay/ffplay). Suara dinonaktifkan."
            print(warn_msg)
            # Kirim notifikasi Telegram jika tersedia
            try:
                from config import USE_TELEGRAM, TELEGRAM_CHAT_ID
                if USE_TELEGRAM and TELEGRAM_CHAT_ID:
                    from telegram_notifier import send_telegram_message_async
                    send_telegram_message_async(
                        "\u26a0\ufe0f *GEMA Imam - Speaker Tidak Terdeteksi*\n"
                        "Sistem tidak menemukan audio player yang didukung (aplay/paplay/ffplay).\n"
                        "Audio takbir tidak akan diputar. Periksa koneksi speaker dan pastikan `aplay` terinstall."
                    )
            except Exception:
                pass

        while True:
            try:
                filepath, delay = self.queue.get()
                self.current_playing_file = filepath
                if delay > 0:
                    time.sleep(delay)

                if sys.platform.startswith("win"):
                    import winsound
                    winsound.PlaySound(filepath, winsound.SND_FILENAME)
                elif sys.platform.startswith("darwin"):
                    self.active_process = subprocess.Popen(["afplay", filepath], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self.active_process.wait()
                elif player:
                    if player == "ffplay":
                        cmd = ["ffplay", "-nodisp", "-autoexit", filepath]
                    elif player == "mpg123":
                        cmd = ["mpg123", "-q", filepath]
                    else:
                        cmd = [player, filepath]
                    self.active_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self.active_process.wait()
                else:
                    pass  # Tidak ada player, lewati tanpa error
            except Exception as e:
                print(f"[AUDIO ERROR] Gagal memutar {filepath if 'filepath' in locals() else ''}: {e}")
            finally:
                self.current_playing_file = None
                self.active_process = None
                self.queue.task_done()


class ButtonListener:
    """
    Mendeteksi penekanan tombol untuk memicu RESET sholat.
    Mendukung dua mode:
      1. GPIO fisik (tombol dihubungkan ke pin GPIO Orange Pi)
         → Aktifkan dengan USE_GPIO_BUTTON = True di config.py
      2. Keyboard (fallback otomatis, tekan 'r' di terminal)
         → Sudah terintegrasi di loop utama OpenCV (KEY_RESET)
    """
    def __init__(self, callback):
        self.callback = callback
        self.running = False
        self.thread = None
        self._gpio_ok = False

    def start(self):
        """Memulai listener sesuai konfigurasi di config.py."""
        if USE_GPIO_BUTTON:
            self._start_gpio()
        else:
            print("[BUTTON] Mode tombol: Keyboard (tekan 'r' untuk reset). GPIO dinonaktifkan.")

    def _start_gpio(self):
        """Coba inisialisasi GPIO. Jika gagal, cetak peringatan saja."""
        try:
            import OPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(GPIO_RESET_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            self._gpio = GPIO
            self._gpio_ok = True
            self.running = True
            self.thread = threading.Thread(target=self._poll_gpio, daemon=True)
            self.thread.start()
            print(f"[BUTTON] GPIO listener diaktifkan pada pin {GPIO_RESET_PIN}. Tekan tombol fisik untuk reset.")
        except ImportError:
            print("[BUTTON WARNING] Library 'OPi.GPIO' tidak ditemukan.")
            print("                 Install dengan: pip install OPi.GPIO")
            print("                 Fallback: gunakan tombol keyboard 'r' untuk reset.")
        except Exception as e:
            print(f"[BUTTON WARNING] Gagal inisialisasi GPIO pin {GPIO_RESET_PIN}: {e}")
            print("                 Fallback: gunakan tombol keyboard 'r' untuk reset.")

    def _poll_gpio(self):
        """Polling pin GPIO di background thread (active-low, pull-up)."""
        prev_state = 1  # HIGH (tidak ditekan)
        while self.running:
            try:
                current_state = self._gpio.input(GPIO_RESET_PIN)
                # Transisi HIGH → LOW = tombol ditekan
                if prev_state == 1 and current_state == 0:
                    print(f"[BUTTON] Tombol GPIO pin {GPIO_RESET_PIN} ditekan. Memicu RESET!")
                    self.callback()
                    time.sleep(0.5)  # debounce
                prev_state = current_state
            except Exception as e:
                print(f"[BUTTON ERROR] Gagal membaca pin GPIO: {e}")
                break
            time.sleep(0.02)  # polling setiap 20ms

    def stop(self):
        self.running = False
        if self._gpio_ok:
            try:
                self._gpio.cleanup()
            except Exception:
                pass


class PoseLandmarkSmoother:
    """
    Menggunakan Exponential Moving Average (EMA) untuk menyaring/memuluskan landmark pose,
    guna mereduksi jitter/jumping pada koordinat landmark MediaPipe.
    """
    def __init__(self, alpha=0.45):
        self.alpha = alpha  # Nilai lebih kecil = lebih mulus tapi ada sedikit delay
        self.prev_landmarks = None

    def reset(self):
        self.prev_landmarks = None

    def smooth(self, pose_landmarks):
        if not pose_landmarks:
            return
        
        # Inisialisasi awal jika baru mendeteksi
        if self.prev_landmarks is None:
            self.prev_landmarks = []
            for lm in pose_landmarks.landmark:
                self.prev_landmarks.append({
                    "x": lm.x,
                    "y": lm.y,
                    "z": lm.z,
                    "visibility": lm.visibility
                })
            return

        # Terapkan EMA pada koordinat x, y, z dan visibilitas landmark
        for i, lm in enumerate(pose_landmarks.landmark):
            prev = self.prev_landmarks[i]
            
            # EMA formula: S_t = alpha * Y_t + (1 - alpha) * S_{t-1}
            lm.x = self.alpha * lm.x + (1 - self.alpha) * prev["x"]
            lm.y = self.alpha * lm.y + (1 - self.alpha) * prev["y"]
            lm.z = self.alpha * lm.z + (1 - self.alpha) * prev["z"]
            lm.visibility = self.alpha * lm.visibility + (1 - self.alpha) * prev["visibility"]
            
            # Simpan untuk iterasi berikutnya
            prev["x"] = lm.x
            prev["y"] = lm.y
            prev["z"] = lm.z
            prev["visibility"] = lm.visibility


class GemaImamApp:
    def __init__(self):
        self.active_prayer = "Subuh"
        if AUTO_DETECT_PRAYER:
            try:
                from prayer_scheduler import get_current_prayer
                self.active_prayer = get_current_prayer()
                print(f"[INFO] Waktu sholat aktif otomatis saat startup: {self.active_prayer}")
            except Exception as e:
                print(f"[WARNING] Gagal melakukan deteksi sholat otomatis: {e}. Menggunakan default: Subuh")
                self.active_prayer = "Subuh"
                
        self.state_machine = SholatStateMachine(self.active_prayer)
        self.audio_player = AudioPlayer()
        self.button_listener = ButtonListener(callback=self.reset_from_button)
        self.debug_mode = False
        self.paused = False
        
        # Inisialisasi MediaPipe Pose
        self.mp_pose = mp.solutions.pose
        self.pose_detector = self.mp_pose.Pose(
            model_complexity=ACTIVE_PROFILE["model_complexity"],
            min_detection_confidence=ACTIVE_PROFILE["min_detection_conf"],
            min_tracking_confidence=ACTIVE_PROFILE["min_tracking_conf"],
        )
        self.landmark_smoother = PoseLandmarkSmoother(alpha=0.45)
        
        # Setup Kalibrasi
        self.calibrating = False
        self.calibration_start_time = 0
        self.calibration_samples = []
        self.load_calibration()
        
        # Data logger
        self.start_timestamp = None
        self.imam_mistakes_count = 0
        
        # Variabel Sesi Web LMS
        self.current_session_id = None
        self.current_student_name = None
        self.force_stop_session = False
        self._last_cancel_check = 0.0
        self._cancel_check_in_flight = False
        # MAC address speaker Bluetooth yang terakhir berhasil terhubung
        # (diisi dari .env saat startup, diperbarui saat /bt atau Web LMS request)
        from config import BLUETOOTH_SPEAKER_MAC
        self._last_bt_mac = BLUETOOTH_SPEAKER_MAC or ""

        # Deteksi imam tidak terdeteksi
        self._no_imam_frames = 0
        self._no_imam_notified = False
        self._NO_IMAM_ALERT_FRAMES = 60 * 15  # ~60 detik pada 15fps (sesuaikan ke FPS platform)

        # Inisialisasi Detektor Chat ID Telegram otomatis saat startup jika kosong
        if USE_TELEGRAM and not TELEGRAM_CHAT_ID:
            self.run_telegram_setup_helper()

        # Mulai Telegram command listener (jika chat ID sudah dikonfigurasi)
        self.telegram_listener = None
        if USE_TELEGRAM and TELEGRAM_CHAT_ID:
            try:
                from telegram_notifier import TelegramCommandListener
                self.telegram_listener = TelegramCommandListener(app_ref=self)
                self.telegram_listener.start()
                self._send_startup_notification()
            except Exception as e:
                print(f"[TELEGRAM CMD WARNING] Gagal memulai command listener: {e}")

    def _send_startup_notification(self):
        """Kirim pesan notifikasi startup ke Telegram secara async."""
        def _notify():
            import time
            from datetime import datetime
            # Beri jeda 5 detik agar inisialisasi kamera & MediaPipe selesai 
            # (mengurangi beban CPU puncak saat startup agar tidak timeout)
            time.sleep(5.0)  
            from telegram_notifier import send_telegram_message
            now_str = datetime.now().strftime("%d %b %Y, %H:%M:%S")
            msg = (
                "GEMA Imam - Sistem Aktif\n"
                "================================\n"
                f"Alat berhasil menyala dan siap beroperasi.\n\n"
                f"Waktu   : {now_str}\n"
                f"Sholat  : {self.active_prayer}\n"
                f"Rakaat  : {self.state_machine.total_rakaats} rakaat\n\n"
                "Ketik /help untuk melihat daftar perintah yang tersedia."
            )
            
            # Coba kirim pesan
            success = send_telegram_message(msg)
            if success:
                print("[TELEGRAM] Notifikasi startup berhasil dikirim.")
            else:
                # Jika gagal/timeout karena jaringan saat booting, coba sekali lagi setelah 5 detik
                print("[TELEGRAM WARNING] Gagal mengirim notifikasi startup. Mencoba kembali dalam 5 detik...")
                time.sleep(5.0)
                if send_telegram_message(msg):
                    print("[TELEGRAM] Notifikasi startup berhasil dikirim pada percobaan kedua.")
                
        threading.Thread(target=_notify, daemon=True, name="TelegramStartupNotif").start()

    def run_telegram_setup_helper(self):
        """Membantu mendeteksi Chat ID pengguna secara non-blocking."""
        def helper():
            import time
            from telegram_notifier import get_telegram_chat_id
            print("\n" + "-" * 55)
            print("[TELEGRAM] ⚠️ Chat ID belum diatur di config.py!")
            print("[TELEGRAM] Silakan buka aplikasi Telegram Anda, cari Bot: @GemalmamBot")
            print("[TELEGRAM] Kirim pesan apa saja (misal: /start atau halo) ke bot tersebut.")
            print("[TELEGRAM] Menunggu deteksi Chat ID otomatis...")
            print("-" * 55)
            
            # Polling selama 15 detik
            for _ in range(15):
                chats = get_telegram_chat_id()
                if chats:
                    print("\n" + "=" * 55)
                    print("[TELEGRAM] BERHASIL MENEMUKAN CHAT ID!")
                    print("=" * 55)
                    for c_id, name in chats.items():
                        print(f"  ID: {c_id} (Pengirim: {name})")
                    print("\n[TELEGRAM] Salin salah satu ID di atas dan masukkan ke:")
                    print("           TELEGRAM_CHAT_ID = \"ID_DI_ATAS\" di file config.py")
                    print("=" * 55 + "\n")
                    return
                time.sleep(2.0)
            print("[TELEGRAM WARNING] Waktu deteksi habis. Kirim pesan ke bot lalu restart program untuk mendeteksi kembali.\n")
            
        thread = threading.Thread(target=helper, daemon=True)
        thread.start()

    def play_niat_audio(self):
        """Memutar audio niat sholat yang aktif."""
        self.audio_player.clear()  # Bersihkan audio sebelumnya
        if self.active_prayer == "Subuh":
            self.audio_player.play(AUDIO_EXTRA["niat_subuh"])
        elif self.active_prayer == "Dhuhur":
            self.audio_player.play(AUDIO_EXTRA["niat_dzuhur"])
        elif self.active_prayer == "Ashar":
            self.audio_player.play(AUDIO_EXTRA["niat_ashar"])
        elif self.active_prayer == "Maghrib":
            self.audio_player.play(AUDIO_EXTRA["niat_maghrib"])
        elif self.active_prayer == "Isya":
            self.audio_player.play(AUDIO_EXTRA["niat_isya"])
        else:
            print(f"[AUDIO] Niat untuk sholat {self.active_prayer} tidak tersedia di folder audio.")

    def reset_from_button(self):
        """Callback untuk me-reset state sholat dari tombol GPIO atau keyboard 'r'."""
        print("[BUTTON] Reset sholat dipicu.")
        if self.start_timestamp:
            self.save_session_logs(force_cancel=True)
            self.start_timestamp = None
            
        self.state_machine.reset()
        self.audio_player.clear()
        self.imam_mistakes_count = 0
        self.force_stop_session = True

    def check_web_status(self):
        """Mengecek ke Web LMS apakah ada sesi praktik aktif."""
        if not WEB_LMS_URL:
            return {"status": "idle"}
            
        url = f"{WEB_LMS_URL.rstrip('/')}/api/iot/status"
        headers = {
            "x-api-key": WEB_LMS_API_KEY,
            "Content-Type": "application/json"
        }
        try:
            response = requests.get(url, headers=headers, timeout=1.5)
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return {"status": "idle"}

    def check_session_cancelled_async(self):
        """Cek ke Web LMS (non-blocking, di background thread) apakah sesi
        yang sedang direkam (self.current_session_id) masih berstatus ACTIVE,
        atau sudah dibatalkan dari web (tombol "Batalkan Sesi"). Kalau sudah
        tidak ACTIVE lagi, pakai jalur yang sama seperti reset fisik/Telegram
        (reset_from_button) supaya sesi tersimpan sebagai Dibatalkan dan alat
        kembali ke standby. Request gagal/timeout dianggap sesi TETAP
        berjalan — jaringan yang sempat putus sesaat tidak boleh menghentikan
        rekaman yang sah.
        """
        if not WEB_LMS_URL or not self.current_session_id or self._cancel_check_in_flight:
            return

        self._cancel_check_in_flight = True
        session_id = self.current_session_id

        def _check():
            try:
                url = f"{WEB_LMS_URL.rstrip('/')}/api/iot/status"
                headers = {
                    "x-api-key": WEB_LMS_API_KEY,
                    "Content-Type": "application/json"
                }
                response = requests.get(
                    url, headers=headers, params={"session_id": session_id}, timeout=3
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("active") is False and not self.force_stop_session:
                        print("[WEB LMS] Sesi dibatalkan dari Web LMS (tombol 'Batalkan Sesi').")
                        self.reset_from_button()
            except Exception:
                pass
            finally:
                self._cancel_check_in_flight = False

        threading.Thread(target=_check, daemon=True, name="WebSessionCancelCheck").start()

    def lapor_sesi_selesai(self, session_id, payload=None):
        """Melaporkan ke Web LMS bahwa sesi sholat telah selesai,
        disertai seluruh payload JSON ringkasan sesi jika tersedia."""
        if not WEB_LMS_URL or not session_id:
            return

        url = f"{WEB_LMS_URL.rstrip('/')}/api/iot/sesi/selesai"
        headers = {
            "x-api-key": WEB_LMS_API_KEY,
            "Content-Type": "application/json"
        }
        # Gunakan payload ringkasan lengkap jika diberikan, minimal kirim sesi_id
        body = payload if payload else {}
        body["sesi_id"] = session_id
        try:
            res = requests.post(url, json=body, headers=headers, timeout=10)
            if res.status_code == 200:
                print(f"[WEB API] Laporan sesi '{session_id}' berhasil dikirim ke Web LMS.")
            else:
                print(f"[WEB API WARNING] Gagal mengirim laporan sesi. Status: {res.status_code}")
        except Exception as e:
            print(f"[WEB API WARNING] Gagal terhubung ke Web LMS saat menutup sesi: {e}")

    def show_standby_frame(self):
        """Membuat dan menampilkan frame standby yang estetik di layar."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Gambar gradasi / box latar belakang modern
        cv2.rectangle(frame, (30, 30), (610, 450), (20, 20, 20), -1)
        cv2.rectangle(frame, (30, 30), (610, 450), (60, 50, 40), 1, cv2.LINE_AA)
        
        # Header / Brand
        cv2.putText(frame, "GEMA IMAM - SISTEM AKTIF", (80, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (200, 220, 255), 2, cv2.LINE_AA)
        cv2.line(frame, (80, 120), (560, 120), (80, 80, 80), 1)
        
        # Status / Menunggu
        cv2.putText(frame, "STATUS: STANDBY MODE", (80, 180),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 200, 100), 2, cv2.LINE_AA)
        cv2.putText(frame, "Menunggu instruksi praktikum dari Web LMS...", (80, 220),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1, cv2.LINE_AA)
        
        # Petunjuk penggunaan untuk Guru / Operator
        cv2.putText(frame, "Instruksi Operator:", (80, 290),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (130, 160, 200), 1, cv2.LINE_AA)
        cv2.putText(frame, "1. Buka Web LMS Next.js di laptop/HP.", (80, 320),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1, cv2.LINE_AA)
        cv2.putText(frame, "2. Pilih Siswa & Klik 'Mulai Praktik'.", (80, 345),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1, cv2.LINE_AA)
        cv2.putText(frame, "3. Kamera alat ini akan otomatis menyala.", (80, 370),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1, cv2.LINE_AA)
        
        # Info exit
        cv2.putText(frame, "Tekan 'q' di jendela ini untuk keluar.", (80, 420),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 100, 100), 1, cv2.LINE_AA)
        
        cv2.imshow("GEMA Imam", frame)


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

    def rotate_logs(self, max_sessions=60):
        """
        Membatasi jumlah file log agar eMMC Orange Pi tidak penuh.
        Hapus sesi terlama jika melebihi max_sessions sesi.
        Satu sesi = 1 pasang file .csv + .json.
        """
        try:
            json_files = sorted(
                [f for f in os.listdir(LOGS_DIR) if f.endswith(".json")],
                key=lambda f: os.path.getmtime(os.path.join(LOGS_DIR, f))
            )  # urut dari yang terlama ke terbaru berdasarkan waktu file
            if len(json_files) > max_sessions:
                to_delete = json_files[:len(json_files) - max_sessions]
                for fname in to_delete:
                    base = fname.replace(".json", "")
                    for ext in (".json", ".csv"):
                        fpath = os.path.join(LOGS_DIR, base + ext)
                        if os.path.exists(fpath):
                            os.remove(fpath)
                print(f"[LOGGER] Rotasi log: {len(to_delete)} sesi lama dihapus (maks {max_sessions} sesi).")
        except Exception as e:
            print(f"[WARNING] Gagal rotasi log: {e}")

    def save_session_logs(self, force_cancel=False):
        """Menyimpan log transisi gerakan (CSV) dan ringkasan sesi (JSON)."""
        if not self.start_timestamp:
            return
            
        timestamp_str = self.start_timestamp.strftime("%Y%m%d_%H%M%S")
        status_str = "Dibatalkan" if force_cancel else "Selesai"
        duration = (datetime.now() - self.start_timestamp).total_seconds()
        
        # APPEND CURRENT ACTIVE STATE SO IT IS NOT LOST
        if self.state_machine.current_state != POSE.UNKNOWN:
            duration_last = 0
            if getattr(self.state_machine, 'state_start_time', None):
                duration_last = time.time() - self.state_machine.state_start_time
            
            entry_t = getattr(self.state_machine, 'state_start_time_str', "00:00:00")
            if entry_t == "-":
                entry_t = "00:00:00"
                
            self.state_machine.completed_steps.append({
                "rakaat": self.state_machine.rakaat_count,
                "state": self.state_machine.current_state,
                "entry_time": entry_t,
                "exit_time": time.strftime("%H:%M:%S") if not force_cancel else "Batal",
                "duration_seconds": round(duration_last, 2),
                "tumaninah_met": False, 
                "bacaan_terpotong": None,
                "gerakan_menyimpang": getattr(self.state_machine, 'current_state_deviations', []),
                "hip_angle": None,
                "knee_angle": None,
                "arm_angle": None,
                "wrist_dist_x": None,
                "head_offset_x": None
            })
            self.state_machine.current_state = POSE.UNKNOWN

        # Hitung statistik tuma'ninah
        total_tumaninah_check = 0
        total_tumaninah_success = 0
        for step in self.state_machine.completed_steps:
            if step.get("tumaninah_met") is not None:
                total_tumaninah_check += 1
                if step["tumaninah_met"] is True:
                    total_tumaninah_success += 1
                    
        tumaninah_score = (total_tumaninah_success / total_tumaninah_check * 100.0) if total_tumaninah_check > 0 else 100.0
        
        # 1. Simpan CSV (Detail Gerakan Rakaat demi Rakaat dengan Metadata Rinci)
        csv_filename = os.path.join(LOGS_DIR, f"sholat_{self.active_prayer}_{timestamp_str}.csv")
        try:
            with open(csv_filename, "w", newline="") as f:
                writer = csv.writer(f)
                
                # Metadata Sholat (Bagian Atas CSV)
                writer.writerow(["=== METADATA SESI SHOLAT ==="])
                writer.writerow(["Nama Sholat", self.active_prayer])
                writer.writerow(["Waktu Mulai", self.start_timestamp.strftime("%Y-%m-%d %H:%M:%S")])
                writer.writerow(["Durasi Total (Detik)", round(duration, 1)])
                writer.writerow(["Status Akhir", status_str])
                writer.writerow(["Rakaat Diselesaikan", self.state_machine.rakaat_count])
                writer.writerow(["Total Kesalahan Imam", self.imam_mistakes_count])
                tumaninah_kpi_str = f"{tumaninah_score:.1f}% ({total_tumaninah_success}/{total_tumaninah_check})" if total_tumaninah_check > 0 else "N/A"
                writer.writerow(["Skor Tuma'ninah", tumaninah_kpi_str])
                writer.writerow([])  # Baris Kosong Pemisah
                
                # Detail Gerakan Per Rakaat
                writer.writerow(["=== DETAIL GERAKAN RAKAAT DEMI RAKAAT ==="])
                writer.writerow([
                    "Rakaat", 
                    "Gerakan/State", 
                    "Waktu Masuk", 
                    "Waktu Keluar", 
                    "Durasi (Detik)", 
                    "Tuma'ninah Terpenuhi", 
                    "Kesalahan (Bacaan Terpotong)",
                    "Gerakan Menyimpang (Jitter)",
                    "Sudut Pinggul (Hip Degree)",
                    "Sudut Lutut (Knee Degree)",
                    "Sudut Lengan (Arm Degree)",
                    "Jarak Pergelangan X (Wrist Dist X)",
                    "Deviasi Kepala X (Head Offset X)"
                ])
                for step in self.state_machine.completed_steps:
                    tumaninah_met_val = step.get("tumaninah_met")
                    tumaninah_str = "N/A"
                    if tumaninah_met_val is True:
                        tumaninah_str = "Ya"
                    elif tumaninah_met_val is False:
                        tumaninah_str = "Tidak"
                        
                    dev_mv = step.get("gerakan_menyimpang", [])
                    dev_mv_str = ", ".join(dev_mv) if dev_mv else "-"
                        
                    writer.writerow([
                        step.get("rakaat", 1),
                        POSE.DISPLAY_NAME.get(step.get("state"), step.get("state", "UNKNOWN")),
                        step.get("entry_time", "-"),
                        step.get("exit_time") if step.get("exit_time") else ("Selesai" if not force_cancel else "Batal"),
                        step.get("duration_seconds") if step.get("duration_seconds") is not None else "-",
                        tumaninah_str,
                        f"Ya (Bacaan: {step.get('bacaan_terpotong')})" if step.get("bacaan_terpotong") else "-",
                        dev_mv_str,
                        step.get("hip_angle", "-"),
                        step.get("knee_angle", "-"),
                        step.get("arm_angle", "-"),
                        step.get("wrist_dist_x", "-"),
                        step.get("head_offset_x", "-")
                    ])
            print(f"[LOGGER] Log CSV detail disimpan di: {csv_filename}")
        except Exception as e:
            print(f"[ERROR] Gagal menyimpan log CSV: {e}")
            
        # 2. Simpan JSON (Ringkasan Sesi - Terstruktur Sama Persis)
        json_filename = os.path.join(LOGS_DIR, f"sholat_{self.active_prayer}_{timestamp_str}.json")
        tumaninah_score = 0
        if total_tumaninah_check > 0:
            tumaninah_score = (total_tumaninah_success / total_tumaninah_check) * 100
            
        summary = {
            "sholat": self.active_prayer,
            "tanggal": self.start_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "durasi_detik": round(duration, 1),
            "status": status_str,
            "total_rakaat_dilewati": self.state_machine.rakaat_count,
            "total_rakaat": self.state_machine.rakaat_count, # backward compat
            "kesalahan_imam": self.imam_mistakes_count,
            "total_kesalahan_imam": self.imam_mistakes_count, # backward compat
            "statistik_tumaninah": {
                "total_gerakan_tumaninah": total_tumaninah_check,
                "terpenuhi": total_tumaninah_success,
                "tidak_terpenuhi": total_tumaninah_check - total_tumaninah_success,
                "skor_persentase": round(tumaninah_score, 1)
            },
            "skor_tumaninah_persen": round(tumaninah_score, 1), # backward compat
            "log_transisi": self.state_machine.completed_steps
        }
        try:
            with open(json_filename, "w") as f:
                json.dump(summary, f, indent=2)
            print(f"[LOGGER] Ringkasan JSON disimpan di: {json_filename}")
        except Exception as e:
            print(f"[ERROR] Gagal menyimpan log JSON: {e}")
            
        # Kirim laporan lengkap ke Web LMS jika sesi aktif
        if self.current_session_id:
            self.lapor_sesi_selesai(self.current_session_id, payload=dict(summary))
            
        # Tampilkan laporan evaluasi KPI di terminal
        print("\n" + "=" * 55)
        print("          LAPORAN EVALUASI SHOLAT (KPI)")
        print("=" * 55)
        print(f" Sholat      : {self.active_prayer}")
        print(f" Tanggal     : {self.start_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f" Status      : {status_str}")
        print(f" Durasi      : {round(duration, 1)} detik")
        print(f" Total Rakaat: {self.state_machine.rakaat_count}")
        print("-" * 55)
        if total_tumaninah_check > 0:
            print(f" SKOR TUMA'NINAH: {tumaninah_score:.1f}% ({total_tumaninah_success}/{total_tumaninah_check} gerakan tepat waktu)")
        else:
            print(" SKOR TUMA'NINAH: N/A (Belum melakukan gerakan ruku/sujud)")
        print(f" KESALAHAN IMAM : {self.imam_mistakes_count} kali (gerakan mendahului bacaan)")
        print("=" * 55 + "\n")
        
        # 3. Kirim laporan ke Bot Telegram (jika diaktifkan)
        if USE_TELEGRAM and TELEGRAM_CHAT_ID:
            tumaninah_kpi = f"{tumaninah_score:.1f}% ({total_tumaninah_success}/{total_tumaninah_check})" if total_tumaninah_check > 0 else "N/A"
            msg = (
                "🕌 *GEMA Imam — Laporan Sholat*\n"
                "---------------------------------\n"
                f"• *Sholat* : {self.active_prayer}\n"
                f"• *Tanggal*: {self.start_timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"• *Status* : {status_str}\n"
                f"• *Durasi* : {round(duration, 1)} detik\n"
                f"• *Rakaat* : {self.state_machine.rakaat_count}\n"
                "---------------------------------\n"
                f"📊 *KPI Evaluasi*:\n"
                f"• *Skor Tuma'ninah*: {tumaninah_kpi}\n"
                f"• *Kesalahan Imam*: {self.imam_mistakes_count} kali\n"
            )
            try:
                from telegram_notifier import send_telegram_message, send_telegram_document
                print("[TELEGRAM] Mengirim laporan KPI ke Telegram...")
                send_telegram_message(msg)
                
                # Kirim file CSV dan JSON langsung secara otomatis!
                if os.path.exists(csv_filename):
                    send_telegram_document(csv_filename, caption=f"Detail Gerakan: {os.path.basename(csv_filename)}")
                if os.path.exists(json_filename):
                    send_telegram_document(json_filename, caption=f"Ringkasan Sesi: {os.path.basename(json_filename)}")
            except Exception as e:
                print(f"[TELEGRAM WARNING] Gagal mengirim laporan/dokumen telegram: {e}")

        # 4. Rotasi log — hapus sesi terlama jika sudah > 60 sesi
        self.rotate_logs()

    def run_active_tracking_session(self):
        camera_index = ACTIVE_PROFILE["camera_index"]
        backend_str = ACTIVE_PROFILE.get("camera_backend", None)
        skip_frame_rate = ACTIVE_PROFILE.get("skip_frame", 0)
        
        is_stream = isinstance(camera_index, str) and (camera_index.startswith("http://") or camera_index.startswith("https://"))
        
        print(f"\n[AI START] Mengaktifkan Kamera! Siswa yang akan sholat: {self.current_student_name}")
        print(f"ID Sesi: {self.current_session_id}\n")
        
        if is_stream:
            cap = cv2.VideoCapture(camera_index)
        else:
            if backend_str == "v4l2":
                cap = cv2.VideoCapture(camera_index, cv2.CAP_V4L2)
            else:
                cap = cv2.VideoCapture(camera_index)
                
        if not cap.isOpened():
            err_msg = f"❌ GAGAL: Tidak bisa membuka kamera/stream: {camera_index}"
            print(err_msg)
            if is_stream:
                print("Pastikan server stream di Windows sudah berjalan.")
            if USE_TELEGRAM and TELEGRAM_CHAT_ID:
                try:
                    from telegram_notifier import send_telegram_message
                    send_telegram_message(
                        "\u274c *GEMA Imam - Kamera Tidak Terdeteksi*\n"
                        f"Sistem gagal membuka kamera (index: `{camera_index}`)."
                    )
                except Exception:
                    pass
            self.lapor_sesi_selesai(self.current_session_id)
            return
            
        # Set resolusi jika kamera lokal
        if not is_stream:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, ACTIVE_PROFILE["camera_width"])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, ACTIVE_PROFILE["camera_height"])
            cap.set(cv2.CAP_PROP_BUFFERSIZE, ACTIVE_PROFILE["buffer_size"])
            
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # Tukar lebar & tinggi jika rotasi vertikal aktif
        rotation = ACTIVE_PROFILE.get("camera_rotation", None)
        if rotation in [90, 270]:
            actual_w, actual_h = actual_h, actual_w
            
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
        cpu_temp = None
        
        # Reset state machine untuk sesi sholat baru
        self.state_machine.reset()
        self.audio_player.clear()
        self.imam_mistakes_count = 0
        
        print("\n" + "=" * 55)
        print(" GEMA IMAM RUNNING (Praktikum Aktif)")
        print("=" * 55 + "\n")
        
        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    print("[WARNING] Kamera terputus! Mencoba menghubungkan kembali dalam 5 detik...")
                    # Loop reconnect
                    reconnect_success = False
                    while not reconnect_success:
                        time.sleep(5.0)
                        print("[INFO] Mencoba menginisialisasi ulang kamera...")
                        cap.release()
                        
                        if is_stream:
                            cap = cv2.VideoCapture(camera_index)
                        else:
                            if backend_str == "v4l2":
                                cap = cv2.VideoCapture(camera_index, cv2.CAP_V4L2)
                            else:
                                cap = cv2.VideoCapture(camera_index)
                                
                        if cap.isOpened():
                            if not is_stream:
                                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
                                cap.set(cv2.CAP_PROP_FRAME_WIDTH, ACTIVE_PROFILE["camera_width"])
                                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, ACTIVE_PROFILE["camera_height"])
                                cap.set(cv2.CAP_PROP_BUFFERSIZE, ACTIVE_PROFILE["buffer_size"])
                            
                            ret_test, frame_test = cap.read()
                            if ret_test:
                                print("✅ Kamera berhasil terhubung kembali!")
                                reconnect_success = True
                                break
                    continue
                    
                if self.force_stop_session:
                    print("\n[INFO] Sesi tracking dibatalkan karena reset/Telegram/Web LMS.")
                    self.force_stop_session = False
                    break

                # Cek ke Web LMS setiap ~3 detik (non-blocking, di background
                # thread) apakah sesi ini sudah dibatalkan dari web (tombol
                # "Batalkan Sesi"). Kalau iya, check_session_cancelled_async()
                # akan memicu reset_from_button() yang men-set force_stop_session
                # (dicek di atas pada iterasi berikutnya).
                now_ts = time.time()
                if now_ts - self._last_cancel_check >= 3.0:
                    self._last_cancel_check = now_ts
                    self.check_session_cancelled_async()

                frame_count += 1
                
                # Baca suhu CPU setiap 150 frame
                if frame_count % 150 == 0:
                    cpu_temp = get_cpu_temp()
                
                # Jeda jika aplikasi di-pause
                if self.paused:
                    if HAS_DISPLAY:
                        cv2.putText(frame, "PAUSED", (actual_w // 2 - 80, actual_h // 2),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3, cv2.LINE_AA)
                        cv2.imshow("GEMA Imam", frame)
                        if cv2.waitKey(30) & 0xFF == ord('p'):
                            self.paused = False
                    continue
                
                # Rotasi frame jika diatur di profil
                rotation = ACTIVE_PROFILE.get("camera_rotation", None)
                if rotation == 90:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                elif rotation == 180:
                    frame = cv2.rotate(frame, cv2.ROTATE_180)
                elif rotation == 270:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
                
                # Mirror frame
                frame = cv2.flip(frame, 1)
                
                # Frame skipping logic
                should_process = (frame_count % (skip_frame_rate + 1)) == 0
                
                if should_process:
                    img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    last_results = self.pose_detector.process(img_rgb)
                    
                    if last_results.pose_landmarks:
                        # Terapkan filter smoothing (EMA) pada landmark
                        self.landmark_smoother.smooth(last_results.pose_landmarks)
                        
                        self._no_imam_frames = 0
                        self._no_imam_notified = False
                        
                        last_classified_pose = classify_pose(last_results.pose_landmarks)
                        last_features = get_pose_features(last_results.pose_landmarks)
                        
                        if not self.calibrating:
                            transition_info = self.state_machine.update(last_classified_pose, last_features)
                            if transition_info:
                                interrupted_files = self.audio_player.clear()
                                
                                for audio_file in interrupted_files:
                                    if audio_file in READING_AUDIOS:
                                        self.imam_mistakes_count += 1
                                        print(f"[EVALUASI IMAM] KESALAHAN: Imam berpindah gerakan sebelum bacaan '{audio_file}' selesai!")
                                        if len(self.state_machine.completed_steps) >= 2:
                                            self.state_machine.completed_steps[-2]["bacaan_terpotong"] = audio_file
                                
                                from_st = transition_info["from"]
                                to_st = transition_info["to"]
                                
                                # Logika Niat
                                if to_st == POSE.BERDIRI_TEGAK and from_st == POSE.UNKNOWN:
                                    self.play_niat_audio()
                                else:
                                    audio_trans = AUDIO_TRANSITION_MAP.get((from_st, to_st))
                                    if audio_trans:
                                        self.audio_player.play(audio_trans)
                                        
                                    if to_st == POSE.BERSEDEKAP:
                                        if transition_info["is_first_sedekap"]:
                                            self.audio_player.play("iftitah.WAV")
                                        self.audio_player.play("alfatihah.WAV")
                                        self.audio_player.play("al-ikhlas.WAV")
                                    else:
                                        audio_state = AUDIO_STATE_MAP.get(to_st)
                                        if audio_state:
                                            self.audio_player.play(audio_state)
                                
                        # Logika Kalibrasi Tinggi Badan
                        if self.calibrating:
                            elapsed_cal = time.time() - self.calibration_start_time
                            if elapsed_cal < 5.0:
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
                                if self.calibration_samples:
                                    avg_sh_y = np.mean([s[0] for s in self.calibration_samples])
                                    avg_hip_y = np.mean([s[1] for s in self.calibration_samples])
                                    avg_knee_y = np.mean([s[2] for s in self.calibration_samples])
                                    self.save_calibration(avg_sh_y, avg_hip_y, avg_knee_y)
                                self.calibrating = False
                                self.calibration_samples = []
                                print("[CALIBRATION] Selesai!")
                    else:
                        self.landmark_smoother.reset()  # Reset agar koordinat tidak lompat ketika orang masuk frame lagi
                        self._no_imam_frames += 1
                        if (self._no_imam_frames >= self._NO_IMAM_ALERT_FRAMES
                                and not self._no_imam_notified
                                and self.state_machine.current_state not in (POSE.SELESAI, POSE.UNKNOWN)):
                            self._no_imam_notified = True
                            print("[WARNING] Imam tidak terdeteksi selama >60 detik!")
                
                # Penanganan akhir sholat (salam kedua selesai) -> auto-reset untuk sholat berikutnya
                if self.state_machine.current_state == POSE.SELESAI:
                    print("[INFO] Sesi sholat selesai dengan sempurna. Mengirim laporan ke Web LMS...")
                    self.save_session_logs(force_cancel=False)
                    break
                elif self.state_machine.current_state == POSE.SALAM_KE_KIRI:
                    if self.audio_player.queue.empty() and not self.audio_player.current_playing_file:
                        print("[INFO] Audio Salam Ke Kiri selesai diputar. Menunggu jeda 5 detik...")
                        time.sleep(5.0)
                        self.state_machine._commit_transition(POSE.SELESAI, last_features)
                                
                # Hitung FPS
                elapsed = time.time() - start_time
                fps = frame_count / elapsed if elapsed > 0 else 0.0
                
                # UI Rendering
                if HAS_DISPLAY:
                    if last_results and last_results.pose_landmarks:
                        visualizer.draw_skeleton(frame, last_results.pose_landmarks)
                        if self.debug_mode and last_features:
                            visualizer.draw_debug_angles(frame, last_results.pose_landmarks, last_features)
                        visualizer.draw_alignment_guide(frame, last_results.pose_landmarks)
                    else:
                        visualizer.draw_alignment_guide(frame, None)
                            
                    visualizer.draw_hud(
                        frame,
                        self.state_machine.current_state,
                        self.active_prayer,
                        self.state_machine.rakaat_count,
                        fps,
                        self.state_machine.hold_counter,
                        self.state_machine.max_hold_frames,
                        cpu_temp
                    )
                    
                    if self.calibrating:
                        elapsed_cal = time.time() - self.calibration_start_time
                        remaining = max(0.0, 5.0 - elapsed_cal)
                        cv2.rectangle(frame, (10, actual_h - 60), (450, actual_h - 10), (0, 0, 0), -1)
                        cv2.putText(frame, f"KALIBRASI: Berdiri Tegak ({remaining:.1f}s)", 
                                    (20, actual_h - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2, cv2.LINE_AA)
                    
                    cv2.imshow("GEMA Imam", frame)
                    
                    key = cv2.waitKey(1) & 0xFF
                    if key == KEY_QUIT:
                        print("[INFO] Menutup sesi sholat secara paksa via keyboard shortcut.")
                        self.audio_player.clear()
                        self.save_session_logs(force_cancel=True)
                        break
                    elif key == KEY_RESET:
                        self.reset_from_button()
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
                            self.play_niat_audio()
                            self.start_session_logging()
                else:
                    if frame_count % 30 == 0:
                        temp_str = f" | CPU Temp: {cpu_temp}°C" if cpu_temp is not None else ""
                        print(f"[Active Session] Frame: {frame_count} | FPS: {fps:.1f} | Pose: {last_classified_pose} | State: {self.state_machine.current_state} (Rakaat {self.state_machine.rakaat_count}){temp_str}")
                        
        except KeyboardInterrupt:
            print("\n[INFO] Sesi sholat dihentikan via KeyboardInterrupt.")
            self.save_session_logs(force_cancel=True)
        except Exception as crash_err:
            import traceback
            tb_str = traceback.format_exc()
            print(f"\n[CRITICAL] Sesi sholat crash: {crash_err}")
            print(tb_str)
            self.save_session_logs(force_cancel=True)
        finally:
            cap.release()
            print(f"\nSesi selesai. Rata-rata FPS: {fps:.1f}")

    def run(self):
        # Start button listener (GPIO atau keyboard)
        self.button_listener.start()
        
        # Mulai Telegram command listener jika chat ID aktif
        if self.telegram_listener:
            try:
                self.telegram_listener.start()
                self._send_startup_notification()
            except Exception as e:
                print(f"[TELEGRAM CMD WARNING] Gagal memulai command listener: {e}")
                
        print("\n==================================================")
        print(" GEMA IMAM STANDBY MODE ACTIVE")
        print(" Menunggu instruksi praktikum dari Web LMS...")
        print("==================================================\n")
        
        try:
            while True:
                # 1. Tanya Web LMS apakah ada praktikum aktif
                status_data = self.check_web_status()
                
                if status_data.get("status") == "active":
                    session_id = status_data.get("session_id")
                    student_name = status_data.get("student_name")
                    
                    self.current_session_id = session_id
                    self.current_student_name = student_name
                    
                    # 2. Jalankan sesi AI aktif
                    self.run_active_tracking_session()
                    
                    print("\n==================================================")
                    print(" GEMA IMAM STANDBY MODE ACTIVE")
                    print(" Menunggu instruksi praktikum dari Web LMS...")
                    print("==================================================\n")
                    
                    self.current_session_id = None
                    self.current_student_name = None
                else:
                    # Cek apakah Web LMS meminta ganti speaker Bluetooth
                    requested_mac = status_data.get("bluetooth_mac", "").strip().upper()
                    if requested_mac and requested_mac != self._last_bt_mac:
                        print(f"[BT] Web LMS meminta ganti speaker ke: {requested_mac}")
                        def _switch_bt(mac=requested_mac):
                            from telegram_notifier import connect_bluetooth
                            ok, msg = connect_bluetooth(mac)
                            if ok:
                                self._last_bt_mac = mac
                                print(f"[BT] ✅ Speaker diganti ke {mac} atas perintah Web LMS.")
                            else:
                                print(f"[BT] ⚠️  Gagal ganti speaker ke {mac}: {msg}")
                        import threading
                        threading.Thread(target=_switch_bt, daemon=True, name="BtSwitchWeb").start()

                    # 3. Mode Standby
                    if HAS_DISPLAY:
                        # Render dan tampilkan frame standby estetik di GUI
                        self.show_standby_frame()
                        key = cv2.waitKey(100) & 0xFF
                        if key == ord('q'):
                            print("[INFO] Menutup program secara manual dari mode Standby.")
                            break
                    else:
                        # Headless mode standby log
                        print("[Standby] Menunggu instruksi 'active' dari Web LMS...", end="\r")
                        time.sleep(2)
        finally:
            self.button_listener.stop()
            if self.telegram_listener:
                self.telegram_listener.stop()
            if HAS_DISPLAY:
                cv2.destroyAllWindows()

if __name__ == '__main__':
    print("=" * 55)
    print(" GEMA Imam — Sholat Tracking System")
    print("=" * 55)
    app = GemaImamApp()
    app.run()
