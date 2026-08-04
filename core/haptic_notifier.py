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

# Konfigurasi — sesuaikan dengan subnet WiFi di lokasi
# Broadcast ke seluruh subnet agar tidak perlu hardcode IP ESP32
HAPTIC_PORT  = 9999
BROADCAST_IP = os.environ.get("HAPTIC_BROADCAST_IP", "192.168.1.255")

class HapticNotifier:
    def __init__(self):
        self._enabled = False
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._sock.settimeout(0.01)  # non-blocking, timeout sangat singkat
            self._enabled = True
            print(f"[HAPTIC] UDP notifier aktif -> broadcast ke {BROADCAST_IP}:{HAPTIC_PORT}")
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
            self._sock.sendto(b"DONE", (BROADCAST_IP, HAPTIC_PORT))
        except Exception:
            pass  # silent fail — tidak mengganggu program utama

    def stop(self):
        """Tutup socket saat program ditutup."""
        if self._enabled:
            try:
                self._sock.close()
            except Exception:
                pass
