# Changelog

Semua perubahan penting pada proyek **GEMA Imam — Sholat Tracking System** akan didokumentasikan di berkas ini. Format penulisan berbasis pada [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) dan proyek ini mengikuti aturan versi semantik.

---

## [1.2.0] — 2026-07-10
### Added
- Integrasi auto-connect ke Bluetooth Speaker berdasarkan konfigurasi `BLUETOOTH_SPEAKER_MAC` pada berkas `.env`.
- Sistem auto-start `x11vnc` di background saat sesi XFCE desktop aktif pada startup.
- Mekanisme **Watchdog Service** pada `run_desktop.sh` untuk melakukan restart otomatis pada aplikasi jika terdeteksi crash/terhenti paksa di lapangan.

### Changed
- Profil `opi4pro`: Nilai `model_complexity` diturunkan ke `0` (Lite) untuk optimasi FPS dan reduksi beban termal CPU Orange Pi 4 Pro.
- Mode Headless: Menghilangkan pembatasan 500 frame benchmark agar aplikasi dapat berjalan tanpa batas secara headless di lapangan.

### Fixed
- Memperbaiki ketidaksesuaian/typo penulisan nama sholat `"Dzuhur"` menjadi `"Dhuhur"` agar selaras dengan skema konfigurasi `SHOLAT_CONFIG`.
- Eliminasi kalkulasi duplikat `get_pose_features` per frame dan menghapus redundansi import di dalam loop utama `main.py`.

---

## [1.1.0] — 2026-07-07
### Added
- Sistem deteksi akhir sholat terotomatisasi (Salam Kanan -> Salam Kiri -> Selesai -> Auto-reset).
- Delay 5 detik pasca-salam untuk memastikan pemutaran audio salam selesai sempurna.
- Ekspor log sesi secara otomatis ke CSV & JSON lalu dikirimkan ke Telegram tanpa perlu memanggil command `/log` secara manual.

### Changed
- Menggantikan startup berbasis `systemd` dengan **XFCE Desktop Autostart** agar GUI OpenCV dapat dirender dengan stabil saat headless menggunakan HDMI Dummy.
- Menyempurnakan HUD dengan mengganti karakter non-ASCII em-dash (`???`) dengan standar tanda hubung ASCII pada `visualizer.py`.

### Fixed
- Error timeout Telegram saat boot dengan menambahkan penanganan pengecualian (*exception handling*) dan skema retrying 5 detik pada notifikasi startup.

---

## [1.0.0] — 2026-06-25
### Added
- Rilis perdana sistem Sholat Tracking berbasis MediaPipe Pose.
- Logika state machine pendeteksi 13 gerakan sholat dengan filter tuma'ninah.
- Audio guide multi-bahasa menggunakan pemutar suara `aplay` lokal.
- Integrasi Notifikasi bot Telegram dan penanganan perintah remote (/status, /reset, /pause, /sholat, /log).
- Sistem logging sesi terstruktur (.csv dan .json) beserta kalkulasi KPI tuma'ninah.
