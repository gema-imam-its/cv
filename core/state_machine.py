"""
============================================================
GEMA Imam — Sholat Movement Tracking
state_machine.py — Logika transisi gerakan sholat (State Machine)
============================================================
"""

from config import SHOLAT_CONFIG, THRESHOLDS, POSE

class SholatStateMachine:
    def __init__(self, active_prayer="Subuh"):
        self.active_prayer = active_prayer
        self.total_rakaats = SHOLAT_CONFIG[active_prayer]["rakaat"]
        self.tasyahud_awal_after = SHOLAT_CONFIG[active_prayer]["tasyahud_awal_after"]
        
        # State awal
        self.current_state = POSE.UNKNOWN
        self.rakaat_count = 1
        
        # Jitter smoothing
        self.hold_counter = 0
        self.target_state = None
        self.max_hold_frames = THRESHOLDS.get("POSE_HOLD_FRAMES", 10)
        
        # Log audit gerakan
        self.completed_steps = []
        
        # Flag untuk tracking audio sedekap (Iftitah hanya rakaat 1)
        self.is_first_sedekap = True
        
        print(f"[INFO] State Machine diinisialisasi untuk Sholat {active_prayer}")
        print(f"       Total Rakaat: {self.total_rakaats}, Tasyahud Awal setelah rakaat: {self.tasyahud_awal_after}")

    def reset(self):
        """Reset seluruh status state machine ke awal."""
        self.current_state = POSE.UNKNOWN
        self.rakaat_count = 1
        self.hold_counter = 0
        self.target_state = None
        self.completed_steps = []
        self.is_first_sedekap = True
        print("[INFO] State Machine berhasil di-reset.")

    def get_allowed_next_states(self):
        """
        Mendapatkan list pose yang valid untuk transisi berikutnya berdasarkan 
        state saat ini dan rakaat sholat yang aktif.
        """
        if self.current_state == POSE.UNKNOWN:
            return [POSE.BERDIRI_TEGAK]
            
        elif self.current_state == POSE.BERDIRI_TEGAK:
            if self.rakaat_count == 1:
                return [POSE.TAKBIRATUL_IHRAM, POSE.BERSEDEKAP]
            else:
                return [POSE.BERSEDEKAP, POSE.RUKUK]
                
        elif self.current_state == POSE.TAKBIRATUL_IHRAM:
            return [POSE.BERSEDEKAP]
            
        elif self.current_state == POSE.BERSEDEKAP:
            return [POSE.RUKUK]
            
        elif self.current_state == POSE.RUKUK:
            return [POSE.ITIDAL]
            
        elif self.current_state == POSE.ITIDAL:
            return [POSE.SUJUD_PERTAMA]
            
        elif self.current_state == POSE.SUJUD_PERTAMA:
            return [POSE.DUDUK_DI_ANTARA_DUA_SUJUD]
            
        elif self.current_state == POSE.DUDUK_DI_ANTARA_DUA_SUJUD:
            return [POSE.SUJUD_KEDUA]
            
        elif self.current_state == POSE.SUJUD_KEDUA:
            # Setelah sujud kedua, tentukan kelanjutan rakaat
            next_states = []
            if self.rakaat_count == self.total_rakaats:
                # Rakaat terakhir -> Tasyahud Akhir
                next_states.append(POSE.DUDUK_TASYAHUD_AKHIR)
            elif self.tasyahud_awal_after is not None and self.rakaat_count == self.tasyahud_awal_after:
                # Tasyahud Awal
                next_states.append(POSE.DUDUK_TASYAHUD_AWAL)
            else:
                # Berdiri ke rakaat berikutnya
                next_states.append(POSE.BERDIRI_TEGAK)
            return next_states
            
        elif self.current_state == POSE.DUDUK_TASYAHUD_AWAL:
            return [POSE.BERDIRI_TEGAK]
            
        elif self.current_state == POSE.DUDUK_TASYAHUD_AKHIR:
            return [POSE.SALAM_KE_KANAN]
            
        elif self.current_state == POSE.SALAM_KE_KANAN:
            return [POSE.SALAM_KE_KIRI]
            
        elif self.current_state == POSE.SALAM_KE_KIRI:
            return [POSE.SELESAI]
            
        elif self.current_state == POSE.SELESAI:
            return []
            
        return []

    def update(self, detected_pose):
        """
        Memperbarui status state machine berdasarkan pose yang dideteksi secara fisik.
        
        Returns:
            dict atau None - Info transisi jika terjadi commit.
        """
        # --- LOGIKA PEMETAAN POSE FISIK KE POSE LOGIS SHOLAT ---
        
        # 1. Pemetaan QIYAM ke ITIDAL jika bangun dari Rukuk
        if self.current_state == POSE.RUKUK and detected_pose == POSE.BERDIRI_TEGAK:
            detected_pose = POSE.ITIDAL

        # 2. Pemetaan Sujud fisik ke Sujud Pertama / Kedua
        if detected_pose == POSE.SUJUD:
            if self.current_state == POSE.ITIDAL:
                detected_pose = POSE.SUJUD_PERTAMA
            elif self.current_state == POSE.DUDUK_DI_ANTARA_DUA_SUJUD:
                detected_pose = POSE.SUJUD_KEDUA

        # 3. Pemetaan Duduk fisik (JALSA) ke Duduk Antara Sujud / Tasyahud
        if detected_pose == POSE.JALSA:
            if self.current_state == POSE.SUJUD_PERTAMA:
                detected_pose = POSE.DUDUK_DI_ANTARA_DUA_SUJUD
            elif self.current_state == POSE.SUJUD_KEDUA:
                if self.rakaat_count == self.total_rakaats:
                    detected_pose = POSE.DUDUK_TASYAHUD_AKHIR
                elif self.tasyahud_awal_after is not None and self.rakaat_count == self.tasyahud_awal_after:
                    detected_pose = POSE.DUDUK_TASYAHUD_AWAL

        # --- VALIDASI TRANSISI ---
        allowed_next = self.get_allowed_next_states()
        
        if detected_pose in allowed_next:
            if self.target_state != detected_pose:
                self.target_state = detected_pose
                self.hold_counter = 1
            else:
                self.hold_counter += 1
                
            if self.hold_counter >= self.max_hold_frames:
                return self._commit_transition(self.target_state)
                
        elif detected_pose == self.current_state:
            self.hold_counter = max(0, self.hold_counter - 1)
            if self.hold_counter == 0:
                self.target_state = None
        else:
            self.hold_counter = max(0, self.hold_counter - 1)
            if self.hold_counter == 0:
                self.target_state = None
        
        return None

    def _commit_transition(self, new_state):
        """Mengonfirmasi transisi dan mengembalikan data transisi."""
        old_state = self.current_state
        self.current_state = new_state
        self.hold_counter = 0
        self.target_state = None
        
        was_first_sedekap = self.is_first_sedekap
        
        # Logika increment rakaat
        if new_state == POSE.BERDIRI_TEGAK:
            if old_state in (POSE.SUJUD_KEDUA, POSE.DUDUK_TASYAHUD_AWAL):
                self.rakaat_count += 1
                
        elif new_state == POSE.BERSEDEKAP:
            if self.is_first_sedekap:
                self.is_first_sedekap = False
            
        log_entry = {
            "rakaat": self.rakaat_count,
            "state": new_state,
        }
        self.completed_steps.append(log_entry)
        
        print(f"[TRANSISI] Rakaat {self.rakaat_count}: {old_state} ──► {new_state}")
        
        return {
            "from": old_state,
            "to": new_state,
            "rakaat": self.rakaat_count,
            "is_first_sedekap": was_first_sedekap and new_state == POSE.BERSEDEKAP,
        }
