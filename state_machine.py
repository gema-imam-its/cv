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
        self.sujud_count_in_rakaat = 0  # 0, 1, atau 2
        
        # Jitter smoothing
        self.hold_counter = 0
        self.target_state = None
        self.max_hold_frames = THRESHOLDS.get("POSE_HOLD_FRAMES", 10)
        
        # Log audit gerakan
        self.completed_steps = []
        
        print(f"[INFO] State Machine diinisialisasi untuk Sholat {active_prayer}")
        print(f"       Total Rakaat: {self.total_rakaats}, Tasyahud Awal setelah rakaat: {self.tasyahud_awal_after}")

    def reset(self):
        """Reset seluruh status state machine ke awal."""
        self.current_state = POSE.UNKNOWN
        self.rakaat_count = 1
        self.sujud_count_in_rakaat = 0
        self.hold_counter = 0
        self.target_state = None
        self.completed_steps = []
        print("[INFO] State Machine berhasil di-reset.")

    def get_allowed_next_states(self):
        """
        Mendapatkan list pose yang valid untuk transisi berikutnya berdasarkan 
        state saat ini, jumlah rakaat, dan hitungan sujud.
        """
        if self.current_state == POSE.UNKNOWN:
            return [POSE.QIYAM]
            
        elif self.current_state == POSE.QIYAM:
            if self.rakaat_count == 1:
                return [POSE.TAKBIR, POSE.SEDEKAP]
            else:
                return [POSE.SEDEKAP, POSE.RUKU]
                
        elif self.current_state == POSE.TAKBIR:
            return [POSE.SEDEKAP]
            
        elif self.current_state == POSE.SEDEKAP:
            return [POSE.RUKU]
            
        elif self.current_state == POSE.RUKU:
            return [POSE.ITIDAL]
            
        elif self.current_state == POSE.ITIDAL:
            return [POSE.SUJUD]
            
        elif self.current_state == POSE.SUJUD:
            if self.sujud_count_in_rakaat == 1:
                return [POSE.JALSA]
            else:
                # Setelah sujud ke-2
                next_states = []
                if self.rakaat_count == self.total_rakaats:
                    next_states.append(POSE.TASYAHUD_AKHIR)
                elif self.tasyahud_awal_after is not None and self.rakaat_count == self.tasyahud_awal_after:
                    next_states.append(POSE.TASYAHUD_AWAL)
                else:
                    next_states.append(POSE.QIYAM)
                return next_states
                
        elif self.current_state == POSE.JALSA:
            return [POSE.SUJUD]
            
        elif self.current_state == POSE.TASYAHUD_AWAL:
            return [POSE.QIYAM]
            
        elif self.current_state == POSE.TASYAHUD_AKHIR:
            return [POSE.SALAM]
            
        elif self.current_state == POSE.SALAM:
            return [POSE.SELESAI]
            
        elif self.current_state == POSE.SELESAI:
            return []
            
        return []

    def update(self, detected_pose):
        """
        Memperbarui status state machine berdasarkan pose yang terdeteksi pada frame saat ini.
        Menerapkan noise-filtering (hold counter) sebelum memicu transisi state resmi.
        """
        # 1. Dapatkan pose-pose berikutnya yang valid
        allowed_next = self.get_allowed_next_states()
        
        # 2. Jika pose yang dideteksi adalah salah satu dari pose berikutnya yang valid
        if detected_pose in allowed_next:
            if self.target_state != detected_pose:
                # Mengubah target transisi baru
                self.target_state = detected_pose
                self.hold_counter = 1
            else:
                # Tambah hold counter jika pose konsisten
                self.hold_counter += 1
                
            # Cek jika counter sudah melampaui batas frame hold
            if self.hold_counter >= self.max_hold_frames:
                self._commit_transition(self.target_state)
                
        # 3. Jika pose yang terdeteksi sama dengan state saat ini (stabil)
        elif detected_pose == self.current_state:
            # Perlahan kurangi counter target transisi (noise tolerance)
            self.hold_counter = max(0, self.hold_counter - 1)
            if self.hold_counter == 0:
                self.target_state = None
                
        # 4. Jika pose terdeteksi adalah noise / tidak relevan
        else:
            # Perlahan kurangi counter (decay filter)
            self.hold_counter = max(0, self.hold_counter - 1)
            if self.hold_counter == 0:
                self.target_state = None

    def _commit_transition(self, new_state):
        """Mengonfirmasi transisi state resmi dan memperbarui log gerakan."""
        old_state = self.current_state
        self.current_state = new_state
        self.hold_counter = 0
        self.target_state = None
        
        # Logika internal untuk melacak jumlah sujud dan rakaat
        if new_state == POSE.SUJUD:
            if old_state == POSE.ITIDAL:
                self.sujud_count_in_rakaat = 1
            elif old_state == POSE.JALSA:
                self.sujud_count_in_rakaat = 2
                
        elif new_state == POSE.QIYAM:
            # Bangkit dari sujud ke-2 atau tasyahud awal memulai rakaat baru
            self.rakaat_count += 1
            self.sujud_count_in_rakaat = 0
            
        # Log string representatif untuk audit/logging session
        log_entry = {
            "rakaat": self.rakaat_count,
            "state": new_state,
            "sujud_index": self.sujud_count_in_rakaat if new_state == POSE.SUJUD else None
        }
        self.completed_steps.append(log_entry)
        
        # Visual/console output
        sujud_suffix = f" ke-{self.sujud_count_in_rakaat}" if new_state == POSE.SUJUD else ""
        print(f"[TRANSISI] Rakaat {self.rakaat_count}: {old_state} ──► {new_state}{sujud_suffix}")
