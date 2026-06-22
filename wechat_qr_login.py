import urllib.request
import urllib.parse
import json
import time
import os
import pathlib

# Optional: qrcode library to print ASCII QR in terminal.
try:
    import qrcode
    HAVE_QRCODE = True
except ImportError:
    HAVE_QRCODE = False

ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
EP_GET_BOT_QR = "/ilink/bot/get_bot_qrcode"
EP_GET_QR_STATUS = "/ilink/bot/get_qrcode_status"

def update_env_file(env_vars: dict):
    env_path = pathlib.Path.home() / ".config" / "gmgn" / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    
    current_lines = []
    if env_path.exists():
        current_lines = env_path.read_text().splitlines()
    
    # Update or add keys
    for k, v in env_vars.items():
        found = False
        for i, line in enumerate(current_lines):
            if line.startswith(f"{k}="):
                current_lines[i] = f"{k}={v}"
                found = True
                break
        if not found:
            current_lines.append(f"{k}={v}")
    
    env_path.write_text("\n".join(current_lines) + "\n")
    print(f"✅ 已成功更新配置文件: {env_path}")

def get_json(url):
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data = response.read().decode('utf-8')
            return json.loads(data)
    except Exception as e:
        print(f"Request error: {e}")
        return None

def main():
    print("⏳ 正在向微信官方 (iLink) 请求配对二维码...")
    qr_resp = get_json(f"{ILINK_BASE_URL}{EP_GET_BOT_QR}?bot_type=3")
    if not qr_resp or not qr_resp.get("qrcode"):
        print("❌ 获取二维码失败！")
        return

    qrcode_value = qr_resp.get("qrcode")
    qrcode_url = qr_resp.get("qrcode_img_content", "")
    
    qr_scan_data = qrcode_url if qrcode_url else qrcode_value

    print("\n==========================================")
    print("👉 请使用微信扫描以下二维码或点击链接：")
    print(qrcode_url)
    print("==========================================\n")

    if HAVE_QRCODE:
        qr = qrcode.QRCode()
        qr.add_data(qr_scan_data)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    else:
        print("💡 提示: 如果您想在终端直接看到二维码图片，可以先运行: pip install qrcode")

    timeout_seconds = 600
    deadline = time.monotonic() + timeout_seconds
    current_base_url = ILINK_BASE_URL
    refresh_count = 0

    print("📡 等待扫码中...", end="", flush=True)

    while time.monotonic() < deadline:
        status_url = f"{current_base_url}{EP_GET_QR_STATUS}?qrcode={qrcode_value}"
        status_resp = get_json(status_url)
        
        if not status_resp:
            time.sleep(2)
            continue
            
        status = status_resp.get("status", "wait")
        
        if status == "wait":
            print(".", end="", flush=True)
        elif status == "scaned":
            print("\n👀 已扫码，请在微信手机端点击确认...")
        elif status == "scaned_but_redirect":
            redirect_host = status_resp.get("redirect_host", "")
            if redirect_host:
                current_base_url = f"https://{redirect_host}"
        elif status == "expired":
            print("\n⚠️ 二维码已过期，请重新运行本脚本。")
            return
        elif status == "confirmed":
            account_id = status_resp.get("ilink_bot_id", "")
            token = status_resp.get("bot_token", "")
            base_url = status_resp.get("baseurl", ILINK_BASE_URL)
            user_id = status_resp.get("ilink_user_id", "")
            
            if not account_id or not token:
                print("\n❌ 微信授权成功，但缺少关键凭证。")
                return
                
            print(f"\n🎉 微信连接成功！")
            print(f"账号 ID: {account_id}")
            print(f"用户 ID: {user_id}")
            
            # Save to GMGN env file so wxclawbot-cli and micro-agi-mvp can use it!
            # Using the format expected by wxclawbot-cli:
            combined_token = f"{account_id}:{token}"
            env_updates = {
                "WXCLAW_TOKEN": combined_token,
                "WXCLAW_BASE_URL": base_url,
                "WXCLAW_DEFAULT_TO": user_id  # Automatically set the default notification recipient to the scanner!
            }
            update_env_file(env_updates)
            print("🚀 一切就绪！您现在可以让 AI 给您发微信了。")
            return
            
        time.sleep(2)
        
    print("\n⏰ 登录超时。")

if __name__ == "__main__":
    main()
