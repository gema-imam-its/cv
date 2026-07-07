# GEMA Imam

> Sistem pemantauan gerakan sholat berbasis Computer Vision untuk membantu masjid memantau kualitas amaliyah imam secara real-time.

**GEMA Imam** adalah perangkat IoT berbasis *Single Board Computer* (Orange Pi 4 Pro) yang menggunakan kamera dan kecerdasan buatan (MediaPipe Pose) untuk mendeteksi gerakan sholat imam secara otomatis, memutar audio bacaan yang sesuai, serta mengirimkan laporan evaluasi ke pengurus masjid melalui Bot Telegram.

---

## Fitur Utama

- **Deteksi 13 Pose Sholat** secara real-time menggunakan MediaPipe Pose (Qiyam, Takbiratul Ihram, Bersedekap, Rukuk, I'tidal, Sujud, Jalsa, Tasyahud, Salam)
- **Audio Panduan Otomatis** — memutar bacaan sholat sesuai gerakan yang terdeteksi
- **Evaluasi Tuma'ninah** — mengukur durasi setiap gerakan dan menilai apakah memenuhi syarat tuma'ninah (≥3 detik)
- **Deteksi Kesalahan Imam** — mencatat gerakan yang mendahului selesainya bacaan wajib
- **Deteksi 5 Waktu Sholat Otomatis** — program otomatis memilih jenis sholat berdasarkan jam sistem (WIB/GMT+7)
- **Laporan KPI via Telegram** — ringkasan evaluasi sholat dikirim otomatis ke HP pengurus setelah sholat selesai
- **Remote Control via Bot Telegram** — kelola sistem dari HP dengan command `/status`, `/reset`, `/pause`, `/sholat`, `/log`
- **Log Sesi** — setiap sesi disimpan dalam format CSV dan JSON untuk analisis lanjutan
- **Kalibrasi Adaptif** — sistem menyesuaikan threshold deteksi dengan tinggi badan pengguna

---

## Arsitektur Sistem

```
Kamera USB
    │
    ▼
MediaPipe Pose  ──►  Pose Classifier  ──►  State Machine  ──►  Audio Player
(33 Landmark)        (13 Gerakan)          (Sholat Logic)       (aplay/pygame)
                                                │
                                                ▼
                                         Session Logger
                                         (CSV + JSON)
                                                │
                                                ▼
                                        Telegram Bot
                                    (Laporan + Remote CMD)
```

---

## Hardware yang Digunakan

| Komponen | Spesifikasi |
|----------|-------------|
| SBC | Orange Pi 4 Pro (RK3399, 4GB RAM) |
| Kamera | USB Webcam 640×480 |
| Audio | Speaker via 3.5mm atau USB |
| OS | Ubuntu 22.04 (ARM64) |
| Python | 3.10 |

---

## Instalasi Cepat

### 1. Clone Repository

```bash
git clone https://github.com/gema-imam-its/cv.git
cd cv
```

### 2. Jalankan Skrip Instalasi Otomatis

```bash
bash install.sh
```

Skrip ini akan otomatis:
- Menginstall dependensi sistem (`apt`)
- Membuat Python virtual environment
- Menginstall semua Python packages (`pip`)
- Membuat berkas `.env` dari template

### 3. Konfigurasi Telegram Bot (Opsional)

Isi kredensial Telegram di berkas `.env`:

```env
TELEGRAM_BOT_TOKEN=token_dari_botfather
TELEGRAM_CHAT_ID=chat_id_kamu
```

### 4. Jalankan Program

```bash
source venv/bin/activate
python core/main.py
```

---

## Penggunaan

### Shortcuts Keyboard (Mode GUI)

| Tombol | Fungsi |
|--------|--------|
| `1`–`5` | Ganti sholat (1=Subuh, 2=Dhuhur, 3=Ashar, 4=Maghrib, 5=Isya) |
| `c` | Mulai kalibrasi tinggi badan (berdiri tegak 5 detik) |
| `r` | Reset sholat dari awal |
| `d` | Toggle debug overlay (tampilkan sudut sendi) |
| `p` | Pause / resume deteksi |
| `q` | Keluar dan simpan log sesi |

### Command Bot Telegram

| Command | Fungsi |
|---------|--------|
| `/status` | Status sholat aktif, rakaat, dan gerakan saat ini |
| `/reset` | Reset sholat dari jarak jauh |
| `/pause` | Pause / resume deteksi dari HP |
| `/sholat maghrib` | Ganti jenis sholat dari HP |
| `/log` | Terima file log JSON sesi terakhir |
| `/help` | Tampilkan daftar command |

---

## Struktur Proyek

```
cv/
├── core/
│   ├── main.py              # Entry point & pipeline koordinasi
│   ├── pose_classifier.py   # Klasifikasi 13 gerakan sholat
│   ├── pose_utils.py        # Utilitas geometri & koordinat
│   ├── state_machine.py     # Mesin state logika sholat
│   ├── visualizer.py        # HUD & rendering skeleton
│   ├── prayer_scheduler.py  # Deteksi waktu sholat otomatis
│   └── telegram_notifier.py # Bot Telegram & command listener
├── audio/                   # File audio bacaan sholat (.WAV)
├── docs/                    # Dokumentasi & runbook
├── logs/                    # Log sesi sholat (CSV + JSON)
├── config.py                # Konfigurasi platform & threshold
├── .env.example             # Template konfigurasi rahasia (.env)
├── install.sh               # Skrip instalasi otomatis
├── test_camera.py           # Pengujian kamera & benchmark FPS
└── requirements.txt         # Dependensi Python
```

---

## Evaluasi & KPI

Setelah setiap sesi sholat, sistem menghasilkan laporan dengan metrik:

- **Skor Tuma'ninah** — persentase gerakan yang memenuhi durasi minimum (≥3 detik)
- **Kesalahan Imam** — jumlah gerakan yang dilakukan sebelum bacaan wajib selesai
- **Total Rakaat** — jumlah rakaat yang berhasil diselesaikan
- **Durasi Sesi** — total waktu sholat berlangsung

---

## Dokumentasi Lengkap

- [Runbook (Setup & Deploy)](docs/runbook.md)
- [Arsitektur Sistem](docs/system_architecture_guide.md)

---

## Tim Pengembang

Dikembangkan untuk **PKM (Pekan Kreativitas Mahasiswa)** — Institut Teknologi Sepuluh Nopember (ITS) Surabaya.

---

## Lisensi

Proyek ini dikembangkan untuk keperluan akademik PKM ITS.
