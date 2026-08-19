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
import random
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
from haptic_notifier import HapticNotifier

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
    "alfatihah.WAV", "al-ikhlas.WAV", "al-falaq.WAV", "an-nas.WAV",
    "an-nasr.WAV", "ruku.WAV", "itidal.WAV",
    "sujud.WAV", "iftirasy.WAV", "tasyahud-awal.WAV", "tasyahud-akhir.WAV",
    "iftitah.WAV", "iqomah.WAV"
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
    def _find_player(candidates=("aplay", "paplay", "ffplay", "mpg123")):
        """Mencari audio player yang tersedia di sistem, dari daftar kandidat
        yang diberikan (default: player untuk WAV)."""
        for player in candidates:
            result = subprocess.run(["which", player], capture_output=True, text=True)
            if result.returncode == 0:
                return player.strip()
        return None

    def _worker(self):
        # Player default (aplay/paplay) dipilih sekali di sini untuk semua
        # bacaan .WAV — ini yang mayoritas dan paling sensitif ke latensi
        # (dipicu tepat waktu oleh state machine gerakan sholat).
        player = self._find_player()
        # aplay/paplay TIDAK bisa decode mp3 (mis. doa.mp3, bukan bagian dari
        # bacaan gerakan) — perlu player compressed-audio terpisah, dicari
        # baru saat file mp3 pertama benar-benar mau diputar (lazy, supaya
        # tidak menambah subprocess `which` di startup kalau tidak dipakai).
        mp3_player = None
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

                is_mp3 = filepath.lower().endswith(".mp3")

                if sys.platform.startswith("win"):
                    import winsound
                    winsound.PlaySound(filepath, winsound.SND_FILENAME)
                elif sys.platform.startswith("darwin"):
                    self.active_process = subprocess.Popen(["afplay", filepath], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self.active_process.wait()
                elif is_mp3:
                    if mp3_player is None:
                        mp3_player = self._find_player(("mpg123", "ffplay")) or ""
                    if mp3_player == "mpg123":
                        cmd = ["mpg123", "-q", filepath]
                    elif mp3_player == "ffplay":
                        cmd = ["ffplay", "-nodisp", "-autoexit", filepath]
                    else:
                        cmd = None
                        print(f"[AUDIO WARNING] Tidak ada player mp3 (mpg123/ffplay) — {os.path.basename(filepath)} dilewati.")
                    if cmd:
                        self.active_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        self.haptic = HapticNotifier()
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
        # Deskripsi kegagalan terakhir dari check_session_cancelled_async() —
        # fungsi itu sebelumnya menelan semua Exception diam-diam (termasuk
        # kegagalan jaringan), jadi kalau pollingnya berhenti berhasil di
        # tengah sesi (mis. preview_requested tidak ter-update lagi), tidak
        # ada petunjuk sama sekali di console. Sama seperti pola
        # _last_status_error di check_web_status().
        self._last_cancel_check_error = None
        # Diisi dari respons check_session_cancelled_async() (field
        # "preview_requested"), dibaca oleh run_active_tracking_session()
        # untuk tahu kapan harus mengirim frame pratinjau "Lihat Kamera" ke
        # Web LMS — lihat send_preview_frame().
        self._preview_requested = False
        self._last_preview_send = 0.0
        # Deskripsi kegagalan terakhir dari check_web_status() — dipakai supaya
        # kegagalan yang sama tidak nge-print berulang tiap poll (tiap ~100ms-2s),
        # tapi tetap kelihatan begitu errornya muncul atau berubah jenis.
        self._last_status_error = None
        # MAC address speaker Bluetooth yang terakhir berhasil terhubung
        # (diisi dari .env saat startup, diperbarui saat /bt atau Web LMS request)
        from config import BLUETOOTH_SPEAKER_MAC
        self._last_bt_mac = BLUETOOTH_SPEAKER_MAC or ""
        # Sesi yang diminta via Telegram (dict: session_id, student_name, prayer)
        # Diset oleh /mulai command; dikonsumsi dan di-None-kan oleh standby loop
        self._pending_session = None
        # Penampung URL foto evaluasi Cloudinary per gerakan (key: "state_rakaat")
        self._captured_images = {}
        # Thread upload foto yang sedang berjalan di background — di-join sebentar
        # saat sesi ditutup supaya foto gerakan terakhir sempat masuk laporan
        self._upload_threads = []


        # Deteksi imam tidak terdeteksi
        self._no_imam_frames = 0
        self._no_imam_notified = False
        self._NO_IMAM_ALERT_FRAMES = 60 * 15  # ~60 detik pada 15fps (sesuaikan ke FPS platform)

        # Inisialisasi Detektor Chat ID Telegram otomatis saat startup jika kosong
        if USE_TELEGRAM and not TELEGRAM_CHAT_ID:
            self.run_telegram_setup_helper()

        # Inisialisasi Telegram command listener (jika chat ID sudah dikonfigurasi)
        # (Akan di-start di method run() untuk mencegah double-start)
        self.telegram_listener = None
        if USE_TELEGRAM and TELEGRAM_CHAT_ID:
            try:
                from telegram_notifier import TelegramCommandListener
                self.telegram_listener = TelegramCommandListener(app_ref=self)
            except Exception as e:
                print(f"[TELEGRAM CMD WARNING] Gagal menginisialisasi command listener: {e}")

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
                self._last_status_error = None
                return response.json()

            # Server menjawab tapi menolak/gagal (mis. 401 API key salah,
            # 500 error server) — dulu ini ditelan diam-diam dan terlihat
            # PERSIS SAMA seperti "idle" biasa, jadi tidak ada petunjuk sama
            # sekali kalau alat tidak pernah berhasil polling dengan benar.
            error_desc = f"HTTP {response.status_code}: {response.text[:200]}"
            if error_desc != self._last_status_error:
                print(f"\n[WEB LMS WARNING] Polling ke {url} gagal — {error_desc}")
                self._last_status_error = error_desc
        except Exception as e:
            error_desc = f"{type(e).__name__}: {e}"
            if error_desc != self._last_status_error:
                print(f"\n[WEB LMS WARNING] Tidak bisa menghubungi {url} — {error_desc}")
                self._last_status_error = error_desc

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
                    self._last_cancel_check_error = None
                    data = response.json()
                    # Dibaca oleh run_active_tracking_session() (throttle
                    # sendiri ~1x/detik di sana) — piggyback di poll ~3
                    # detik yang sudah ada ini, tidak perlu request baru.
                    self._preview_requested = bool(data.get("preview_requested", False))
                    if data.get("active") is False and not self.force_stop_session:
                        # Jawaban "not active" yang telat bisa juga berarti sesi ini
                        # BARU SAJA selesai secara alami (sudah dilaporkan "Selesai"),
                        # bukan berarti dibatalkan dari web — cek dua hal sebelum
                        # bertindak: (1) ini masih sesi yang sama yang sedang berjalan
                        # (bukan cek basi untuk sesi lama setelah sesi baru dimulai),
                        # dan (2) state machine belum mencapai POSE.SELESAI duluan.
                        if (session_id == self.current_session_id
                                and self.state_machine.current_state != POSE.SELESAI):
                            print("[WEB LMS] Sesi dibatalkan dari Web LMS (tombol 'Batalkan Sesi').")
                            self.reset_from_button()
                else:
                    error_desc = f"HTTP {response.status_code}: {response.text[:200]}"
                    if error_desc != self._last_cancel_check_error:
                        print(f"\n[WEB LMS WARNING] Cek status sesi (poll ~3 detik) gagal — {error_desc}")
                        self._last_cancel_check_error = error_desc
            except Exception as e:
                error_desc = f"{type(e).__name__}: {e}"
                if error_desc != self._last_cancel_check_error:
                    print(f"\n[WEB LMS WARNING] Tidak bisa cek status sesi (poll ~3 detik) — {error_desc}")
                    self._last_cancel_check_error = error_desc
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

    def upload_pose_image(self, jpeg_bytes, img_key):
        """Unggah satu foto evaluasi (JPEG) ke Cloudinary lewat Web LMS.
        Dipanggil di background thread (lihat pemanggilnya) supaya tidak
        memblokir loop pemrosesan frame menunggu upload selesai. URL yang
        didapat disimpan ke self._captured_images; kalau gagal, foto itu
        cuma jadi None di laporan akhir — bukan alasan sesi gagal total."""
        if not WEB_LMS_URL:
            return

        url = f"{WEB_LMS_URL.rstrip('/')}/api/iot/media/upload"
        headers = {"x-api-key": WEB_LMS_API_KEY}
        try:
            res = requests.post(
                url,
                headers=headers,
                files={"file": (f"{img_key}.jpg", jpeg_bytes, "image/jpeg")},
                timeout=8,
            )
            if res.status_code == 200:
                data = res.json()
                if data.get("success") and data.get("url"):
                    self._captured_images[img_key] = data["url"]
                    return
            print(f"[MEDIA UPLOAD WARNING] Gagal unggah foto '{img_key}': HTTP {res.status_code}")
        except Exception as e:
            print(f"[MEDIA UPLOAD WARNING] Gagal unggah foto '{img_key}': {e}")

    def send_preview_frame(self, jpeg_bytes):
        """Kirim satu frame kamera saat ini ke Web LMS untuk panel "Lihat
        Kamera" guru — dipanggil di background thread (lihat pemanggilnya
        di run_active_tracking_session) supaya tidak memblokir loop
        pemrosesan frame. Ini cuma pratinjau langsung, bukan arsip: tidak
        disimpan di mana pun di sisi Pi, dan Web LMS sendiri cuma menyimpan
        frame terakhir di memori (bukan Cloudinary/DB). Gagal kirim tidak
        menghentikan sesi (sama seperti upload_pose_image) tapi TETAP
        dicetak ke console — sebelumnya ini gagal 100% diam-diam, yang
        membuat masalah pengiriman frame pratinjau mustahil didiagnosis
        dari sisi Pi."""
        if not WEB_LMS_URL:
            return

        url = f"{WEB_LMS_URL.rstrip('/')}/api/iot/preview/frame"
        headers = {"x-api-key": WEB_LMS_API_KEY}
        try:
            res = requests.post(
                url,
                headers=headers,
                files={"file": ("preview.jpg", jpeg_bytes, "image/jpeg")},
                timeout=3,
            )
            if res.status_code != 200:
                print(f"[PREVIEW UPLOAD WARNING] Gagal kirim frame pratinjau: HTTP {res.status_code}: {res.text[:200]}")
        except Exception as e:
            print(f"[PREVIEW UPLOAD WARNING] Gagal kirim frame pratinjau: {e}")

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
        """Menyimpan ringkasan sesi sholat ke file JSON."""
        if not self.start_timestamp:
            return
            
        timestamp_str = self.start_timestamp.strftime("%Y%m%d_%H%M%S")
        status_str = "Dibatalkan" if force_cancel else "Selesai"
        duration = (datetime.now() - self.start_timestamp).total_seconds()
        
        # Tutup entry gerakan terakhir yang masih terbuka (belum ada exit_time)
        # supaya datanya tidak hilang — TANPA menduplikasi entry yang sudah dibuat
        # oleh _commit_transition() saat gerakan ini dimulai. (Kode lama selalu
        # menambah entry BARU di sini, jadi gerakan yang lagi berjalan saat sesi
        # berakhir — dibatalkan ataupun selesai wajar — selalu tercatat dua kali,
        # salah satunya dengan entry_time palsu "00:00:00".)
        if self.state_machine.current_state != POSE.UNKNOWN:
            steps = self.state_machine.completed_steps
            last_step = steps[-1] if steps else None

            if (last_step
                    and last_step.get("state") == self.state_machine.current_state
                    and last_step.get("exit_time") is None):
                # Entry gerakan ini sudah ada — cukup lengkapi exit_time & durasinya.
                duration_last = 0.0
                if self.state_machine.state_start_time is not None:
                    duration_last = time.time() - self.state_machine.state_start_time
                last_step["exit_time"] = time.strftime("%H:%M:%S") if not force_cancel else "Batal"
                last_step["duration_seconds"] = round(duration_last, 2)
            else:
                # Fallback langka: belum ada entry untuk state ini sama sekali —
                # catat seadanya supaya datanya tidak hilang.
                self.state_machine.completed_steps.append({
                    "rakaat": self.state_machine.rakaat_count,
                    "state": self.state_machine.current_state,
                    "entry_time": "00:00:00",
                    "exit_time": time.strftime("%H:%M:%S") if not force_cancel else "Batal",
                    "duration_seconds": None,
                    "tumaninah_met": None,
                    "bacaan_terpotong": None,
                    "gerakan_menyimpang": [],
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
        
        # Tunggu upload foto yang masih berjalan (maks ~3 detik total) supaya foto
        # dari gerakan-gerakan terakhir sempat masuk sebelum laporan dikirim —
        # upload jalan di background thread, jadi tidak semuanya pasti selesai
        # tepat saat sesi berakhir.
        if self._upload_threads:
            deadline = time.time() + 3.0
            for t in self._upload_threads:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                t.join(timeout=remaining)
            self._upload_threads = []

        # Sematkan URL foto evaluasi (Cloudinary) ke setiap langkah gerakan transisi
        for step in self.state_machine.completed_steps:
            img_key = f"{step.get('state')}_{step.get('rakaat')}"
            step["foto_pose_url"] = self._captured_images.get(img_key, None)

        # Simpan JSON (Ringkasan + Detail Lengkap)
        json_filename = os.path.join(LOGS_DIR, f"sholat_{self.active_prayer}_{timestamp_str}.json")
        tumaninah_score = 0
        if total_tumaninah_check > 0:
            tumaninah_score = (total_tumaninah_success / total_tumaninah_check) * 100
            
        summary = {
            "session_id": self.current_session_id,
            "sholat": self.active_prayer,
            "tanggal": self.start_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "durasi_detik": round(duration, 1),
            "status": status_str,
            "total_rakaat_dilewati": self.state_machine.rakaat_count,
            "total_rakaat": self.state_machine.rakaat_count,
            "kesalahan_imam": self.imam_mistakes_count,
            "total_kesalahan_imam": self.imam_mistakes_count,
            "statistik_tumaninah": {
                "total_gerakan_tumaninah": total_tumaninah_check,
                "terpenuhi": total_tumaninah_success,
                "tidak_terpenuhi": total_tumaninah_check - total_tumaninah_success,
                "skor_persentase": round(tumaninah_score, 1)
            },
            "skor_tumaninah_persen": round(tumaninah_score, 1),
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
                
                # Kirim file JSON secara otomatis
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
        self._captured_images = {}
        self._upload_threads = []
        self.audio_player.clear()
        self.audio_player.play("ready.wav")
        self.imam_mistakes_count = 0
        self._preview_requested = False
        self._last_preview_send = 0.0
        
        # Variabel pelacak waktu selesai audio untuk auto-transition
        self._audio_completed_timestamp = None
        self._last_checked_state = None
        
        # Variabel pelacak status audio untuk trigger haptic (modul getar)
        self._prev_audio_playing = False
        
        # Buat daftar surat pendek acak untuk sesi sholat ini
        # Kumpulkan semua surat pendek yang ada di folder audio
        available_surahs = ["al-ikhlas.WAV", "al-falaq.WAV", "an-nas.WAV", "an-nasr.WAV"]
        random.shuffle(available_surahs)
        self._session_surahs = available_surahs
        print(f"[AUDIO] Surat pendek yang akan dibaca (acak): {self._session_surahs[:2]}")
        
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

                # Kirim frame pratinjau ke panel "Lihat Kamera" guru di Web
                # LMS kalau sedang diminta (flag diisi oleh
                # check_session_cancelled_async() di atas, dari field
                # "preview_requested" pada respons /api/iot/status yang
                # sudah dipoll ~3 detik itu juga — tidak ada request baru).
                # Throttle sendiri ke ~1x/detik supaya tidak ikut membebani
                # loop pemrosesan frame walau flag-nya true terus. Diambil
                # DI SINI, setelah rotasi+mirror di atas — sebelumnya ini
                # ada sebelum baris rotasi, jadi preview di web selalu
                # menampilkan frame mentah kamera (miring 90 derajat sesuai
                # pemasangan fisik), sementara HUD lokal dan deteksi pose
                # sudah benar karena keduanya memakai `frame` yang sudah
                # dikoreksi di sini.
                if self._preview_requested and now_ts - self._last_preview_send >= 1.0:
                    self._last_preview_send = now_ts
                    try:
                        h, w = frame.shape[:2]
                        preview_frame = cv2.resize(frame, (480, int(h * 480 / w))) if w > 480 else frame
                        success, encoded_preview = cv2.imencode(
                            '.jpg', preview_frame, [cv2.IMWRITE_JPEG_QUALITY, 60]
                        )
                        if success:
                            threading.Thread(
                                target=self.send_preview_frame,
                                args=(encoded_preview.tobytes(),),
                                daemon=True,
                                name="PreviewFrameUpload",
                            ).start()
                    except Exception as preview_err:
                        print(f"[WARNING] Gagal menyiapkan frame pratinjau: {preview_err}")

                # Frame skipping logic
                should_process = (frame_count % (skip_frame_rate + 1)) == 0
                
                if should_process:
                    img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    last_results = self.pose_detector.process(img_rgb)
                    
                    if last_results.pose_landmarks:
                        # ── SOLUSI A: FILTER UKURAN IMAM (Shoulder Size Filter) ──
                        # Imam selalu lebih dekat ke kamera → bahu lebih lebar di frame.
                        # Jika jarak bahu kiri-kanan < 12% lebar frame, kemungkinan besar
                        # ini adalah makmum di belakang imam → abaikan deteksi ini.
                        lm = last_results.pose_landmarks.landmark
                        _sh_l_x = lm[self.mp_pose.PoseLandmark.LEFT_SHOULDER].x
                        _sh_r_x = lm[self.mp_pose.PoseLandmark.RIGHT_SHOULDER].x
                        _shoulder_width = abs(_sh_r_x - _sh_l_x)
                        if _shoulder_width < 0.11:
                            # Deteksi terlalu kecil → bukan imam → lewati frame ini
                            self._no_imam_frames += 1
                            continue

                        # Terapkan filter smoothing (EMA) pada landmark
                        self.landmark_smoother.smooth(last_results.pose_landmarks)
                        
                        self._no_imam_frames = 0
                        self._no_imam_notified = False
                        
                        last_classified_pose = classify_pose(last_results.pose_landmarks)
                        last_features = get_pose_features(last_results.pose_landmarks)
                        
                        if not self.calibrating:
                            transition_info = None
                            
                            # ── LOGIKA AUTO-TRANSITION SITUASIONAL (3 DETIK SETELAH BACAAN SELESAI) ──
                            curr_state = self.state_machine.current_state
                            monitored_states = {
                                POSE.BERSEDEKAP: POSE.RUKUK,
                                POSE.ITIDAL: POSE.SUJUD_PERTAMA,
                                POSE.DUDUK_DI_ANTARA_DUA_SUJUD: POSE.SUJUD_KEDUA,
                                POSE.DUDUK_TASYAHUD_AKHIR: POSE.SALAM_KE_KANAN,
                                POSE.SALAM_KE_KANAN: POSE.SALAM_KE_KIRI,
                            }
                            
                            if curr_state in monitored_states:
                                # Periksa apakah audio playlist di state ini sedang aktif diputar
                                is_audio_playing = not self.audio_player.queue.empty() or self.audio_player.current_playing_file is not None
                                
                                # Reset timer jika baru memasuki state baru
                                if curr_state != self._last_checked_state:
                                    self._last_checked_state = curr_state
                                    self._audio_completed_timestamp = None
                                
                                # Catat waktu ketika audio selesai diputar
                                if not is_audio_playing and self._audio_completed_timestamp is None:
                                    self._audio_completed_timestamp = time.time()
                                    print(f"[AUTO-TRANSITION] Playlist audio untuk {curr_state} selesai. Timer 3 detik dimulai...")
                                
                                # Jika timer aktif, periksa apakah sudah melebihi 3 detik
                                if self._audio_completed_timestamp is not None:
                                    elapsed = time.time() - self._audio_completed_timestamp
                                    if elapsed >= 3.0:
                                        target_state = monitored_states[curr_state]
                                        print(f"[AUTO-TRANSITION] Pose {target_state} belum terdeteksi setelah 3 detik. Memicu transisi otomatis...")
                                        transition_info = self.state_machine._commit_transition(target_state, last_features)
                                        # Reset timer
                                        self._audio_completed_timestamp = None
                                        self._last_checked_state = None
                            
                            # ── LOGIKA HOLD STATE HINGGA BACAAN AUDIO SELESAI ──
                            hold_audio_states = {
                                POSE.RUKUK,
                                POSE.DUDUK_TASYAHUD_AWAL,
                                POSE.DUDUK_TASYAHUD_AKHIR,
                                POSE.SALAM_KE_KANAN,
                                POSE.SALAM_KE_KIRI
                            }
                            
                            is_audio_playing = not self.audio_player.queue.empty() or self.audio_player.current_playing_file is not None

                            # ── TRIGGER MODUL GETAR: audio selesai secara alami ──
                            # Jika audio baru saja selesai (True→False) DAN bukan karena
                            # state transition (clear() paksa) → kirim sinyal getar ke ESP32
                            if self._prev_audio_playing and not is_audio_playing and transition_info is None:
                                self.haptic.notify()
                            self._prev_audio_playing = is_audio_playing

                            # Fallback: Jika tidak terjadi auto-transition, lakukan pencocokan klasifikasi pose normal
                            if transition_info is None:
                                if curr_state in hold_audio_states and is_audio_playing:
                                    # Audio bacaan masih diputar -> tahan (hold) state saat ini
                                    transition_info = None
                                else:
                                    transition_info = self.state_machine.update(last_classified_pose, last_features)
                                
                            if transition_info:
                                # Kirim sinyal 1x getar ke ESP32 saat masuk ke gerakan baru
                                self.haptic.notify_start()

                                interrupted_files = self.audio_player.clear()
                                
                                for audio_file in interrupted_files:
                                    if audio_file in READING_AUDIOS:
                                        self.imam_mistakes_count += 1
                                        print(f"[EVALUASI IMAM] KESALAHAN: Imam berpindah gerakan sebelum bacaan '{audio_file}' selesai!")
                                        if len(self.state_machine.completed_steps) >= 2:
                                            self.state_machine.completed_steps[-2]["bacaan_terpotong"] = audio_file
                                
                                from_st = transition_info["from"]
                                to_st = transition_info["to"]

                                # 📸 Capture gambar evaluasi (dengan visualisasi skeleton), lalu
                                # unggah ke Cloudinary di background thread — non-blocking supaya
                                # loop pemrosesan frame tidak nge-lag menunggu upload selesai.
                                try:
                                    # Copy frame agar gambar HUD asli tidak terganggu
                                    eval_frame = frame.copy()
                                    if last_results and last_results.pose_landmarks:
                                        # Gambar skeleton pose di atas frame copy
                                        visualizer.draw_skeleton(eval_frame, last_results.pose_landmarks)
                                        if last_features:
                                            visualizer.draw_debug_angles(eval_frame, last_results.pose_landmarks, last_features)

                                    # Perkecil resolusi ke 320x240 agar upload hemat & cepat
                                    eval_frame_resized = cv2.resize(eval_frame, (320, 240))

                                    # Compress ke format JPEG dengan kualitas 60% (~6-10 KB per gambar)
                                    success, encoded_img = cv2.imencode('.jpg', eval_frame_resized, [cv2.IMWRITE_JPEG_QUALITY, 60])
                                    if success:
                                        # Simpan di memory dengan key format "state_rakaat"
                                        img_key = f"{to_st}_{self.state_machine.rakaat_count}"
                                        upload_thread = threading.Thread(
                                            target=self.upload_pose_image,
                                            args=(encoded_img.tobytes(), img_key),
                                            daemon=True,
                                            name=f"PoseUpload-{img_key}",
                                        )
                                        self._upload_threads.append(upload_thread)
                                        upload_thread.start()
                                except Exception as img_err:
                                    print(f"[WARNING] Gagal mengambil gambar evaluasi: {img_err}")

                                # Putar audio transisi (Takbir Intiqal / Tasmi')
                                audio_trans = AUDIO_TRANSITION_MAP.get((from_st, to_st))
                                if audio_trans:
                                    self.audio_player.play(audio_trans)

                                # Putar audio state yang baru dimasuki
                                if to_st == POSE.BERSEDEKAP:
                                    if transition_info["is_first_sedekap"]:
                                        self.audio_player.play("iftitah.WAV")
                                    self.audio_player.play("alfatihah.WAV")
                                    
                                    # Surat pendek hanya dibaca pada rakaat 1 dan rakaat 2
                                    if self.state_machine.rakaat_count in (1, 2):
                                        # Ambil surat dari array acak berdasarkan index rakaat (rakaat_count - 1)
                                        idx = self.state_machine.rakaat_count - 1
                                        if hasattr(self, '_session_surahs') and idx < len(self._session_surahs):
                                            surah_to_play = self._session_surahs[idx]
                                        else:
                                            surah_to_play = "al-ikhlas.WAV"  # fallback default
                                        self.audio_player.play(surah_to_play)
                                        print(f"[AUDIO] Rakaat {self.state_machine.rakaat_count}: Membaca surat pendek '{surah_to_play}'")
                                    else:
                                        print(f"[AUDIO] Rakaat {self.state_machine.rakaat_count}: Melewati pembacaan surat pendek (hanya Al-Fatihah)")
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
        self.audio_player.play("standby.wav")
        
        try:
            while True:
                # 1a. Cek sesi yang diminta via Telegram (/mulai)
                #     Prioritas lebih tinggi dari Web LMS agar bisa dipakai tanpa koneksi web
                if self._pending_session:
                    pending = self._pending_session
                    self._pending_session = None          # konsumsi, agar tidak loop terus

                    self.current_session_id   = pending["session_id"]
                    self.current_student_name = pending["student_name"]
                    # Ganti prayer type sesuai permintaan /mulai
                    new_prayer = pending.get("prayer", self.active_prayer)
                    if new_prayer != self.active_prayer:
                        self.active_prayer = new_prayer
                        from state_machine import SholatStateMachine
                        self.state_machine = SholatStateMachine(new_prayer)

                    print(f"[TELEGRAM] Sesi dimulai dari Telegram → Siswa: {self.current_student_name} | Sholat: {self.active_prayer}")
                    self.run_active_tracking_session()

                    print("\n==================================================")
                    print(" GEMA IMAM STANDBY MODE ACTIVE")
                    print(" Menunggu instruksi praktikum dari Web LMS / Telegram...")
                    print("==================================================\n")
                    self.audio_player.play("standby.wav")

                    self.current_session_id   = None
                    self.current_student_name = None
                    continue

                # 1b. Tanya Web LMS apakah ada praktikum aktif
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
                    print(" Menunggu instruksi praktikum dari Web LMS / Telegram...")
                    print("==================================================\n")
                    self.audio_player.play("standby.wav")
                    
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

                    # Cek apakah guru minta putar Dzikir & Doa Penutup dari
                    # Web LMS. Sengaja hanya dicek di sini (standby, bukan
                    # selagi sesi ACTIVE direkam) — server hanya menyertakan
                    # doa_requested pada balasan idle (lihat
                    # src/app/api/iot/status/route.ts di repo lms), justru
                    # supaya tidak menyela antrean audio bacaan gerakan yang
                    # real-time kalau tombolnya kepencet di tengah sesi.
                    if status_data.get("doa_requested"):
                        print("[WEB LMS] Guru meminta putar Dzikir & Doa Penutup.")
                        self.audio_player.play("doa.mp3")

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
            self.haptic.stop()
            if self.telegram_listener:
                self.telegram_listener.stop()
            if HAS_DISPLAY:
                cv2.destroyAllWindows()

if __name__ == '__main__':
    print("=" * 55)
    print(" GEMA Imam — Sholat Tracking System")
    print("=" * 55)
    # Cetak status konfigurasi Web LMS di awal — tanpa ini, kalau
    # WEB_LMS_URL kosong (mis. .env tidak ke-load), alat cuma diam di
    # STANDBY MODE selamanya tanpa ada petunjuk kenapa "Mulai Sesi" di
    # website tidak pernah terdeteksi.
    if WEB_LMS_URL:
        print(f" [CONFIG] WEB_LMS_URL   : {WEB_LMS_URL}")
        print(f" [CONFIG] WEB_LMS_API_KEY: {'(terisi)' if WEB_LMS_API_KEY else '(KOSONG!)'}")
    else:
        print(" [CONFIG] ⚠️  WEB_LMS_URL KOSONG — polling ke Web LMS DINONAKTIFKAN.")
        print(" [CONFIG] ⚠️  Cek apakah .env ada & ter-load dengan benar sebelum lapor 'tidak terdeteksi'.")
    print("=" * 55)
    app = GemaImamApp()
    app.run()
