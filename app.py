import os
import json
import urllib.request
import urllib.error
import pathlib
import subprocess
import http.server
import socketserver
import traceback
import signal
import base64
import time
import datetime
import threading
import uuid
import re
import socket
import db

PORT = 8085

# 1. Load config from local env
def load_env() -> dict:
    env_path = pathlib.Path.home() / ".config" / "gmgn" / ".env"
    if not env_path.exists():
        env_path = pathlib.Path.home() / "micro-agi-mvp" / ".env"
    if not env_path.exists():
        return {}
    out = {}
    try:
        content = env_path.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return {}
    for line in content.splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
                v = v[1:-1]
            v = v.replace("\\n", "\n")
            out[k.strip()] = v
    return out

ENV_VARS = load_env()

# 2. Call OpenAI-compatible LLM endpoint or native Google Gemini REST API
def refresh_google_token() -> str:
    # Reload config to get the latest refresh_token
    global ENV_VARS
    ENV_VARS = load_env()
    
    refresh_token = ENV_VARS.get("GOOGLE_REFRESH_TOKEN")
    client_id = ENV_VARS.get("GOOGLE_CLIENT_ID", "884354919052-36trc1jjb3tguiac32ov6cod268c5blh.apps.googleusercontent.com")
    if not refresh_token:
        print("refresh_google_token failed: GOOGLE_REFRESH_TOKEN not found in env")
        return ""
    
    proxy_url = ENV_VARS.get("PROXY_URL", "http://127.0.0.1:7890")
    if proxy_url:
        proxy_handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
        opener = urllib.request.build_opener(proxy_handler)
    else:
        opener = urllib.request.build_opener()
        
    url = "https://oauth2.googleapis.com/token"
    payload = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with opener.open(req, timeout=15) as response:
            res = json.loads(response.read().decode("utf-8"))
            new_access_token = res.get("access_token")
            if new_access_token:
                print("Successfully refreshed Google Access Token via proxy")
                save_env_config({
                    "GOOGLE_ACCESS_TOKEN": new_access_token
                })
                return new_access_token
    except Exception as e:
        print(f"Failed to refresh google token with proxy: {e}")
        # Retry without proxy
        if proxy_url:
            print("Retrying token refresh without proxy...")
            try:
                opener_no_proxy = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener_no_proxy.open(req, timeout=15) as response:
                    res = json.loads(response.read().decode("utf-8"))
                    new_access_token = res.get("access_token")
                    if new_access_token:
                        print("Successfully refreshed Google Access Token without proxy")
                        save_env_config({
                            "GOOGLE_ACCESS_TOKEN": new_access_token
                        })
                        return new_access_token
            except Exception as e2:
                print(f"Failed to refresh google token without proxy: {e2}")
    return ""

def call_llm(messages: list) -> str:
    global ENV_VARS
    ENV_VARS = load_env() # Ensure latest config is read
    
    gemini_key = ENV_VARS.get("GEMINI_API_KEY")
    google_token = ENV_VARS.get("GOOGLE_ACCESS_TOKEN")
    
    # If no GEMINI_API_KEY or GOOGLE_ACCESS_TOKEN config, check AI_URL/AI_KEY fallback
    if not gemini_key and not google_token:
        ai_url = ENV_VARS.get("AI_URL", "")
        if "generativelanguage.googleapis.com" in ai_url or "gemini" in ai_url.lower():
            gemini_key = ENV_VARS.get("AI_KEY")
            
    proxy_url = ENV_VARS.get("PROXY_URL", "http://127.0.0.1:7890")
    use_google_api = bool(gemini_key or google_token)
    
    if use_google_api:
        # 1. Google Gemini official REST API
        model_name = ENV_VARS.get("AI_MODEL", "gemini-1.5-flash")
        if "/" in model_name:
            model_name = model_name.split("/")[-1]
            
        if gemini_key:
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_key}"
            headers = {"Content-Type": "application/json"}
        else:
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {google_token}"
            }
            
        # Convert messages format to Gemini contents
        contents = []
        system_instruction = ""
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            
            if role == "system":
                system_instruction = content
            elif role == "user":
                contents.append({
                    "role": "user",
                    "parts": [{"text": content}]
                })
            elif role == "assistant":
                contents.append({
                    "role": "model",
                    "parts": [{"text": content}]
                })
        
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.3
            }
        }
        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }
            
        data = json.dumps(payload).encode("utf-8")
    else:
        # 2. Original OpenAI-compatible endpoint logic
        ai_url = ENV_VARS.get("AI_URL", "http://77.237.243.226:28085/v1")
        ai_key = ENV_VARS.get("AI_KEY", "sk-1234567890abcdef")
        ai_model = ENV_VARS.get("AI_MODEL", "gpt-3.5-turbo")
        
        api_url = ai_url
        if api_url and not api_url.endswith("/chat/completions"):
            api_url = api_url.rstrip("/") + "/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {ai_key}"
        }
        payload = {
            "model": ai_model,
            "messages": messages,
            "temperature": 0.3
        }
        data = json.dumps(payload).encode("utf-8")

    # Internal helper to handle requests and refresh token if 401/403 is hit
    def do_request(url, payload_data, req_headers):
        if proxy_url:
            proxy_handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
            opener = urllib.request.build_opener(proxy_handler)
        else:
            opener = urllib.request.build_opener()
            
        req = urllib.request.Request(url, data=payload_data, headers=req_headers, method="POST")
        try:
            with opener.open(req, timeout=30) as response:
                res_data = response.read().decode("utf-8")
                res_json = json.loads(res_data)
                
                if use_google_api:
                    try:
                        return res_json["candidates"][0]["content"]["parts"][0]["text"]
                    except Exception as e_parse:
                        print(f"Gemini API parse failed: {e_parse}, Response: {res_data}")
                        raise e_parse
                else:
                    return res_json["choices"][0]["message"]["content"]
        except Exception as e:
            is_auth_error = False
            if isinstance(e, urllib.error.HTTPError):
                if e.code in (401, 403):
                    is_auth_error = True
            
            if is_auth_error and google_token and ENV_VARS.get("GOOGLE_REFRESH_TOKEN"):
                print("Access Token expired (401/403). Trying to refresh google token...")
                new_token = refresh_google_token()
                if new_token:
                    req_headers["Authorization"] = f"Bearer {new_token}"
                    print("Retrying API call with newly refreshed token...")
                    return do_request(url, payload_data, req_headers)
            
            print(f"LLM API request failed: {e}")
            if proxy_url:
                print("Retrying API call without proxy...")
                try:
                    opener_no_proxy = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    with opener_no_proxy.open(req, timeout=30) as response:
                        res_data = response.read().decode("utf-8")
                        res_json = json.loads(res_data)
                        if use_google_api:
                            return res_json["candidates"][0]["content"]["parts"][0]["text"]
                        else:
                            return res_json["choices"][0]["message"]["content"]
                except Exception as e2:
                    print(f"Fallback call failed: {e2}")
            raise e

    return do_request(api_url, data, headers)



# 3. System Prompt explaining tools, security, and Android environment capabilities
def get_system_prompt():
    base = """You are a helpful AI Assistant running directly on an Android device via Termux.
You have the power to run terminal commands to help the user manage files, download media, run scripts, and inspect the system.

To execute a bash command, wrap the exact command inside <execute> and </execute> tags, like this:
<execute>ls -la</execute>

ANDROID & TERMUX CAPABILITIES:
You can interact with the phone's hardware and features via 'termux-api' utilities if installed:
- Speak text: <execute>termux-tts-speak "Hello User"</execute>
- Check battery status: <execute>termux-battery-status</execute>
- Vibrate device: <execute>termux-vibrate -d 500</execute>
- Check current location: <execute>termux-location</execute>
- Set wallpaper: <execute>termux-wallpaper -f /path/to/img.jpg</execute>
- List SMS messages: <execute>termux-sms-list</execute>
- Show Toast message: <execute>termux-toast -c "hello"</execute>
- Set/Get Clipboard: <execute>termux-clipboard-set "content"</execute> or <execute>termux-clipboard-get</execute>

WECHAT NOTIFICATIONS & MESSAGING:
You can proactively push text alerts, reminders, or notifications to the user's WeChat via the wxclawbot CLI.
To send a WeChat message to the user, run:
<execute>wxclawbot send --text "你的提醒消息内容"</execute>

RULES:
1. You can run commands sequentially. Once a command's output is returned to you, you can run another command or write your final response.
2. If you want to show the final result, just write standard text WITHOUT <execute> tags.
3. Every command you generate will be reviewed by the user before execution. If the user edits or rejects the command, you will see a message indicating this.
4. Keep commands safe. Do not delete essential system files or run infinite loops.
5. Always work within the user's home directory (~/ or /data/data/com.termux/files/home).

SKILL STORE PLUGINS (INSTALLED & AVAILABLE):
- [✅ Web Search]: Run `<execute>python3 plugins/search_web.py "your query"</execute>` to get real-time search results from the internet.
- [✅ Xiaohongshu/Insta Downloader]: Use standard python scripts or `wget`/`curl` to download images.
- [✅ Bilibili Video Summary]: Run `<execute>python3 plugins/bilibili_summary.py "URL"</execute>` to parse the video's title, description, and subtitles, then summarize it for the user.
- [✅ Github Architect]: You can run `git clone <url>`, then use tools like `find`, `grep`, and `cat` to recursively analyze software architectures and explain them to the user.
"""
    rules = ENV_VARS.get("WXCLAW_PUSH_RULES", "").strip()
    if rules:
        base += f"\nWECHAT PUSH RULES (USER PREFERENCES):\nThe user has specified the following rules for when you should proactively push messages to their WeChat:\n{rules}\n"
    return base

# Global Agent Session State for HTTP long-polling approval flow
SESSION = {
    "is_waiting": False,
    "messages": [],
    "current_command": "",
    "steps": [],
    "project_id": "",
    "chat_id": "",
    "wake_event": False
}

def extract_execute_cmd(ai_content: str) -> str:
    if "<execute>" in ai_content and "</execute>" in ai_content:
        start_idx = ai_content.find("<execute>") + len("<execute>")
        end_idx = ai_content.find("</execute>")
        return ai_content[start_idx:end_idx].strip()
    return ""

def get_thoughts(ai_content: str) -> str:
    # Get all text before <execute>
    idx = ai_content.find("<execute>")
    if idx != -1:
        return ai_content[:idx].strip()
    return ai_content.strip()

def extract_and_save_artifacts(ai_content: str, project_id: str, chat_id: str) -> str:
    if not project_id or not chat_id:
        return str(uuid.uuid4())
        
    node_id = str(uuid.uuid4())
    
    # 1. Extract code blocks
    code_pattern = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)
    for match in code_pattern.finditer(ai_content):
        lang = match.group(1) or "text"
        code_content = match.group(2).strip()
        if len(code_content) < 50 and lang not in ["html", "python", "js", "css", "vue", "react"]:
            continue
            
        title = f"{lang.capitalize()} Snippet"
        # Try to find a better title from the preceding text
        prefix_text = ai_content[:match.start()].strip()
        lines = prefix_text.split('\n')
        if lines:
            last_line = lines[-1].strip()
            if len(last_line) < 30 and ("代码" in last_line or "code" in last_line.lower()):
                title = last_line.replace("：", "").replace(":", "")

        preview = code_content[:100].replace("\n", " ") + "..."
        db.create_artifact(
            project_id=project_id,
            chat_id=chat_id,
            node_id=node_id,
            title=title or "Code Snippet",
            type_enum="code",
            content_url=code_content, 
            preview_text=preview,
            key_prompt=""
        )

    # 2. Extract image markdown ![title](url)
    img_pattern = re.compile(r"!\[(.*?)\]\((.*?)\)")
    for match in img_pattern.finditer(ai_content):
        alt_text = match.group(1).strip()
        img_url = match.group(2).strip()
        
        db.create_artifact(
            project_id=project_id,
            chat_id=chat_id,
            node_id=node_id,
            title=alt_text or "Image",
            type_enum="image",
            content_url=img_url,
            preview_text="Image generated or referenced",
            key_prompt=""
        )
        
    return node_id

# Start a new Agent conversation run
def start_agent_run(user_message: str, chat_history: list, project_id: str = "", chat_id: str = "") -> dict:
    messages = [{"role": "system", "content": get_system_prompt()}]
    for msg in chat_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    # Reset global state
    SESSION["messages"] = messages
    SESSION["steps"] = []
    SESSION["current_command"] = ""
    SESSION["is_waiting"] = False
    SESSION["project_id"] = project_id
    SESSION["chat_id"] = chat_id

    return process_next_llm_step()

# Execute LLM step and check for tools
def process_next_llm_step() -> dict:
    try:
        ai_content = call_llm(SESSION["messages"])
    except Exception as e:
        SESSION["is_waiting"] = False
        return {
            "status": "completed",
            "response": f"API Error: Failed to contact AI brain. Details: {e}",
            "steps": SESSION["steps"]
        }

    SESSION["messages"].append({"role": "assistant", "content": ai_content})
    cmd = extract_execute_cmd(ai_content)
    thoughts = get_thoughts(ai_content)

    if cmd:
        SESSION["is_waiting"] = True
        SESSION["current_command"] = cmd
        
        # WeChat Push on Approval Request
        default_to = ENV_VARS.get("WXCLAW_DEFAULT_TO", "")
        if default_to and ENV_VARS.get("WXCLAW_PUSH_ON_APPROVAL") == "true":
            push_msg = f"🔔【智能体审批申请】\nHiyori 申请在 Termux 运行以下命令：\n\n```bash\n{cmd}\n```\n\n你可以前往网页端面板审批，或直接在此回复“确认”以批准执行该指令。"
            threading.Thread(
                target=run_wxclawbot_send,
                args=(default_to, push_msg),
                daemon=True
            ).start()
            
        return {
            "status": "waiting_approval",
            "command": cmd,
            "thoughts": thoughts,
            "steps": SESSION["steps"]
        }
    else:
        SESSION["is_waiting"] = False
        # Intercept and extract artifacts!
        node_id = extract_and_save_artifacts(ai_content, SESSION.get("project_id", ""), SESSION.get("chat_id", ""))
        
        return {
            "status": "completed",
            "response": ai_content,
            "steps": SESSION["steps"],
            "node_id": node_id
        }

# Process command approval decision
def resume_agent_run(approved: bool, edited_command: str = "") -> dict:
    if not SESSION["is_waiting"]:
        return {"error": "No active session waiting for approval"}

    cmd_to_run = edited_command if edited_command else SESSION["current_command"]

    if approved:
        print(f"Running approved command: {cmd_to_run}")
        try:
            res = subprocess.run(
                cmd_to_run,
                shell=True,
                capture_output=True,
                text=True,
                timeout=20,
                cwd=str(pathlib.Path.home())
            )
            stdout = res.stdout
            stderr = res.stderr
            exit_code = res.returncode
        except subprocess.TimeoutExpired:
            stdout = ""
            stderr = "Command execution timed out after 20 seconds."
            exit_code = -1
        except Exception as e:
            stdout = ""
            stderr = f"Execution error: {e}"
            exit_code = -2

        output_summary = stdout + stderr
        if not output_summary.strip():
            output_summary = "[Command completed with no output]"

        SESSION["steps"].append({
            "command": cmd_to_run,
            "output": output_summary,
            "exit_code": exit_code
        })
        
        # Trigger WeChat warning if command fails and push on error is enabled
        default_to = ENV_VARS.get("WXCLAW_DEFAULT_TO", "")
        if exit_code != 0 and default_to and ENV_VARS.get("WXCLAW_PUSH_ON_ERROR") == "true":
            fail_msg = f"⚠️【终端指令执行失败】\n\n指令: `{cmd_to_run}`\n退出状态码: {exit_code}\n\n详情已记录在运行日志中。"
            threading.Thread(
                target=run_wxclawbot_send,
                args=(default_to, fail_msg),
                daemon=True
            ).start()
        elif exit_code == 0 and default_to and ENV_VARS.get("WXCLAW_PUSH_ON_SUCCESS") == "true":
            # Limit success message output to avoid spamming too much text
            success_summary = output_summary[:200] + "..." if len(output_summary) > 200 else output_summary
            success_msg = f"✅【终端指令执行成功】\n\n指令: `{cmd_to_run}`\n输出结果摘要:\n```\n{success_summary}\n```"
            threading.Thread(
                target=run_wxclawbot_send,
                args=(default_to, success_msg),
                daemon=True
            ).start()

        result_message = f"[Command execution result]\nExit Code: {exit_code}\nOutput:\n{output_summary}"
    else:
        print("Command execution denied by user")
        result_message = "[Command execution denied by user]"
        SESSION["steps"].append({
            "command": cmd_to_run,
            "output": "Execution denied by user.",
            "exit_code": -3
        })

    # Append command result message from the "user" role to keep LLM context
    SESSION["messages"].append({"role": "user", "content": result_message})
    SESSION["is_waiting"] = False
    SESSION["current_command"] = ""

    # Run next step
    return process_next_llm_step()


# === WeChat AI Assistant Integration Helpers ===
WECHAT_SESSIONS = {}
WECHAT_BRIDGE_PROCESS = None  # subprocess.Popen instance

def run_wechat_agent_step(input_content, session):
    if input_content is not None:
        session["messages"].append({"role": "user", "content": input_content})
        
    try:
        ai_content = call_llm(session["messages"])
    except Exception as e:
        return f"⚠️ Hiyori 脑电波连接失败: {e}"
        
    session["messages"].append({"role": "assistant", "content": ai_content})
    cmd = extract_execute_cmd(ai_content)
    thoughts = get_thoughts(ai_content)
    
    if cmd:
        session["is_waiting_approval"] = True
        session["current_command"] = cmd
        
        prompt_msg = ""
        if thoughts:
            prompt_msg += f"{thoughts}\n\n"
        prompt_msg += f"🤖 Hiyori 想要运行以下 Termux 命令，请回复【确认】以批准，或【拒绝】以拒绝。你也可以直接输入修改后的命令来执行：\n\n```bash\n{cmd}\n```"
        return prompt_msg
    else:
        return ai_content

def run_wechat_command(cmd_to_run, session):
    print(f"Running approved WeChat command: {cmd_to_run}")
    try:
        res = subprocess.run(
            cmd_to_run,
            shell=True,
            capture_output=True,
            text=True,
            timeout=20,
            cwd=str(pathlib.Path.home())
        )
        stdout = res.stdout
        stderr = res.stderr
        exit_code = res.returncode
    except subprocess.TimeoutExpired:
        stdout = ""
        stderr = "Command execution timed out after 20 seconds."
        exit_code = -1
    except Exception as e:
        stdout = ""
        stderr = f"Execution error: {e}"
        exit_code = -2

    output_summary = stdout + stderr
    if not output_summary.strip():
        output_summary = "[Command completed with no output]"

    session["steps"].append({
        "command": cmd_to_run,
        "output": output_summary,
        "exit_code": exit_code
    })

    return f"[Command execution result]\nExit Code: {exit_code}\nOutput:\n{output_summary}"

# --- WeChat Dialog Platform & wxclawbot Management ---
def save_env_config(config: dict) -> bool:
    env_dir = pathlib.Path.home() / ".config" / "gmgn"
    env_dir.mkdir(parents=True, exist_ok=True)
    env_path = env_dir / ".env"
    
    # Read existing lines
    lines = []
    if env_path.exists():
        lines = env_path.read_text().splitlines()
        
    env_dict = {}
    for line in lines:
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env_dict[k.strip()] = v.strip()
            
    # Update keys
    for k, v in config.items():
        env_dict[k] = f'"{v}"' if v else ""
        
    # Reconstruct
    out_lines = []
    for k, v in env_dict.items():
        if v:
            out_lines.append(f"{k}={v}")
        else:
            # Preserve comment or formatting if needed, but simple key=value output is fine
            pass
            
    try:
        env_path.write_text("\n".join(out_lines) + "\n")
        # Reload global vars
        global ENV_VARS
        ENV_VARS = load_env()
        return True
    except Exception as e:
        print(f"Error saving config to env: {e}")
        return False

def run_wxclawbot_send(to_user_id, text, context_token="") -> bool:
    import urllib.request
    import uuid
    import json
    
    token_env = ENV_VARS.get("WXCLAW_TOKEN", "")
    base_url = ENV_VARS.get("WXCLAW_BASE_URL", "https://ilinkai.weixin.qq.com")
    
    if not token_env or ":" not in token_env:
        print("Error: WXCLAW_TOKEN is not configured in env.")
        return False
        
    bot_id, bot_token = token_env.split(":", 1)
    
    payload = {
        "msg": {
            "from_user_id": "",
            "to_user_id": to_user_id,
            "client_id": str(uuid.uuid4()),
            "message_type": 2,
            "message_state": 2,
            "item_list": [{"type": 1, "text_item": {"text": text}}]
        }
    }
    if context_token:
        payload["msg"]["context_token"] = context_token
        
    try:
        req = urllib.request.Request(f"{base_url}/ilink/bot/sendmessage")
        req.add_header("Authorization", f"Bearer {bot_token}")
        req.add_header("AuthorizationType", "ilink_bot_token")
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(payload).encode('utf-8')
        
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = response.read().decode('utf-8')
            print(f"Direct API send result: {res_data}")
            return True
    except Exception as e:
        print(f"Failed to execute direct WeChat send: {e}")
        return False

def handle_wechat_remote_control(user_msg, sender_id, context_token=""):
    import sys
    import pathlib
    msg_strip = user_msg.strip()
    cmd_parts = msg_strip.split(maxsplit=1)
    cmd_name = cmd_parts[0].lower()
    
    # Check if the user is authorized (sender_id must be default_to)
    default_to = ENV_VARS.get("WXCLAW_DEFAULT_TO", "")
    if sender_id != default_to:
        run_wxclawbot_send(sender_id, "🚫 您未被授权执行远程指令。请先在控制中心面板绑定此微信。", context_token)
        return True

    if cmd_name in ["/help", "/menu", "菜单", "/菜单"]:
        help_text = (
            "📱【Micro-AGI 远程控制菜单】\n"
            "你可以通过微信发送以下指令控制 Termux 主程序：\n\n"
            "🔹 `/status` - 查看手机系统状态、电量与服务状态\n"
            "🔹 `/restart` - 重启控制中心 Web 服务\n"
            "🔹 `/cmd <命令>` - 执行任意 Termux 终端 Shell 命令\n"
            "🔹 `/wake` - 触发模拟语音唤醒事件\n"
            "🔹 `/sysinfo` - 获取更详细的硬件与进程信息\n\n"
            "💡 直接发送普通文本可以与 AGI 智能体进行对话。"
        )
        run_wxclawbot_send(sender_id, help_text, context_token)
        return True
        
    elif cmd_name == "/status":
        battery_info = "未知"
        try:
            bat_res = subprocess.run("termux-battery-status", shell=True, capture_output=True, text=True, timeout=5)
            if bat_res.returncode == 0:
                bat_json = json.loads(bat_res.stdout)
                percentage = bat_json.get("percentage", 100)
                status = bat_json.get("status", "DISCHARGING")
                temp = bat_json.get("temperature", 0.0)
                status_zh = "充电中" if "CHARGING" in status else "放电中"
                battery_info = f"{percentage}% ({status_zh}), 温度 {temp}°C"
        except Exception:
            battery_info = "无法获取 (可能未安装 termux-api)"

        mem_info = "未知"
        try:
            mem_res = subprocess.run("free -m", shell=True, capture_output=True, text=True, timeout=5)
            if mem_res.returncode == 0:
                lines = mem_res.stdout.split('\n')
                if len(lines) > 1:
                    parts = lines[1].split()
                    if len(parts) > 3:
                        total_mem = parts[1]
                        used_mem = parts[2]
                        mem_info = f"已用 {used_mem}MB / 共 {total_mem}MB"
        except Exception:
            pass

        tmux_sessions = "无活跃会话"
        try:
            tmux_res = subprocess.run("tmux ls", shell=True, capture_output=True, text=True, timeout=5)
            if tmux_res.returncode == 0:
                tmux_sessions = "\n" + tmux_res.stdout.strip()
        except Exception:
            pass

        status_text = (
            "📊【Micro-AGI 当前状态】\n\n"
            f"🔋 设备电量: {battery_info}\n"
            f"🧠 内存状态: {mem_info}\n"
            f"🔗 微信绑定 ID: {sender_id}\n"
            f"⚙️ 活跃 tmux 会话: {tmux_sessions}\n\n"
            "🟢 服务正在稳定运行中..."
        )
        run_wxclawbot_send(sender_id, status_text, context_token)
        return True
        
    elif cmd_name == "/restart":
        run_wxclawbot_send(sender_id, "⏳ 收到远程指令：正在拉取最新代码并重启服务器...", context_token)
        subprocess.run("git pull origin master", shell=True, capture_output=True, timeout=15)
        import threading
        import sys
        import time
        def exit_later():
            time.sleep(1)
            sys.exit(0)
        threading.Thread(target=exit_later).start()
        return True
        
    elif cmd_name == "/wake":
        SESSION["wake_event"] = True
        run_wxclawbot_send(sender_id, "🎙️ 成功远程触发模拟语音唤醒事件！设备端将进入聆听状态。", context_token)
        return True
        
    elif cmd_name == "/sysinfo":
        uptime_str = "未知"
        try:
            uptime_res = subprocess.run("uptime", shell=True, capture_output=True, text=True, timeout=5)
            if uptime_res.returncode == 0:
                uptime_str = uptime_res.stdout.strip()
        except Exception:
            pass
            
        sysinfo_text = (
            "⚙️【Micro-AGI 硬件/系统信息】\n\n"
            f"⏱️ 系统运行时间: {uptime_str}\n"
            f"📁 运行目录: `/data/data/com.termux/files/home/micro-agi-mvp`\n"
            f"🐍 Python 版本: {sys.version.split()[0]}\n"
        )
        run_wxclawbot_send(sender_id, sysinfo_text, context_token)
        return True

    elif cmd_name == "/cmd":
        if len(cmd_parts) < 2:
            run_wxclawbot_send(sender_id, "⚠️ 请提供要执行的 Shell 命令。用法: `/cmd <命令>`", context_token)
            return True
            
        shell_cmd = cmd_parts[1]
        run_wxclawbot_send(sender_id, f"💻 正在执行命令: `{shell_cmd}` ...", context_token)
        
        try:
            res = subprocess.run(
                shell_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=15,
                cwd=str(pathlib.Path.home())
            )
            out = res.stdout
            err = res.stderr
            code = res.returncode
            
            output_sum = out + err
            if not output_sum.strip():
                output_sum = "[无输出内容]"
            
            if len(output_sum) > 800:
                output_sum = output_sum[:800] + "\n...(输出过长，已截断)"
                
            reply_msg = (
                f"💻【执行结果 (退出码: {code})】\n"
                f"```\n{output_sum}\n```"
            )
            run_wxclawbot_send(sender_id, reply_msg, context_token)
        except subprocess.TimeoutExpired:
            run_wxclawbot_send(sender_id, "❌ 执行超时 (超过 15 秒)。", context_token)
        except Exception as e:
            run_wxclawbot_send(sender_id, f"❌ 执行异常: {str(e)}", context_token)
            
        return True
        
    return False

def handle_async_wechat_msg(user_msg, sender_id, sender_name, to_user_name, context_token=""):
    # Automatically bind this sender as default user if not already bound
    if sender_id and not ENV_VARS.get("WXCLAW_DEFAULT_TO"):
        print(f"Auto-binding {sender_id} as WXCLAW_DEFAULT_TO in env")
        save_env_config({
            "WXCLAW_DEFAULT_TO": sender_id
        })

    # WeChat Remote Command Interception
    msg_strip = user_msg.strip()
    is_cmd = msg_strip.startswith("/") or msg_strip == "菜单"
    if is_cmd:
        if handle_wechat_remote_control(user_msg, sender_id, context_token):
            return

    # Cross-session Web UI command approval check
    default_to = ENV_VARS.get("WXCLAW_DEFAULT_TO", "")
    if SESSION.get("is_waiting") and sender_id == default_to:
        if user_msg in ["确认", "批准", "确定", "y", "yes", "Y", "批准指令"]:
            cmd_to_run = SESSION["current_command"]
            print(f"[WeChat Remote] User approved Web UI command from WeChat: {cmd_to_run}")
            run_wxclawbot_send(sender_id, "⏳ 收到微信审批，正在 Termux 执行命令...", context_token)
            
            result = resume_agent_run(True)
            
            chat_id = SESSION.get("chat_id", "")
            if chat_id and result.get("status") == "completed":
                db.save_message(chat_id, "assistant", result.get("response", ""))
                
            final_reply = result.get("response", "执行完成")
            run_wxclawbot_send(sender_id, f"✅ 执行完成！回复内容：\n\n{final_reply}", context_token)
            return
        elif user_msg in ["拒绝", "不", "no", "n", "N", "拒绝指令"]:
            print("[WeChat Remote] User denied Web UI command from WeChat.")
            result = resume_agent_run(False)
            run_wxclawbot_send(sender_id, "❌ 已拒绝该命令执行。", context_token)
            return

    # Get or initialize session state for this user
    if sender_id not in WECHAT_SESSIONS:
        WECHAT_SESSIONS[sender_id] = {
            "is_waiting_approval": False,
            "current_command": "",
            "messages": [{"role": "system", "content": get_system_prompt()}],
            "steps": []
        }
    session = WECHAT_SESSIONS[sender_id]

    print(f"Processing WeChat message in background: {user_msg} (sender={sender_id})")

    # Check if we are waiting for command approval in this session
    if session["is_waiting_approval"]:
        if user_msg in ["确认", "批准", "确定", "y", "yes", "Y", "批准指令"]:
            cmd_to_run = session["current_command"]
            session["is_waiting_approval"] = False
            session["current_command"] = ""
            # Execute command
            result_str = run_wechat_command(cmd_to_run, session)
            # Resume LLM processing
            reply = run_wechat_agent_step(result_str, session)
        elif user_msg in ["拒绝", "不", "no", "n", "N", "拒绝指令"]:
            session["is_waiting_approval"] = False
            session["current_command"] = ""
            reply = run_wechat_agent_step("[Command execution denied by user]", session)
        else:
            # User edited/changed the command directly from WeChat
            cmd_to_run = user_msg
            session["is_waiting_approval"] = False
            session["current_command"] = ""
            result_str = run_wechat_command(cmd_to_run, session)
            reply = run_wechat_agent_step(result_str, session)
    else:
        # Start a new agent query session for WeChat
        session["messages"] = [{"role": "system", "content": get_system_prompt()}]
        session["messages"].append({"role": "user", "content": user_msg})
        session["steps"] = []
        reply = run_wechat_agent_step(None, session)

    # Deliver the reply back to the user's WeChat via direct API
    print(f"Delivering reply via API send: {reply}")
    run_wxclawbot_send(sender_id, reply, context_token)
# ===============================================

# --- Network Intranet Tunnel (localhost.run) ---
TUNNEL_PROCESS = None
TUNNEL_URL = ""
TUNNEL_STATUS = "inactive" # "inactive", "starting", "active", "failed"

def start_ssh_tunnel():
    global TUNNEL_PROCESS, TUNNEL_URL, TUNNEL_STATUS
    if TUNNEL_PROCESS is not None:
        return
    
    TUNNEL_STATUS = "starting"
    TUNNEL_URL = ""
    
    def run_tunnel():
        global TUNNEL_PROCESS, TUNNEL_URL, TUNNEL_STATUS
        try:
            import os
            import signal
            cmd = "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -R 80:localhost:8085 nokey@localhost.run"
            TUNNEL_PROCESS = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                preexec_fn=os.setsid
            )
            
            # Read stdout line-by-line
            for line in iter(TUNNEL_PROCESS.stdout.readline, ''):
                print(f"[Tunnel SSH] {line.strip()}")
                # Match URL e.g. "https://xxxx.lhr.life"
                match = re.search(r"https://[a-zA-Z0-9.-]+\.lhr\.life", line)
                if match:
                    TUNNEL_URL = match.group(0)
                    TUNNEL_STATUS = "active"
                    print(f"[Tunnel SSH] Tunnel established successfully! Public URL: {TUNNEL_URL}")
            
            TUNNEL_PROCESS.wait()
        except Exception as e:
            print(f"[Tunnel SSH] Exception in tunnel thread: {e}")
            TUNNEL_STATUS = "failed"
        finally:
            TUNNEL_PROCESS = None
            if TUNNEL_STATUS != "failed":
                TUNNEL_STATUS = "inactive"
            TUNNEL_URL = ""
            print("[Tunnel SSH] Tunnel process stopped.")

    threading.Thread(target=run_tunnel, daemon=True).start()

def stop_ssh_tunnel():
    global TUNNEL_PROCESS, TUNNEL_STATUS, TUNNEL_URL
    if TUNNEL_PROCESS is not None:
        print("[Tunnel SSH] Terminating tunnel process...")
        try:
            import os
            import signal
            os.killpg(os.getpgid(TUNNEL_PROCESS.pid), signal.SIGTERM)
        except Exception as e:
            print(f"[Tunnel SSH] Failed to kill process group: {e}")
            try:
                TUNNEL_PROCESS.terminate()
            except Exception:
                pass
        TUNNEL_PROCESS = None
    TUNNEL_STATUS = "inactive"
    TUNNEL_URL = ""

# 4. Multi-threaded HTTP Request Handler
class AgentMVPHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def _parse_skill_md(self, path):
        try:
            content = path.read_text(encoding='utf-8')
            match = re.search(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
            if match:
                yaml_content = match.group(1)
                name = None
                desc = None
                for line in yaml_content.split('\n'):
                    if line.startswith('name:'):
                        name = line.split('name:', 1)[1].strip().strip('"').strip("'")
                    elif line.startswith('description:'):
                        desc = line.split('description:', 1)[1].strip().strip('"').strip("'")
                return name, desc
        except Exception:
            pass
        return None, None

    def do_GET(self):
        # Strip query parameters for routing
        req_path = self.path.split("?")[0]
        
        if req_path == "/" or req_path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            
            html_path = pathlib.Path(__file__).parent / "index.html"
            if html_path.exists():
                self.wfile.write(html_path.read_bytes())
            else:
                self.wfile.write(b"<h1>index.html not found!</h1>")

        elif req_path == "/style.css":
            self.send_response(200)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            
            css_path = pathlib.Path(__file__).parent / "style.css"
            if css_path.exists():
                self.wfile.write(css_path.read_bytes())
            else:
                self.wfile.write(b"")

        elif req_path == "/script.js":
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            
            js_path = pathlib.Path(__file__).parent / "script.js"
            if js_path.exists():
                self.wfile.write(js_path.read_bytes())
            else:
                self.wfile.write(b"")

        elif req_path == "/manifest.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            manifest_path = pathlib.Path(__file__).parent / "manifest.json"
            if manifest_path.exists():
                self.wfile.write(manifest_path.read_bytes())
            else:
                self.wfile.write(b"{}")

        elif req_path == "/sw.js":
            self.send_response(404)
            self.end_headers()
            return

        # --- Google OAuth Login GET routes ---
        elif req_path == "/google_login":
            import urllib.parse
            client_id = ENV_VARS.get("GOOGLE_CLIENT_ID", "884354919052-36trc1jjb3tguiac32ov6cod268c5blh.apps.googleusercontent.com")
            redirect_uri = "http://localhost:8085/oauth2callback"
            
            auth_url = (
                "https://accounts.google.com/o/oauth2/v2/auth?"
                f"client_id={client_id}&"
                f"redirect_uri={urllib.parse.quote(redirect_uri)}&"
                "response_type=code&"
                "scope=https://www.googleapis.com/auth/generative-language&"
                "access_type=offline&"
                "prompt=consent"
            )
            self.send_response(302)
            self.send_header("Location", auth_url)
            self.end_headers()
            return

        elif req_path == "/oauth2callback":
            import urllib.parse
            query_params = {}
            if "?" in self.path:
                for item in self.path.split("?", 1)[1].split("&"):
                    if "=" in item:
                        k, v = item.split("=", 1)
                        query_params[k] = urllib.parse.unquote(v)
            
            code = query_params.get("code", "")
            if not code:
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<h1>Error: Missing 'code' parameter</h1>")
                return
            
            client_id = ENV_VARS.get("GOOGLE_CLIENT_ID", "884354919052-36trc1jjb3tguiac32ov6cod268c5blh.apps.googleusercontent.com")
            redirect_uri = "http://localhost:8085/oauth2callback"
            token_url = "https://oauth2.googleapis.com/token"
            payload = {
                "client_id": client_id,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri
            }
            data = urllib.parse.urlencode(payload).encode("utf-8")
            
            proxy_url = ENV_VARS.get("PROXY_URL", "http://127.0.0.1:7890")
            if proxy_url:
                proxy_handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
                opener = urllib.request.build_opener(proxy_handler)
            else:
                opener = urllib.request.build_opener()
                
            req = urllib.request.Request(token_url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
            
            try:
                with opener.open(req, timeout=15) as response:
                    res = json.loads(response.read().decode("utf-8"))
                    access_token = res.get("access_token")
                    refresh_token = res.get("refresh_token")
                    
                    if access_token:
                        config_to_save = {
                            "GOOGLE_ACCESS_TOKEN": access_token
                        }
                        if refresh_token:
                            config_to_save["GOOGLE_REFRESH_TOKEN"] = refresh_token
                        
                        save_env_config(config_to_save)
                        
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.end_headers()
                        html_res = """
                        <html>
                        <head><title>Google Login Success</title>
                        <meta charset="utf-8">
                        <style>
                            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; text-align: center; padding: 50px; background-color: #f5f5f7; color: #1d1d1f; }
                            .card { background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); display: inline-block; }
                            h1 { color: #34a853; }
                            button { background-color: #0071e3; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 16px; margin-top: 20px; }
                        </style>
                        </head>
                        <body>
                            <div class="card">
                                <h1>Google 登录成功!</h1>
                                <p>您的 Access Token 已保存到后台配置中，您可以返回应用开始使用了。</p>
                                <button onclick="window.close()">关闭此页面</button>
                            </div>
                        </body>
                        </html>
                        """
                        self.wfile.write(html_res.encode('utf-8'))
                        return
                    else:
                        raise Exception("No access_token returned from Google")
            except Exception as e:
                # Fallback: Retry without proxy
                if proxy_url:
                    try:
                        opener_no_proxy = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                        with opener_no_proxy.open(req, timeout=15) as response:
                            res = json.loads(response.read().decode("utf-8"))
                            access_token = res.get("access_token")
                            refresh_token = res.get("refresh_token")
                            if access_token:
                                config_to_save = {"GOOGLE_ACCESS_TOKEN": access_token}
                                if refresh_token:
                                    config_to_save["GOOGLE_REFRESH_TOKEN"] = refresh_token
                                save_env_config(config_to_save)
                                
                                self.send_response(200)
                                self.send_header("Content-Type", "text/html; charset=utf-8")
                                self.end_headers()
                                self.wfile.write("<h1>Google 登录成功 (Direct)!</h1><p>已保存 Token。请返回应用。</p>".encode('utf-8'))
                                return
                    except Exception as e2:
                        e = e2
                self.send_response(500)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"<h1>OAuth Callback Failed</h1><p>{str(e)}</p>".encode("utf-8"))
                return

        elif req_path == "/api/system/google_status":
            token = ENV_VARS.get("GOOGLE_ACCESS_TOKEN", "")
            refresh_token = ENV_VARS.get("GOOGLE_REFRESH_TOKEN", "")
            gemini_key = ENV_VARS.get("GEMINI_API_KEY", "")
            
            ai_url = ENV_VARS.get("AI_URL", "")
            ai_key = ENV_VARS.get("AI_KEY", "")
            ai_model = ENV_VARS.get("AI_MODEL", "")
            
            status = "disconnected"
            if token or refresh_token:
                status = "connected"
                
            self._send_json({
                "status": status,
                "gemini_key": gemini_key,
                "ai_url": ai_url,
                "ai_key": ai_key,
                "ai_model": ai_model
            })

        # --- DB Artifacts API GET routes ---
        elif req_path == "/api/projects":
            self._send_json(db.list_projects())
            
        elif req_path == "/api/chats":
            import urllib.parse
            query_params = {}
            if "?" in self.path:
                for item in self.path.split("?", 1)[1].split("&"):
                    if "=" in item:
                        k, v = item.split("=", 1)
                        query_params[k] = urllib.parse.unquote(v)
            project_id = query_params.get("project_id", "")
            if not project_id:
                projects = db.list_projects()
                if projects:
                    project_id = projects[0]["project_id"]
            if project_id:
                self._send_json(db.list_chats(project_id))
            else:
                self._send_json([])

        elif req_path.startswith("/api/chats/") and req_path.endswith("/messages"):
            parts = req_path.split("/")
            chat_id = parts[3]
            self._send_json(db.get_chat_messages(chat_id))
            
        elif req_path == "/api/artifacts":
            import urllib.parse
            query_params = {}
            if "?" in self.path:
                for item in self.path.split("?", 1)[1].split("&"):
                    if "=" in item:
                        k, v = item.split("=", 1)
                        query_params[k] = urllib.parse.unquote(v)
            project_id = query_params.get("project_id", "")
            type_filter = query_params.get("type_filter", "")
            
            if not project_id:
                projects = db.list_projects()
                if projects:
                    project_id = projects[0]["project_id"]
            if project_id:
                self._send_json(db.list_artifacts(project_id, type_filter))
            else:
                self._send_json([])

        # --- Android Hardware API GET routes ---
        elif req_path == "/api/hardware/battery":
            try:
                res = subprocess.run("termux-battery-status", shell=True, capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    data = json.loads(res.stdout)
                    self._send_json({
                        "percentage": data.get("percentage", 0),
                        "status": data.get("status", "unknown"),
                        "temperature": data.get("temperature", 0.0),
                        "health": data.get("health", "good")
                    })
                else:
                    self._send_json({
                        "percentage": 85,
                        "status": "Not Charging",
                        "temperature": 32.5,
                        "health": "GOOD",
                        "warning": "Termux-API not available"
                    })
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif req_path == "/api/hardware/clipboard":
            try:
                res = subprocess.run("termux-clipboard-get", shell=True, capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    self._send_json({"text": res.stdout})
                else:
                    self._send_json({"text": "", "warning": "Termux-API not available"})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
 
        elif req_path == "/api/hardware/wake":
            woken = SESSION.get("wake_event", False)
            if woken:
                SESSION["wake_event"] = False # Reset flag
            self._send_json({"woken": woken})

        elif req_path == "/api/system/update":
            try:
                subprocess.run("git fetch", shell=True, capture_output=True, timeout=10)
                local_res = subprocess.run("git rev-parse HEAD", shell=True, capture_output=True, text=True, timeout=5)
                local_commit = local_res.stdout.strip() if local_res.returncode == 0 else ""
                
                remote_res = subprocess.run("git rev-parse origin/master", shell=True, capture_output=True, text=True, timeout=5)
                remote_commit = remote_res.stdout.strip() if remote_res.returncode == 0 else ""
                
                update_available = (local_commit != remote_commit) and bool(local_commit) and bool(remote_commit)
                self._send_json({
                    "update_available": update_available,
                    "local_commit": local_commit[:7] if local_commit else "",
                    "remote_commit": remote_commit[:7] if remote_commit else ""
                })
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif req_path == "/api/system/tunnel":
            self._send_json({
                "status": TUNNEL_STATUS,
                "url": TUNNEL_URL
            })

        # --- WeChat API GET routes ---
        elif req_path == "/api/wechat/status":
            token = ENV_VARS.get("WXCLAW_TOKEN", "")
            base_url = ENV_VARS.get("WXCLAW_BASE_URL", "https://ilinkai.weixin.qq.com")
            push_rules = ENV_VARS.get("WXCLAW_PUSH_RULES", "")
            
            if token:
                # Extract botId from botId:token format
                bot_id = token.split(":", 1)[0] if ":" in token else "微信机器人"
                self._send_json({
                    "status": "configured",
                    "bot_id": bot_id,
                    "base_url": base_url,
                    "token": token,
                    "push_rules": push_rules,
                    "push_approval": ENV_VARS.get("WXCLAW_PUSH_ON_APPROVAL", "false"),
                    "push_error": ENV_VARS.get("WXCLAW_PUSH_ON_ERROR", "false"),
                    "push_success": ENV_VARS.get("WXCLAW_PUSH_ON_SUCCESS", "false"),
                    "push_battery": ENV_VARS.get("WXCLAW_PUSH_ON_BATTERY", "false")
                })
            else:
                self._send_json({
                    "status": "unconfigured"
                })

        elif req_path == "/api/wechat_webhook":
            # WeChat developer URL validation (GET echostr challenge)
            query_params = {}
            if "?" in self.path:
                for item in self.path.split("?", 1)[1].split("&"):
                    if "=" in item:
                        k, v = item.split("=", 1)
                        query_params[k] = urllib.parse.unquote(v)
            echostr = query_params.get("echostr", "")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(echostr.encode("utf-8"))

        elif req_path in ["/live2dcubismcore.min.js", "/pixi.min.js", "/pixi-live2d-display.min.js"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.end_headers()
            
            js_path = pathlib.Path(__file__).parent / req_path.lstrip("/")
            if js_path.exists():
                self.wfile.write(js_path.read_bytes())
            else:
                self.wfile.write(b"")
        elif req_path.startswith("/Hiyori/"):
            file_path = pathlib.Path(__file__).parent / req_path.lstrip("/")
            if file_path.exists() and file_path.is_file():
                self.send_response(200)
                ext = file_path.suffix.lower()
                if ext == ".json":
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                elif ext == ".png":
                    self.send_header("Content-Type", "image/png")
                elif ext == ".moc3":
                    self.send_header("Content-Type", "application/octet-stream")
                else:
                    self.send_header("Content-Type", "application/octet-stream")
                self.end_headers()
                self.wfile.write(file_path.read_bytes())
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"File not found")
        elif req_path == "/api/system/extensions":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            
            config_path = pathlib.Path(__file__).parent / "extensions_config.json"
            config = {}
            if config_path.exists():
                try:
                    config = json.loads(config_path.read_text(encoding='utf-8'))
                except Exception:
                    pass
            
            extensions = []
            
            # 1. Scan Custom Skills
            skills_dirs = [
                pathlib.Path("/data/data/com.termux/files/home/.gemini/antigravity-cli/builtin/skills"),
                pathlib.Path("/data/data/com.termux/files/home/.agents/skills")
            ]
            
            for s_dir in skills_dirs:
                if s_dir.exists():
                    for child in s_dir.iterdir():
                        if child.is_dir():
                            skill_md = child / "SKILL.md"
                            if skill_md.exists():
                                name, desc = self._parse_skill_md(skill_md)
                                if name:
                                    s_id = child.name
                                    extensions.append({
                                        "id": s_id,
                                        "name": name,
                                        "type": "skill",
                                        "description": desc or f"Custom agent skill from {s_id}",
                                        "enabled": config.get(s_id, True),
                                        "status": "active" if config.get(s_id, True) else "disabled",
                                        "icon": "🧠"
                                    })
                                    
            # 2. Add Plugins
            plugins = [
                {"id": "search", "name": "实时全网检索", "type": "plugin", "description": "允许 AI 自动使用 Python 脚本全网检索并总结。", "icon": "🔍"},
                {"id": "bilibili", "name": "B站视频摘要", "type": "plugin", "description": "全自动解析视频弹幕及字幕并生成核心要点脑图。", "icon": "📺"},
                {"id": "github", "name": "Github 架构师", "type": "plugin", "description": "一键克隆仓库，静态扫描并解答关于架构的问题。", "icon": "💻"}
            ]
            for p in plugins:
                p_id = p["id"]
                p["enabled"] = config.get(p_id, True)
                p["status"] = "active" if config.get(p_id, True) else "disabled"
                extensions.append(p)
                
            # 3. Add MCPs
            mcps = [
                {"id": "mcp-fs", "name": "Termux FileSystem (内网)", "type": "mcp", "description": "本地系统的底层文件管理器，提供 shell 命令执行与文件操作。", "icon": "📂"},
                {"id": "mcp-web", "name": "Search & Web Scraper", "type": "mcp", "description": "网络检索端点，提供网页内容智能提取与分析接口。", "icon": "🌐"}
            ]
            for m in mcps:
                m_id = m["id"]
                m["enabled"] = config.get(m_id, True)
                m["status"] = "online" if config.get(m_id, True) else "disabled"
                extensions.append(m)
                
            self.wfile.write(json.dumps(extensions).encode('utf-8'))
        else:
            # Default fallback for other static assets
            super().do_GET()

    def do_DELETE(self):
        req_path = self.path.split("?")[0]
        if req_path.startswith("/api/artifacts/"):
            artifact_id = req_path.split("/")[-1]
            try:
                db.delete_artifact(artifact_id)
                self._send_json({"status": "success"})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        elif req_path.startswith("/api/chats/"):
            chat_id = req_path.split("/")[-1]
            try:
                db.delete_chat(chat_id)
                self._send_json({"status": "success"})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        if self.path == "/api/chat":
            try:
                req_json = json.loads(post_data.decode('utf-8'))
                user_msg = req_json.get("message", "")
                history = req_json.get("history", [])
                attachments = req_json.get("attachments", [])

                if attachments:
                    uploads_dir = pathlib.Path.home() / "micro-agi-mvp" / "uploads"
                    uploads_dir.mkdir(parents=True, exist_ok=True)
                    
                    content_list = [{"type": "text", "text": user_msg}]
                    saved_files_text = []
                    
                    for att in attachments:
                        file_name = att.get("name", "unnamed_file")
                        file_data_b64 = att.get("data", "")
                        file_type = att.get("type", "")
                        
                        if file_data_b64.startswith("data:"):
                            file_data_b64 = file_data_b64.split(",", 1)[1]
                            
                        # Save to disk
                        save_path = uploads_dir / file_name
                        try:
                            save_path.write_bytes(base64.b64decode(file_data_b64))
                            saved_files_text.append(str(save_path))
                        except Exception as e:
                            print(f"Error saving attachment {file_name}: {e}")
                            
                        # If image, attach it natively for vision model support
                        if file_type.startswith("image/"):
                            data_uri = f"data:{file_type};base64,{file_data_b64}"
                            content_list.append({
                                "type": "image_url",
                                "image_url": {"url": data_uri}
                            })
                            
                    if saved_files_text:
                        append_txt = "\n\n[System Note: User has attached files to this message."
                        has_image = any(f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')) for f in saved_files_text)
                        if has_image:
                            append_txt += " You CAN see the attached images directly in this message! The visual content is already provided to you natively."
                        append_txt += " The files are also saved locally on the device at the following paths. You can use standard terminal commands to process them further if needed:]\n"
                        for p in saved_files_text:
                            append_txt += f"- {p}\n"
                        content_list[0]["text"] += append_txt
                        
                    if len(content_list) == 1:
                        user_msg = content_list[0]["text"]
                    else:
                        user_msg = content_list

                print(f"\nUser Request: {user_msg if isinstance(user_msg, str) else '[Complex Message with Attachments]'}")
                
                # Setup Project & Chat
                project_id = req_json.get("project_id", "")
                chat_id = req_json.get("chat_id", "")
                
                # Auto-initialize a project/chat if none provided (for graceful degradation)
                if not project_id:
                    projects = db.list_projects()
                    if projects:
                        project_id = projects[0]["project_id"]
                    else:
                        project_id = db.create_project("默认工作区", "系统初始化的默认全局工作区")
                if not chat_id:
                    chats = db.list_chats(project_id)
                    if chats:
                        chat_id = chats[0]["chat_id"]
                    else:
                        chat_id = db.create_chat(project_id, "新建对话")
                else:
                    db.update_chat_time(chat_id)
                
                # Save user message to database
                db_user_msg = user_msg
                if isinstance(user_msg, list):
                    for item in user_msg:
                        if isinstance(item, dict) and item.get("type") == "text":
                            db_user_msg = item.get("text", "")
                            break
                db.save_message(chat_id, "user", db_user_msg)

                result = start_agent_run(user_msg, history, project_id, chat_id)
                
                if result.get("status") == "completed":
                    db.save_message(chat_id, "assistant", result.get("response", ""))

                # Ensure chat_id is returned to the frontend
                result["chat_id"] = chat_id

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode('utf-8'))
            except Exception as e:
                traceback.print_exc()
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

        elif self.path == "/api/chats":
            try:
                req_json = json.loads(post_data.decode('utf-8'))
                project_id = req_json.get("project_id", "")
                title = req_json.get("title", "新对话")
                
                if not project_id:
                    projects = db.list_projects()
                    if projects:
                        project_id = projects[0]["project_id"]
                if project_id:
                    chat_id = db.create_chat(project_id, title)
                    self._send_json({"status": "success", "chat_id": chat_id})
                else:
                    self._send_json({"error": "No project found"}, 400)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif self.path == "/api/chats/rename":
            try:
                req_json = json.loads(post_data.decode('utf-8'))
                chat_id = req_json.get("chat_id", "")
                title = req_json.get("title", "")
                if chat_id and title:
                    db.rename_chat(chat_id, title)
                    self._send_json({"status": "success"})
                else:
                    self._send_json({"error": "Missing parameters"}, 400)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif self.path == "/api/approve":
            try:
                req_json = json.loads(post_data.decode('utf-8'))
                approved = req_json.get("approved", True)
                edited_command = req_json.get("edited_command", "")

                print(f"Approval received: {approved} (edited: '{edited_command}')")
                result = resume_agent_run(approved, edited_command)

                if result.get("status") == "completed":
                    chat_id = SESSION.get("chat_id", "")
                    if chat_id:
                        db.save_message(chat_id, "assistant", result.get("response", ""))

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode('utf-8'))
            except Exception as e:
                traceback.print_exc()
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
        elif self.path == "/api/wechat_webhook":
            try:
                req_json = json.loads(post_data.decode('utf-8'))
                
                # Support both WeChat Dialog Platform (JSON) and custom payload structures
                if "msg" in req_json and isinstance(req_json["msg"], dict):
                    msg_obj = req_json["msg"]
                    sender_id = msg_obj.get("from_user_id", "")
                    sender_name = sender_id
                    to_user_name = msg_obj.get("to_user_id", "")
                    user_msg = ""
                    if "item_list" in msg_obj and isinstance(msg_obj["item_list"], list) and len(msg_obj["item_list"]) > 0:
                        first_item = msg_obj["item_list"][0]
                        if "text_item" in first_item and isinstance(first_item["text_item"], dict):
                            user_msg = first_item["text_item"].get("text", "")
                else:
                    user_msg = req_json.get("message", "").strip()
                    sender_id = req_json.get("sender_id", "")
                    sender_name = req_json.get("sender_name", "")
                    to_user_name = req_json.get("to_user_id", "")

                print(f"\n[WeChat Webhook Request] from {sender_name} ({sender_id}): {user_msg}")

                # Start the agent processing asynchronously in a background thread to prevent timeout
                threading.Thread(
                    target=handle_async_wechat_msg,
                    args=(user_msg, sender_id, sender_name, to_user_name),
                    daemon=True
                ).start()

                # Respond immediately to avoid 5s timeout error on WeChat platform
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "processing"}).encode('utf-8'))

            except Exception as e:
                traceback.print_exc()
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
        # --- WeChat management POST routes ---
        elif self.path == "/api/wechat/qr_login":
            try:
                import urllib.request
                ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
                EP_GET_BOT_QR = "/ilink/bot/get_bot_qrcode"
                
                req = urllib.request.Request(f"{ILINK_BASE_URL}{EP_GET_BOT_QR}?bot_type=3")
                with urllib.request.urlopen(req, timeout=15) as response:
                    data = json.loads(response.read().decode('utf-8'))
                
                qrcode_value = data.get("qrcode")
                qrcode_url = data.get("qrcode_img_content", "")
                
                if not qrcode_value:
                    self._send_json({"error": "微信平台未返回二维码信息"}, 500)
                    return
                
                def poll_qr(q_val):
                    import time
                    timeout_seconds = 600
                    deadline = time.monotonic() + timeout_seconds
                    current_base_url = "https://ilinkai.weixin.qq.com"
                    while time.monotonic() < deadline:
                        try:
                            req_stat = urllib.request.Request(f"{current_base_url}/ilink/bot/get_qrcode_status?qrcode={q_val}")
                            with urllib.request.urlopen(req_stat, timeout=15) as resp_stat:
                                s_data = json.loads(resp_stat.read().decode('utf-8'))
                            
                            status = s_data.get("status", "wait")
                            if status == "scaned_but_redirect":
                                r_host = s_data.get("redirect_host", "")
                                if r_host: current_base_url = f"https://{r_host}"
                            elif status == "expired":
                                break
                            elif status == "confirmed":
                                acc_id = s_data.get("ilink_bot_id", "")
                                tk = s_data.get("bot_token", "")
                                b_url = s_data.get("baseurl", "https://ilinkai.weixin.qq.com")
                                u_id = s_data.get("ilink_user_id", "")
                                if acc_id and tk:
                                    save_env_config({
                                        "WXCLAW_TOKEN": f"{acc_id}:{tk}",
                                        "WXCLAW_BASE_URL": b_url,
                                        "WXCLAW_DEFAULT_TO": u_id
                                    })
                                break
                        except Exception:
                            pass
                        time.sleep(2)
                
                threading.Thread(target=poll_qr, args=(qrcode_value,), daemon=True).start()
                self._send_json({"url": qrcode_url or qrcode_value, "ok": True})
            except Exception as e:
                traceback.print_exc()
                self._send_json({"error": str(e)}, 500)

        elif self.path == "/api/wechat/config":
            try:
                req_json = json.loads(post_data.decode('utf-8'))
                
                update_dict = {}
                if "token" in req_json:
                    update_dict["WXCLAW_TOKEN"] = req_json.get("token", "").strip()
                if "base_url" in req_json:
                    update_dict["WXCLAW_BASE_URL"] = req_json.get("base_url", "https://ilinkai.weixin.qq.com").strip()
                if "push_rules" in req_json:
                    update_dict["WXCLAW_PUSH_RULES"] = req_json.get("push_rules", "").strip()
                if "push_approval" in req_json:
                    update_dict["WXCLAW_PUSH_ON_APPROVAL"] = "true" if req_json.get("push_approval") else "false"
                if "push_error" in req_json:
                    update_dict["WXCLAW_PUSH_ON_ERROR"] = "true" if req_json.get("push_error") else "false"
                if "push_success" in req_json:
                    update_dict["WXCLAW_PUSH_ON_SUCCESS"] = "true" if req_json.get("push_success") else "false"
                if "push_battery" in req_json:
                    update_dict["WXCLAW_PUSH_ON_BATTERY"] = "true" if req_json.get("push_battery") else "false"
                
                success = save_env_config(update_dict)
                
                self._send_json({"ok": success, "message": "配置保存成功" if success else "配置保存失败"})
            except Exception as e:
                traceback.print_exc()
                self._send_json({"ok": False, "message": str(e)}, 500)

        elif self.path == "/api/wechat/stop":
            try:
                # Simply clear configuration
                success = save_env_config({
                    "WXCLAW_TOKEN": "",
                    "WXCLAW_BASE_URL": ""
                })
                self._send_json({"ok": success, "message": "微信已断开并清除配置"})
            except Exception as e:
                traceback.print_exc()
                self._send_json({"ok": False, "message": str(e)}, 500)

        # --- Android Hardware API POST routes ---
        elif self.path == "/api/hardware/torch":
            try:
                req_json = json.loads(post_data.decode('utf-8'))
                status = req_json.get("status", "off")
                cmd = f"termux-torch {status}"
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
                self._send_json({"ok": res.returncode == 0 or True})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif self.path == "/api/hardware/vibrate":
            try:
                req_json = json.loads(post_data.decode('utf-8'))
                duration = req_json.get("duration", 200)
                cmd = f"termux-vibrate -d {duration}"
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
                self._send_json({"ok": res.returncode == 0 or True})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif self.path == "/api/system/command":
            try:
                req_json = json.loads(post_data.decode('utf-8'))
                cmd = req_json.get("cmd", "").strip()
                if not cmd:
                    self._send_json({"stdout": "", "stderr": "Error: Empty command"})
                else:
                    # 拦截并翻译 agy / antigravity 命令为完整的 Termux proot 物理执行链，解决 Alias 失效问题
                    termux_home = "/data/data/com.termux/files/home"
                    termux_usr = "/data/data/com.termux/files/usr"
                    
                    agy_real_command = (
                        "LANG=C.UTF-8 LANGUAGE=C.UTF-8 LC_ALL=C.UTF-8 "
                        f"proot -b {termux_usr}/etc/tls:/etc/ssl/certs "
                        f"-b {termux_usr}/etc/resolv.conf:/etc/resolv.conf "
                        f"-b {termux_usr}/etc/hosts:/etc/hosts "
                        f"-b {termux_home}/.local/glibc:/lib "
                        f"{termux_home}/.local/glibc/ld-linux-aarch64.so.1 {termux_home}/.local/bin/agy"
                    )
                    
                    if cmd == "agy":
                        cmd = agy_real_command
                    elif cmd.startswith("agy "):
                        cmd = agy_real_command + cmd[3:]
                    elif cmd == "antigravity":
                        cmd = agy_real_command
                    elif cmd.startswith("antigravity "):
                        cmd = agy_real_command + cmd[11:]
                        
                    env = os.environ.copy()
                    env["PATH"] = termux_usr + "/bin:" + env.get("PATH", "")
                    env["LD_LIBRARY_PATH"] = termux_usr + "/lib"
                    env["PYTHONHOME"] = termux_usr
                    env["HOME"] = termux_home
                    env["SHELL"] = termux_usr + "/bin/sh"
                    
                    res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30, env=env)
                    self._send_json({
                        "stdout": res.stdout,
                        "stderr": res.stderr
                    })
            except subprocess.TimeoutExpired:
                self._send_json({"stdout": "", "stderr": "Error: Command timed out after 30 seconds."})
            except Exception as e:
                self._send_json({"stdout": "", "stderr": f"Error executing command: {str(e)}"}, 500)

        elif self.path == "/api/hardware/clipboard":
            try:
                req_json = json.loads(post_data.decode('utf-8'))
                text = req_json.get("text", "")
                proc = subprocess.Popen(["termux-clipboard-set"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                stdout, stderr = proc.communicate(input=text, timeout=5)
                self._send_json({"ok": proc.returncode == 0 or True})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
 
        elif self.path == "/api/hardware/wake":
            try:
                SESSION["wake_event"] = True
                self._send_json({"ok": True})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif self.path == "/api/system/update":
            try:
                res = subprocess.run("git pull origin master", shell=True, capture_output=True, text=True, timeout=15)
                if res.returncode == 0:
                    self._send_json({"ok": True})
                    import threading
                    import sys
                    def exit_later():
                        time.sleep(1)
                        print("Updating server... exiting now to trigger auto-restart wrapper script.")
                        sys.exit(0)
                    threading.Thread(target=exit_later).start()
                else:
                    self._send_json({"ok": False, "error": res.stderr})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif self.path == "/api/system/tunnel":
            try:
                req_json = json.loads(post_data.decode('utf-8'))
                action = req_json.get("active", False)
                if action:
                    start_ssh_tunnel()
                else:
                    stop_ssh_tunnel()
                self._send_json({"ok": True})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif self.path == "/api/system/save_gemini_key":
            try:
                req_json = json.loads(post_data.decode('utf-8'))
                gemini_key = req_json.get("gemini_key", "").strip()
                ai_url = req_json.get("ai_url", "").strip()
                ai_key = req_json.get("ai_key", "").strip()
                ai_model = req_json.get("ai_model", "").strip()
                
                config_to_save = {}
                config_to_save["GEMINI_API_KEY"] = gemini_key
                if ai_url:
                    config_to_save["AI_URL"] = ai_url
                if ai_key:
                    config_to_save["AI_KEY"] = ai_key
                if ai_model:
                    config_to_save["AI_MODEL"] = ai_model
                    
                save_env_config(config_to_save)
                self._send_json({"status": "success"})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
                
        elif self.path == "/api/system/google_logout":
            try:
                save_env_config({
                    "GOOGLE_ACCESS_TOKEN": "",
                    "GOOGLE_REFRESH_TOKEN": ""
                })
                self._send_json({"status": "success"})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
                
        elif self.path == "/api/system/command":
            try:
                req_json = json.loads(post_data.decode('utf-8'))
                cmd = req_json.get("cmd", "").strip()
                if not cmd:
                    self._send_json({"error": "Empty command"}, 400)
                    return
                
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                self._send_json({
                    "exit_code": res.returncode,
                    "stdout": res.stdout,
                    "stderr": res.stderr
                })
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        else:
            self.send_response(404)
            self.end_headers()

def wechat_long_poll_daemon():
    import urllib.request
    import time
    
    sync_buf = ""
    consecutive_failures = 0
    
    while True:
        token_env = ENV_VARS.get("WXCLAW_TOKEN", "")
        base_url = ENV_VARS.get("WXCLAW_BASE_URL", "https://ilinkai.weixin.qq.com")
        
        if not token_env or ":" not in token_env:
            time.sleep(5)
            continue
            
        bot_id, bot_token = token_env.split(":", 1)
        
        try:
            req = urllib.request.Request(f"{base_url}/ilink/bot/getupdates")
            req.add_header("Authorization", f"Bearer {bot_token}")
            req.add_header("AuthorizationType", "ilink_bot_token")
            req.add_header("Content-Type", "application/json")
            
            payload = {"get_updates_buf": sync_buf}
            req.data = json.dumps(payload).encode('utf-8')
            
            with urllib.request.urlopen(req, timeout=35) as response:
                resp_data = json.loads(response.read().decode('utf-8'))
                
            ret = resp_data.get("ret", 0)
            if ret != 0:
                time.sleep(5)
                continue
                
            new_sync_buf = resp_data.get("get_updates_buf", "")
            if new_sync_buf:
                sync_buf = new_sync_buf
                
            msgs = resp_data.get("msgs", [])
            for msg in msgs:
                sender_id = msg.get("from_user_id", "")
                if sender_id and sender_id != bot_id:
                    # Avoid duplicated messages simply (wechat might send duplicates, a proper implementation would use message_id)
                    item_list = msg.get("item_list", [])
                    user_msg = ""
                    for item in item_list:
                        if "text_item" in item and "text" in item["text_item"]:
                            user_msg += item["text_item"]["text"]
                    
                    if user_msg:
                        context_token = msg.get("context_token", "")
                        print(f"\n[WeChat Daemon] Received from {sender_id}: {user_msg}")
                        # Process message asynchronously
                        threading.Thread(
                            target=lambda m=user_msg, s=sender_id, ctx=context_token: handle_async_wechat_msg(m, s, s, "", ctx),
                            daemon=True
                        ).start()
            
            consecutive_failures = 0
            # Wait a tiny bit before polling again
            time.sleep(1)
        except urllib.error.URLError as e:
            if isinstance(e.reason, socket.timeout):
                # Timeout is normal for long polling
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                time.sleep(min(30, 2 ** consecutive_failures))
        except Exception as e:
            consecutive_failures += 1
            time.sleep(min(30, 2 ** consecutive_failures))

# Start the polling daemon
threading.Thread(target=wechat_long_poll_daemon, daemon=True).start()

def battery_monitor_daemon():
    import time
    last_notified_time = 0
    
    while True:
        try:
            default_to = ENV_VARS.get("WXCLAW_DEFAULT_TO", "")
            is_battery_push_enabled = ENV_VARS.get("WXCLAW_PUSH_ON_BATTERY", "false") == "true"
            
            if default_to and is_battery_push_enabled:
                current_time = time.time()
                # Run at most once every 2 hours (7200 seconds) to avoid spamming
                if current_time - last_notified_time > 7200:
                    res = subprocess.run("termux-battery-status", shell=True, capture_output=True, text=True, timeout=5)
                    if res.returncode == 0:
                        bat_json = json.loads(res.stdout)
                        percentage = bat_json.get("percentage", 100)
                        status = bat_json.get("status", "DISCHARGING")
                        
                        if percentage <= 20 and "CHARGING" not in status:
                            warn_msg = f"🔋【系统低电量警报】\n\n当前手机设备电量仅为 {percentage}%，且处于未充电状态。为了避免智能体服务中断，请及时为手机充电！"
                            run_wxclawbot_send(default_to, warn_msg)
                            last_notified_time = current_time
        except Exception as e:
            print(f"Error in battery monitor daemon: {e}")
            
        time.sleep(300) # Check every 5 minutes

# Start the battery monitor daemon
threading.Thread(target=battery_monitor_daemon, daemon=True).start()

class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

def run_server():
    server_address = ('', PORT)
    httpd = ThreadingHTTPServer(server_address, AgentMVPHandler)
    print(f"==================================================")
    print(f"🚀 Micro-AGI MVP Server is running on port {PORT}")
    print(f"👉 Local URL: http://localhost:{PORT}")
    print(f"Press Ctrl+C to terminate.")
    print(f"==================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
