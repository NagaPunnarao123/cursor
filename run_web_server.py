import http.server
import socketserver
import webbrowser
import os
import sys

PORT = 8000

class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Add CORS and Security headers for MediaPipe & WebRTC camera access
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        super().end_headers()

def main():
    # Set current directory to directory of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    print("=" * 60)
    print("      VIRTUAL CURSOR WEB PLAYGROUND - LOCAL SERVER")
    print("=" * 60)
    print(f"[+] Serving Web App at: http://localhost:{PORT}")
    print("[+] Opening default browser...")
    print("=" * 60)

    url = f"http://localhost:{PORT}"
    webbrowser.open(url)

    try:
        with socketserver.TCPServer(("", PORT), Handler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[+] Server stopped.")
        sys.exit(0)

if __name__ == "__main__":
    main()
