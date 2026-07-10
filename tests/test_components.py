import unittest
import sys
import os
from unittest.mock import MagicMock

# Tambahkan path core agar bisa diimport
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core"))

from config import POSE, LANDMARK
from core.prayer_scheduler import get_current_prayer
from core.pose_classifier import get_pose_features, classify_pose

class TestPrayerScheduler(unittest.TestCase):
    """Menguji logika penentuan waktu sholat otomatis berbasis jam."""
    
    def test_subuh_slot(self):
        # 04:30 berada di dalam slot Subuh (03:45 - 06:00)
        self.assertEqual(get_current_prayer("04:30"), "Subuh")
        
    def test_dhuhur_slot(self):
        # 12:00 berada di dalam slot Dhuhur (11:15 - 14:30)
        self.assertEqual(get_current_prayer("12:00"), "Dhuhur")
        
    def test_ashar_slot(self):
        # 15:30 berada di dalam slot Ashar (14:30 - 17:15)
        self.assertEqual(get_current_prayer("15:30"), "Ashar")
        
    def test_maghrib_slot(self):
        # 17:50 berada di dalam slot Maghrib (17:15 - 18:30)
        self.assertEqual(get_current_prayer("17:50"), "Maghrib")
        
    def test_isya_slot(self):
        # 20:00 malam dan 01:00 dini hari berada di slot Isya
        self.assertEqual(get_current_prayer("20:00"), "Isya")
        self.assertEqual(get_current_prayer("01:00"), "Isya")


class TestPoseClassifier(unittest.TestCase):
    """Menguji logika ekstraksi fitur dan klasifikasi gerakan sholat."""

    def _create_mock_landmark(self, x, y, visibility=0.9):
        # Helper untuk membuat objek landmark tiruan
        lm = MagicMock()
        lm.x = x
        lm.y = y
        lm.visibility = visibility
        return lm

    def _build_mock_landmarks(self):
        # Membuat array/list mock MediaPipe landmarks dengan 33 poin
        landmarks_mock = MagicMock()
        # Default all landmarks ke posisi berdiri tegak
        landmarks_mock.landmark = [self._create_mock_landmark(0.5, 0.8) for _ in range(33)]
        
        # Atur beberapa posisi default berdiri tegak
        # Bahu di Y = 0.3
        landmarks_mock.landmark[LANDMARK.LEFT_SHOULDER] = self._create_mock_landmark(0.4, 0.3)
        landmarks_mock.landmark[LANDMARK.RIGHT_SHOULDER] = self._create_mock_landmark(0.6, 0.3)
        # Hidung di Y = 0.15
        landmarks_mock.landmark[LANDMARK.NOSE] = self._create_mock_landmark(0.5, 0.15)
        # Pinggul di Y = 0.55
        landmarks_mock.landmark[LANDMARK.LEFT_HIP] = self._create_mock_landmark(0.4, 0.55)
        landmarks_mock.landmark[LANDMARK.RIGHT_HIP] = self._create_mock_landmark(0.6, 0.55)
        # Siku di Y = 0.45
        landmarks_mock.landmark[LANDMARK.LEFT_ELBOW] = self._create_mock_landmark(0.35, 0.45)
        landmarks_mock.landmark[LANDMARK.RIGHT_ELBOW] = self._create_mock_landmark(0.65, 0.45)
        # Pergelangan tangan di Y = 0.65 (berdiri tegak tangan ke bawah)
        landmarks_mock.landmark[LANDMARK.LEFT_WRIST] = self._create_mock_landmark(0.35, 0.65)
        landmarks_mock.landmark[LANDMARK.RIGHT_WRIST] = self._create_mock_landmark(0.65, 0.65)
        # Lutut di Y = 0.75
        landmarks_mock.landmark[LANDMARK.LEFT_KNEE] = self._create_mock_landmark(0.4, 0.75)
        landmarks_mock.landmark[LANDMARK.RIGHT_KNEE] = self._create_mock_landmark(0.6, 0.75)
        # Mata kaki di Y = 0.95
        landmarks_mock.landmark[LANDMARK.LEFT_ANKLE] = self._create_mock_landmark(0.4, 0.95)
        landmarks_mock.landmark[LANDMARK.RIGHT_ANKLE] = self._create_mock_landmark(0.6, 0.95)
        
        return landmarks_mock

    def test_classify_unknown_visibility(self):
        # Jika visibility landmark kritis rendah, harus mengembalikan POSE.UNKNOWN
        lm = self._build_mock_landmarks()
        # Set visibility bahu ke 0.1 (sangat buram)
        lm.landmark[LANDMARK.LEFT_SHOULDER].visibility = 0.1
        self.assertEqual(classify_pose(lm), POSE.UNKNOWN)

    def test_classify_berdiri_tegak(self):
        # Pada kondisi default yang lurus, classifier harus mendeteksi BERDIRI_TEGAK
        lm = self._build_mock_landmarks()
        self.assertEqual(classify_pose(lm), POSE.BERDIRI_TEGAK)

    def test_classify_takbir(self):
        lm = self._build_mock_landmarks()
        # Untuk Takbir, tangan sejajar/di atas kepala (Y hidung = 0.15)
        lm.landmark[LANDMARK.LEFT_WRIST] = self._create_mock_landmark(0.35, 0.13)
        lm.landmark[LANDMARK.RIGHT_WRIST] = self._create_mock_landmark(0.65, 0.13)
        self.assertEqual(classify_pose(lm), POSE.TAKBIRATUL_IHRAM)

    def test_classify_sedekap(self):
        lm = self._build_mock_landmarks()
        # Untuk Bersedekap, tangan di bawah bahu (0.3), di atas pinggul (0.55), dan berdekatan secara X
        lm.landmark[LANDMARK.LEFT_WRIST] = self._create_mock_landmark(0.48, 0.45)
        lm.landmark[LANDMARK.RIGHT_WRIST] = self._create_mock_landmark(0.52, 0.45)
        self.assertEqual(classify_pose(lm), POSE.BERSEDEKAP)


if __name__ == '__main__':
    unittest.main()
