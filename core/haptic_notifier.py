import socket
import os
import subprocess
import threading
import time

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
        self.last_esp32_ip = None
        self._running = False
        self._listener_thread = None

        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._sock.bind(("", HAPTIC_PORT))
            self._sock.settimeout(1.0)
            self._enabled = True
            self._running = True

            # Thread background untuk auto-discover IP ESP32 dari sinyal PING
            self._listener_thread = threading.Thread(
                target=self._listen_heartbeat, daemon=True, name="HapticHeartbeat"
            )
            self._listener_thread.start()

            print(f"[HAPTIC] UDP notifier aktif (Auto-Discovery) -> Broadcast: {self.broadcast_ip}:{HAPTIC_PORT}")
        except Exception as e:
            print(f"[HAPTIC WARNING] Gagal inisialisasi UDP socket: {e}. Modul getar dinonaktifkan.")

    def _listen_heartbeat(self):
        """Mendengarkan sinyal PING berkala dari ESP32 untuk mencatat IP Aslinya (Direct IP)."""
        while self._running:
            try:
                data, addr = self._sock.recvfrom(64)
                if data and b"PING" in data:
                    sender_ip = addr[0]
                    if sender_ip != self.last_esp32_ip:
                        self.last_esp32_ip = sender_ip
                        print(f"[HAPTIC] 🎯 ESP32 terdeteksi di Direct IP: {self.last_esp32_ip}")
            except socket.timeout:
                continue
            except Exception:
                break

    def _send(self, payload: bytes):
        """
        Kirim payload UDP ke ESP32 secara ganda (Dual Send):
        1. Via Direct IP (jika terdeteksi dari PING -> tembus WiFi Kampus/Enterprise)
        2. Via Broadcast IP (untuk Hotspot HP / Router Biasa)
        """
        if not self._enabled:
            return

        # 1. Kirim Direct ke IP ESP32 jika terdaftar (Bypass AP Isolation WiFi Kampus)
        if self.last_esp32_ip:
            try:
                self._sock.sendto(payload, (self.last_esp32_ip, HAPTIC_PORT))
            except Exception:
                pass

        # 2. Kirim via Broadcast (untuk Hotspot HP)
        try:
            self._sock.sendto(payload, (self.broadcast_ip, HAPTIC_PORT))
        except Exception:
            pass

    def notify_start(self):
        """
        Kirim sinyal 'START' (1x getar) saat masuk ke pose/gerakan baru.
        """
        self._send(b"START")

    def notify(self):
        """
        Kirim sinyal 'DONE' (2x getar) saat audio bacaan selesai diputar.
        """
        self._send(b"DONE")

    def notify_done(self):
        """Alias untuk notify()."""
        self._send(b"DONE")

    def stop(self):
        """Tutup socket dan thread saat program ditutup."""
        self._running = False
        if self._enabled:
            try:
                self._sock.close()
            except Exception:
                pass
