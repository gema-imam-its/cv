"""
============================================================
GEMA Imam — Sholat Movement Tracking
visualizer.py — Render HUD, Skeleton, Progress Bar, & Debug Angles
============================================================
"""

import cv2
import numpy as np
from config import POSE, LANDMARK

def get_pixel_coords(lm, idx, w, h):
    """Mengonversi koordinat landmark ternormalisasi ke pixel gambar."""
    landmark = lm.landmark[idx]
    return int(landmark.x * w), int(landmark.y * h)

def draw_skeleton(frame, lm, color_theme=(0, 255, 100)):
    """
    Menggambar kerangka (skeleton) pose kustom dengan warna estetis.
    Membagi warna kerangka per bagian tubuh untuk tampilan premium.
    """
    h, w, _ = frame.shape
    
    # 1. Definisikan koneksi garis kerangka
    connections = {
        "torso": [
            (LANDMARK.LEFT_SHOULDER, LANDMARK.RIGHT_SHOULDER),
            (LANDMARK.RIGHT_SHOULDER, LANDMARK.RIGHT_HIP),
            (LANDMARK.RIGHT_HIP, LANDMARK.LEFT_HIP),
            (LANDMARK.LEFT_HIP, LANDMARK.LEFT_SHOULDER)
        ],
        "arms_l": [
            (LANDMARK.LEFT_SHOULDER, LANDMARK.LEFT_ELBOW),
            (LANDMARK.LEFT_ELBOW, LANDMARK.LEFT_WRIST)
        ],
        "arms_r": [
            (LANDMARK.RIGHT_SHOULDER, LANDMARK.RIGHT_ELBOW),
            (LANDMARK.RIGHT_ELBOW, LANDMARK.RIGHT_WRIST)
        ],
        "legs_l": [
            (LANDMARK.LEFT_HIP, LANDMARK.LEFT_KNEE),
            (LANDMARK.LEFT_KNEE, LANDMARK.LEFT_ANKLE)
        ],
        "legs_r": [
            (LANDMARK.RIGHT_HIP, LANDMARK.RIGHT_KNEE),
            (LANDMARK.RIGHT_KNEE, LANDMARK.RIGHT_ANKLE)
        ],
        "face": [
            (LANDMARK.LEFT_EAR, LANDMARK.LEFT_EYE),
            (LANDMARK.LEFT_EYE, LANDMARK.NOSE),
            (LANDMARK.NOSE, LANDMARK.RIGHT_EYE),
            (LANDMARK.RIGHT_EYE, LANDMARK.RIGHT_EAR)
        ]
    }
    
    # Warna HSL/RGB kustom untuk setiap segmen tubuh
    colors = {
        "torso": (255, 200, 50),   # Cyan/Light Blue
        "arms_l": (50, 150, 255),  # Orange Kiri
        "arms_r": (50, 150, 255),  # Orange Kanan
        "legs_l": (100, 255, 100), # Green Kiri
        "legs_r": (100, 255, 100), # Green Kanan
        "face": (255, 255, 255)    # White
    }
    
    # Gambar Garis Penghubung
    for segment, lines in connections.items():
        segment_color = colors[segment]
        for start_idx, end_idx in lines:
            # Pastikan landmark terlihat cukup jelas sebelum menggambar garis
            if (lm.landmark[start_idx].visibility > 0.5 and 
                    lm.landmark[end_idx].visibility > 0.5):
                pt1 = get_pixel_coords(lm, start_idx, w, h)
                pt2 = get_pixel_coords(lm, end_idx, w, h)
                cv2.line(frame, pt1, pt2, segment_color, 2, cv2.LINE_AA)
                
    # Gambar Sendi Bulat
    for idx in range(33):
        if lm.landmark[idx].visibility > 0.5:
            pt = get_pixel_coords(lm, idx, w, h)
            # Sendi kritis digambar dengan bulatan lebih tebal
            if idx in LANDMARK.CRITICAL:
                cv2.circle(frame, pt, 5, (0, 0, 255), -1) # Merah untuk kritis
                cv2.circle(frame, pt, 7, (255, 255, 255), 1, cv2.LINE_AA)
            else:
                cv2.circle(frame, pt, 4, color_theme, -1)

def draw_hud(frame, state, active_prayer, rakaat, fps, hold_counter, max_hold):
    """
    Menggambar HUD Card dengan gaya glassmorphism semi-transparan untuk
    menampilkan informasi sesi sholat saat ini.
    """
    h, w, _ = frame.shape
    
    # 1. Gambar latar HUD card semi-transparan (Top-Left)
    card_w, card_h = 320, 160
    overlay = frame.copy()
    cv2.rectangle(overlay, (15, 15), (15 + card_w, 15 + card_h), (35, 30, 25), -1)
    # Terapkan alpha blending untuk efek transparan
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
    
    # Gambar outline card
    cv2.rectangle(frame, (15, 15), (15 + card_w, 15 + card_h), (120, 100, 80), 1, cv2.LINE_AA)
    
    # 2. Tulis Info Sholat
    # Header Sholat
    cv2.putText(frame, f"GEMA IMAM — {active_prayer.upper()}", (25, 40), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 220, 255), 2, cv2.LINE_AA)
    
    # Rakaat
    cv2.putText(frame, f"Rakaat: {rakaat}", (25, 65), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1, cv2.LINE_AA)
    
    # FPS
    cv2.putText(frame, f"FPS: {fps:.1f}", (240, 65), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (160, 160, 160), 1, cv2.LINE_AA)
    
    # Garis Pembatas
    cv2.line(frame, (25, 75), (15 + card_w - 10, 75), (80, 80, 80), 1)
    
    # 3. Pose Aktif
    display_pose = POSE.DISPLAY_NAME.get(state, "Mencari Pose...")
    # Tentukan warna teks pose
    pose_colors = {
        POSE.UNKNOWN: (150, 150, 150),
        POSE.BERDIRI_TEGAK: (255, 255, 200),
        POSE.TAKBIRATUL_IHRAM: (180, 255, 180),
        POSE.BERSEDEKAP: (180, 255, 255),
        POSE.RUKUK: (255, 220, 180),
        POSE.ITIDAL: (230, 230, 230),
        POSE.SUJUD_PERTAMA: (180, 180, 255),
        POSE.SUJUD_KEDUA: (180, 180, 255),
        POSE.DUDUK_DI_ANTARA_DUA_SUJUD: (255, 180, 255),
        POSE.DUDUK_TASYAHUD_AWAL: (255, 150, 200),
        POSE.DUDUK_TASYAHUD_AKHIR: (255, 100, 180),
        POSE.SALAM_KE_KANAN: (100, 255, 255),
        POSE.SALAM_KE_KIRI: (100, 255, 255),
        POSE.SELESAI: (100, 255, 100)
    }
    pose_color = pose_colors.get(state, (255, 255, 255))
    
    cv2.putText(frame, "Pose Terdeteksi:", (25, 95), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)
    cv2.putText(frame, display_pose, (25, 120), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, pose_color, 2, cv2.LINE_AA)
                
    # 4. Progress Bar (Tahan Pose)
    if hold_counter > 0 and state != POSE.SELESAI:
        # Hitung persentase progress
        pct = min(1.0, hold_counter / max_hold)
        bar_w = card_w - 20
        bar_start_x = 25
        bar_y = 145
        
        # Latar belakang bar
        cv2.rectangle(frame, (bar_start_x, bar_y), (bar_start_x + bar_w, bar_y + 8), (50, 50, 50), -1)
        # Bar isi
        cv2.rectangle(frame, (bar_start_x, bar_y), (bar_start_x + int(bar_w * pct), bar_y + 8), (0, 255, 150), -1)

def draw_debug_angles(frame, lm, angles):
    """
    Menggambar nilai sudut sendi langsung di sebelah posisi sendi fisik di layar
    untuk memudahkan tuning threshold.
    """
    h, w, _ = frame.shape
    
    # Definisikan pemetaan sudut ke joint landmark untuk penempatan teks
    joint_mapping = {
        "hip_angle": LANDMARK.LEFT_HIP,
        "knee_angle": LANDMARK.LEFT_KNEE,
        "arm_angle": LANDMARK.LEFT_ELBOW
    }
    
    for name, angle in angles.items():
        if name in joint_mapping:
            idx = joint_mapping[name]
            if lm.landmark[idx].visibility > 0.5:
                pt = get_pixel_coords(lm, idx, w, h)
                # Tulis label sudut di sebelah sendi (geser sedikit ke kanan)
                cv2.putText(frame, f"{int(angle)}*", (pt[0] + 15, pt[1] + 5), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (50, 255, 255), 2, cv2.LINE_AA)
