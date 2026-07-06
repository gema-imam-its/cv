"""
============================================================
GEMA Imam — Sholat Movement Tracking
config.py — Semua konstanta, threshold, dan konfigurasi hardware
============================================================

Cara pakai:
    from config import ACTIVE_PROFILE, SHOLAT_CONFIG, THRESHOLDS, LANDMARK

Untuk deploy ke Orange Pi 4 Pro, ganti:
    PLATFORM = "opi4pro"
"""

# ─────────────────────────────────────────────────────────────
# 1. PILIHAN PLATFORM
# ─────────────────────────────────────────────────────────────
# Ganti ke "opi4pro" saat deploy ke Orange Pi 4 Pro
PLATFORM = "laptop"  # "laptop" | "opi4pro"

HARDWARE_PROFILES = {
    "laptop": {
        "model_complexity":  1,      # 0=Lite, 1=Full, 2=Heavy
        "camera_index":      "stream", # "stream" untuk streaming dari Windows, atau integer (e.g. 0) untuk lokal
        "camera_backend":    None,   # None = auto, atau cv2.CAP_V4L2
        "camera_width":      640,    # Diturunkan ke 640x480 untuk streaming lebih lancar
        "camera_height":     480,
        "camera_fps":        30,
        "buffer_size":       1,
        "skip_frame":        0,      # 0 = proses setiap frame
        "camera_rotation":   None,   # Rotasi kamera: None, 90, 180, atau 270 (dalam derajat CW)
        "min_detection_conf": 0.7,
        "min_tracking_conf":  0.7,
    },
    "opi4pro": {
        "model_complexity":  0,      # Lite — paling ringan untuk ARM CPU
        "camera_index":      0,
        "camera_backend":    "v4l2", # wajib V4L2 di Linux embedded
        "camera_width":      640,
        "camera_height":     480,
        "camera_fps":        15,
        "buffer_size":       1,
        "skip_frame":        1,      # proses 1 dari 2 frame (frame skipping)
        "camera_rotation":   None,   # Rotasi kamera: None, 90, 180, atau 270 (dalam derajat CW)
        "min_detection_conf": 0.6,   # sedikit diturunkan untuk toleransi
        "min_tracking_conf":  0.6,
    },
}

def get_wsl_host_ip():
    """Mendapatkan IP host Windows dari dalam WSL2 untuk koneksi streaming."""
    import subprocess
    try:
        # Membaca IP gateway default WSL2
        route = subprocess.check_output("ip route show | grep default", shell=True).decode()
        return route.split()[2]
    except Exception:
        try:
            with open("/etc/resolv.conf", "r") as f:
                for line in f:
                    if "nameserver" in line:
                        return line.split()[1]
        except Exception:
            return "127.0.0.1"

# Profile aktif yang digunakan program
ACTIVE_PROFILE = HARDWARE_PROFILES[PLATFORM]

# Jika di laptop menggunakan mode stream, ubah camera_index menjadi URL streaming Windows
if PLATFORM == "laptop" and ACTIVE_PROFILE["camera_index"] == "stream":
    host_ip = get_wsl_host_ip()
    ACTIVE_PROFILE["camera_index"] = f"http://{host_ip}:8080/video"


# ─────────────────────────────────────────────────────────────
# 2. KONFIGURASI 5 WAKTU SHOLAT
# ─────────────────────────────────────────────────────────────
SHOLAT_CONFIG = {
    #          rakaat  tasyahud_awal_after (None = tidak ada tasyahud awal)
    "Subuh":   {"rakaat": 2, "tasyahud_awal_after": None},
    "Dhuhur":  {"rakaat": 4, "tasyahud_awal_after": 2},
    "Ashar":   {"rakaat": 4, "tasyahud_awal_after": 2},
    "Maghrib": {"rakaat": 3, "tasyahud_awal_after": 2},
    "Isya":    {"rakaat": 4, "tasyahud_awal_after": 2},
}

# Keyboard shortcut untuk pemilihan sholat (key → nama sholat)
SHOLAT_KEY_MAP = {
    ord("1"): "Subuh",
    ord("2"): "Dhuhur",
    ord("3"): "Ashar",
    ord("4"): "Maghrib",
    ord("5"): "Isya",
}


# ─────────────────────────────────────────────────────────────
# 3. THRESHOLD DETEKSI POSE (default — akan di-override oleh kalibrasi)
# ─────────────────────────────────────────────────────────────
THRESHOLDS = {
    # Jumlah frame minimum sebelum pose dikonfirmasi
    # Lebih kecil = lebih responsif, tapi lebih rentan jitter
    # Rekomendasi: 5 (cepat) s/d 10 (stabil). Default: 5
    "POSE_HOLD_FRAMES":         5,

    # ── Sudut Pinggul (hip_angle) ──────────────────────────
    "HIP_STRAIGHT_MIN":        150,   # berdiri tegak: pinggul > nilai ini
    "HIP_RUKU_MIN":             55,   # ruku': batas bawah (lebih longgar)
    "HIP_RUKU_MAX":            130,   # ruku': batas atas (lebih longgar)
    "HIP_SUJUD_MAX":            90,   # sujud: pinggul harus < nilai ini (lebih longgar)

    # ── Sudut Lutut (knee_angle) ───────────────────────────
    "KNEE_STRAIGHT_MIN":       140,   # lutut lurus (berdiri/ruku'): > nilai ini (lebih mudah)
    "KNEE_BENT_MAX":           125,   # lutut tertekuk (duduk/sujud): < nilai ini

    # ── Posisi Pergelangan Tangan (wrist Y) ───────────────
    # (koordinat Y ternormalisasi: 0=atas, 1=bawah)
    # Takbir: wrist sejajar kepala (antara telinga & hidung)
    # wrist.y < nose.y + offset ini  →  tangan setinggi kepala
    "TAKBIR_WRIST_ABOVE_SHOULDER": 0.0,   # (tidak lagi dipakai untuk takbir, dipertahankan sbg cadangan)
    "TAKBIR_WRIST_NEAR_HEAD_OFFSET": 0.10, # wrist.y < nose.y + offset (makin kecil = makin ketat)

    # Sedekap: wrist harus di BAWAH bahu dan di ATAS pinggul
    "SEDEKAP_WRIST_BELOW_SHOULDER": 0.02,  # wrist.y > shoulder.y + offset ini
    "SEDEKAP_WRIST_ABOVE_HIP":     -0.02,  # wrist.y < hip.y + offset ini

    # Sedekap: kedua tangan harus berdekatan (perbedaan X)
    "SEDEKAP_HAND_MAX_DIST_X":     0.20,

    # ── Posisi Kepala (nose Y) ────────────────────────────
    # Sujud: hidung harus LEBIH RENDAH (Y lebih besar) dari bahu
    "SUJUD_NOSE_BELOW_SHOULDER":  -0.05, # hidung boleh sedikit lebih tinggi dari bahu (lebih toleran)
    "SUJUD_NOSE_BELOW_HIP":        0.0,   # nose.y > hip.y + offset ini

    # ── Deteksi Salam (head rotation) ────────────────────
    # Offset X kepala dari center badan untuk mendeteksi menoleh
    "SALAM_HEAD_OFFSET_THRESHOLD": 0.05, # lebih sensitif (sebelumnya 0.08)

    # ── Visibilitas Landmark ──────────────────────────────
    "LANDMARK_MIN_VISIBILITY":     0.5,   # landmark dengan vis < ini diabaikan

    # ── Sudut Lengan (arm_angle) ──────────────────────────
    "TAKBIR_ARM_ANGLE_MIN":        60,    # lengan harus cukup terbuka saat takbir

    # ── Durasi Tuma'ninah (Detik) ─────────────────────────
    "TUMANINAH_MIN_DURATION":      3.0,   # Durasi minimum dalam detik untuk memenuhi tuma'ninah
}


# ─────────────────────────────────────────────────────────────
# 4. INDEX LANDMARK MEDIAPIPE POSE (33 landmark)
# ─────────────────────────────────────────────────────────────
class LANDMARK:
    """Nama konstanta untuk index landmark MediaPipe Pose."""

    # ── Kepala & Wajah ────────────────────────────────────
    NOSE             = 0
    LEFT_EYE_INNER   = 1
    LEFT_EYE         = 2
    LEFT_EYE_OUTER   = 3
    RIGHT_EYE_INNER  = 4
    RIGHT_EYE        = 5
    RIGHT_EYE_OUTER  = 6
    LEFT_EAR         = 7
    RIGHT_EAR        = 8
    MOUTH_LEFT       = 9
    MOUTH_RIGHT      = 10

    # ── Lengan Atas ───────────────────────────────────────
    LEFT_SHOULDER    = 11
    RIGHT_SHOULDER   = 12
    LEFT_ELBOW       = 13
    RIGHT_ELBOW      = 14
    LEFT_WRIST       = 15
    RIGHT_WRIST      = 16

    # ── Jari Tangan ───────────────────────────────────────
    LEFT_PINKY       = 17
    RIGHT_PINKY      = 18
    LEFT_INDEX       = 19
    RIGHT_INDEX      = 20
    LEFT_THUMB       = 21
    RIGHT_THUMB      = 22

    # ── Pinggul, Lutut, Kaki ──────────────────────────────
    LEFT_HIP         = 23
    RIGHT_HIP        = 24
    LEFT_KNEE        = 25
    RIGHT_KNEE       = 26
    LEFT_ANKLE       = 27
    RIGHT_ANKLE      = 28
    LEFT_HEEL        = 29
    RIGHT_HEEL       = 30
    LEFT_FOOT_INDEX  = 31
    RIGHT_FOOT_INDEX = 32

    # ── Kelompok untuk iterasi / visualisasi ─────────────
    HEAD_GROUP      = [0, 2, 5, 7, 8]
    SHOULDER_GROUP  = [11, 12]
    ARM_GROUP       = [11, 12, 13, 14, 15, 16]
    HAND_GROUP      = [15, 16, 17, 18, 19, 20, 21, 22]
    TORSO_GROUP     = [11, 12, 23, 24]
    LEG_GROUP       = [23, 24, 25, 26, 27, 28]
    FOOT_GROUP      = [27, 28, 29, 30, 31, 32]

    # ── Landmark KRITIS (jika tidak visible, skip klasifikasi) ─
    # Hanya sertakan Hidung, Bahu, dan Pinggul.
    # Pergelangan tangan, lutut, dan telinga dilepas agar deteksi tetap stabil 
    # saat anggota tubuh tersebut terhalang (seperti saat sujud, duduk, atau salam).
    CRITICAL = [0, 11, 12, 23, 24]


# ─────────────────────────────────────────────────────────────
# 5. NAMA POSE / STATE
# ─────────────────────────────────────────────────────────────
class POSE:
    """Nama string untuk setiap state/pose sholat."""
    UNKNOWN                    = "UNKNOWN"
    BERDIRI_TEGAK              = "BERDIRI_TEGAK"              # Berdiri Tegak / Niat
    TAKBIRATUL_IHRAM           = "TAKBIRATUL_IHRAM"           # Takbiratul Ihram (Allahu Akbar)
    BERSEDEKAP                 = "BERSEDEKAP"                 # Bersedekap (Membaca Al-Fatihah, dll)
    RUKUK                      = "RUKUK"                      # Rukuk
    ITIDAL                     = "ITIDAL"                     # I'tidal (Tahmid / Doa I'tidal)
    SUJUD_PERTAMA              = "SUJUD_PERTAMA"              # Sujud Pertama
    DUDUK_DI_ANTARA_DUA_SUJUD  = "DUDUK_DI_ANTARA_DUA_SUJUD"  # Duduk di Antara Dua Sujud
    SUJUD_KEDUA                = "SUJUD_KEDUA"                # Sujud Kedua
    DUDUK_TASYAHUD_AWAL        = "DUDUK_TASYAHUD_AWAL"        # Duduk Tasyahud Awal
    DUDUK_TASYAHUD_AKHIR       = "DUDUK_TASYAHUD_AKHIR"       # Duduk Tasyahud Akhir
    SALAM_KE_KANAN             = "SALAM_KE_KANAN"             # Salam ke Kanan
    SALAM_KE_KIRI              = "SALAM_KE_KIRI"              # Salam ke Kiri
    SELESAI                    = "SELESAI"                    # Selesai

    # Penamaan kelas fisik pembantu (yang dikembalikan oleh pose_classifier)
    SUJUD                      = "SUJUD"                      # Fisik Sujud
    JALSA                      = "JALSA"                      # Fisik Duduk

    # Deskripsi UI yang ditampilkan ke pengguna
    DISPLAY_NAME = {
        UNKNOWN:                    "Tidak Terdeteksi",
        BERDIRI_TEGAK:              "Berdiri Tegak",
        TAKBIRATUL_IHRAM:           "Takbiratul Ihram",
        BERSEDEKAP:                 "Bersedekap",
        RUKUK:                      "Rukuk",
        ITIDAL:                     "I'tidal",
        SUJUD_PERTAMA:              "Sujud Pertama",
        DUDUK_DI_ANTARA_DUA_SUJUD:  "Duduk di Antara Dua Sujud",
        SUJUD_KEDUA:                "Sujud Kedua",
        DUDUK_TASYAHUD_AWAL:        "Duduk Tasyahud Awal",
        DUDUK_TASYAHUD_AKHIR:       "Duduk Tasyahud Akhir",
        SALAM_KE_KANAN:             "Salam ke Kanan",
        SALAM_KE_KIRI:              "Salam ke Kiri",
        SELESAI:                    "Selesai ✓",
    }


# ─────────────────────────────────────────────────────────────
# 6. AUDIO MAPPING
# ─────────────────────────────────────────────────────────────
# Audio yang diputar saat MEMASUKI suatu state (bacaan utama di posisi tersebut)
AUDIO_STATE_MAP = {
    POSE.TAKBIRATUL_IHRAM:          "takbiratul-ihram.WAV",   # "Allahu Akbar" (Takbiratul Ihram)
    POSE.BERSEDEKAP:                "iftitah.WAV",            # Doa Iftitah (hanya rakaat 1, lihat logic)
    POSE.RUKUK:                     "ruku.WAV",               # Doa/Tasbih Rukuk
    POSE.ITIDAL:                    "itidal.WAV",             # Tahmid / Doa I'tidal
    POSE.SUJUD_PERTAMA:             "sujud.WAV",              # Doa/Tasbih Sujud 1
    POSE.DUDUK_DI_ANTARA_DUA_SUJUD: "iftirasy.WAV",           # Doa Duduk di Antara Dua Sujud
    POSE.SUJUD_KEDUA:               "sujud.WAV",              # Doa/Tasbih Sujud 2
    POSE.DUDUK_TASYAHUD_AWAL:       "tasyahud-awal.WAV",      # Doa Tasyahud Awal
    POSE.DUDUK_TASYAHUD_AKHIR:      "tasyahud-akhir.WAV",     # Doa Tasyahud Akhir
    POSE.SALAM_KE_KANAN:            "salam.WAV",              # Salam Kanan
    POSE.SALAM_KE_KIRI:             "salam.WAV",              # Salam Kiri
}

# Audio TRANSISI yang diputar saat BERGERAK MENUJU state berikutnya (Takbir Intiqal / Tasmi')
AUDIO_TRANSITION_MAP = {
    # Takbir Intiqal — diucapkan saat turun/naik antar gerakan
    (POSE.BERSEDEKAP, POSE.RUKUK):                  "takbir.WAV",    # Turun ke Rukuk
    (POSE.ITIDAL,  POSE.SUJUD_PERTAMA):             "takbir.WAV",    # Turun ke Sujud Pertama
    (POSE.SUJUD_PERTAMA, POSE.DUDUK_DI_ANTARA_DUA_SUJUD): "takbir.WAV", # Bangkit dari Sujud Pertama
    (POSE.DUDUK_DI_ANTARA_DUA_SUJUD, POSE.SUJUD_KEDUA): "takbir.WAV",  # Turun ke Sujud Kedua
    (POSE.SUJUD_KEDUA, POSE.BERSEDEKAP):             "takbir.WAV",    # Bangkit bersedekap ke rakaat berikutnya (rakaat 2+)
    (POSE.SUJUD_KEDUA, POSE.BERDIRI_TEGAK):          "takbir.WAV",    # Bangkit berdiri (fallback)
    (POSE.SUJUD_KEDUA, POSE.DUDUK_TASYAHUD_AWAL):   "takbir.WAV",    # Duduk tasyahud awal
    (POSE.SUJUD_KEDUA, POSE.DUDUK_TASYAHUD_AKHIR):  "takbir.WAV",    # Duduk tasyahud akhir
    (POSE.DUDUK_TASYAHUD_AWAL, POSE.BERDIRI_TEGAK):  "takbir.WAV",    # Bangkit dari tasyahud awal ke rakaat berikutnya

    # Tasmi' — diucapkan saat bangkit dari Rukuk
    (POSE.RUKUK,    POSE.ITIDAL):                   "tasmi.WAV",     # "Sami'allahu liman hamidah"
}

# Audio tambahan per sholat (niat, Al-Fatihah, Surat)
AUDIO_EXTRA = {
    "niat_subuh":   "niat-subuh.WAV",
    "niat_dzuhur":  "niat-dzuhur.WAV",
    "niat_ashar":   "niat-ashar.WAV",
    "niat_maghrib": "niat-maghrib.WAV",
    "niat_isya":    "niat-isya.WAV",
    "alfatihah":    "alfatihah.WAV",
    "surat":        "al-ikhlas.WAV",     # Surat/ayat pendek default
}


# ─────────────────────────────────────────────────────────────
# 7. KEYBOARD SHORTCUTS (saat program berjalan)
# ─────────────────────────────────────────────────────────────
KEY_QUIT        = ord("q")   # Keluar program
KEY_RESET       = ord("r")   # Reset state machine
KEY_DEBUG       = ord("d")   # Toggle debug overlay (tampilkan sudut)
KEY_PAUSE       = ord("p")   # Pause / resume
KEY_CALIBRATE   = ord("c")   # Mulai mode kalibrasi


# ─────────────────────────────────────────────────────────────
# 8. PATH FILE
# ─────────────────────────────────────────────────────────────
import os

BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR          = os.path.join(BASE_DIR, "logs")
AUDIO_DIR         = os.path.join(BASE_DIR, "audio")
CALIBRATION_FILE  = os.path.join(BASE_DIR, "calibration.json")

# Pastikan folder logs ada
os.makedirs(LOGS_DIR, exist_ok=True)


# ─────────────────────────────────────────────────────────────
# 9. GPIO CONFIGURATION (Orange Pi 4 Pro)
# ─────────────────────────────────────────────────────────────
# Set ke True jika menggunakan tombol fisik yang dihubungkan ke GPIO Orange Pi
USE_GPIO_BUTTON = False  
GPIO_RESET_PIN  = 85     # Pin GPIO Orange Pi 4 Pro (Physical Pin 7 = GPIO2_C5 = 85)


# ─────────────────────────────────────────────────────────────
# 10. DETEKSI SHOLAT OTOMATIS (WIB / GMT+7)
# ─────────────────────────────────────────────────────────────
AUTO_DETECT_PRAYER = True        # Aktifkan deteksi sholat otomatis saat startup berdasarkan jam sistem
PRAYER_OFFSET_MINUTES = 30       # Masuk waktu sholat X menit lebih awal (misal: 30 menit sebelum Subuh)


# ─────────────────────────────────────────────────────────────
# 11. BOT TELEGRAM NOTIFIKASI (IoT)
# ─────────────────────────────────────────────────────────────
USE_TELEGRAM = True

# Muat environment variable dari file .env (lokal, tidak di-commit ke GitHub)
_env_path = os.path.join(BASE_DIR, ".env")
if os.path.exists(_env_path):
    try:
        with open(_env_path, "r") as _f:
            for _line in _f:
                _line = _line.strip()
                if not _line or _line.startswith("#"):
                    continue
                if "=" in _line:
                    _k, _v = _line.split("=", 1)
                    # Bersihkan spasi dan tanda petik
                    os.environ[_k.strip()] = _v.strip().strip("'\"")
    except Exception as _e:
        print(f"[WARNING] Gagal membaca file .env: {_e}")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "isi_token_bot_anda_di_sini")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
