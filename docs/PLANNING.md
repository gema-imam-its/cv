# 🕌 GEMA Imam — Sholat Movement Tracking System
## Planning Document v3.0 — Final Design (5 Waktu Sholat, Multi-Rakaat, Kalibrasi, Logging)

---

## 1. Ringkasan Proyek

Sistem ini mendeteksi dan memverifikasi urutan gerakan sholat secara **real-time dan offline** menggunakan kamera dan MediaPipe Pose. Seluruh inferensi berjalan **100% lokal di Python** — tidak ada koneksi internet, tidak ada API cloud, tidak ada API AI eksternal.

**Target Platform (Dua Tahap):**
| Tahap | Hardware | Tujuan |
|-------|----------|--------|
| **Prototipe** | ASUS TUF Gaming Laptop (x86_64) | Pengembangan & tuning threshold |
| **Produk Final PKM** | Orange Pi 4 Pro (ARM64) + SSD | Produk embedded yang berdiri sendiri |

---

## 2. Perbandingan Hardware

### 🖥️ ASUS TUF Laptop (Prototipe)
| Komponen | Estimasi Spesifikasi |
|----------|---------------------|
| CPU | Intel/AMD x86_64, 6–16 core, 2.5–4.5 GHz |
| RAM | 8–16 GB DDR4/DDR5 |
| GPU | NVIDIA/AMD dedicated (opsional untuk CV) |
| OS | Linux (Ubuntu/Arch) x86_64 |
| Kemampuan Inferensi | Tinggi — bisa `model_complexity=2` |

### 🍊 Orange Pi 4 Pro (Produk Final PKM)
| Komponen | Spesifikasi Aktual |
|----------|---------------------|
| SoC | **Allwinner A733** |
| CPU | 2× Cortex-**A76** @ 2.0 GHz + 6× Cortex-**A55** (big.LITTLE) |
| GPU | Imagination BXM-4-64 |
| **NPU** | **3 TOPS** (INT8/INT16/FP16/BF16) |
| RAM | LPDDR5, tersedia 4GB / 6GB / 8GB / 12GB / 16GB |
| Storage | NVMe SSD via PCIe (kamu sudah punya ini ✅) |
| OS | Ubuntu/Debian ARM64 |

> **Catatan Penting:** NPU 3 TOPS pada OPi 4 Pro mendukung TensorFlow & ONNX.
> MediaPipe standar **tidak secara otomatis menggunakan NPU** (butuh integrasi TFLite delegate khusus).
> Untuk fase PKM, kita tetap gunakan **CPU path** karena lebih mudah dan cukup.

---

## 3. 🚧 BATASAN KERAS (Hard Limits)

Ini adalah batasan yang **tidak bisa dilampaui** dalam scope proyek ini:

### ❌ Batasan Hardware Orange Pi 4 Pro

| Batasan | Penjelasan |
|---------|-----------|
| **FPS Maksimum Realistis** | **10–15 FPS** dengan `model_complexity=0`; 5–8 FPS dengan `model_complexity=1` |
| **Tidak ada real-time 30 FPS** | Untuk pose estimation berat di ARM CPU murni, 30 FPS tidak tercapai tanpa NPU delegate |
| **Thermal Throttling** | CPU A76 akan menurun frekuensinya jika suhu > 80°C dalam operasi panjang; butuh pendinginan pasif |
| **RAM yang aman dipakai** | Sisakan minimal 1 GB untuk OS. Dari 4 GB, efektif ~2.5 GB untuk program |
| **Resolusi kamera maksimum** | 480p (640×480) disarankan untuk OPi 4 Pro. 720p akan menurunkan FPS secara signifikan |

### ❌ Batasan MediaPipe Pose

| Batasan | Penjelasan |
|---------|-----------|
| **Jumlah landmark TETAP = 33** | MediaPipe Pose selalu menghasilkan tepat 33 titik. Tidak bisa ditambah |
| **Bukan 3D sesungguhnya** | Koordinat `z` adalah estimasi kedalaman relatif, bukan depth sensor. Akurasi terbatas |
| **Hanya 1 orang** | `mp.solutions.pose` hanya mendeteksi 1 orang per frame |
| **Kamera depan terbatas** | Sujud & Ruku' sangat sulit dideteksi dari sudut pandang depan karena oklusi |
| **Tidak ada deteksi wajah/jari detail** | Untuk jari detail butuh `mp.solutions.hands` (pipeline terpisah, beban lebih berat) |
| **Visibilitas landmark** | Jika `landmark.visibility < 0.5`, landmark tersebut tidak bisa diandalkan |

### ❌ Batasan Algoritma Deteksi

| Batasan | Penjelasan |
|---------|-----------|
| **Variasi tubuh** | Threshold sudut satu nilai untuk semua orang — perlu kalibrasi per-sesi |
| **Pencahayaan buruk** | Akurasi deteksi turun drastis di kondisi cahaya < 200 lux |
| **Pakaian putih polos** | Warna seragam (jubah putih tanpa kontras) bisa membingungkan landmark detector |
| **Salam sulit dideteksi** | Gerakan kepala menoleh kecil, dari kamera depan hampir tidak bisa dibedakan |

### ✅ Yang BISA Dicapai dalam Scope PKM

- Deteksi **7 dari 9 pose** dengan akurasi > 80% (Salam sebagai bonus)
- FPS **stabil 10–15** di OPi 4 Pro dengan `model_complexity=0`
- Berjalan **penuh offline**, tidak perlu internet
- Tracking urutan **state machine** yang valid

---

## 4. Apakah Perlu API AI? **TIDAK.**

**MediaPipe adalah AI yang berjalan lokal.**

```
Cara kerja (semua di dalam Python lokal):
┌─────────────────────────────────────────────────┐
│ Frame kamera → MediaPipe TFLite Model           │
│               (sudah bundled di package Python) │
│                    ↓                            │
│              33 Koordinat Landmark              │
│                    ↓                            │
│         Kode Python kita (kalkulasi sudut,      │
│         state machine, logika deteksi)          │
│                    ↓                            │
│              Output: Nama Pose                  │
└─────────────────────────────────────────────────┘
```

- `pip install mediapipe` → model TFLite sudah di-download otomatis
- **Tidak ada request ke server** saat program berjalan
- **Tidak butuh GPU** (walau ada, tidak digunakan oleh MediaPipe Python API standar)
- **Tidak butuh internet** setelah instalasi

---

## 5. Semua 33 Landmark MediaPipe Pose

MediaPipe Pose menghasilkan **tepat 33 landmark**. Berikut daftar lengkapnya beserta relevansinya untuk sholat:

### Kepala & Wajah (0–10)
| Index | Nama | Dipakai? | Fungsi untuk Sholat |
|-------|------|----------|---------------------|
| 0 | Hidung (Nose) | ✅ **Ya** | Deteksi posisi kepala untuk Sujud & Salam |
| 1 | Mata Kiri Dalam | ⚠️ Opsional | Referensi wajah |
| 2 | Mata Kiri | ✅ **Ya** | Deteksi arah kepala untuk Salam |
| 3 | Mata Kiri Luar | ⚠️ Opsional | |
| 4 | Mata Kanan Dalam | ⚠️ Opsional | |
| 5 | Mata Kanan | ✅ **Ya** | Deteksi arah kepala untuk Salam |
| 6 | Mata Kanan Luar | ⚠️ Opsional | |
| 7 | Telinga Kiri | ✅ **Ya** | Proxy rotasi kepala (Salam kanan/kiri) |
| 8 | Telinga Kanan | ✅ **Ya** | Proxy rotasi kepala (Salam kanan/kiri) |
| 9 | Mulut Kiri | ❌ Tidak | Tidak relevan |
| 10 | Mulut Kanan | ❌ Tidak | Tidak relevan |

### Lengan Atas (11–16)
| Index | Nama | Dipakai? | Fungsi untuk Sholat |
|-------|------|----------|---------------------|
| 11 | Bahu Kiri | ✅ **KRITIS** | Referensi utama — sudut pinggul, posisi tangan |
| 12 | Bahu Kanan | ✅ **KRITIS** | Referensi utama |
| 13 | Siku Kiri | ✅ **Ya** | Sudut lengan (Takbir vs Sedekap) |
| 14 | Siku Kanan | ✅ **Ya** | Sudut lengan |
| 15 | Pergelangan Tangan Kiri | ✅ **KRITIS** | Posisi tangan (atas/bawah bahu) untuk Takbir |
| 16 | Pergelangan Tangan Kanan | ✅ **KRITIS** | Posisi tangan |

### Jari Tangan (17–22)
| Index | Nama | Dipakai? | Fungsi untuk Sholat |
|-------|------|----------|---------------------|
| 17 | Jari Kelingking Kiri | ✅ **Ya** | Deteksi Sedekap (kedua tangan berdekatan) |
| 18 | Jari Kelingking Kanan | ✅ **Ya** | Deteksi Sedekap |
| 19 | Jari Telunjuk Kiri | ✅ **Ya** | Batas posisi tangan |
| 20 | Jari Telunjuk Kanan | ✅ **Ya** | Batas posisi tangan |
| 21 | Ibu Jari Kiri | ⚠️ Opsional | |
| 22 | Ibu Jari Kanan | ⚠️ Opsional | |

### Pinggul, Lutut, Kaki (23–32)
| Index | Nama | Dipakai? | Fungsi untuk Sholat |
|-------|------|----------|---------------------|
| 23 | Pinggul Kiri | ✅ **KRITIS** | Pusat perhitungan sudut membungkuk |
| 24 | Pinggul Kanan | ✅ **KRITIS** | Pusat perhitungan sudut membungkuk |
| 25 | Lutut Kiri | ✅ **KRITIS** | Berdiri vs Duduk vs Sujud |
| 26 | Lutut Kanan | ✅ **KRITIS** | Berdiri vs Duduk vs Sujud |
| 27 | Pergelangan Kaki Kiri | ✅ **Ya** | Posisi kaki untuk Jalsa |
| 28 | Pergelangan Kaki Kanan | ✅ **Ya** | Posisi kaki untuk Jalsa |
| 29 | Tumit Kiri (Heel) | ✅ **Ya** | Verifikasi posisi kaki Sujud (menyentuh lantai) |
| 30 | Tumit Kanan (Heel) | ✅ **Ya** | Verifikasi posisi kaki Sujud |
| 31 | Ujung Kaki Kiri (Foot Index) | ✅ **Ya** | Orientasi kaki Sujud (jari kaki menghadap kiblat) |
| 32 | Ujung Kaki Kanan (Foot Index) | ✅ **Ya** | Orientasi kaki Sujud |

### Ringkasan Penggunaan Landmark:
- **Dipakai (✅):** 26 dari 33 landmark
- **Kritis (❌ jika tidak ada, deteksi gagal):** 10 landmark (0, 7, 8, 11, 12, 15, 16, 23, 24, 25, 26)
- **Tidak dipakai:** Hanya 4 landmark sekitar mata dan mulut

> **Catatan Visibilitas:** Selalu cek `lm[idx].visibility > 0.5` sebelum menggunakan nilai landmark.
> Jika landmark kritis tidak visible, tahan di state sebelumnya (jangan klasifikasi ulang).

---

## 6. Gerakan Sholat yang Dideteksi (9 Pose)

| No | Gerakan | Kode State | Landmark Kunci |
|----|---------|-----------|----------------|
| 1 | Berdiri tegak | `QIYAM` | 11,12,23,24,25,26 |
| 2 | Angkat tangan | `TAKBIR` | 11,12,15,16 |
| 3 | Tangan bersedekap | `SEDEKAP` | 11,12,15,16,17,18 |
| 4 | Membungkuk 90° | `RUKU` | 11,12,23,24,25,26 |
| 5 | Kembali tegak | `ITIDAL` | 11,12,23,24 + state sebelumnya |
| 6 | Sujud | `SUJUD` | 0,11,12,23,24,25,26,29,30 |
| 7 | Duduk antara sujud | `JALSA` | 23,24,25,26,27,28 |
| 8 | Duduk tasyahud | `TASYAHUD` | 23,24,25,26 + durasi |
| 9 | Menoleh Salam | `SALAM` | 0,7,8,11,12 |

---

## 7. Kriteria Deteksi Per Gerakan

Semua koordinat adalah **koordinat ternormalisasi [0.0 – 1.0]**.
`y` makin besar = makin ke **bawah** layar.

### 🔹 QIYAM (Berdiri Tegak)
```
✓ hip_angle    > 160°   — pinggul lurus, tidak membungkuk
✓ knee_angle   > 160°   — lutut lurus, tidak jongkok
✓ lm[15].y    > lm[11].y — tangan kiri di bawah bahu
✓ lm[16].y    > lm[12].y — tangan kanan di bawah bahu
```

### 🔹 TAKBIR (Takbiratul Ihram)
```
✓ hip_angle    > 160°   — badan masih tegak
✓ lm[15].y    < lm[11].y — pergelangan kiri di ATAS bahu kiri
✓ lm[16].y    < lm[12].y — pergelangan kanan di ATAS bahu kanan
✓ arm_angle_L  > 70°    — lengan terbuka/terangkat (bukan tertekuk ke bawah)
✓ arm_angle_R  > 70°
```

### 🔹 SEDEKAP (Tangan di Dada)
```
✓ hip_angle    > 160°   — badan tegak
✓ lm[15].y    > lm[11].y — tangan di bawah bahu (tidak diangkat)
✓ lm[15].y    < lm[23].y — tangan di atas pinggul (area dada)
✓ lm[16].y    > lm[12].y
✓ lm[16].y    < lm[24].y
✓ abs(lm[15].x - lm[16].x) < 0.2 — kedua tangan berdekatan di tengah badan
```

### 🔹 RUKU' (Membungkuk)
```
✓ 60° < hip_angle < 120° — pinggul membengkok (~90°)
✓ knee_angle     > 150°  — lutut tetap lurus (ciri khas ruku')
✓ lm[11].y ≈ lm[23].y   — bahu dan pinggul sejajar secara vertikal (punggung horizontal)
```

### 🔹 I'TIDAL (Bangkit dari Ruku')
```
✓ Kondisi SAMA dengan QIYAM secara pose
✓ SYARAT TAMBAHAN: state sebelumnya HARUS RUKU'
   (inilah yang membedakan I'tidal dari Qiyam awal)
```

### 🔹 SUJUD
```
✓ lm[0].y   > lm[11].y  — hidung LEBIH RENDAH dari bahu (kepala ke lantai)
✓ lm[0].y   > lm[23].y  — hidung lebih rendah dari pinggul
✓ knee_angle < 130°      — lutut tertekuk (berlutut)
✓ lm[29].y  ≈ lm[27].y  — tumit dan pergelangan kaki dekat (kaki dilipat)
```

### 🔹 JALSA (Duduk Antara Sujud)
```
✓ knee_angle < 130°      — lutut tertekuk (posisi duduk/berlutut)
✓ lm[0].y   < lm[11].y  — kepala LEBIH TINGGI dari bahu (tidak sujud)
✓ lm[25].y  > lm[23].y  — lutut lebih rendah dari pinggul (duduk, bukan sujud)
```

### 🔹 TASYAHUD (Duduk Tasyahud)
```
✓ Kondisi sama dengan JALSA
✓ SYARAT TAMBAHAN: sudah melewati sujud ke-2 dalam rakaat
✓ Posisi stabil > N detik (lebih lama dari Jalsa biasa)
```

### 🔹 SALAM (Menoleh)
```
Strategi: Hitung offset kepala relatif terhadap sumbu tengah badan

center_x = (lm[11].x + lm[12].x) / 2   — sumbu tengah bahu
head_offset = lm[0].x - center_x        — simpangan kepala dari tengah

✓ Salam Kanan:  head_offset > +0.08  (kepala ke kanan, x membesar)
✓ Salam Kiri:   head_offset < -0.08  (kepala ke kiri, x mengecil)

Alternatif lebih stabil: Gunakan jarak telinga
✓ Salam Kanan:  lm[7].visibility > lm[8].visibility (telinga kiri lebih terlihat)
✓ Salam Kiri:   lm[8].visibility > lm[7].visibility (telinga kanan lebih terlihat)
```

---

## 8. Sudut-Sudut yang Dihitung

Fungsi inti `calculate_angle(A, B, C)` menghitung sudut di titik **B**.

| Nama Sudut | Titik A | Vertex B | Titik C | Kegunaan |
|-----------|---------|---------|---------|----------|
| `hip_angle_L` | lm[11] Bahu Kiri | lm[23] Pinggul Kiri | lm[25] Lutut Kiri | Membungkuk/Sujud |
| `hip_angle_R` | lm[12] Bahu Kanan | lm[24] Pinggul Kanan | lm[26] Lutut Kanan | Simetri check |
| `knee_angle_L` | lm[23] Pinggul Kiri | lm[25] Lutut Kiri | lm[27] Kaki Kiri | Berdiri/Duduk |
| `knee_angle_R` | lm[24] Pinggul Kanan | lm[26] Lutut Kanan | lm[28] Kaki Kanan | Berdiri/Duduk |
| `arm_angle_L` | lm[11] Bahu Kiri | lm[13] Siku Kiri | lm[15] Pergelangan | Takbir/Sedekap |
| `arm_angle_R` | lm[12] Bahu Kanan | lm[14] Siku Kanan | lm[16] Pergelangan | Takbir/Sedekap |

> **Strategi Simetri**: Selalu rata-rata L+R untuk robustness.
> `hip_angle = (hip_angle_L + hip_angle_R) / 2`

---

## 9. Optimasi Kode untuk Dua Platform

### Strategi: Satu Kode, Dua Profil

Gunakan file `config.py` dengan **profil hardware** yang bisa dipilih:

```python
# config.py
PLATFORM = "laptop"  # Ganti ke "opi4pro" saat deploy ke Orange Pi

PROFILES = {
    "laptop": {
        "model_complexity": 1,     # Full model — akurat
        "camera_width":  1280,
        "camera_height": 720,
        "target_fps":    30,
        "skip_frame":    0,        # Proses setiap frame
    },
    "opi4pro": {
        "model_complexity": 0,     # Lite model — cepat
        "camera_width":  640,
        "camera_height": 480,
        "target_fps":    15,
        "skip_frame":    1,        # Proses 1 dari 2 frame (frame skipping)
    }
}
```

### Tabel Perbandingan Performa Estimasi

| Metrik | TUF Laptop | OPi 4 Pro (tanpa NPU) |
|--------|-----------|------------------------|
| `model_complexity=0` | ~30 FPS | **~12–18 FPS** ✅ |
| `model_complexity=1` | ~30 FPS | ~6–10 FPS ⚠️ |
| `model_complexity=2` | ~25 FPS | ~3–5 FPS ❌ |
| Resolusi optimal | 1280×720 | **640×480** |
| RAM usage (MediaPipe) | ~300 MB | ~300 MB |

> **Rekomendasi OPi 4 Pro:** `model_complexity=0` + 640×480 + frame skipping
> Ini cukup akurat untuk sholat karena gerakan tidak cepat-cepat amat.

### Teknik Optimasi Khusus OPi 4 Pro:

1. **Frame Skipping** — proses 1 frame, skip 1 frame. State machine tetap update tiap frame, inferensi tidak
2. **Pin thread ke A76 core** — set `MEDIAPIPE_DISABLE_GPU=1` dan gunakan `taskset` untuk pin ke core besar
3. **Nonaktifkan visualisasi debug** di mode produksi (tidak perlu draw sudut di final product)
4. **Gunakan `cv2.CAP_V4L2`** — wajib di Linux embedded untuk performa buffer optimal
5. **Buffer kamera = 1** — `cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)` agar frame tidak stale

---

## 10. Arsitektur Kode (Modular)

```
proto-2/
├── PLANNING.md              ← File ini
├── requirements.txt         ← Dependency Python
├── config.py                ← Profil hardware & semua threshold
├── pose_utils.py            ← Fungsi geometri (calculate_angle, dll.)
├── pose_classifier.py       ← Logika klasifikasi pose dari 26 landmark
├── state_machine.py         ← Mesin urutan gerakan sholat
├── visualizer.py            ← Overlay UI & debug rendering
└── main.py                  ← Entry point: kamera + loop utama
```

### Deskripsi Modul:

#### `config.py`
- Profil platform (`laptop` / `opi4pro`)
- Semua threshold sudut (mudah di-tune)
- Konstanta index landmark

#### `pose_utils.py`
- `calculate_angle(a, b, c) → float`
- `get_coords(lm, idx) → [x, y]`
- `get_avg_angle(lm, side_L_idxs, side_R_idxs) → float`
- `check_visibility(lm, required_idxs, min_vis=0.5) → bool`

#### `pose_classifier.py`
- `classify_pose(landmarks) → str`
- `is_qiyam(lm, angles) → bool`
- `is_takbir(lm, angles) → bool`
- `is_ruku(lm, angles) → bool`
- `is_sujud(lm, angles) → bool`
- ... (satu fungsi per pose)

#### `state_machine.py`
```python
class SholatStateMachine:
    current_state: str
    hold_counter: int          # Berapa frame pose ini sudah ditahan
    rakaat_count: int          # Hitungan rakaat
    completed_steps: list[str] # Log gerakan yang sudah dikonfirmasi
    sujud_count_in_rakaat: int # Sujud ke-1 atau ke-2

    def update(self, detected_pose: str) → None
    def is_valid_transition(from_state, to_state) → bool
    def reset() → None
```

#### `visualizer.py`
- `draw_skeleton(frame, lm)` — skeleton dengan warna custom per kelompok landmark
- `draw_pose_label(frame, pose, confidence)` — label pose besar di atas
- `draw_angles(frame, angles_dict)` — debug overlay sudut (toggle `d`)
- `draw_progress(frame, completed, current)` — progress sholat di samping
- `draw_hold_bar(frame, counter, max_val)` — bar "tahan pose"

#### `main.py`
```python
# Keyboard shortcuts:
# q → quit
# r → reset state machine
# d → toggle debug mode (tampilkan sudut)
# p → pause/resume
```

---

## 11. State Machine Diagram

```
    ┌──────────────────────────────────────────────────────┐
    │                                                      │
    ▼                                                      │
 [QIYAM] ──angkat tangan──► [TAKBIR] ──turunkan──► [SEDEKAP]
                                                       │
                                                  membungkuk
                                                       │
                                                       ▼
 [ITIDAL] ◄──bangkit──── [RUKU'] ◄──────────────────(90°)
    │
  sujud
    │
    ▼
 [SUJUD] ──duduk──► [JALSA] ──sujud lagi──► [SUJUD ke-2]
                                                  │
                                            (rakaat terakhir)
                                                  │
                                                  ▼
                                            [TASYAHUD]
                                                  │
                                               salam
                                                  │
                                                  ▼
                                             [SALAM] ──► SELESAI
```

**Aturan Transisi:**
- Setiap pose harus ditahan minimal `POSE_HOLD_FRAMES` frame
- Transisi tidak valid → diabaikan, tetap di state sebelumnya
- Jika pose tidak dideteksi → `hold_counter` tidak bertambah

---

## 12. Parameter Threshold

Semua nilai ini **perlu dikalibrasi** melalui pengujian nyata:

| Parameter | Nilai Awal | Range Tuning |
|-----------|-----------|-------------|
| `POSE_HOLD_FRAMES` | 10 frame | 8–20 |
| `HIP_RUKU_MIN` | 60° | 50–70° |
| `HIP_RUKU_MAX` | 120° | 110–130° |
| `HIP_SUJUD_MAX` | 80° | 60–90° |
| `KNEE_STRAIGHT_MIN` | 155° | 145–165° |
| `KNEE_BENT_MAX` | 130° | 110–140° |
| `WRIST_ABOVE_SHOULDER_Y` | 0.0 | ±0.03 |
| `SEDEKAP_HAND_DISTANCE_X` | 0.20 | 0.15–0.25 |
| `SALAM_HEAD_OFFSET_X` | 0.08 | 0.06–0.12 |
| `LANDMARK_MIN_VISIBILITY` | 0.5 | 0.4–0.7 |

---

## 13. UI / Visual Overlay

```
┌──────────────────────────────────────────────────────────┐
│  [POSE]: Ruku'     🔴 Tahan: ██████░░░░ 6/10   [10 FPS] │
├──────────────────────────────────────────────────────────┤
│                                                          │
│                  [Live camera                            │
│                   + skeleton overlay                     │
│                   warna: hijau=OK, merah=hilang]         │
│                                                          │
├──────────────────────────────────────────────────────────┤
│  Debug (d):  hip=95.2°  knee=167.1°  arm_L=142.0°       │
├──────────────────────────────────────────────────────────┤
│  Rakaat: 1/4                                             │
│  ✅ Qiyam  ✅ Takbir  ✅ Sedekap  ✅ Ruku'               │
│  ⏳ I'tidal  ○ Sujud  ○ Jalsa  ○ Tasyahud  ○ Salam      │
└──────────────────────────────────────────────────────────┘
```

---

## 14. Dependencies

```txt
# requirements.txt
opencv-python>=4.8.0
mediapipe>=0.10.0
numpy>=1.24.0
```

**Tidak diperlukan:**
- ❌ `google-generativeai` / `google-genai` — tidak ada API AI cloud
- ❌ `tensorflow` / `torch` — MediaPipe sudah bundling TFLite-nya sendiri
- ❌ Koneksi internet saat runtime

**Instalasi di OPi 4 Pro (ARM64):**
```bash
# MediaPipe tersedia untuk ARM64 sejak versi 0.10.x
pip install mediapipe opencv-python numpy
```

---

## 15. Rencana Pengembangan (Fase)

### ✅ Fase 0 — Setup & Infrastruktur
- [ ] Buat `requirements.txt`
- [ ] Buat `config.py` dengan profil `laptop` dan `opi4pro`
- [ ] Setup venv dan install dependencies
- [ ] Test kamera terbuka dengan V4L2 backend

### 🔨 Fase 1 — Core Detection MVP (di Laptop)
- [ ] Implementasi `pose_utils.py` (sudut, jarak, visibility check)
- [ ] Implementasi `pose_classifier.py` untuk 4 pose: Qiyam, Takbir, Ruku', Sujud
- [ ] Test live dengan kamera, tampilkan nama pose + sudut
- [ ] Tuning threshold sampai akurasi > 80% untuk 4 pose ini

### 🔨 Fase 2 — State Machine & Pose Lengkap
- [ ] Implementasi `state_machine.py`
- [ ] Tambahkan pose: Sedekap, I'tidal, Jalsa, Tasyahud, Salam
- [ ] Integrasi classifier + state machine
- [ ] Test satu rakaat penuh

### 🔨 Fase 3 — Visualisasi & UI
- [ ] Implementasi `visualizer.py`
- [ ] Progress bar + hold counter
- [ ] Debug mode (toggle `d`) menampilkan nilai sudut
- [ ] Warna skeleton berbeda per kelompok sendi

### 🔨 Fase 4 — Optimasi & Deploy ke OPi 4 Pro
- [ ] Switch ke profil `opi4pro` di `config.py`
- [ ] Implementasi frame skipping
- [ ] Benchmark FPS di OPi 4 Pro
- [ ] Tuning ulang threshold jika ada perbedaan
- [ ] Multi-rakaat tracking (hitung jumlah rakaat)
- [ ] Logging gerakan ke file CSV

---

## 16. Posisi Kamera — Rekomendasi

| Posisi | Akurasi Ruku' | Akurasi Sujud | Akurasi Sedekap | Catatan |
|--------|:---:|:---:|:---:|---------|
| **Samping (90°)** | ✅ Terbaik | ✅ Terbaik | ⚠️ Sulit | Sudut hip & knee terlihat jelas |
| **Depan (0°)** | ⚠️ Terbatas | ⚠️ Terbatas | ✅ Terbaik | Oklusi tangan saat ruku' |
| **Sudut 45°** | ✅ Baik | ✅ Baik | ✅ Baik | **Rekomendasi untuk PKM** |

> **Saran PKM Final:** Tempatkan kamera di **sudut 45°** dari sisi kanan pengguna,
> pada ketinggian setinggi pinggul (~90–100 cm dari lantai).
> Ini memberikan keseimbangan terbaik untuk semua gerakan.

---

## 17. Keputusan Desain (Final) ✅

| # | Keputusan | Jawaban |
|---|-----------|--------|
| 1 | Rakaat support | **Semua 5 waktu sholat** (Subuh 2, Maghrib 3, Dhuhur/Ashar/Isya 4 rakaat) |
| 2 | Deteksi Salam | **Di akhir sesi** — bonus setelah semua fitur utama selesai |
| 3 | Kalibrasi | **Ya**, dengan mode mudah: berdiri tegak → tekan tombol → 5 detik auto-kalibrasi |
| 4 | Output | **Logging CSV** + visual real-time di layar |

---

## 18. Sistem Multi-Rakaat — 5 Waktu Sholat

### Konfigurasi Per Waktu Sholat

```python
# config.py
SHOLAT_CONFIG = {
    "Subuh":   {"rakaat": 2, "tasyahud_awal_after": None},  # langsung Tasyahud Akhir
    "Dhuhur":  {"rakaat": 4, "tasyahud_awal_after": 2},     # Tasyahud Awal setelah rakaat 2
    "Ashar":   {"rakaat": 4, "tasyahud_awal_after": 2},
    "Maghrib": {"rakaat": 3, "tasyahud_awal_after": 2},
    "Isya":    {"rakaat": 4, "tasyahud_awal_after": 2},
}
```

### Struktur 1 Rakaat (Internal)

Setiap rakaat memiliki urutan internal yang **sama**:
```
QIYAM → [TAKBIR*] → SEDEKAP → RUKU → ITIDAL → SUJUD_1 → JALSA → SUJUD_2
        (* hanya rakaat pertama: Takbiratul Ihram. Rakaat 2+ langsung SEDEKAP)
```

Setelah SUJUD_2, sistem memutuskan:
```
┌──────────────────────────────────────────────────────────────────┐
│ Selesai SUJUD_2 di rakaat ke-N                                   │
│                                                                  │
│  N == tasyahud_awal_after?  ──Ya──►  TASYAHUD_AWAL ─► QIYAM     │
│  (Misal N==2 untuk sholat 4 rakaat)         (lanjut rakaat N+1) │
│                                                                  │
│  N == total_rakaat?  ──Ya──►  TASYAHUD_AKHIR ─► SALAM ─► SELESAI │
│                                                                  │
│  Selain itu:  ──────────────────────────►  QIYAM (rakaat N+1)   │
└──────────────────────────────────────────────────────────────────┘
```

### Diagram Lengkap: Sholat 4 Rakaat (Dhuhur/Ashar/Isya)

```
Rakaat 1:  QIYAM → TAKBIR → SEDEKAP → RUKU → ITIDAL → SUJUD_1 → JALSA → SUJUD_2
                                                                              │
                                                                         (lanjut)
                                                                              ▼
Rakaat 2:  QIYAM → SEDEKAP → RUKU → ITIDAL → SUJUD_1 → JALSA → SUJUD_2
                                                                    │
                                                           (N==2 = tasyahud_awal)
                                                                    ▼
                                                           TASYAHUD_AWAL
                                                                    │
                                                               (berdiri)
                                                                    ▼
Rakaat 3:  QIYAM → SEDEKAP → RUKU → ITIDAL → SUJUD_1 → JALSA → SUJUD_2
                                                                    │
                                                               (lanjut)
                                                                    ▼
Rakaat 4:  QIYAM → SEDEKAP → RUKU → ITIDAL → SUJUD_1 → JALSA → SUJUD_2
                                                                    │
                                                         (N==4 = rakaat terakhir)
                                                                    ▼
                                                           TASYAHUD_AKHIR
                                                                    │
                                                                  SALAM
                                                                    │
                                                                SELESAI ✅
```

### Diagram: Sholat 3 Rakaat (Maghrib)

```
Rakaat 1 & 2: (sama seperti di atas)
                          │
                   TASYAHUD_AWAL
                          │
Rakaat 3:  QIYAM → SEDEKAP → RUKU → ITIDAL → SUJUD_1 → JALSA → SUJUD_2
                                                                    │
                                                           TASYAHUD_AKHIR → SALAM
```

### Diagram: Sholat 2 Rakaat (Subuh)

```
Rakaat 1: QIYAM → TAKBIR → SEDEKAP → RUKU → ITIDAL → SUJUD_1 → JALSA → SUJUD_2
                                                                              │
Rakaat 2: QIYAM → SEDEKAP → RUKU → ITIDAL → SUJUD_1 → JALSA → SUJUD_2
                                                                    │
                                                          TASYAHUD_AKHIR → SALAM
```

### State Machine Class (Extended)

```python
class SholatStateMachine:
    sholat_type: str          # "Subuh", "Dhuhur", "Ashar", "Maghrib", "Isya"
    total_rakaat: int         # 2, 3, atau 4
    tasyahud_awal_after: int  # setelah rakaat ke berapa ada Tasyahud Awal

    current_rakaat: int       # 1 sampai total_rakaat
    current_state: str        # state dalam rakaat saat ini
    hold_counter: int         # berapa frame pose sudah ditahan

    completed_steps: list     # log semua gerakan yang dikonfirmasi
    is_first_rakaat: bool     # untuk bedakan Takbiratul Ihram vs Takbir intiqal
    sujud_count: int          # 0, 1, 2 dalam rakaat saat ini
    is_finished: bool         # True setelah Salam

    # Metode utama:
    def select_prayer(sholat_type: str)     # dipanggil saat user memilih
    def update(detected_pose: str)          # dipanggil setiap frame
    def is_valid_transition(from_s, to_s)  # validasi urutan
    def next_rakaat()                       # increment rakaat, reset state internal
    def reset()                             # reset semua ke awal
```

### Cara User Memilih Sholat

Sebelum sesi dimulai, user menekan tombol keyboard:
```
Keyboard shortcut saat di layar pemilihan:
  1 → Subuh   (2 rakaat)
  2 → Dhuhur  (4 rakaat)
  3 → Ashar   (4 rakaat)
  4 → Maghrib (3 rakaat)
  5 → Isya    (4 rakaat)
  C → mulai Kalibrasi
  Q → keluar
```

---

## 19. Mode Kalibrasi

Tujuan: menyesuaikan threshold sudut secara otomatis dengan proporsi tubuh pengguna.

### Alur Kalibrasi (Mudah Dioperasikan)

```
┌──────────────────────────────────────────────────────┐
│  LAYAR KALIBRASI                                     │
│                                                      │
│  1. Pengguna melihat instruksi di layar              │
│  2. "Berdiri tegak, tekan [C] untuk mulai"           │
│  3. Countdown 5 detik di layar (+ bar progress)      │
│  4. Sistem merekam rata-rata posisi landmark         │
│  5. "Kalibrasi selesai! Tekan [1-5] untuk sholat"    │
└──────────────────────────────────────────────────────┘
```

### Yang Dikalibrasi Secara Otomatis

| Parameter | Cara Kalibrasi |
|-----------|---------------|
| `shoulder_y_ref` | Rata-rata Y bahu saat berdiri tegak |
| `hip_y_ref` | Rata-rata Y pinggul saat berdiri tegak |
| `knee_y_ref` | Rata-rata Y lutut saat berdiri tegak |
| `body_height_ref` | Jarak vertikal bahu–lutut (normalisasi ukuran tubuh) |
| Threshold Ruku' | Dihitung ulang berdasarkan proporsi tubuh |
| Threshold Sujud | Dihitung ulang berdasarkan proporsi tubuh |

### Contoh Penyesuaian Threshold Dinamis

```python
def apply_calibration(calib_data: dict, config: dict) -> dict:
    body_h = calib_data["shoulder_y"] - calib_data["knee_y"]  # tinggi relatif

    # Sesuaikan threshold berdasarkan proporsi tubuh pengguna
    # (orang tinggi vs pendek akan punya range sudut berbeda)
    config["HIP_RUKU_MIN"] = calib_data["hip_angle_standing"] - 80
    config["HIP_RUKU_MAX"] = calib_data["hip_angle_standing"] - 40
    config["WRIST_ABOVE_SHOULDER"] = calib_data["shoulder_y"] + 0.02
    return config
```

### Penyimpanan Kalibrasi

Kalibrasi disimpan ke file `calibration.json` agar **tidak perlu kalibrasi ulang** setiap sesi:
```json
{
  "calibrated_at": "2026-06-23T23:00:00",
  "shoulder_y": 0.32,
  "hip_y": 0.58,
  "knee_y": 0.75,
  "body_height_ref": 0.43,
  "thresholds": {
    "HIP_RUKU_MIN": 68,
    "HIP_RUKU_MAX": 115,
    "HIP_SUJUD_MAX": 75
  }
}
```

---

## 20. CSV Logging

### Format File Log

Log disimpan di: `logs/sholat_YYYYMMDD_HHMMSS.csv`

```csv
timestamp,sholat_type,rakaat,pose,hold_frames,duration_sec,status,notes
2026-06-23 23:01:00,Dhuhur,1,TAKBIR,12,0.80,CONFIRMED,
2026-06-23 23:01:01,Dhuhur,1,SEDEKAP,48,3.20,CONFIRMED,
2026-06-23 23:01:04,Dhuhur,1,RUKU,18,1.20,CONFIRMED,
2026-06-23 23:01:05,Dhuhur,1,ITIDAL,10,0.67,CONFIRMED,
2026-06-23 23:01:06,Dhuhur,1,SUJUD_1,15,1.00,CONFIRMED,
2026-06-23 23:01:07,Dhuhur,1,JALSA,10,0.67,CONFIRMED,
2026-06-23 23:01:08,Dhuhur,1,SUJUD_2,15,1.00,CONFIRMED,
2026-06-23 23:01:09,Dhuhur,2,SEDEKAP,50,3.33,CONFIRMED,
...
2026-06-23 23:10:00,Dhuhur,4,TASYAHUD_AKHIR,60,4.00,CONFIRMED,
2026-06-23 23:10:04,Dhuhur,4,SALAM,20,1.33,CONFIRMED,
2026-06-23 23:10:05,Dhuhur,4,SELESAI,,,DONE,Total: 9m05s
```

### Ringkasan Sesi (Session Summary)

Di akhir sesi, sistem juga menulis file `logs/summary_YYYYMMDD_HHMMSS.json`:
```json
{
  "sholat_type": "Dhuhur",
  "total_rakaat": 4,
  "started_at": "2026-06-23 23:01:00",
  "finished_at": "2026-06-23 23:10:05",
  "total_duration_sec": 545,
  "poses_confirmed": 38,
  "poses_missed": 0,
  "avg_ruku_duration_sec": 1.15,
  "avg_sujud_duration_sec": 1.05,
  "status": "COMPLETED"
}
```

### Implementasi (Sederhana)

```python
import csv, json
from datetime import datetime

class SholatLogger:
    def __init__(self, sholat_type: str):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.csv_path = f"logs/sholat_{timestamp}.csv"
        self.json_path = f"logs/summary_{timestamp}.json"
        self._init_csv()

    def log_pose(self, rakaat, pose, frames, duration, status):
        # Tulis satu baris ke CSV
        ...

    def write_summary(self, stats: dict):
        # Tulis ringkasan ke JSON
        ...
```

---

## 21. Rencana Pengembangan (Diperbarui)

### ✅ Fase 0 — Setup & Infrastruktur
- [ ] Buat struktur folder: `proto-2/`, `proto-2/logs/`
- [ ] Buat `requirements.txt`
- [ ] Buat `config.py` dengan profil `laptop`/`opi4pro` + `SHOLAT_CONFIG` 5 waktu
- [ ] Buat `calibration.json` kosong sebagai template
- [ ] Test kamera terbuka dengan V4L2 backend

### 🔨 Fase 1 — Core Detection MVP (di Laptop)
- [ ] Implementasi `pose_utils.py` (sudut, jarak, visibility check)
- [ ] Implementasi `pose_classifier.py` — 4 pose: Qiyam, Takbir, Ruku', Sujud
- [ ] Test live kamera, tampilkan nama pose + nilai sudut
- [ ] Tuning threshold sampai akurasi ≥ 80% untuk 4 pose ini

### 🔨 Fase 2 — Semua Pose + State Machine
- [ ] Tambahkan pose: Sedekap, I'tidal, Jalsa, Tasyahud Awal/Akhir
- [ ] Implementasi `state_machine.py` dengan multi-rakaat support
- [ ] Integrasi classifier + state machine untuk 1 rakaat penuh
- [ ] Tambahkan pemilihan sholat (keyboard 1–5)
- [ ] Test semua 5 waktu sholat end-to-end

### 🔨 Fase 3 — Kalibrasi & Logging
- [ ] Implementasi mode kalibrasi + simpan `calibration.json`
- [ ] Implementasi `SholatLogger` — CSV + JSON summary
- [ ] Load kalibrasi otomatis saat startup jika file ada
- [ ] Test logging satu sesi penuh

### 🔨 Fase 4 — Visualisasi & UI
- [ ] Implementasi `visualizer.py`
- [ ] Layar pemilihan sholat (keyboard 1–5)
- [ ] Progress bar rakaat + pose
- [ ] Hold counter bar animasi
- [ ] Debug mode toggle (`d`) — tampilkan nilai sudut
- [ ] Warna skeleton berbeda per kelompok sendi

### 🔨 Fase 5 — Optimasi OPi 4 Pro
- [ ] Switch ke profil `opi4pro` di `config.py`
- [ ] Implementasi frame skipping
- [ ] Benchmark FPS di OPi 4 Pro
- [ ] Tuning threshold ulang jika ada perbedaan
- [ ] Stress test panjang (30 menit) → cek thermal throttling

### 🎁 Fase 6 — Bonus: Deteksi Salam
- [ ] Implementasi deteksi Salam (head offset method)
- [ ] Bedakan Salam kanan vs kiri
- [ ] Integrasi ke state machine sebagai state terakhir

---

*Dokumen ini adalah living document — update seiring implementasi.*
*Terakhir diperbarui: 2026-06-23 | Versi: 3.0*
