import subprocess
import re
import sys
import os
import urllib.request
import ssl

QR_CACHE_DIR = os.path.expanduser("~/desktop/infoglut/qrcodecache")
os.makedirs(QR_CACHE_DIR, exist_ok=True)
QR_SAVE_PATH = os.path.join(QR_CACHE_DIR, "infoglut_qr.png")

def generate_qr(url: str):
    api = f"https://api.qrserver.com/v1/create-qr-code/?data={urllib.request.quote(url, safe='')}&size=400x400"
    print(f"[QR] 正在生成二维码: {url}")
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(api, context=ctx) as response:
            with open(QR_SAVE_PATH, 'wb') as f:
                f.write(response.read())
        print(f"[QR] 已保存到 {QR_SAVE_PATH}")
        if sys.platform == "win32":
            os.startfile(QR_SAVE_PATH)
        else:
            os.system(f'open "{QR_SAVE_PATH}"')
    except Exception as e:
        print(f"[QR] 生成失败: {e}")

def main():
    print("[Tunnel] 正在启动 Cloudflare 隧道...")
    proc = subprocess.Popen(
        ["npx", "cloudflared", "tunnel", "--url", "http://localhost:8080"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    url_found = False
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()

        if not url_found:
            match = re.search(r'https://[a-zA-Z0-9\-]+\.trycloudflare\.com', line)
            if match:
                tunnel_url = match.group(0)
                url_found = True
                generate_qr(tunnel_url)

    proc.wait()

if __name__ == "__main__":
    main()
