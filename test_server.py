"""Simple test server - no dependencies except Python stdlib"""
import http.server
import socketserver
import json

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({"status": "healthy", "message": "Test server works!"}).encode())
    def log_message(self, format, *args):
        print(f"Request: {args[0]}")

PORT = 8000
print(f"Test server starting on http://localhost:{PORT}")
print("Open http://localhost:8000 in your browser")
print("Press Ctrl+C to stop")
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    httpd.serve_forever()
