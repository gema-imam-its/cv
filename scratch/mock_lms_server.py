from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import time

PORT = 3000
SECRET_KEY = "gema-super-rahasia-2025"
current_status = "idle"  # status: "idle" | "active"
current_session_id = "550e8400-e29b-41d4-a716-446655440000"
current_student_name = "Budi"

class MockLMSHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Override to clean up stdout
        print(f"[SERVER LOG] {args[0]}")

    def do_GET(self):
        # 1. Validasi API Key
        api_key = self.headers.get("x-api-key")
        if api_key != SECRET_KEY:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": "Unauthorized"}).encode())
            return

        if self.path == "/api/iot/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            
            if current_status == "active":
                response = {
                    "status": "active",
                    "session_id": current_session_id,
                    "student_name": current_student_name
                }
            else:
                response = {
                    "status": "idle"
                }
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        # 1. Validasi API Key
        api_key = self.headers.get("x-api-key")
        if api_key != SECRET_KEY:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": "Unauthorized"}).encode())
            return

        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')
        payload = json.loads(post_data) if post_data else {}

        if self.path == "/api/iot/gerakan/catat":
            print(f"\n[RECEIVED MOVEMENT] Sesi: {payload.get('session_id')}")
            print(f" -> Gerakan: {payload.get('movement_type')} | Akurasi: {payload.get('accuracy_score')}%")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": true}).encode())
            
        elif self.path == "/api/iot/sesi/selesai":
            global current_status
            print(f"\n[SESSION COMPLETED] Sesi: {payload.get('session_id')} telah ditutup oleh IoT.")
            current_status = "idle"  # Kembalikan status server ke idle
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": true, "message": "Sesi selesai"}).encode())
            
        elif self.path == "/trigger_start":
            # API utilitas lokal untuk men-trigger dimulainya sholat dari browser/curl
            current_status = "active"
            print("\n[TRIGGER] Status diubah menjadi ACTIVE (Budi bersiap sholat).")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Status changed to ACTIVE. IoT should wake up now.")
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == "__main__":
    server = HTTPServer(('0.0.0.0', PORT), MockLMSHandler)
    print("=" * 60)
    print(f" MOCK WEB LMS SERVER RUNNING ON PORT {PORT}")
    print("=" * 60)
    print(f" 1. IoT API Key   : {SECRET_KEY}")
    print(f" 2. Trigger Mulai : http://localhost:{PORT}/trigger_start (via POST)")
    print("=" * 60 + "\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
