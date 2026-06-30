"""
============================================================
GEMA Imam — Sholat Movement Tracking
pose_classifier.py — Klasifikasi pose instan berdasarkan landmark
============================================================
"""

from config import THRESHOLDS, LANDMARK, POSE
from pose_utils import get_coords, calculate_angle, get_avg_angle, check_visibility

def get_pose_features(landmarks):
    """
    Menghitung sudut dan fitur spasial penting untuk klasifikasi pose.
    Mengembalikan dictionary berisi nilai fitur.
    """
    feat = {}
    
    # 1. Koordinat dasar landmark utama
    nose = get_coords(landmarks, LANDMARK.NOSE)
    sh_l = get_coords(landmarks, LANDMARK.LEFT_SHOULDER)
    sh_r = get_coords(landmarks, LANDMARK.RIGHT_SHOULDER)
    hip_l = get_coords(landmarks, LANDMARK.LEFT_HIP)
    hip_r = get_coords(landmarks, LANDMARK.RIGHT_HIP)
    knee_l = get_coords(landmarks, LANDMARK.LEFT_KNEE)
    knee_r = get_coords(landmarks, LANDMARK.RIGHT_KNEE)
    wrist_l = get_coords(landmarks, LANDMARK.LEFT_WRIST)
    wrist_r = get_coords(landmarks, LANDMARK.RIGHT_WRIST)
    
    # 2. Perhitungan sudut sendi (Rata-rata Kiri + Kanan)
    feat["hip_angle"] = get_avg_angle(
        landmarks,
        [LANDMARK.LEFT_SHOULDER, LANDMARK.RIGHT_SHOULDER],
        [LANDMARK.LEFT_HIP, LANDMARK.RIGHT_HIP],
        [LANDMARK.LEFT_KNEE, LANDMARK.RIGHT_KNEE]
    )
    
    feat["knee_angle"] = get_avg_angle(
        landmarks,
        [LANDMARK.LEFT_HIP, LANDMARK.RIGHT_HIP],
        [LANDMARK.LEFT_KNEE, LANDMARK.RIGHT_KNEE],
        [LANDMARK.LEFT_ANKLE, LANDMARK.RIGHT_ANKLE]
    )
    
    feat["arm_angle"] = get_avg_angle(
        landmarks,
        [LANDMARK.LEFT_SHOULDER, LANDMARK.RIGHT_SHOULDER],
        [LANDMARK.LEFT_ELBOW, LANDMARK.RIGHT_ELBOW],
        [LANDMARK.LEFT_WRIST, LANDMARK.RIGHT_WRIST]
    )
    
    # 3. Posisi relatif pergelangan tangan (Y-axis: 0=atas, 1=bawah)
    # Rata-rata bahu & pinggul sebagai pembanding Y
    sh_y_avg = (sh_l[1] + sh_r[1]) / 2.0
    hip_y_avg = (hip_l[1] + hip_r[1]) / 2.0
    
    feat["wrist_l_above_shoulder"] = wrist_l[1] < (sh_l[1] + THRESHOLDS["TAKBIR_WRIST_ABOVE_SHOULDER"])
    feat["wrist_r_above_shoulder"] = wrist_r[1] < (sh_r[1] + THRESHOLDS["TAKBIR_WRIST_ABOVE_SHOULDER"])
    
    feat["wrist_l_below_shoulder"] = wrist_l[1] > (sh_l[1] + THRESHOLDS["SEDEKAP_WRIST_BELOW_SHOULDER"])
    feat["wrist_r_below_shoulder"] = wrist_r[1] > (sh_r[1] + THRESHOLDS["SEDEKAP_WRIST_BELOW_SHOULDER"])
    
    feat["wrist_l_above_hip"] = wrist_l[1] < (hip_l[1] + THRESHOLDS["SEDEKAP_WRIST_ABOVE_HIP"])
    feat["wrist_r_above_hip"] = wrist_r[1] < (hip_r[1] + THRESHOLDS["SEDEKAP_WRIST_ABOVE_HIP"])
    
    # Jarak horizontal antar tangan (untuk sedekap)
    feat["wrist_dist_x"] = abs(wrist_l[0] - wrist_r[0])
    
    # Hidung relatif terhadap bahu & pinggul
    feat["nose_below_shoulder"] = nose[1] > (sh_y_avg + THRESHOLDS["SUJUD_NOSE_BELOW_SHOULDER"])
    feat["nose_below_hip"] = nose[1] > (hip_y_avg + THRESHOLDS["SUJUD_NOSE_BELOW_HIP"])
    feat["nose_above_shoulder"] = nose[1] < sh_y_avg
    
    # Posisi vertikal lutut vs pinggul
    knee_y_avg = (knee_l[1] + knee_r[1]) / 2.0
    feat["knee_below_hip"] = knee_y_avg > hip_y_avg
    
    # Deteksi simpangan kepala untuk salam (X-axis)
    sh_x_center = (sh_l[0] + sh_r[0]) / 2.0
    feat["head_offset_x"] = nose[0] - sh_x_center
    
    return feat

def classify_pose(landmarks):
    """
    Mengklasifikasikan pose instan (per frame) dari MediaPipe landmarks.
    Mengembalikan nama string dari kelas POSE.
    """
    # 1. Validasi visibilitas landmark kritis
    if not check_visibility(landmarks, LANDMARK.CRITICAL, THRESHOLDS["LANDMARK_MIN_VISIBILITY"]):
        return POSE.UNKNOWN
        
    feat = get_pose_features(landmarks)
    
    # ── A. SUJUD ──
    # Ciri khas: Lutut tertekuk tajam, hidung berada di bawah bahu & pinggul
    if (feat["knee_angle"] < THRESHOLDS["KNEE_BENT_MAX"] and 
            feat["nose_below_shoulder"] and 
            feat["nose_below_hip"] and
            feat["hip_angle"] < THRESHOLDS["HIP_SUJUD_MAX"]):
        return POSE.SUJUD
        
    # ── B. DUDUK (Jalsa / Tasyahud) ──
    # Ciri khas: Lutut tertekuk, kepala tegak (hidung di atas bahu), lutut di bawah pinggul
    if (feat["knee_angle"] < THRESHOLDS["KNEE_BENT_MAX"] and 
            feat["nose_above_shoulder"] and 
            feat["knee_below_hip"]):
        return POSE.JALSA
        
    # ── C. RUKU' ──
    # Ciri khas: Pinggul tertekuk mendekati 90 derajat, lutut tetap lurus
    if (THRESHOLDS["HIP_RUKU_MIN"] <= feat["hip_angle"] <= THRESHOLDS["HIP_RUKU_MAX"] and 
            feat["knee_angle"] > THRESHOLDS["KNEE_STRAIGHT_MIN"]):
        return POSE.RUKUK
        
    # ── D. SALAM (Menoleh Kanan / Kiri saat Berdiri/Duduk) ──
    # Catatan: Salam terdeteksi dari simpangan kepala
    if feat["head_offset_x"] > THRESHOLDS["SALAM_HEAD_OFFSET_THRESHOLD"]:
        return POSE.SALAM_KE_KANAN  # Salam (arah kanan)
    elif feat["head_offset_x"] < -THRESHOLDS["SALAM_HEAD_OFFSET_THRESHOLD"]:
        return POSE.SALAM_KE_KIRI   # Salam (arah kiri)
        
    # ── E. POSE BERDIRI (Takbir / Sedekap / Qiyam) ──
    # Jika pinggul dan lutut dalam posisi lurus/tegak
    if (feat["hip_angle"] > THRESHOLDS["HIP_STRAIGHT_MIN"] and 
            feat["knee_angle"] > THRESHOLDS["KNEE_STRAIGHT_MIN"]):
            
        # 1. Takbiratul Ihram: Kedua tangan di atas bahu
        if feat["wrist_l_above_shoulder"] and feat["wrist_r_above_shoulder"]:
            # Validasi tambahan: sudut siku terangkat / terbuka
            if feat["arm_angle"] > THRESHOLDS["TAKBIR_ARM_ANGLE_MIN"]:
                return POSE.TAKBIRATUL_IHRAM
                
        # 2. Bersedekap: Tangan di bawah bahu, di atas pinggul, dan berdekatan secara X
        if (feat["wrist_l_below_shoulder"] and feat["wrist_r_below_shoulder"] and 
                feat["wrist_l_above_hip"] and feat["wrist_r_above_hip"] and 
                feat["wrist_dist_x"] < THRESHOLDS["SEDEKAP_HAND_MAX_DIST_X"]):
            return POSE.BERSEDEKAP
            
        # 3. Qiyam: Berdiri tegak normal (tangan ke bawah)
        return POSE.BERDIRI_TEGAK
        
    # Jika tidak memenuhi syarat gerakan apapun
    return POSE.UNKNOWN
