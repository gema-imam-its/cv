<div align="center">

<br/>

<h1>GEMA Imam</h1>

**GEMA Imam**

*Program Pendampingan Kemandirian Ibadah melalui Integrasi Sensor Visual menjadi Audio di SLB Paedagogia Surabaya*

<br/>

[![Python](https://img.shields.io/badge/Python-3.10-blue?style=flat-square&logo=python)](https://python.org)
[![MediaPipe](https://img.shields.io/badge/MediaPipe-Pose-orange?style=flat-square)](https://mediapipe.dev)
[![Platform](https://img.shields.io/badge/Platform-Orange%20Pi%204%20Pro-red?style=flat-square)](https://orangepi.org)
[![License](https://img.shields.io/badge/License-Akademik%20PKM%20ITS-green?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-Passing-brightgreen?style=flat-square)](#pengujian)

<br/>

> **Proyek Unggulan PKM-PM — Institut Teknologi Sepuluh Nopember (ITS) Surabaya**
>
> Diadaptasi dari hasil penelitian terapan untuk solusi nyata di lingkungan SLB Paedagogia.

<br/>

![Demo GEMA Imam](<!-- TODO: ganti dengan path/URL screenshot atau demo GIF program berjalan di Orange Pi -->)

</div>

---

## Daftar Isi

- [Latar Belakang](#latar-belakang)
- [Fitur Utama](#fitur-utama)
- [Arsitektur Sistem](#arsitektur-sistem)
- [Hardware](#hardware)
- [Instalasi Cepat](#instalasi-cepat)
- [Konfigurasi](#konfigurasi)
- [Penggunaan](#penggunaan)
- [Telegram Bot Remote Control](#telegram-bot-remote-control)
- [Autostart & Deployment](#autostart--deployment)
- [Evaluasi & KPI](#evaluasi--kpi)
- [Struktur Proyek](#struktur-proyek)
- [Pengujian](#pengujian)
- [Tim Pengembang](#tim-pengembang)
- [Lisensi](#lisensi)

---

## Latar Belakang

Siswa tunawicara di **SLB Paedagogia Surabaya** menghadapi kendala saat memimpin salat berjamaah karena harus bergantung pada audio kaku dari laptop akibat ketiadaan guru laki-laki, ditambah lagi dengan absennya mata pelajaran Pendidikan Agama Islam yang menyulitkan para siswa dalam mempelajari tata cara salat. Menjawab permasalahan tersebut, diusulkanlah "Program Gema Imam", sebuah program pengabdian masyarakat yang memanfaatkan teknologi Computer Vision untuk merespons gerakan imam menjadi audio takbir secara otomatis, serta mengintegrasikan Learning Management System (LMS) sebagai platform edukasi inklusif yang mendukung hak penyandang disabilitas dalam belajar dan melaksanakan ibadah secara lebih mandiri.

---

## Fitur Utama

| Fitur | Deskripsi |
|---|---|
| **Deteksi 13 Pose Sholat** | Klasifikasi gerakan real-time menggunakan MediaPipe Pose: Qiyam, Takbiratul Ihram, Bersedekap, Rukuk, I'tidal, Sujud (1 & 2), Jalsa, Tasyahud Awal/Akhir, Salam Kanan/Kiri |
| **Evaluasi Tuma'ninah** | Mengukur durasi setiap gerakan dan menilai apakah memenuhi syarat tuma'ninah (≥3 detik) secara objektif |
| **Deteksi Kesalahan Imam** | Mencatat gerakan yang mendahului selesainya bacaan wajib yang sedang diputar |
| **Audio Panduan Otomatis** | Memutar bacaan sholat yang sesuai dengan gerakan yang terdeteksi menggunakan sistem antrean audio |
| **Deteksi Waktu Sholat Otomatis** | Program secara mandiri memilih jenis sholat yang aktif berdasarkan jam sistem (WIB/GMT+7) |
| **Laporan KPI via Telegram** | Ringkasan evaluasi sholat (skor tuma'ninah, kesalahan imam, log sudut sendi) dikirim otomatis ke HP pengurus setelah sholat selesai |
| **Remote Control via Telegram Bot** | Kelola sistem dari HP dengan perintah `/status`, `/reset`, `/pause`, `/sholat`, `/log`, `/help` |
| **Kalibrasi Adaptif** | Sistem menyesuaikan threshold deteksi dengan tinggi badan pengguna melalui kalibrasi 5 detik |
| **Log Sesi Terinci** | Setiap sesi disimpan dalam CSV dan JSON berisi metadata sesi, sudut sendi, durasi per gerakan |
| **Kamera Reconnection Loop** | Sistem secara otomatis mendeteksi dan memulihkan koneksi kamera yang terputus tanpa menghentikan program |
| **Monitoring Suhu CPU** | Membaca suhu prosesor Orange Pi dan menampilkannya di overlay layar secara real-time |
| **Autostart via Systemd** | Program berjalan otomatis saat Orange Pi dinyalakan kembali setelah mati listrik |

---

## Arsitektur Sistem

```
┌─────────────────────────────────────────────────────────────────────┐
│                         GEMA Imam — Hardware Layer                  │
│                                                                      │
│   Kamera USB (640×480)  →  Orange Pi 4 Pro (RK3399, 4GB)           │
│                                ↓                                     │
│   Speaker (3.5mm/USB)  ←  Audio Player (aplay/pygame)               │
└─────────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────┐
│                         Software Pipeline                            │
│                                                                      │
│   Frame Capture  →  MediaPipe Pose  →  Pose Classifier              │
│                      (33 Landmark)     (13 Pose Kelas)              │
│                                               ↓                      │
│                               Sholat State Machine                   │
│                          (Transisi + Tuma'ninah Eval)                │
│                                               ↓                      │
│                               Session Logger                         │
│                             (CSV + JSON + KPI)                       │
└─────────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────┐
│                         Notification Layer                           │
│                                                                      │
│   Telegram Bot API  →  Pengurus Masjid (HP)                         │
│   (Laporan, Peringatan, Remote Command)                              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Hardware

| Komponen | Spesifikasi |
|---|---|
| SBC (*Single Board Computer*) | Orange Pi 4 Pro — Rockchip RK3399, 4GB LPDDR4 RAM |
| Kamera | USB Webcam, resolusi minimum 640×480 px |
| Audio | Speaker pasif via 3.5mm jack atau USB Speaker |
| Penyimpanan | eMMC 32GB onboard |
| OS | Ubuntu 22.04 LTS (ARM64) |
| Python | 3.10 |

> **Catatan Penempatan Kamera**: Untuk cakupan seluruh tubuh pada jarak dekat, kamera disarankan dipasang secara vertikal (portrait/90°). Sistem mendukung rotasi frame secara software melalui konfigurasi `camera_rotation: 90` di `config.py`.

---

## Instalasi Cepat

> **Prasyarat**: Pastikan Orange Pi sudah terhubung ke internet dan memiliki Ubuntu 22.04 yang bersih.

### 1. Clone Repository

```bash
git clone https://github.com/<!-- TODO: isi username/org GitHub -->/cv.git
cd cv
```

### 2. Jalankan Skrip Instalasi Otomatis

```bash
bash install.sh
```

Skrip ini secara otomatis akan:
- ✅ Menginstall dependensi sistem (`apt-get`)
- ✅ Membuat Python virtual environment
- ✅ Menginstall semua Python packages (`pip`)
- ✅ Membuat berkas konfigurasi `.env` dari template
- ✅ Menyiapkan folder `logs/`

### 3. Konfigurasi Kredensial Telegram

Buka dan isi berkas `.env`:

```bash
nano .env
```

```env
TELEGRAM_BOT_TOKEN=<!-- TODO: isi token dari @BotFather -->
TELEGRAM_CHAT_ID=<!-- TODO: isi Chat ID pengurus masjid -->
```

> **Cara mendapatkan Chat ID**: Jalankan program (`python core/main.py`) tanpa mengisi `TELEGRAM_CHAT_ID`. Sistem akan mendeteksi dan mencetak Chat ID secara otomatis di terminal saat pengurus pertama kali mengirim pesan ke bot.

### 4. Uji Kamera

```bash
source venv/bin/activate
python test_camera.py
```

### 5. Jalankan Program

```bash
python core/main.py
```

---

## Konfigurasi

Semua parameter sistem dapat dikonfigurasi di berkas [`config.py`](config.py).

### Memilih Platform

```python
# Ganti ke "opi4pro" saat deploy ke Orange Pi 4 Pro
PLATFORM = "opi4pro"  # "laptop" | "opi4pro"
```

### Parameter Threshold Deteksi Kunci

| Parameter | Default | Deskripsi |
|---|---|---|
| `TUMANINAH_MIN_DURATION` | `3.0` detik | Durasi minimum tuma'ninah |
| `POSE_HOLD_FRAMES` | `5` frame | Frame minimum untuk commit transisi pose |
| `LANDMARK_MIN_VISIBILITY` | `0.5` | Nilai minimum visibilitas landmark MediaPipe |

---

## Penggunaan

### Shortcuts Keyboard (Mode GUI)

| Tombol | Fungsi |
|---|---|
| `1`–`5` | Ganti sholat: 1=Subuh, 2=Dhuhur, 3=Ashar, 4=Maghrib, 5=Isya |
| `c` | Mulai kalibrasi tinggi badan (berdiri tegak selama 5 detik) |
| `r` | Reset sholat dari awal (menyimpan log sesi sebelumnya) |
| `d` | Toggle debug overlay — tampilkan sudut sendi pada body |
| `p` | Pause / resume deteksi |
| `q` | Keluar dan simpan log sesi |

### Kalibrasi Tinggi Badan

Kalibrasi wajib dilakukan satu kali di setiap lokasi baru untuk menyesuaikan threshold deteksi dengan kondisi fisik pengguna:

1. Tekan `c` pada keyboard.
2. Berdiri tegak menghadap kamera selama 5 detik.
3. Kalibrasi otomatis tersimpan ke `calibration.json` dan digunakan pada sesi berikutnya.

---

## Telegram Bot Remote Control

Program GEMA Imam memiliki bot Telegram yang terhubung langsung ke alat di lapangan. Pengurus masjid dapat memantau dan mengontrol sistem dari HP tanpa perlu menyentuh perangkat secara fisik.

### Perintah yang Tersedia

| Command | Deskripsi |
|---|---|
| `/help` | Tampilkan daftar seluruh perintah |
| `/status` | Tampilkan status sholat aktif, rakaat, dan gerakan saat ini |
| `/reset` | Reset sholat dari awal (log sesi berjalan otomatis tersimpan) |
| `/pause` | Toggle pause / resume deteksi |
| `/sholat <nama>` | Ganti jenis sholat, contoh: `/sholat maghrib` |
| `/log` | Kirimkan file log JSON sesi sholat terakhir ke HP |

### Notifikasi Otomatis

Selain perintah manual, bot juga mengirimkan notifikasi otomatis:

- 🟢 **Sistem menyala** — pesan sambutan dikirim saat program berhasil diinisialisasi
- 📊 **Laporan sholat** — ringkasan KPI dikirim otomatis setelah sholat selesai
- ⚠️ **Kamera terputus** — peringatan instan jika koneksi kamera hilang
- ✅ **Kamera tersambung kembali** — konfirmasi setelah reconnect berhasil
- 🔴 **Crash program** — notifikasi darurat beserta detail error jika terjadi crash

---

## Autostart & Deployment

Agar program berjalan otomatis setiap kali Orange Pi dinyalakan kembali (misalnya setelah mati listrik):

```bash
# 1. Salin berkas service
sudo cp gema-imam.service /etc/systemd/system/

# 2. Aktifkan dan jalankan service
sudo systemctl daemon-reload
sudo systemctl enable gema-imam.service
sudo systemctl start gema-imam.service

# 3. Cek status
sudo systemctl status gema-imam.service
```

Untuk memantau log real-time program:
```bash
journalctl -u gema-imam.service -f
```

---

## Evaluasi & KPI

Setelah setiap sesi sholat berakhir, sistem secara otomatis menghasilkan berkas log yang mengandung metrik evaluasi berikut dan mengirimkan ringkasannya ke Telegram pengurus.

| Metrik | Deskripsi |
|---|---|
| **Skor Tuma'ninah** | Persentase gerakan wajib tuma'ninah yang telah memenuhi durasi minimum ≥3 detik |
| **Kesalahan Imam** | Jumlah gerakan yang terjadi sebelum bacaan wajib selesai diputar |
| **Total Rakaat** | Jumlah rakaat yang berhasil diselesaikan |
| **Durasi Sesi** | Total waktu sholat berlangsung |
| **Sudut Sendi per Gerakan** | Data numerik sudut pinggul, lutut, dan lengan pada setiap transisi gerakan (tersedia di log CSV/JSON) |

---

## Struktur Proyek

```
cv/
├── core/
│   ├── main.py               # Entry point, pipeline orchestration, & event loop utama
│   ├── pose_classifier.py    # Klasifikasi 13 pose sholat dari landmark MediaPipe
│   ├── pose_utils.py         # Utilitas kalkulasi sudut geometri & koordinat
│   ├── state_machine.py      # Mesin state transisi logika sholat
│   ├── visualizer.py         # HUD overlay, rendering skeleton, debug angles
│   ├── prayer_scheduler.py   # Deteksi waktu sholat aktif berdasarkan jam sistem
│   └── telegram_notifier.py  # Telegram Bot API — notifikasi & command listener
├── audio/                    # File audio bacaan sholat (.WAV)
├── docs/                     # Dokumentasi & runbook teknis
│   └── runbook.md            # Panduan setup, deploy, kalibrasi, & systemd
├── logs/                     # Log sesi sholat (auto-generated, .csv + .json)
├── tests/
│   └── test_state_machine.py # Unit tests logika state machine (Python unittest)
├── config.py                 # Konfigurasi platform, threshold, audio mapping
├── .env.example              # Template konfigurasi rahasia (token Telegram)
├── gema-imam.service         # Template systemd service untuk autostart
├── run_systemd.sh            # Runner script untuk systemd
├── install.sh                # Skrip instalasi otomatis
├── test_camera.py            # Pengujian kamera & benchmark FPS
└── requirements.txt          # Dependensi Python
```

---

## Pengujian

Unit test tersedia untuk memvalidasi keandalan logika inti sistem:

```bash
source venv/bin/activate
python -m unittest discover -s tests -p "test_*.py"
```

Cakupan pengujian saat ini:

| Test Case | Deskripsi |
|---|---|
| `test_initial_state` | Validasi inisialisasi state machine |
| `test_allowed_transitions` | Validasi daftar transisi state yang diizinkan |
| `test_transition_commit_hold` | Validasi logika hold frames sebelum commit transisi |
| `test_full_sequence_subuh` | Simulasi penuh alur sholat Subuh 2 rakaat hingga Salam |

---

## Tim Pengembang

<!-- TODO: Lengkapi nama dan NRP masing-masing anggota tim -->

| Nama | NRP | Peran |
|---|---|---|
| <!-- TODO --> | <!-- TODO --> | Ketua Tim / Computer Vision Lead |
| <!-- TODO --> | <!-- TODO --> | Hardware Integration / IoT Engineer |
| <!-- TODO --> | <!-- TODO --> | Anggota / Software Engineer |

**Dosen Pembimbing**: <!-- TODO: isi nama dosen pembimbing -->

Dikembangkan sebagai bagian dari **PKM-KC (Pekan Kreativitas Mahasiswa — Karsa Cipta)**
Institut Teknologi Sepuluh Nopember (ITS), Surabaya.

---

## Dokumentasi Teknis

- [📘 Runbook Setup & Deploy](docs/runbook.md)
- [📐 Panduan Arsitektur Sistem](docs/system_architecture_guide.md)

---

## Lisensi

Proyek ini dikembangkan untuk keperluan akademik dalam rangka kegiatan **PKM (Pekan Kreativitas Mahasiswa)** Institut Teknologi Sepuluh Nopember (ITS).

Penggunaan kode dan sistem di luar keperluan akademik memerlukan persetujuan tertulis dari tim pengembang.

---

<div align="center">

Dibuat dengan ❤️ oleh Tim GEMA Imam — ITS Surabaya

</div>
