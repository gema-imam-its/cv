"""
============================================================
GEMA Imam — Sholat Tracking System
telegram_notifier.py — Integrasi Bot Telegram untuk Laporan IoT & Remote Control
============================================================
"""

import requests
import sys
import os
import threading
import time

# Tambahkan base path agar bisa import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def send_telegram_message(text, chat_id=None):
    """
    Mengirimkan pesan teks ke Telegram Chat ID secara sinkron.
    """
    token = TELEGRAM_BOT_TOKEN
    target_chat = chat_id if chat_id else TELEGRAM_CHAT_ID

    if not token or token == "isi_token_bot_anda_di_sini":
        print("[TELEGRAM WARNING] Token Bot belum dikonfigurasi.")
        return False

    if not target_chat:
        print("[TELEGRAM WARNING] Chat ID belum dikonfigurasi. Lewati pengiriman.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": text,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, json=payload, timeout=8)
        res_json = response.json()
        if response.status_code == 200 and res_json.get("ok"):
            print("[TELEGRAM] Pesan berhasil terkirim ke Telegram!")
            return True
        else:
            print(f"[TELEGRAM ERROR] Gagal mengirim: {res_json.get('description', 'Unknown error')}")
            return False
    except Exception as e:
        print(f"[TELEGRAM WARNING] Gagal menghubungkan ke Telegram API (Timeout / Offline): {e}")
        return False


def send_telegram_message_async(text, chat_id=None):
    """
    Mengirimkan pesan teks ke Telegram secara asinkron (non-blocking thread).
    """
    thread = threading.Thread(target=send_telegram_message, args=(text, chat_id), daemon=True)
    thread.start()


def send_telegram_document(filepath, caption="", chat_id=None):
    """
    Mengirimkan file dokumen ke Telegram (misal: file log JSON).
    """
    token = TELEGRAM_BOT_TOKEN
    target_chat = chat_id if chat_id else TELEGRAM_CHAT_ID

    if not token or not target_chat:
        return False
    if not os.path.exists(filepath):
        print(f"[TELEGRAM WARNING] File tidak ditemukan: {filepath}")
        return False

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    try:
        with open(filepath, "rb") as f:
            response = requests.post(
                url,
                data={"chat_id": target_chat, "caption": caption},
                files={"document": f},
                timeout=15
            )
        return response.status_code == 200 and response.json().get("ok")
    except Exception as e:
        print(f"[TELEGRAM WARNING] Gagal mengirim dokumen: {e}")
        return False


def get_telegram_chat_id():
    """
    Mengambil daftar Chat ID aktif yang pernah mengirim pesan ke Bot Anda.
    Digunakan untuk mendeteksi Chat ID secara otomatis pada saat startup.
    """
    token = TELEGRAM_BOT_TOKEN
    if not token or token == "isi_token_bot_anda_di_sini":
        return None

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        response = requests.get(url, timeout=5)
        res_json = response.json()
        if response.status_code == 200 and res_json.get("ok"):
            results = res_json.get("result", [])
            found_chats = {}
            for update in results:
                message = update.get("message")
                if message:
                    chat = message.get("chat")
                    from_user = message.get("from", {})
                    if chat:
                        chat_id = chat.get("id")
                        first_name = from_user.get("first_name", "")
                        username = from_user.get("username", "")
                        name_str = f"{first_name} (@{username})" if username else first_name
                        found_chats[chat_id] = name_str
            return found_chats
    except Exception:
        pass
    return None


class TelegramCommandListener:
    """
    Listener background untuk menerima dan mengeksekusi perintah dari Telegram Bot.
    Menggunakan long polling agar efisien (tidak spam API setiap detik).

    Command yang didukung:
      /help              - Tampilkan daftar perintah
      /status            - Status sholat saat ini
      /reset             - Reset state machine (mulai ulang sholat)
      /pause             - Pause / resume deteksi
      /sholat <nama>     - Ganti sholat (subuh/dhuhur/ashar/maghrib/isya)
      /log               - Kirim file log JSON sesi terakhir
    """

    VALID_PRAYERS = ["subuh", "dhuhur", "ashar", "maghrib", "isya"]
    PRAYER_DISPLAY = {
        "subuh": "Subuh",
        "dhuhur": "Dhuhur",
        "ashar": "Ashar",
        "maghrib": "Maghrib",
        "isya": "Isya"
    }

    def __init__(self, app_ref):
        """
        app_ref: referensi ke instance GemaImamApp.
        """
        self._app = app_ref
        self._token = TELEGRAM_BOT_TOKEN
        self._chat_id = TELEGRAM_CHAT_ID
        self._running = False
        self._thread = None
        self._last_update_id = 0

    def start(self):
        """Mulai thread listener background."""
        if not self._token or not self._chat_id:
            print("[TELEGRAM CMD] Listener tidak dimulai: token/chat_id belum diatur.")
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="TelegramCmdListener"
        )
        self._thread.start()
        print("[TELEGRAM CMD] Command listener aktif. Kirim /help ke bot untuk melihat daftar perintah.")

    def stop(self):
        """Hentikan thread listener."""
        self._running = False

    def _poll_loop(self):
        """Loop utama long polling Telegram getUpdates."""
        # Lewati pesan lama agar tidak diproses saat startup
        self._skip_old_updates()

        while self._running:
            try:
                url = f"https://api.telegram.org/bot{self._token}/getUpdates"
                params = {
                    "offset": self._last_update_id + 1,
                    "timeout": 30,              # long polling — tunggu sampai 30 detik
                    "allowed_updates": ["message"]
                }
                resp = requests.get(url, params=params, timeout=35)
                if resp.status_code != 200:
                    time.sleep(3)
                    continue

                data = resp.json()
                if not data.get("ok"):
                    time.sleep(3)
                    continue

                for update in data.get("result", []):
                    uid = update.get("update_id", 0)
                    if uid > self._last_update_id:
                        self._last_update_id = uid
                    self._handle_update(update)

            except requests.exceptions.Timeout:
                # Timeout long polling adalah normal — langsung poll lagi
                continue
            except Exception as e:
                print(f"[TELEGRAM CMD WARNING] Error polling: {e}")
                time.sleep(5)

    def _skip_old_updates(self):
        """Ambil update_id terbaru saat startup agar pesan lama tidak diproses ulang."""
        try:
            url = f"https://api.telegram.org/bot{self._token}/getUpdates"
            resp = requests.get(url, params={"timeout": 0}, timeout=5)
            if resp.status_code == 200 and resp.json().get("ok"):
                results = resp.json().get("result", [])
                if results:
                    self._last_update_id = max(u["update_id"] for u in results)
        except Exception:
            pass

    def _handle_update(self, update):
        """Proses satu update/pesan dari Telegram."""
        message = update.get("message")
        if not message:
            return

        # Hanya proses pesan dari chat_id yang diotorisasi
        chat_id = str(message.get("chat", {}).get("id", ""))
        if chat_id != str(self._chat_id):
            return

        text = (message.get("text") or "").strip().lower()
        if not text.startswith("/"):
            return

        # Parse command dan argumen
        parts = text.split()
        command = parts[0]
        args = parts[1:]

        print(f"[TELEGRAM CMD] Perintah diterima: {text}")

        if command == "/help":
            self._cmd_help()
        elif command == "/status":
            self._cmd_status()
        elif command == "/reset":
            self._cmd_reset()
        elif command == "/pause":
            self._cmd_pause()
        elif command == "/sholat":
            self._cmd_sholat(args)
        elif command == "/log":
            self._cmd_log()
        else:
            self._reply(
                f"Perintah `{command}` tidak dikenal.\n\nKetik /help untuk melihat daftar perintah."
            )

    def _reply(self, text):
        """Kirim balasan ke chat yang diotorisasi."""
        send_telegram_message(text, chat_id=self._chat_id)

    # ──────────────────────────────────────────────
    # Implementasi setiap command
    # ──────────────────────────────────────────────

    def _cmd_help(self):
        msg = (
            "GEMA Imam - Daftar Perintah Bot\n"
            "--------------------------------\n"
            "/status            - Status sholat saat ini\n"
            "/reset             - Reset & mulai ulang sholat\n"
            "/pause             - Pause / resume deteksi\n"
            "/sholat <nama>     - Ganti sholat aktif\n"
            "  Contoh: /sholat subuh\n"
            "  Pilihan: subuh, dhuhur, ashar, maghrib, isya\n"
            "/log               - Kirim file log sesi terakhir\n"
            "/help              - Tampilkan pesan ini"
        )
        self._reply(msg)

    def _cmd_status(self):
        app = self._app
        sm = app.state_machine

        state_display = {
            "UNKNOWN": "Tidak Terdeteksi",
            "BERDIRI_TEGAK": "Berdiri Tegak",
            "TAKBIRATUL_IHRAM": "Takbiratul Ihram",
            "BERSEDEKAP": "Bersedekap",
            "RUKUK": "Rukuk",
            "ITIDAL": "I'tidal",
            "SUJUD_PERTAMA": "Sujud Pertama",
            "DUDUK_DI_ANTARA_DUA_SUJUD": "Duduk Antara Sujud",
            "SUJUD_KEDUA": "Sujud Kedua",
            "DUDUK_TASYAHUD_AWAL": "Tasyahud Awal",
            "DUDUK_TASYAHUD_AKHIR": "Tasyahud Akhir",
            "SALAM_KE_KANAN": "Salam ke Kanan",
            "SALAM_KE_KIRI": "Salam ke Kiri",
            "SELESAI": "Selesai",
        }
        current = state_display.get(sm.current_state, sm.current_state)
        paused_str = "PAUSED" if app.paused else "Berjalan"
        session_str = "Sudah dimulai" if app.start_timestamp else "Belum dimulai"

        msg = (
            "Status GEMA Imam\n"
            "-----------------\n"
            f"Sholat  : {app.active_prayer}\n"
            f"Rakaat  : {sm.rakaat_count} / {sm.total_rakaats}\n"
            f"Gerakan : {current}\n"
            f"Status  : {paused_str}\n"
            f"Sesi    : {session_str}\n"
            f"Kesalahan: {app.imam_mistakes_count} kali"
        )
        self._reply(msg)

    def _cmd_reset(self):
        app = self._app
        app.state_machine.reset()
        app.audio_player.clear()
        app.imam_mistakes_count = 0
        app.start_timestamp = None
        self._reply(
            f"Sholat {app.active_prayer} berhasil di-reset!\n"
            "Silakan mulai kembali dari awal."
        )
        print("[TELEGRAM CMD] Reset sholat dieksekusi dari Telegram.")

    def _cmd_pause(self):
        app = self._app
        app.paused = not app.paused
        if app.paused:
            self._reply("Deteksi dijeda (PAUSED).\nKirim /pause lagi untuk melanjutkan.")
        else:
            self._reply("Deteksi dilanjutkan (RESUMED).")
        print(f"[TELEGRAM CMD] Paused = {app.paused}")

    def _cmd_sholat(self, args):
        if not args:
            self._reply(
                "Sebutkan nama sholat.\n"
                "Contoh: /sholat maghrib\n"
                "Pilihan: subuh, dhuhur, ashar, maghrib, isya"
            )
            return

        nama = args[0].lower()
        if nama not in self.VALID_PRAYERS:
            self._reply(
                f"Sholat '{nama}' tidak dikenal.\n"
                "Pilihan valid: subuh, dhuhur, ashar, maghrib, isya"
            )
            return

        display_name = self.PRAYER_DISPLAY[nama]
        app = self._app

        # Reset state machine lama dan buat yang baru
        app.audio_player.clear()
        app.imam_mistakes_count = 0
        app.start_timestamp = None

        from state_machine import SholatStateMachine
        app.active_prayer = display_name
        app.state_machine = SholatStateMachine(display_name)

        self._reply(
            f"Sholat diganti ke: {display_name}\n"
            "State machine telah di-reset. Silakan mulai."
        )
        print(f"[TELEGRAM CMD] Sholat diganti ke {display_name}.")

    def _cmd_log(self):
        """Kirim file log JSON sesi terakhir ke Telegram."""
        from config import LOGS_DIR
        try:
            files = sorted(
                [f for f in os.listdir(LOGS_DIR) if f.endswith(".json")],
                reverse=True
            )
            if not files:
                self._reply("Belum ada file log tersedia.")
                return

            latest = os.path.join(LOGS_DIR, files[0])
            caption = f"Log sesi terakhir: {files[0]}"
            ok = send_telegram_document(latest, caption=caption, chat_id=self._chat_id)
            if not ok:
                self._reply("Gagal mengirim file log. Coba lagi nanti.")
        except Exception as e:
            self._reply(f"Error saat mengambil log: {e}")
