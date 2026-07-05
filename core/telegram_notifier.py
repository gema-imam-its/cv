"""
============================================================
GEMA Imam — Sholat Tracking System
telegram_notifier.py — Integrasi Bot Telegram untuk Laporan IoT
============================================================
"""

import requests
import sys
import os
import threading

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
        response = requests.post(url, json=payload, timeout=5)
        res_json = response.json()
        if response.status_code == 200 and res_json.get("ok"):
            print("[TELEGRAM] Laporan KPI berhasil terkirim ke Telegram!")
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
