"""
============================================================
GEMA Imam — Sholat Movement Tracking
haptic_notifier.py — Kirim sinyal UDP ke modul getar ESP32
============================================================

Mengirim satu UDP packet ke ESP32 saat audio bacaan state
sholat selesai diputar — sebagai feedback taktil untuk imam.

Tidak perlu install library tambahan (pakai socket bawaan Python).
Silent fail jika ESP32 tidak terhubung — tidak mengganggu program utama.
"""

import socket
import os
import subprocess

HAPTIC_PORT = 9999

def get_auto_broadcast_ip():
    """
    Otomatis mendeteksi IP Broadcast dari interface jaringan aktif (misal wlan0).
    Jika HAPTIC_BROADCAST_IP di .env diisi, gunakan nilai tersebut.
    Jika tidak diisi, otomatis deteksi dari sistem.
    """
    env_override = os.environ.get("HAPTIC_BROADCAST_IP", "").strip()
    if env_override:
        return env_override

    try:
        res = subprocess.run(["ip", "-4", "addr", "show"], capture_output=True, text=True, timeout=2)
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if "brd" in line and " scope global " in line and " lo" not in line:
                    parts = line.strip().split()
                    if "brd" in parts:
                        idx = parts.index("brd")
                        if idx + 1 < len(parts):
                            return parts[idx + 1]
    except Exception:
        pass

    return "255.255.255.255"

class HapticNotifier:
    def __init__(self):
        self._enabled = False
        self.broadcast_ip = get_auto_broadcast_ip()
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._sock.settimeout(0.01)  # non-blocking, timeout sangat singkat
            self._enabled = True
            print(f"[HAPTIC] UDP notifier aktif -> broadcast ke {self.broadcast_ip}:{HAPTIC_PORT}")
        except Exception as e:
            print(f"[HAPTIC WARNING] Gagal inisialisasi UDP socket: {e}. Modul getar dinonaktifkan.")

    def notify(self):
        """
        Kirim sinyal ke ESP32 untuk memicu getaran 1x.
        Dipanggil ketika audio bacaan state sholat selesai diputar.
        """
        if not self._enabled:
            return
        try:
            self._sock.sendto(b"DONE", (self.broadcast_ip, HAPTIC_PORT))
        except Exception:
            pass  # silent fail — tidak mengganggu program utama

    def stop(self):
        """Tutup socket saat program ditutup."""
        if self._enabled:
            try:
                self._sock.close()
            except Exception:
                pass
