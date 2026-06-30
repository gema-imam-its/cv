# Runbook — Setup & Penggunaan GEMA Imam

Panduan ini berisi langkah-langkah lengkap untuk memasang, mengonfigurasi, dan menjalankan sistem tracking sholat **GEMA Imam** baik di Laptop (Windows/WSL2) maupun di Orange Pi 4 Pro (SBC).

---

## 1. Persiapan Awal & Clone Repository

Buka terminal di mesin target (Laptop Linux/WSL2 atau Orange Pi via SSH):

```bash
# Clone repository ke lokal
git clone https://github.com/khosy/cv.git
cd cv
```

---

## 2. Membuat Virtual Environment & Instalasi Dependensi

Gunakan Python virtual environment (venv) agar tidak mengganggu package global sistem:

```bash
# 1. Pastikan python3-venv dan pip terinstall (Ubuntu/Debian)
sudo apt update
sudo apt install -y python3-pip python3-venv libgl1-mesa-glx libglib2.0-0

# 2. Buat virtual environment
python3 -m venv venv

# 3. Aktifkan venv
source venv/bin/activate

# 4. Upgrade pip & install dependensi
pip install --upgrade pip
pip install -r requirements.txt
```

> **Catatan Pemakaian CP310/CP312 (Orange Pi 4 Pro):** Jika terjadi error saat mencari package MediaPipe untuk arsitektur ARM64 di `requirements.txt`, silakan install manual dengan:
> ```bash
> pip install opencv-python numpy
> pip install mediapipe
> ```

---

## 3. Konfigurasi Sistem (`config.py`)

Buka file [config.py](file:///home/khosy/playground/cv/config.py) untuk mengubah parameter sesuai dengan platform atau peletakan kamera di lapangan:

### A. Memilih Platform Aktif (Baris 18)
*   **`PLATFORM = "laptop"`**: Profil untuk pengujian lokal laptop (ASUS TUF / WSL2).
*   **`PLATFORM = "opi4pro"`**: Profil untuk produk final Orange Pi 4 Pro (mengaktifkan model hemat daya, resolusi rendah, dan skip frame).

### B. Mengubah Rotasi Kamera (90° Vertikal / Portrait)
Jika kamera webcam diputar 90 derajat secara vertikal (CW) di lapangan agar memuat seluruh tubuh pada jarak dekat, ubah parameter berikut di dalam profil yang aktif:
```python
"camera_rotation": 90,  # Ubah dari None menjadi 90
```
*Sistem otomatis mendeteksi konfigurasi ini, memutar video feed secara real-time, dan menyesuaikan koordinat HUD secara otomatis.*

---

## 4. Pengujian Kamera & Environment

Sebelum menjalankan program utama, jalankan script pengujian kamera untuk memverifikasi fungsionalitas dan performa (FPS):

```bash
# Aktifkan venv jika belum
source venv/bin/activate

# Jalankan pengujian kamera
python test_camera.py
```

*   **Mode GUI (Laptop/Monitor Tersambung)**: Jendela OpenCV akan muncul menampilkan feed kamera secara cermin lengkap dengan gambar garis skeleton berwarna-warni. Tekan **`q`** untuk keluar.
*   **Mode Headless (SSH/Tanpa Display)**: Otomatis aktif jika dijalankan via SSH. Program akan menjalankan benchmark selama 100 frame di konsol dan mengukur performa FPS rata-rata di Orange Pi.

---

## 5. Menjalankan Aplikasi Utama

Setelah pengujian kamera berhasil, jalankan program tracking sholat:

```bash
# Jalankan aplikasi utama
python core/main.py
```

### Shortcuts Keyboard (Mode GUI):
*   **`1` s.d. `5`**: Memilih waktu sholat (1=Subuh, 2=Dhuhur, 3=Ashar, 4=Maghrib, 5=Isya).
*   **`c`**: Mulai Kalibrasi Tinggi Badan (Harap berdiri tegak selama 5 detik hitung mundur).
*   **`r`**: Reset state machine (mengulang sholat dari awal).
*   **`d`**: Mengaktifkan/menonaktifkan visualisasi sudut sendi di layar.
*   **`p`**: Pause / resume program.
*   **`q`**: Keluar dari aplikasi.

---

## 6. Kalibrasi & Penyesuaian Lapangan

### A. Cara Kalibrasi Tubuh Pengguna
Setiap memulai sesi di tempat baru, lakukan kalibrasi agar threshold ketinggian (sujud/sedekap) menyesuaikan dengan tinggi badan pengguna:
1. Jalankan `python core/main.py`.
2. Tekan tombol **`c`** di keyboard.
3. Berdiri tegak menghadap kamera selama 5 detik hingga proses selesai.
4. Hasil kalibrasi otomatis disimpan ke `calibration.json` dan dimuat otomatis pada sesi berikutnya.

### B. Membaca Log Selesai Sholat
Setiap kali sesi sholat diselesaikan (atau ditekan `q` di tengah jalan), sistem akan menyimpan 2 file log di folder `logs/`:
*   `sholat_NamaSholat_Tanggal_Waktu.csv`: Detail langkah transisi gerakan per rakaat.
*   `sholat_NamaSholat_Tanggal_Waktu.json`: Ringkasan sesi sholat (total durasi, status selesai/batal, jumlah rakaat).
