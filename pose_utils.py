"""
============================================================
GEMA Imam — Sholat Movement Tracking
pose_utils.py — Fungsi geometri & pemrosesan landmark
============================================================
"""

import numpy as np

def get_coords(landmarks, idx):
    """
    Mengambil koordinat (x, y) dari landmark MediaPipe berdasarkan index.
    Mengembalikan array numpy [x, y].
    """
    lm = landmarks.landmark[idx]
    return np.array([lm.x, lm.y])

def calculate_angle(a, b, c):
    """
    Menghitung sudut di titik b (dalam derajat) menggunakan 3 titik 2D: a, b, c.
    Formula: Cos(theta) = (BA . BC) / (|BA| * |BC|)
    """
    a = np.array(a)
    b = np.array(b)
    c = np.array(c)
    
    ba = a - b
    bc = c - b
    
    # Hitung dot product dan magnitude
    dot_product = np.dot(ba, bc)
    norm_ba = np.linalg.norm(ba)
    norm_bc = np.linalg.norm(bc)
    
    # Cegah pembagian dengan nol
    if norm_ba == 0 or norm_bc == 0:
        return 0.0
        
    cosine_angle = dot_product / (norm_ba * norm_bc)
    
    # Batasi nilai cosinus agar tetap dalam range [-1.0, 1.0] (menghindari error float precision)
    cosine_angle = np.clip(cosine_angle, -1.0, 1.0)
    
    # Ambil angle dalam radian lalu ubah ke derajat
    angle = np.degrees(np.arccos(cosine_angle))
    return float(angle)

def get_avg_angle(landmarks, idxs_a, idxs_b, idxs_c):
    """
    Menghitung rata-rata sudut sisi kiri dan kanan untuk mengurangi noise.
    Format index: [left_idx, right_idx]
    """
    # Sisi kiri
    a_l = get_coords(landmarks, idxs_a[0])
    b_l = get_coords(landmarks, idxs_b[0])
    c_l = get_coords(landmarks, idxs_c[0])
    angle_l = calculate_angle(a_l, b_l, c_l)
    
    # Sisi kanan
    a_r = get_coords(landmarks, idxs_a[1])
    b_r = get_coords(landmarks, idxs_b[1])
    c_r = get_coords(landmarks, idxs_c[1])
    angle_r = calculate_angle(a_r, b_r, c_r)
    
    return (angle_l + angle_r) / 2.0

def check_visibility(landmarks, required_idxs, min_vis=0.5):
    """
    Memeriksa apakah seluruh landmark dalam list required_idxs memiliki
    nilai visibilitas di atas min_vis.
    """
    for idx in required_idxs:
        if landmarks.landmark[idx].visibility < min_vis:
            return False
    return True
