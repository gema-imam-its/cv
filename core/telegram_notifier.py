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


def connect_bluetooth(mac_address, retries=3, retry_delay=3):
    """Koneksikan ke speaker Bluetooth berdasarkan MAC Address secara sinkron.

    Melakukan disconnect dari perangkat yang terhubung saat ini (jika ada),
    lalu connect ke MAC baru. PulseAudio otomatis mendeteksi sink baru.

    Returns:
        (True, "OK")                  — berhasil terhubung
        (False, "<pesan error>")       — gagal setelah semua percobaan
    """
    import subprocess
    import re

    # Sanitasi MAC address
    mac = mac_address.strip().upper()
    if not re.match(r'^([0-9A-F]{2}:){5}[0-9A-F]{2}$', mac):
        return False, f"Format MAC tidak valid: {mac}"

    print(f"[BT] Mencoba menghubungkan ke {mac} ...")

    for attempt in range(1, retries + 1):
        try:
            result = subprocess.run(
                ["bluetoothctl", "connect", mac],
                capture_output=True, text=True, timeout=15
            )
            output = result.stdout + result.stderr
            if "Connection successful" in output or "AlreadyConnected" in output:
                print(f"[BT] ✅ Berhasil terhubung ke {mac} (percobaan {attempt})")
                # Beri jeda agar PulseAudio mendaftarkan sink Bluetooth baru
                time.sleep(2)
                return True, "OK"
            else:
                print(f"[BT] Percobaan {attempt}/{retries} gagal: {output.strip()}")
        except subprocess.TimeoutExpired:
            print(f"[BT] Percobaan {attempt}/{retries} timeout.")
        except FileNotFoundError:
            return False, "bluetoothctl tidak ditemukan di sistem."
        except Exception as e:
            return False, str(e)

        if attempt < retries:
            time.sleep(retry_delay)

    return False, f"Gagal terhubung ke {mac} setelah {retries} percobaan."


def switch_audio_sink(mode):
    """Pindahkan audio output ke sink yang sesuai menggunakan PulseAudio (pactl).

    Args:
        mode: "jack" untuk audio kabel (3.5mm/HDMI/USB), "bt" untuk Bluetooth.

    Returns:
        (True, sink_name)          — berhasil, nama sink yang dipilih
        (False, "<pesan error>")   — gagal
    """
    import subprocess

    try:
        # Ambil daftar semua sink yang tersedia
        result = subprocess.run(
            ["pactl", "list", "short", "sinks"],
            capture_output=True, text=True, timeout=5
        )
        sinks_raw = result.stdout.strip().splitlines()
    except FileNotFoundError:
        return False, "pactl tidak ditemukan. Pastikan PulseAudio/PipeWire sudah terinstall."
    except Exception as e:
        return False, f"Gagal mengambil daftar sink: {e}"

    if not sinks_raw:
        return False, "Tidak ada sink audio yang terdeteksi oleh PulseAudio."

    # Kata kunci identifikasi tipe sink di Linux/Orange Pi
    # Bluetooth: nama sink mengandung "bluez"
    # Kabel (jack/HDMI/USB): mengandung "alsa", "analog", "hdmi", atau "usb"
    BT_KEYWORDS   = ["bluez", "bluetooth"]
    JACK_KEYWORDS = ["alsa", "analog", "hdmi", "usb", "hw:", "_card", "codec", "playback"]

    chosen_sink = None
    all_sinks   = []

    for line in sinks_raw:
        parts = line.split()
        if len(parts) < 2:
            continue
        sink_name = parts[1]
        all_sinks.append(sink_name)
        sink_lower = sink_name.lower()

        if mode == "bt" and any(kw in sink_lower for kw in BT_KEYWORDS):
            chosen_sink = sink_name
            break
        elif mode == "jack" and any(kw in sink_lower for kw in JACK_KEYWORDS):
            chosen_sink = sink_name
            break

    if not chosen_sink:
        mode_label = "Bluetooth" if mode == "bt" else "kabel (jack/HDMI/USB)"
        # Bungkus setiap nama sink dengan backtick agar aman dari markdown parse error (karena ada '_')
        formatted_sinks = [f"`{s}`" for s in all_sinks]
        return False, (
            f"Sink {mode_label} tidak ditemukan.\n"
            f"Sink tersedia: {', '.join(formatted_sinks) or 'tidak ada'}"
        )

    # Set sebagai default sink
    try:
        subprocess.run(
            ["pactl", "set-default-sink", chosen_sink],
            capture_output=True, timeout=5, check=True
        )
    except subprocess.CalledProcessError as e:
        return False, f"Gagal set-default-sink: {e}"
    except Exception as e:
        return False, str(e)

    # Pindahkan semua stream audio yang sedang aktif ke sink baru
    try:
        inputs_result = subprocess.run(
            ["pactl", "list", "short", "sink-inputs"],
            capture_output=True, text=True, timeout=5
        )
        for inp_line in inputs_result.stdout.strip().splitlines():
            inp_parts = inp_line.split()
            if inp_parts:
                subprocess.run(
                    ["pactl", "move-sink-input", inp_parts[0], chosen_sink],
                    capture_output=True, timeout=5
                )
    except Exception:
        pass  # Tidak kritis — stream baru akan otomatis pakai default sink

    print(f"[AUDIO] ✅ Default sink diganti ke: {chosen_sink}")
    return True, chosen_sink


class TelegramCommandListener:
    """
    Listener background untuk menerima dan mengeksekusi perintah dari Telegram Bot.
    Menggunakan long polling agar efisien (tidak spam API setiap detik).

    Command yang didukung:
      /help              - Tampilkan daftar perintah
      /mulai [sholat] [nama] - Mulai sesi tracking (tanpa Web LMS)
      /status            - Status sholat saat ini
      /reset             - Hentikan/reset sesi yang berjalan
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

        text = (message.get("text") or "").strip()
        if not text.startswith("/"):
            return

        # Parse command dan argumen (command lowercase, args pertahankan case asli untuk SSID/Password)
        parts = text.split()
        command = parts[0].lower()
        args = parts[1:]

        print(f"[TELEGRAM CMD] Perintah diterima: {text}")

        if command == "/help":
            self._cmd_help()
        elif command == "/mulai":
            self._cmd_mulai(args)
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
        elif command == "/bt":
            self._cmd_bt(args)
        elif command == "/audio":
            self._cmd_audio(args)
        elif command == "/wifi":
            self._cmd_wifi(args)
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
            "🕌 *GEMA Imam — Daftar Perintah Bot*\n"
            "\n"
            "*── Sesi Praktik ──*\n"
            "`/mulai [sholat] [nama]` — Mulai sesi tracking\n"
            "  Contoh: `/mulai subuh Ahmad`\n"
            "  Tanpa argumen: pakai sholat & nama default\n"
            "`/reset`               — Hentikan/reset sesi yang berjalan\n"
            "`/status`              — Status sholat saat ini\n"
            "\n"
            "*── Kontrol Sholat ──*\n"
            "`/pause`               — Pause / resume deteksi\n"
            "`/sholat <nama>`       — Ganti sholat aktif\n"
            "  Pilihan: subuh, dhuhur, ashar, maghrib, isya\n"
            "\n"
            "*── Audio & Network ──*\n"
            "`/bt <MAC_ADDRESS>`    — Ganti speaker Bluetooth\n"
            "  Contoh: `/bt B8:F6:53:XX:XX:XX`\n"
            "`/audio jack`          — Output ke speaker kabel (3.5mm/HDMI)\n"
            "`/audio bt`            — Output ke speaker Bluetooth\n"
            "`/audio list`          — Lihat semua sink audio\n"
            "`/wifi`                — Pindai jaringan WiFi terdekat\n"
            "`/wifi <SSID> <PASS>`  — Hubungkan Orange Pi ke WiFi baru\n"
            "\n"
            "*── Log & Info ──*\n"
            "`/log`                 — Kirim file log sesi terakhir\n"
            "`/help`                — Tampilkan pesan ini"
        )
        self._reply(msg)

    def _cmd_status(self):
        app = self._app
        sm = app.state_machine

        state_display = {
            "UNKNOWN": "Tidak Terdeteksi",
            "BERDIRI_TEGAK": "Berdiri Tegak",
            "TAKBIRATUL_IHRAM": "Takbiratul Ihram",
            "IQOMAH": "Iqomah",
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
        paused_str = "⏸ PAUSED" if app.paused else "▶️ Berjalan"

        if app.start_timestamp:
            session_str = f"Aktif (ID: `{app.current_session_id or '-'}`)"
            student_str = app.current_student_name or "—"
        elif app._pending_session:
            session_str = "⏳ Menunggu dimulai..."
            student_str = app._pending_session.get("student_name", "—")
        else:
            session_str = "Standby (belum ada sesi)"
            student_str = "—"

        msg = (
            "🕌 *Status GEMA Imam*\n"
            "─────────────────────\n"
            f"👤 Siswa   : {student_str}\n"
            f"🕌 Sholat  : *{app.active_prayer}*\n"
            f"🔢 Rakaat  : {sm.rakaat_count} / {sm.total_rakaats}\n"
            f"🤸 Gerakan : {current}\n"
            f"⚙️ Status  : {paused_str}\n"
            f"📋 Sesi    : {session_str}\n"
            f"❌ Kesalahan: {app.imam_mistakes_count} kali"
        )
        self._reply(msg)

    def _cmd_reset(self):
        """Hentikan sesi aktif / batalkan pending session / reset state machine."""
        app = self._app

        # Batalkan pending session yang belum sempat diproses
        if app._pending_session is not None:
            app._pending_session = None
            self._reply("✅ Permintaan sesi dibatalkan sebelum dimulai.")
            print("[TELEGRAM CMD] /reset → Pending session dibatalkan.")
            return

        # Cek apakah ada sesi aktif SEBELUM reset (reset_from_button akan set start_timestamp = None)
        had_active_session = app.start_timestamp is not None

        # Hentikan & reset sesi yang sedang berjalan
        app.reset_from_button()

        if had_active_session:
            # Ada sesi aktif — laporan akan dikirim otomatis setelah tracking berhenti
            self._reply(
                f"🛑 Sesi *{app.active_prayer}* dihentikan.\n"
                "Log sesi telah disimpan. Laporan dikirim otomatis setelah diproses.\n\n"
                "📷 Kamera kembali ke mode standby."
            )
        else:
            # Tidak ada sesi aktif — hanya reset state machine
            self._reply(
                f"🔄 State machine di-reset untuk Sholat *{app.active_prayer}*.\n"
                "Silakan mulai kembali dengan /mulai."
            )
        print("[TELEGRAM CMD] /reset dieksekusi dari Telegram.")

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
            f"Sholat diganti ke: *{display_name}*\n"
            "State machine telah di-reset. Silakan mulai."
        )
        print(f"[TELEGRAM CMD] Sholat diganti ke {display_name}.")

    def _cmd_mulai(self, args):
        """Mulai sesi tracking langsung dari Telegram tanpa memerlukan Web LMS."""
        import time
        app = self._app

        # Cek apakah sesi sedang berjalan (kamera aktif)
        if app.start_timestamp is not None:
            self._reply(
                "⚠️ Sesi sedang berjalan!\n"
                f"Siswa: *{app.current_student_name or 'Tidak diketahui'}* | Sholat: *{app.active_prayer}*\n\n"
                "Kirim /selesai untuk menghentikan sesi terlebih dahulu."
            )
            return

        # Cek apakah ada pending session yang belum diproses
        if app._pending_session is not None:
            self._reply("⏳ Ada permintaan mulai yang masih diproses. Tunggu sebentar...")
            return

        # Parse argumen: /mulai [sholat] [nama siswa...]
        prayer_name = app.active_prayer   # default: sholat yang sedang aktif
        student_name = "Imam (Telegram)"  # default nama

        if args:
            first = args[0].lower()
            if first in self.VALID_PRAYERS:
                prayer_name = self.PRAYER_DISPLAY[first]
                # Sisa argumen (jika ada) adalah nama siswa
                if len(args) > 1:
                    student_name = " ".join(args[1:])
            else:
                # Argumen pertama bukan nama sholat → anggap semua sebagai nama siswa
                student_name = " ".join(args)

        # Buat session_id lokal (TG-<timestamp>)
        session_id = f"TG-{int(time.time())}"

        # Simpan ke _pending_session; standby loop akan mengambilnya di iterasi berikutnya
        app._pending_session = {
            "session_id":   session_id,
            "student_name": student_name,
            "prayer":       prayer_name,
        }

        self._reply(
            f"✅ Sesi tracking dimulai!\n"
            f"👤 Siswa  : *{student_name}*\n"
            f"🕌 Sholat : *{prayer_name}*\n"
            f"🆔 ID Sesi: `{session_id}`\n\n"
            "Kamera akan menyala dalam beberapa detik.\n"
            "Kirim /selesai untuk mengakhiri sesi kapan saja."
        )
        print(f"[TELEGRAM CMD] /mulai → Sesi '{session_id}' dijadwalkan untuk {student_name} ({prayer_name}).")


    def _cmd_log(self):
        """Kirim file log JSON sesi terakhir ke Telegram."""
        from config import LOGS_DIR
        try:
            files = sorted(
                [f for f in os.listdir(LOGS_DIR) if f.endswith(".json")],
                key=lambda f: os.path.getmtime(os.path.join(LOGS_DIR, f)),
                reverse=True  # index [0] = file paling baru
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

    def _cmd_bt(self, args):
        """Ganti speaker Bluetooth aktif saat runtime tanpa merestart program."""
        if not args:
            self._reply(
                "Format salah. Gunakan:\n"
                "`/bt B8:F6:53:XX:XX:XX`\n\n"
                "Cara mendapatkan MAC Address:\n"
                "Jalankan `bluetoothctl devices` di terminal Orange Pi."
            )
            return

        new_mac = args[0].upper()
        # Validasi format MAC address sederhana (AA:BB:CC:DD:EE:FF)
        import re
        if not re.match(r'^([0-9A-F]{2}:){5}[0-9A-F]{2}$', new_mac):
            self._reply(
                f"Format MAC Address `{new_mac}` tidak valid.\n"
                "Contoh format yang benar: `B8:F6:53:1A:2B:3C`"
            )
            return

        self._reply(f"Menghubungkan ke speaker Bluetooth `{new_mac}`...")

        def _do_connect():
            ok, msg = connect_bluetooth(new_mac)
            if ok:
                self._reply(
                    f"Speaker Bluetooth berhasil diganti!\n"
                    f"MAC Aktif: `{new_mac}`\n"
                    "Audio akan otomatis diarahkan ke speaker baru."
                )
            else:
                self._reply(
                    f"Gagal terhubung ke `{new_mac}`.\n"
                    f"Detail: {msg}\n\n"
                    "Pastikan speaker sudah dinyalakan dan dalam jangkauan Bluetooth Orange Pi."
                )

        import threading
        threading.Thread(target=_do_connect, daemon=True, name="BtSwitch").start()

    def _cmd_audio(self, args):
        """Switch output audio antara speaker kabel (jack) dan Bluetooth via PulseAudio."""
        import subprocess

        if not args or args[0] not in ("jack", "bt", "list"):
            self._reply(
                "Format salah. Pilihan:\n"
                "/audio jack   — output ke speaker kabel (3.5mm / HDMI / USB)\n"
                "/audio bt     — output ke speaker Bluetooth\n"
                "/audio list   — tampilkan semua sink audio yang tersedia"
            )
            return

        mode = args[0]

        # Mode list: tampilkan semua sink tanpa mengubah apapun
        if mode == "list":
            try:
                result = subprocess.run(
                    ["pactl", "list", "short", "sinks"],
                    capture_output=True, text=True, timeout=5
                )
                sinks = result.stdout.strip()
                if not sinks:
                    self._reply("Tidak ada sink audio yang terdeteksi.")
                    return
                # Format output agar mudah dibaca di Telegram
                lines = []
                for line in sinks.splitlines():
                    parts = line.split()
                    if len(parts) >= 2:
                        lines.append(f"• `{parts[1]}`")
                self._reply(
                    "🔊 Sink audio tersedia di Orange Pi:\n" +
                    "\n".join(lines) +
                    "\n\nGunakan `/audio jack` atau `/audio bt` untuk berpindah."
                )
            except FileNotFoundError:
                self._reply("pactl tidak ditemukan. PulseAudio/PipeWire belum terinstall?")
            except Exception as e:
                self._reply(f"Gagal mengambil daftar sink: `{e}`")
            return

        # Mode jack atau bt: jalankan di background agar tidak blokir polling
        mode_label = "kabel (jack/HDMI/USB)" if mode == "jack" else "Bluetooth"
        self._reply(f"Mengalihkan audio ke {mode_label}...")

        def _do_switch(m=mode, label=mode_label):
            ok, result = switch_audio_sink(m)
            if ok:
                self._reply(
                    f"✅ Audio berhasil dialihkan ke {label}!\n"
                    f"Sink aktif: `{result}`\n"
                    "Semua audio yang sedang diputar sudah dipindahkan ke output baru."
                )
            else:
                self._reply(
                    f"❌ Gagal mengalihkan ke {label}.\n"
                    f"Detail:\n`{result}`\n\n"
                    "Coba `/audio list` untuk melihat sink yang tersedia."
                )

        import threading
        threading.Thread(target=_do_switch, daemon=True, name="AudioSwitch").start()

    def _cmd_wifi(self, args):
        """Ganti koneksi WiFi Orange Pi 4 Pro atau scan WiFi terdekat."""
        import subprocess
        import threading

        if not args or args[0].lower() in ("scan", "list"):
            self._reply("🔍 Memindai jaringan WiFi terdekat di sekitar Orange Pi...")

            def _do_scan():
                try:
                    res = subprocess.run(
                        ["nmcli", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list", "--rescan", "yes"],
                        capture_output=True, text=True, timeout=12
                    )
                    output = res.stdout.strip()
                    if not output:
                        self._reply("Tidak ada jaringan WiFi yang ditemukan.")
                        return

                    lines = output.splitlines()
                    rows = lines[1:11]  # ambil maksimal 10 WiFi terkuat

                    formatted = ["📶 *Daftar WiFi Terdekat:*"]
                    for row in rows:
                        row_str = row.strip()
                        if row_str:
                            formatted.append(f"• `{row_str}`")

                    formatted.append("\n💡 *Cara terhubung:*")
                    formatted.append("`/wifi NamaWiFi PasswordWiFi`")
                    self._reply("\n".join(formatted))
                except FileNotFoundError:
                    self._reply("⚠️ `nmcli` (NetworkManager) tidak ditemukan di Orange Pi.")
                except Exception as e:
                    self._reply(f"⚠️ Gagal memindai WiFi: `{e}`")

            threading.Thread(target=_do_scan, daemon=True, name="WifiScan").start()
            return

        # Format: /wifi <SSID> [PASSWORD]
        ssid = args[0]
        password = " ".join(args[1:]) if len(args) > 1 else ""

        if password:
            self._reply(f"🔄 Menghubungkan ke WiFi *{ssid}*...")
        else:
            self._reply(f"🔄 Menghubungkan ke WiFi *{ssid}* (tanpa password)...")

        def _do_connect(s=ssid, p=password):
            try:
                cmd = ["nmcli", "dev", "wifi", "connect", s]
                if p:
                    cmd.extend(["password", p])

                res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
                if res.returncode == 0:
                    self._reply(
                        f"✅ *Berhasil Terhubung ke WiFi!*\n"
                        f"SSID: *{s}*\n"
                        "Orange Pi sekarang aktif di jaringan baru."
                    )
                    print(f"[TELEGRAM CMD] Berhasil terhubung ke WiFi {s}")
                else:
                    err_msg = res.stderr.strip() or res.stdout.strip()
                    self._reply(
                        f"❌ *Gagal Terhubung ke WiFi {s}*\n"
                        f"Detail: `{err_msg}`\n\n"
                        "Periksa kembali SSID dan Password."
                    )
            except subprocess.TimeoutExpired:
                self._reply(
                    f"⚠️ *Waktu Sambung Habis (Timeout)* saat mencoba terhubung ke `{s}`.\n"
                    "Orange Pi mungkin otomatis kembali ke WiFi sebelumnya."
                )
            except Exception as e:
                self._reply(f"⚠️ Gagal mengeksekusi koneksi WiFi: `{e}`")

        threading.Thread(target=_do_connect, daemon=True, name="WifiConnect").start()
