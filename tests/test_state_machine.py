import unittest
import sys
import os

# Tambahkan path core agar bisa diimport
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core"))

from config import POSE
from core.state_machine import SholatStateMachine

class TestSholatStateMachine(unittest.TestCase):
    def setUp(self):
        # Inisialisasi state machine untuk Sholat Subuh (2 Rakaat)
        self.sm = SholatStateMachine("Subuh")

    def test_initial_state(self):
        self.assertEqual(self.sm.current_state, POSE.UNKNOWN)
        self.assertEqual(self.sm.rakaat_count, 1)

    def test_allowed_transitions(self):
        # Dari UNKNOWN, hanya boleh ke BERDIRI_TEGAK
        allowed = self.sm.get_allowed_next_states()
        self.assertIn(POSE.BERDIRI_TEGAK, allowed)

    def test_transition_commit_hold(self):
        # Jalankan loop update untuk mensimulasikan hold frames
        # Sesuai konfigurasi, butuh self.sm.max_hold_frames frame hold sebelum commit
        hold_required = self.sm.max_hold_frames
        transition = None
        for i in range(hold_required):
            transition = self.sm.update(POSE.BERDIRI_TEGAK)
            if i < hold_required - 1:
                self.assertIsNone(transition)
                self.assertEqual(self.sm.current_state, POSE.UNKNOWN)
        
        self.assertIsNotNone(transition)
        self.assertEqual(self.sm.current_state, POSE.BERDIRI_TEGAK)
        self.assertEqual(transition["to"], POSE.BERDIRI_TEGAK)

    def test_full_sequence_subuh(self):
        # Simulasi full sequence sholat Subuh
        # Rakaat 1
        self._simulate_pose(POSE.BERDIRI_TEGAK)
        self._simulate_pose(POSE.BERSEDEKAP)
        self._simulate_pose(POSE.RUKUK)
        self._simulate_pose(POSE.ITIDAL)
        self._simulate_pose(POSE.SUJUD_PERTAMA)
        self._simulate_pose(POSE.DUDUK_DI_ANTARA_DUA_SUJUD)
        self._simulate_pose(POSE.SUJUD_KEDUA)
        
        # Selesai Rakaat 1 -> Berdiri ke Rakaat 2 (langsung bersedekap)
        transition = self._simulate_pose(POSE.BERSEDEKAP)
        self.assertEqual(self.sm.rakaat_count, 2)
        
        # Rakaat 2
        self._simulate_pose(POSE.RUKUK)
        self._simulate_pose(POSE.ITIDAL)
        self._simulate_pose(POSE.SUJUD_PERTAMA)
        self._simulate_pose(POSE.DUDUK_DI_ANTARA_DUA_SUJUD)
        self._simulate_pose(POSE.SUJUD_KEDUA)
        
        # Rakaat 2 adalah rakaat terakhir Subuh -> harus masuk ke Tasyahud Akhir
        self._simulate_pose(POSE.DUDUK_TASYAHUD_AKHIR)
        self._simulate_pose(POSE.SALAM_KE_KANAN)
        self._simulate_pose(POSE.SALAM_KE_KIRI)
        self._simulate_pose(POSE.SELESAI)
        
        self.assertEqual(self.sm.current_state, POSE.SELESAI)
        self.assertEqual(self.sm.rakaat_count, 2)

    def _simulate_pose(self, pose):
        # Helper untuk commit pose (kirim max_hold_frames)
        transition = None
        for _ in range(self.sm.max_hold_frames):
            transition = self.sm.update(pose)
        return transition

if __name__ == '__main__':
    unittest.main()
