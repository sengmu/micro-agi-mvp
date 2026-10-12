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
import ipaddress
import mimetypes
import urllib.parse
import hmac
from http.cookies import SimpleCookie
from urllib import parse as urlparse
import sys
import tempfile
import db
import solana_watch

PORT = 8087
HOST = "127.0.0.1"
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
MAX_REQUEST_BYTES = 12 * 1024 * 1024
active_auth_process = None
EMBEDDED_SESSION_TOKEN = None
EMBEDDED_CSP = (
    "default-src 'self'; base-uri 'none'; object-src 'none'; frame-src 'none'; "
    "connect-src 'self'; img-src 'self' data: blob:; "
    "media-src 'self' data: blob:; font-src 'self' data:; "
    # The matching PIXI 5.3.12 patch replaces dynamic uniform-sync functions.
    # Cubism Core still needs permission to instantiate bundled WebAssembly.
    "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; "
    "form-action 'self'"
)


def embedded_mode():
    return os.environ.get("MICRO_AGI_EMBEDDED") == "1"


def set_embedded_session_token(token):
    """Called by the native host before starting the embedded HTTP server."""
    global EMBEDDED_SESSION_TOKEN
    if not embedded_mode() or not isinstance(token, str) or len(token) < 40:
        raise ValueError("Invalid embedded session token")
    EMBEDDED_SESSION_TOKEN = token


def embedded_health_proof():
    if not embedded_mode() or not EMBEDDED_SESSION_TOKEN:
        return ""
    return hmac.new(EMBEDDED_SESSION_TOKEN.encode("ascii"),
                    b"micro-agi-embedded-health-v1", "sha256").hexdigest()


EMBEDDED_BUNDLE_ASSETS = (
    "index.html", "style.css", "script.js", "solana-wallet.js",
    "pet.html", "manifest.json", "sw.js", "nami_render.png",
    "companion-room-night.png",
    "pixi.min.js", "pixi-unsafe-eval.min.js", "pixi-unsafe-eval.LICENSE",
    "live2dcubismcore.min.js", "pixi-live2d-display.min.js",
    "fonts/outfit.css", "fonts/QGYvz_MVcBeNP4NJuktqQ4E.woff2",
    "fonts/QGYvz_MVcBeNP4NJtEtq.woff2",
    "Hiyori/Hiyori.moc3", "Hiyori/Hiyori.cdi3.json",
    "Hiyori/Hiyori.2048/texture_00.png",
    "Hiyori/Hiyori.physics3.json", "Hiyori/Hiyori.model3.json",
    "Hiyori/motion/hiyori_m01.motion3.json",
    "Hiyori/motion/hiyori_m02.motion3.json",
    "Hiyori/motion/hiyori_m03.motion3.json",
    "Hiyori/motion/hiyori_m04.motion3.json",
    "Hiyori/motion/hiyori_m05.motion3.json",
    "Hiyori/motion/hiyori_m06.motion3.json",
    "Hiyori/motion/hiyori_m07.motion3.json",
    "Hiyori/motion/hiyori_m08.motion3.json",
)


def embedded_assets_ready():
    """Do not present an apparently healthy standalone app with missing UI files."""
    root = pathlib.Path(__file__).resolve().parent
    return all((root / relative).is_file() for relative in EMBEDDED_BUNDLE_ASSETS)


def gemini_visible_text(response):
    """Extract only answer text, never Gemini thought-summary parts."""
    try:
        parts = response["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return ""
    if not isinstance(parts, list):
        return ""
    return "".join(
        part["text"] for part in parts
        if isinstance(part, dict) and not part.get("thought")
        and isinstance(part.get("text"), str)
    )


def gemini_finished_normally(response):
    """Gemini omits finishReason while generation is still in progress."""
    try:
        return response["candidates"][0]["finishReason"] == "STOP"
    except (KeyError, IndexError, TypeError):
        return False


MAX_LLM_RESPONSE_BYTES = 4 * 1024 * 1024


def read_llm_response(response):
    raw = response.read(MAX_LLM_RESPONSE_BYTES + 1)
    if len(raw) > MAX_LLM_RESPONSE_BYTES:
        raise RuntimeError("Model response exceeded size limit")
    return raw.decode("utf-8", errors="ignore")

# 1. Load config from local env
def load_env() -> dict:
    out = {}
    # Project defaults < legacy Termux config < app-managed config < process env.
    for env_path in (
        pathlib.Path(__file__).resolve().parent / ".env",
        pathlib.Path.home() / "micro-agi-mvp" / ".env",
        pathlib.Path.home() / ".config" / "gmgn" / ".env",
    ):
        try:
            content = env_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in content.splitlines():
            if "=" not in line or line.strip().startswith("#"):
                continue
            k, v = line.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
                v = v[1:-1]
            out[k.strip()] = v.replace("\\n", "\n")
    out.update(os.environ)
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
    
    proxy_url = ENV_VARS.get("PROXY_URL", "")
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
    
    # 支持本地自定义 Antigravity CLI (agy) 大模型引擎后端
    llm_backend = ENV_VARS.get("LLM_BACKEND", "gemini").lower()
    
    if llm_backend == "agy":
        if embedded_mode():
            raise RuntimeError("Antigravity CLI requires Termux and is unavailable in the standalone Android app. Configure an API key instead.")
        user_prompt = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_prompt = msg.get("content", "")
                break
        if not user_prompt:
            return "Error: No user message found in chat history."
            
        if isinstance(user_prompt, list):
            for item in user_prompt:
                if isinstance(item, dict) and item.get("type") == "text":
                    user_prompt = item.get("text", "")
                    break
                    
        termux_home = "/data/data/com.termux/files/home"
        termux_usr = "/data/data/com.termux/files/usr"
        escaped_prompt = user_prompt.replace("'", "'\\''")
        is_termux = os.path.exists("/data/data/com.termux")
        
        if is_termux:
            cmd_str = (
                "LANG=C.UTF-8 LANGUAGE=C.UTF-8 LC_ALL=C.UTF-8 "
                f"proot -b {termux_usr}/etc/tls:/etc/ssl/certs "
                f"-b {termux_usr}/etc/resolv.conf:/etc/resolv.conf "
                f"-b {termux_usr}/etc/hosts:/etc/hosts "
                f"-b {termux_home}/.local/glibc:/lib "
                f"{termux_home}/.local/glibc/ld-linux-aarch64.so.1 {termux_home}/.local/bin/agy "
                f"--prompt '{escaped_prompt}'"
            )
            env = os.environ.copy()
            env["PATH"] = termux_usr + "/bin:" + env.get("PATH", "")
            env["LD_LIBRARY_PATH"] = termux_usr + "/lib"
            env["PYTHONHOME"] = termux_usr
            env["HOME"] = termux_home
        else:
            cmd_str = f"agy --prompt '{escaped_prompt}'"
            env = os.environ.copy()
            
        try:
            print(f"[LLM-AGY] Executing prompt: {user_prompt[:50]}...")
            res = subprocess.run(
                cmd_str,
                shell=True,
                capture_output=True,
                text=True,
                env=env,
                timeout=60
            )
            if res.returncode == 0:
                output = res.stdout.strip()
                if "Welcome to the Antigravity CLI" in output:
                    parts = output.split("--------------------------------------------------")
                    if len(parts) > 1:
                        output = parts[-1].strip()
                return output
            else:
                return f"Error executing agy: {res.stderr.strip()}"
        except Exception as e:
            return f"Exception executing agy: {str(e)}"

    gemini_key = ENV_VARS.get("GEMINI_API_KEY")
    google_token = ENV_VARS.get("GOOGLE_ACCESS_TOKEN")
    
    # If no GEMINI_API_KEY or GOOGLE_ACCESS_TOKEN config, check AI_URL/AI_KEY fallback
    if not gemini_key and not google_token:
        ai_url = ENV_VARS.get("AI_URL", "")
        if "generativelanguage.googleapis.com" in ai_url or "gemini" in ai_url.lower():
            gemini_key = ENV_VARS.get("AI_KEY")
            
    proxy_url = ENV_VARS.get("PROXY_URL", "")
    use_google_api = bool(gemini_key or google_token)
    
    if use_google_api:
        # 1. Google Gemini official REST API
        model_name = ENV_VARS.get("AI_MODEL", DEFAULT_GEMINI_MODEL)
        if "/" in model_name:
            model_name = model_name.split("/")[-1]
            
        if gemini_key:
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
            headers = {"Content-Type": "application/json", "x-goog-api-key": gemini_key}
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
        ai_url = ENV_VARS.get("AI_URL", "")
        ai_key = ENV_VARS.get("AI_KEY", "")
        ai_model = ENV_VARS.get("AI_MODEL", "")
        if not ai_url or not ai_model:
            raise RuntimeError("Configure AI_URL and AI_MODEL before chatting")
        
        api_url = ai_url
        if api_url and not api_url.endswith("/chat/completions"):
            api_url = api_url.rstrip("/") + "/chat/completions"

        headers = {"Content-Type": "application/json"}
        if ai_key:
            headers["Authorization"] = f"Bearer {ai_key}"
        payload = {
            "model": ai_model,
            "messages": messages,
            "temperature": 0.3
        }
        data = json.dumps(payload).encode("utf-8")

    def is_local_url(target_url: str) -> bool:
        return "localhost" in target_url or "127.0.0.1" in target_url

    # Internal helper to handle requests and refresh token if 401/403 is hit
    def do_request(url, payload_data, req_headers):
        if proxy_url and not is_local_url(url):
            proxy_handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
            opener = urllib.request.build_opener(proxy_handler)
        else:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            
        req = urllib.request.Request(url, data=payload_data, headers=req_headers, method="POST")
        try:
            with opener.open(req, timeout=30) as response:
                res_data = read_llm_response(response)
                res_json = json.loads(res_data)
                
                if use_google_api:
                    try:
                        if not gemini_finished_normally(res_json):
                            raise ValueError("Gemini generation did not finish normally")
                        answer = gemini_visible_text(res_json)
                        if not answer:
                            raise ValueError("Gemini returned no user-visible text")
                        return answer
                    except Exception as e_parse:
                        print(f"Gemini API parse failed: {e_parse}")
                        raise e_parse
                else:
                    if "choices" in res_json and len(res_json["choices"]) > 0:
                        return res_json["choices"][0]["message"]["content"]
                    else:
                        raise RuntimeError(f"Unexpected LLM response format: {res_data}")
        except Exception as e:
            is_429 = "429" in str(e) or "Resource has been exhausted" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
            is_timeout = "timed out" in str(e).lower() or "timeout" in str(e).lower()
            is_auth_error = False
            if isinstance(e, urllib.error.HTTPError):
                if e.code in (401, 403):
                    is_auth_error = True
                elif e.code == 429:
                    is_429 = True
            
            if is_auth_error and not gemini_key and google_token and ENV_VARS.get("GOOGLE_REFRESH_TOKEN"):
                print("Access Token expired (401/403). Trying to refresh google token...")
                new_token = refresh_google_token()
                if new_token:
                    req_headers["Authorization"] = f"Bearer {new_token}"
                    print("Retrying API call with newly refreshed token...")
                    return do_request(url, payload_data, req_headers)

            if gemini_key:
                # A timed-out generation may already have consumed the user's quota.
                # Do not silently issue the same billable request again.
                if is_429:
                    raise RuntimeError("Gemini API 已限流或额度不足；请检查此 Key 的配额后手动重试。") from None
                if is_timeout:
                    raise RuntimeError("Gemini 请求超时，服务端可能已处理；请稍后手动重试。") from None
                raise RuntimeError("Gemini 请求失败；请检查 API Key、模型权限和网络连接。") from None
            
            if is_429 or is_timeout:
                raise RuntimeError("模型服务限流或请求超时；请检查配额并手动重试。") from None

            print(f"LLM API request failed: {e}")
            if proxy_url:
                print("Retrying API call without proxy...")
                try:
                    opener_no_proxy = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    with opener_no_proxy.open(req, timeout=30) as response:
                        res_data = read_llm_response(response)
                        res_json = json.loads(res_data)
                        if use_google_api:
                            if not gemini_finished_normally(res_json):
                                raise ValueError("Gemini generation did not finish normally")
                            answer = gemini_visible_text(res_json)
                            if not answer:
                                raise ValueError("Gemini returned no user-visible text")
                            return answer
                        else:
                            return res_json["choices"][0]["message"]["content"]
                except Exception as e2:
                    print(f"Fallback call failed: {e2}")
            raise e

    return do_request(api_url, data, headers)


def _llm_route_setup(messages: list):
    """Resolve backend route: returns dict with mode, url, headers, payload, proxy_url, use_google."""
    global ENV_VARS
    ENV_VARS = load_env()
    llm_backend = ENV_VARS.get("LLM_BACKEND", "gemini").lower()
    proxy_url = ENV_VARS.get("PROXY_URL", "")

    if llm_backend == "agy":
        if embedded_mode():
            raise RuntimeError("Antigravity CLI requires Termux and is unavailable in the standalone Android app. Configure an API key instead.")
        return {"mode": "agy", "proxy_url": proxy_url}

    gemini_key = ENV_VARS.get("GEMINI_API_KEY")
    google_token = ENV_VARS.get("GOOGLE_ACCESS_TOKEN")
    if not gemini_key and not google_token:
        ai_url = ENV_VARS.get("AI_URL", "")
        if "generativelanguage.googleapis.com" in ai_url or "gemini" in ai_url.lower():
            gemini_key = ENV_VARS.get("AI_KEY")
    use_google_api = bool(gemini_key or google_token)

    if use_google_api:
        model_name = ENV_VARS.get("AI_MODEL", DEFAULT_GEMINI_MODEL)
        if "/" in model_name:
            model_name = model_name.split("/")[-1]
        if gemini_key:
            api_url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model_name}:streamGenerateContent?alt=sse"
            )
            headers = {"Content-Type": "application/json", "x-goog-api-key": gemini_key}
        else:
            api_url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model_name}:streamGenerateContent?alt=sse"
            )
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {google_token}",
            }
        contents = []
        system_instruction = ""
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "system":
                system_instruction = content if isinstance(content, str) else str(content)
            elif role == "user":
                if isinstance(content, list):
                    # flatten multimodal to text for stream path; vision still via non-stream if needed
                    texts = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            texts.append(item.get("text", ""))
                        elif isinstance(item, dict) and item.get("type") == "image_url":
                            texts.append("[image attached]")
                    content = "\n".join(texts)
                contents.append({"role": "user", "parts": [{"text": str(content)}]})
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": str(content)}]})
        payload = {"contents": contents, "generationConfig": {"temperature": 0.3}}
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        return {
            "mode": "gemini_stream",
            "api_url": api_url,
            "headers": headers,
            "payload": payload,
            "proxy_url": proxy_url,
            "google_token": google_token,
        }

    ai_url = ENV_VARS.get("AI_URL", "")
    ai_key = ENV_VARS.get("AI_KEY", "")
    ai_model = ENV_VARS.get("AI_MODEL", "")
    if not ai_url or not ai_model:
        raise RuntimeError("Configure AI_URL and AI_MODEL before chatting")
    api_url = ai_url
    if api_url and not api_url.endswith("/chat/completions"):
        api_url = api_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if ai_key:
        headers["Authorization"] = f"Bearer {ai_key}"
    # OpenAI-compatible: normalize multimodal messages if list content
    norm_messages = []
    for msg in messages:
        m = dict(msg)
        c = m.get("content")
        if isinstance(c, list):
            # keep list for vision-capable OpenAI endpoints
            m["content"] = c
        norm_messages.append(m)
    payload = {
        "model": ai_model,
        "messages": norm_messages,
        "temperature": 0.3,
        "stream": True,
    }
    return {
        "mode": "openai_stream",
        "api_url": api_url,
        "headers": headers,
        "payload": payload,
        "proxy_url": proxy_url,
    }


def call_llm_stream(messages: list):
    """
    Yield text chunks from the LLM. Non-stream backends (agy) yield a single chunk.
    OpenAI-compatible streams may fall back to call_llm() before any text is sent.
    """
    setup = _llm_route_setup(messages)
    mode = setup.get("mode")

    if mode == "agy":
        text = call_llm(messages)
        if text:
            yield text
        return

    proxy_url = setup.get("proxy_url") or ""
    api_url = setup["api_url"]
    headers = setup["headers"]
    data = json.dumps(setup["payload"]).encode("utf-8")

    def open_stream(url, req_headers, use_proxy=True):
        if use_proxy and proxy_url and not ("localhost" in url or "127.0.0.1" in url):
            proxy_handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
            opener = urllib.request.build_opener(proxy_handler)
        else:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
        return opener.open(req, timeout=90)

    yielded = False
    gemini_finished = False
    received_bytes = 0

    def read_stream_line(response):
        nonlocal received_bytes
        line = response.readline(MAX_LLM_RESPONSE_BYTES + 1)
        received_bytes += len(line)
        if received_bytes > MAX_LLM_RESPONSE_BYTES:
            raise RuntimeError("Model stream exceeded response limit")
        return line

    try:
        try:
            resp = open_stream(api_url, headers, use_proxy=True)
        except Exception as e1:
            # retry without proxy
            if proxy_url and mode != "gemini_stream":
                print(f"[LLM-STREAM] proxy failed ({e1}), retry direct...")
                resp = open_stream(api_url, headers, use_proxy=False)
            else:
                raise e1

        ctype = (resp.headers.get("Content-Type") or "").lower()
        # Some backends ignore stream=true and return a full JSON body
        if "application/json" in ctype and "event-stream" not in ctype:
            with resp:
                raw = read_llm_response(resp)
            obj = json.loads(raw)
            if mode == "gemini_stream":
                if not gemini_finished_normally(obj):
                    raise RuntimeError("Gemini generation did not finish normally")
                text = gemini_visible_text(obj)
            else:
                text = obj["choices"][0]["message"]["content"]
            if text:
                yielded = True
                yield text
            if not yielded:
                raise RuntimeError("Empty JSON completion from LLM")
            return

        with resp:
            if mode == "openai_stream":
                while True:
                    line = read_stream_line(resp)
                    if not line:
                        break
                    line = line.strip()
                    if not line or not line.startswith(b"data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == b"[DONE]":
                        if not yielded:
                            break
                        return
                    try:
                        obj = json.loads(payload.decode("utf-8", errors="ignore"))
                    except Exception:
                        continue
                    try:
                        delta = obj["choices"][0].get("delta") or {}
                        piece = delta.get("content") or ""
                        if piece:
                            yielded = True
                            yield piece
                    except Exception:
                        try:
                            piece = obj["choices"][0]["message"]["content"]
                            if piece:
                                yielded = True
                                yield piece
                        except Exception:
                            # surface API error objects
                            err = obj.get("error") or obj.get("detail")
                            if err:
                                raise RuntimeError(str(err))
            elif mode == "gemini_stream":
                while True:
                    line = read_stream_line(resp)
                    if not line:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith(b"data:"):
                        line = line[5:].strip()
                    try:
                        obj = json.loads(line.decode("utf-8", errors="ignore"))
                    except Exception:
                        continue
                    if obj.get("error"):
                        raise RuntimeError("Gemini stream reported an error")
                    candidates = obj.get("candidates") or []
                    finish_reason = candidates[0].get("finishReason") if candidates else None
                    text = gemini_visible_text(obj)
                    if text:
                        yielded = True
                        yield text
                    if finish_reason:
                        if finish_reason != "STOP":
                            raise RuntimeError("Gemini stream did not complete normally")
                        gemini_finished = True
                        break
        if mode == "gemini_stream" and not gemini_finished:
            raise RuntimeError("Gemini stream ended without a finish reason")
        if not yielded:
            raise RuntimeError("LLM stream ended with no content")
    except Exception as e:
        if mode == "gemini_stream" or yielded:
            raise RuntimeError(
                "模型流式请求中断，服务端可能已处理；请手动重试。") from None
        print(f"[LLM-STREAM] failed, fallback to non-stream: {e}")
        try:
            text = call_llm(messages)
            if text:
                yield text
            else:
                raise RuntimeError(f"Stream failed ({e}) and non-stream empty")
        except Exception as e2:
            raise RuntimeError(f"LLM unavailable: {e2}")


def process_next_llm_step_stream(session):
    """
    Generator of SSE event dicts:
      {"type":"token","text":...}
      {"type":"done", status, response/command/thoughts, steps, node_id?}
      {"type":"error","error":...}
    """
    collected = []
    try:
        for piece in call_llm_stream(session["messages"]):
            if not piece:
                continue
            collected.append(piece)
            yield {"type": "token", "text": piece}
    except Exception:
        session["is_waiting"] = False
        yield {
            # A failed generation is not a completed assistant answer. In
            # particular, the HTTP layer must not persist it as chat history.
            "type": "error",
            "error": "模型请求未完成；请检查网络与 API 配置后手动重试。",
        }
        return

    ai_content = "".join(collected)
    if not ai_content.strip():
        ai_content = "（模型未返回内容）"

    ai_content = strip_embedded_execute(ai_content)
    session["messages"].append({"role": "assistant", "content": ai_content})
    cmd = extract_execute_cmd(ai_content)
    thoughts = get_thoughts(ai_content)

    if cmd:
        session["is_waiting"] = True
        session["current_command"] = cmd
        default_to = ENV_VARS.get("WXCLAW_DEFAULT_TO", "")
        if default_to and ENV_VARS.get("WXCLAW_PUSH_ON_APPROVAL") == "true":
            push_msg = (
                f"🔔【智能体审批申请】\nHiyori 申请在 Termux 运行以下命令：\n\n"
                f"```bash\n{cmd}\n```\n\n你可以前往网页端面板审批。"
            )
            threading.Thread(
                target=run_wxclawbot_send, args=(default_to, push_msg), daemon=True
            ).start()
        yield {
            "type": "done",
            "status": "waiting_approval",
            "command": cmd,
            "thoughts": thoughts,
            "steps": session["steps"],
            "response": ai_content,
        }
    else:
        session["is_waiting"] = False
        node_id = extract_and_save_artifacts(
            ai_content, session.get("project_id", ""), session.get("chat_id", "")
        )
        yield {
            "type": "done",
            "status": "completed",
            "response": ai_content,
            "steps": session["steps"],
            "node_id": node_id,
        }


def start_agent_run_stream(user_message: str, chat_history: list, project_id: str = "", chat_id: str = ""):
    session = get_web_session(chat_id)
    messages = [{"role": "system", "content": get_system_prompt()}]
    for msg in chat_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})
    with session["lock"]:
        session["messages"] = messages
        session["steps"] = []
        session["current_command"] = ""
        session["is_waiting"] = False
        session["project_id"] = project_id
        session["chat_id"] = chat_id
        yield from process_next_llm_step_stream(session)


def resume_agent_run_stream(approved: bool, edited_command: str = "", chat_id: str = ""):
    """Run command (if approved), then stream next LLM step."""
    session = find_web_session(chat_id)
    if not session:
        yield {"type": "error", "error": "No active session waiting for approval"}
        return
    with session["lock"]:
        yield from _resume_agent_run_stream_locked(session, approved, edited_command)


def _resume_agent_run_stream_locked(session, approved, edited_command):
    if not session["is_waiting"]:
        yield {"type": "error", "error": "No active session waiting for approval"}
        return

    cmd_to_run = edited_command if edited_command else session["current_command"]
    blocked_in_embedded = approved and embedded_mode()
    if blocked_in_embedded:
        approved = False

    if approved:
        print(f"Running approved command: {cmd_to_run}")
        try:
            res = subprocess.run(
                cmd_to_run,
                shell=True,
                capture_output=True,
                text=True,
                timeout=20,
                cwd=str(pathlib.Path.home()),
            )
            stdout = res.stdout
            stderr = res.stderr
            exit_code = res.returncode
        except subprocess.TimeoutExpired:
            stdout, stderr, exit_code = "", "Command execution timed out after 20 seconds.", -1
        except Exception as e:
            stdout, stderr, exit_code = "", f"Execution error: {e}", -2

        output_summary = stdout + stderr
        if not output_summary.strip():
            output_summary = "[Command completed with no output]"

        session["steps"].append({
            "command": cmd_to_run,
            "output": output_summary,
            "exit_code": exit_code,
        })
        yield {
            "type": "step",
            "command": cmd_to_run,
            "output": output_summary,
            "exit_code": exit_code,
        }
        result_message = f"[Command execution result]\nExit Code: {exit_code}\nOutput:\n{output_summary}"
    else:
        reason = ("Command execution unavailable in standalone Android app."
                  if blocked_in_embedded else "Execution denied by user.")
        print(reason)
        result_message = (f"[{reason}]" if blocked_in_embedded
                          else "[Command execution denied by user]")
        session["steps"].append({
            "command": cmd_to_run,
            "output": reason,
            "exit_code": -3,
        })
        yield {
            "type": "step",
            "command": cmd_to_run,
            "output": reason,
            "exit_code": -3,
        }

    session["messages"].append({"role": "user", "content": result_message})
    session["is_waiting"] = False
    session["current_command"] = ""
    yield from process_next_llm_step_stream(session)


# 3. System Prompt explaining tools, security, and Android environment capabilities
def get_system_prompt():
    if embedded_mode():
        return ("You are Hiyori, a helpful AI assistant inside a standalone Android app. "
                "You have no shell, Termux, system-command, or wallet-signing tools. "
                "Never request command execution or claim to run commands. "
                "A Solana wallet can only be connected in the separate native wallet screen "
                "after the user confirms in their wallet. Do not request seed phrases or private keys.")
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
    # 长期记忆注入（本地）
    try:
        mem_block = db.memory_prompt_block(limit=24)
        if mem_block:
            base += "\n\n" + mem_block + "\n"
            base += "If the user says 记住：... you should acknowledge and the system will store it.\n"
    except Exception:
        pass
    base += """
AI PHONE ENTRY:
- You are the central AI of this Android phone (Micro-AGI / 日和).
- Prefer concise actionable answers. For proactive digests the system may push notifications.
"""
    return base

# Wake notification is global; agent runs and approvals are scoped by chat ID.
SESSION = {"wake_event": False}
WEB_SESSIONS = {}
WEB_SESSIONS_LOCK = threading.Lock()


def get_web_session(chat_id):
    if not chat_id:
        raise ValueError("chat_id is required")
    with WEB_SESSIONS_LOCK:
        if chat_id not in WEB_SESSIONS:
            WEB_SESSIONS[chat_id] = {
                "lock": threading.RLock(),
                "is_waiting": False,
                "messages": [],
                "current_command": "",
                "steps": [],
                "project_id": "",
                "chat_id": chat_id,
            }
        return WEB_SESSIONS[chat_id]


def find_web_session(chat_id):
    if not chat_id:
        return None
    with WEB_SESSIONS_LOCK:
        return WEB_SESSIONS.get(chat_id)

def extract_execute_cmd(ai_content: str) -> str:
    if "<execute>" in ai_content and "</execute>" in ai_content:
        start_idx = ai_content.find("<execute>") + len("<execute>")
        end_idx = ai_content.find("</execute>")
        return ai_content[start_idx:end_idx].strip()
    return ""

def strip_embedded_execute(ai_content: str) -> str:
    """Never offer a command-approval flow in the standalone Android app."""
    if not embedded_mode() or not extract_execute_cmd(ai_content):
        return ai_content
    visible = re.sub(r"<execute>.*?</execute>", "", ai_content, flags=re.DOTALL).strip()
    notice = "（独立版不支持命令执行；本次未执行任何命令。）"
    return f"{visible}\n\n{notice}" if visible else notice

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
    important_langs = {
        "html", "htm", "python", "py", "javascript", "js", "typescript", "ts",
        "css", "vue", "react", "jsx", "tsx", "json", "bash", "sh", "sql",
        "markdown", "md", "yaml", "yml", "go", "rust", "java", "kotlin",
    }

    # 1. Extract code blocks (more permissive so short useful snippets are kept)
    code_pattern = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)
    for match in code_pattern.finditer(ai_content):
        lang = (match.group(1) or "text").strip().lower()
        code_content = match.group(2).strip()
        if not code_content:
            continue
        # Keep short blocks for important langs; skip tiny noise for plain text
        if lang in important_langs:
            if len(code_content) < 12:
                continue
        elif len(code_content) < 40:
            continue

        lang_label = lang.upper() if len(lang) <= 4 else lang.capitalize()
        line_count = code_content.count("\n") + 1
        title = f"{lang_label} · {line_count} 行"
        prefix_text = ai_content[:match.start()].strip()
        lines = [ln.strip() for ln in prefix_text.split("\n") if ln.strip()]
        if lines:
            last_line = re.sub(r"^[#>*\-\d\.\s]+", "", lines[-1]).strip()
            if 2 < len(last_line) <= 40:
                title = f"{last_line} ({lang_label})"

        preview = code_content[:140].replace("\n", " ")
        if len(code_content) > 140:
            preview += "…"
        db.create_artifact(
            project_id=project_id,
            chat_id=chat_id,
            node_id=node_id,
            title=title or "Code Snippet",
            type_enum="code",
            content_url=code_content,
            preview_text=preview,
            key_prompt=lang,
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
            preview_text="图片素材 / 外链预览",
            key_prompt=""
        )
        
    return node_id

# Start a new Agent conversation run
def start_agent_run(user_message: str, chat_history: list, project_id: str = "", chat_id: str = "") -> dict:
    session = get_web_session(chat_id)
    messages = [{"role": "system", "content": get_system_prompt()}]
    for msg in chat_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    with session["lock"]:
        session["messages"] = messages
        session["steps"] = []
        session["current_command"] = ""
        session["is_waiting"] = False
        session["project_id"] = project_id
        session["chat_id"] = chat_id
        return process_next_llm_step(session)

# Execute LLM step and check for tools
def process_next_llm_step(session) -> dict:
    try:
        ai_content = call_llm(session["messages"])
    except Exception:
        session["is_waiting"] = False
        return {
            "status": "error",
            "error": "模型请求未完成；请检查网络与 API 配置后手动重试。",
            "steps": session["steps"]
        }

    ai_content = strip_embedded_execute(ai_content)
    session["messages"].append({"role": "assistant", "content": ai_content})
    cmd = extract_execute_cmd(ai_content)
    thoughts = get_thoughts(ai_content)

    if cmd:
        session["is_waiting"] = True
        session["current_command"] = cmd
        
        # WeChat Push on Approval Request
        default_to = ENV_VARS.get("WXCLAW_DEFAULT_TO", "")
        if default_to and ENV_VARS.get("WXCLAW_PUSH_ON_APPROVAL") == "true":
            push_msg = f"🔔【智能体审批申请】\nHiyori 申请在 Termux 运行以下命令：\n\n```bash\n{cmd}\n```\n\n请前往对应网页对话审批。"
            threading.Thread(
                target=run_wxclawbot_send,
                args=(default_to, push_msg),
                daemon=True
            ).start()
            
        return {
            "status": "waiting_approval",
            "command": cmd,
            "thoughts": thoughts,
            "steps": session["steps"]
        }
    else:
        session["is_waiting"] = False
        # Intercept and extract artifacts!
        node_id = extract_and_save_artifacts(ai_content, session.get("project_id", ""), session.get("chat_id", ""))
        
        return {
            "status": "completed",
            "response": ai_content,
            "steps": session["steps"],
            "node_id": node_id
        }

# Process command approval decision
def resume_agent_run(approved: bool, edited_command: str = "", chat_id: str = "") -> dict:
    session = find_web_session(chat_id)
    if not session:
        return {"error": "No active session waiting for approval"}
    with session["lock"]:
        return _resume_agent_run_locked(session, approved, edited_command)


def _resume_agent_run_locked(session, approved, edited_command):
    if not session["is_waiting"]:
        return {"error": "No active session waiting for approval"}

    cmd_to_run = edited_command if edited_command else session["current_command"]
    blocked_in_embedded = approved and embedded_mode()
    if blocked_in_embedded:
        approved = False

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

        session["steps"].append({
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
        reason = ("Command execution unavailable in standalone Android app."
                  if blocked_in_embedded else "Execution denied by user.")
        print(reason)
        result_message = (f"[{reason}]" if blocked_in_embedded
                          else "[Command execution denied by user]")
        session["steps"].append({
            "command": cmd_to_run,
            "output": reason,
            "exit_code": -3
        })

    # Append command result message from the "user" role to keep LLM context
    session["messages"].append({"role": "user", "content": result_message})
    session["is_waiting"] = False
    session["current_command"] = ""

    # Run next step
    return process_next_llm_step(session)


# === WeChat AI Assistant Integration Helpers ===
WECHAT_SESSIONS = {}
WECHAT_MESSAGE_LOCK = threading.Lock()
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
        if embedded_mode() or ENV_VARS.get("ENABLE_WECHAT_SYSTEM_COMMANDS", "false").lower() != "true":
            session["is_waiting_approval"] = False
            session["current_command"] = ""
            return "微信终端命令功能未开启，请在本机网页中完成此操作。"
        session["is_waiting_approval"] = True
        session["current_command"] = cmd
        
        prompt_msg = ""
        if thoughts:
            prompt_msg += f"{thoughts}\n\n"
        prompt_msg += f"🤖 Hiyori 想要运行以下 Termux 命令，请回复【确认】以批准，或【拒绝】以拒绝。其他回复不会执行命令：\n\n```bash\n{cmd}\n```"
        return prompt_msg
    else:
        return ai_content

def run_wechat_command(cmd_to_run, session):
    if embedded_mode() or ENV_VARS.get("ENABLE_WECHAT_SYSTEM_COMMANDS", "false").lower() != "true":
        return "[WeChat command execution disabled]"
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
    temp_path = None
    try:
        if not isinstance(config, dict) or any(
            not isinstance(k, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", k)
            or not isinstance(v, str) or any(c in v for c in "\r\n\0")
            for k, v in config.items()
        ):
            return False
        env_dir = pathlib.Path.home() / ".config" / "gmgn"
        env_dir.mkdir(parents=True, exist_ok=True)
        env_path = env_dir / ".env"
        lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
        env_dict = {}
        for line in lines:
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env_dict[k.strip()] = v.strip()
        for k, v in config.items():
            env_dict[k] = f'"{v}"' if v else ""
        out_lines = [f"{k}={v}" for k, v in env_dict.items() if v]
        fd, temp_name = tempfile.mkstemp(prefix=".env-", dir=env_dir)
        temp_path = pathlib.Path(temp_name)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write("\n".join(out_lines) + "\n")
        os.replace(temp_path, env_path)
        temp_path = None
        # Reload global vars
        global ENV_VARS
        ENV_VARS = load_env()
        return True
    except Exception as e:
        print(f"Error saving config to env: {e}")
        return False
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

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

    if cmd_name in ("/cmd", "/restart") and ENV_VARS.get("ENABLE_WECHAT_SYSTEM_COMMANDS", "false").lower() != "true":
        run_wxclawbot_send(sender_id, "微信终端命令功能未开启。", context_token)
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
        if embedded_mode():
            run_wxclawbot_send(sender_id, "独立 Android 版本不支持终端命令。", context_token)
            return True
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
    # Long-polling dispatches each message on a new thread. Serialize approval
    # decisions so two confirmations cannot execute the same command twice.
    with WECHAT_MESSAGE_LOCK:
        return _handle_async_wechat_msg_locked(user_msg, sender_id, sender_name, to_user_name, context_token)


def _handle_async_wechat_msg_locked(user_msg, sender_id, sender_name, to_user_name, context_token=""):
    # First-sender binding is opt-in; otherwise untrusted senders cannot gain control.
    if sender_id and not ENV_VARS.get("WXCLAW_DEFAULT_TO") and ENV_VARS.get("WXCLAW_ALLOW_FIRST_SENDER_BIND", "false").lower() == "true":
        print(f"Auto-binding {sender_id} as WXCLAW_DEFAULT_TO in env")
        save_env_config({
            "WXCLAW_DEFAULT_TO": sender_id,
            "WXCLAW_ALLOW_FIRST_SENDER_BIND": "false",
        })
    if not sender_id or sender_id != ENV_VARS.get("WXCLAW_DEFAULT_TO"):
        print("Ignoring WeChat message from an unbound sender")
        return

    # WeChat Remote Command Interception
    msg_strip = user_msg.strip()
    is_cmd = msg_strip.startswith("/") or msg_strip == "菜单"
    if is_cmd:
        if handle_wechat_remote_control(user_msg, sender_id, context_token):
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
    approval_words = ("确认", "批准", "确定", "y", "yes", "Y", "批准指令")
    rejection_words = ("拒绝", "不", "no", "n", "N", "拒绝指令")
    if session["is_waiting_approval"]:
        if msg_strip in approval_words:
            cmd_to_run = session["current_command"]
            session["is_waiting_approval"] = False
            session["current_command"] = ""
            # Execute command
            result_str = run_wechat_command(cmd_to_run, session)
            # Resume LLM processing
            reply = run_wechat_agent_step(result_str, session)
        elif msg_strip in rejection_words:
            session["is_waiting_approval"] = False
            session["current_command"] = ""
            reply = run_wechat_agent_step("[Command execution denied by user]", session)
        else:
            reply = "仍在等待命令审批。请回复【确认】或【拒绝】；其他回复不会执行命令。"
    else:
        if msg_strip in approval_words or msg_strip in rejection_words:
            reply = "当前没有待审批命令。"
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
class AgentMVPHandler(http.server.BaseHTTPRequestHandler):
    PUBLIC_ASSETS = {
        "/pet.html", "/fonts/outfit.css", "/nami_render.png",
        "/companion-room-night.png",
    }

    def log_message(self, format, *args):
        pass

    def _reject_request(self, data, status, mutation):
        # On Windows, closing a POST socket with an unread small body can send
        # RST before the client receives our JSON denial. Drain only a bounded
        # body with a short timeout; never let an unauthenticated large upload
        # occupy a request thread just to produce an error response.
        if mutation:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if 0 < length <= 4096 and not self.headers.get("Transfer-Encoding"):
                old_timeout = self.connection.gettimeout()
                try:
                    self.connection.settimeout(1)
                    self.rfile.read(length)
                except (OSError, TimeoutError):
                    pass
                finally:
                    self.connection.settimeout(old_timeout)
            self.close_connection = True
        self._send_json(data, status)

    def _request_allowed(self, mutation=False):
        try:
            peer = ipaddress.ip_address(self.client_address[0])
            if not peer.is_loopback:
                self._reject_request({"error": "Local access only"}, 403, mutation)
                return False
        except ValueError:
            self._reject_request({"error": "Invalid client address"}, 403, mutation)
            return False

        host = self.headers.get("Host", "").lower()
        if host and host.split(":", 1)[0] not in ("localhost", "127.0.0.1", "[::1]"):
            self._reject_request({"error": "Invalid host"}, 403, mutation)
            return False
        request_path = self.path.split("?", 1)[0]
        api_request = request_path.startswith("/api/")
        if api_request and request_path != "/api/health" and embedded_mode():
            if not EMBEDDED_SESSION_TOKEN:
                self._reject_request({"error": "Embedded session unavailable"}, 503, mutation)
                return False
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get("Cookie", ""))
                submitted = cookie.get("magi_session")
                valid = (submitted is not None and hmac.compare_digest(
                    submitted.value.encode("utf-8"), EMBEDDED_SESSION_TOKEN.encode("ascii")))
            except (ValueError, UnicodeError):
                valid = False
            if not valid:
                self._reject_request({"error": "Invalid app session"}, 403, mutation)
                return False
        if embedded_mode() and (
            request_path in {
                "/google_login", "/oauth2callback", "/api/wechat_webhook",
                "/api/approve", "/api/approve/stream",
                "/api/system/update", "/api/system/google_logout",
                "/api/hardware/battery",
                "/api/hardware/clipboard", "/api/hardware/torch",
                "/api/hardware/vibrate", "/api/aios/entry/refresh",
                "/api/aios/digest",
            }
            or request_path.startswith(("/api/wechat/", "/api/system/auth/"))
        ):
            self._reject_request({"error": "Feature requires native Android migration"}, 501, mutation)
            return False
        # A remote web page must not invoke local APIs through images, forms, or fetch.
        # OAuth callback routes live outside /api/ and retain their redirect flow.
        fetch_site = self.headers.get("Sec-Fetch-Site", "").lower()
        if api_request and fetch_site not in ("", "same-origin", "none"):
            self._reject_request({"error": "Cross-site API request denied"}, 403, mutation)
            return False
        if mutation or api_request:
            origin = self.headers.get("Origin", "")
            if origin:
                try:
                    parsed = urllib.parse.urlparse(origin)
                    valid_origin = (parsed.scheme == "http"
                                    and parsed.hostname in ("localhost", "127.0.0.1", "::1")
                                    and parsed.port == PORT)
                except ValueError:
                    valid_origin = False
                if not valid_origin:
                    self._reject_request({"error": "Invalid origin"}, 403, mutation)
                    return False
        return True

    def _serve_asset(self, request_path):
        root = pathlib.Path(__file__).resolve().parent
        if request_path in self.PUBLIC_ASSETS or request_path.startswith(("/fonts/", "/Hiyori/")):
            relative = urllib.parse.unquote(request_path).lstrip("/")
            target = (root / relative).resolve()
            allowed_root = (root / relative.split("/", 1)[0]).resolve()
            if (target.is_file() and target.is_relative_to(allowed_root)
                    and target.suffix.lower() in (".html", ".css", ".woff2", ".png", ".json", ".moc3")):
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
                if embedded_mode() and target.suffix.lower() == ".html":
                    self.send_header("Content-Security-Policy", EMBEDDED_CSP)
                self.end_headers()
                self.wfile.write(target.read_bytes())
                return
        self.send_error(404, "Not found")

    @staticmethod
    def _save_attachment(uploads_dir, attachment):
        original_name = str(attachment.get("name", "unnamed_file"))
        clean_name = original_name.replace("\\", "/").split("/")[-1]
        if clean_name in ("", ".", "..") or clean_name != original_name:
            raise ValueError("Invalid attachment filename")
        encoded = attachment.get("data", "")
        if not isinstance(encoded, str):
            raise ValueError("Invalid attachment data")
        if encoded.startswith("data:"):
            encoded = encoded.split(",", 1)[1]
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError("Attachment exceeds 8 MB")
        suffix = pathlib.Path(clean_name).suffix.lower()[:16]
        save_path = uploads_dir / f"{uuid.uuid4().hex}{suffix}"
        save_path.write_bytes(raw)
        return save_path, encoded

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def _begin_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-transform")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

    def _sse_send(self, event: dict):
        try:
            payload = json.dumps(event, ensure_ascii=False)
            self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            raise

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
        global ENV_VARS
        if not self._request_allowed():
            return
        # Strip query parameters for routing
        req_path = self.path.split("?")[0]

        if req_path == "/api/health":
            ready = embedded_assets_ready() if embedded_mode() else True
            self._send_json({"ok": ready, "ready": ready,
                             "service": "micro-agi", "port": PORT,
                             "embedded": embedded_mode(),
                             "proof": embedded_health_proof()})
            return

        if req_path == "/api/solana/devnet/balance":
            query = urlparse.parse_qs(urlparse.urlsplit(self.path).query)
            address = query.get("address", [""])[0]
            if not solana_watch.validate_public_key(address):
                self._send_json({"error": "Invalid Solana public key"}, 400)
                return
            try:
                self._send_json(solana_watch.get_devnet_balance(address))
            except (OSError, TimeoutError, ValueError, json.JSONDecodeError):
                self._send_json({"error": "Solana Devnet balance is unavailable"}, 502)
            return
        
        if req_path == "/" or req_path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            if embedded_mode():
                self.send_header("Content-Security-Policy", EMBEDDED_CSP)
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

        elif req_path == "/solana-wallet.js":
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write((pathlib.Path(__file__).parent / "solana-wallet.js").read_bytes())

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
                "scope=https://www.googleapis.com/auth/userinfo.email+https://www.googleapis.com/auth/cloud-platform&"
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
            client_secret = ENV_VARS.get("GOOGLE_CLIENT_SECRET", "")
            redirect_uri = "http://localhost:8085/oauth2callback"
            token_url = "https://oauth2.googleapis.com/token"
            payload = {
                "client_id": client_id,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri
            }
            if client_secret:
                payload["client_secret"] = client_secret
            data = urllib.parse.urlencode(payload).encode("utf-8")
            
            proxy_url = ENV_VARS.get("PROXY_URL", "")
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
            ENV_VARS = load_env()
            llm_backend = ENV_VARS.get("LLM_BACKEND", "gemini").lower()
            gemini_key = ENV_VARS.get("GEMINI_API_KEY", "")
            
            ai_url = ENV_VARS.get("AI_URL", "")
            ai_key = ENV_VARS.get("AI_KEY", "")
            ai_model = ENV_VARS.get("AI_MODEL", "")
            
            status = "disconnected"
            
            if llm_backend == "agy" and not embedded_mode():
                termux_home = "/data/data/com.termux/files/home"
                termux_usr = "/data/data/com.termux/files/usr"
                is_termux = os.path.exists("/data/data/com.termux")
                if is_termux:
                    cmd_str = (
                        "LANG=C.UTF-8 LANGUAGE=C.UTF-8 LC_ALL=C.UTF-8 "
                        f"proot -b {termux_usr}/etc/tls:/etc/ssl/certs "
                        f"-b {termux_usr}/etc/resolv.conf:/etc/resolv.conf "
                        f"-b {termux_usr}/etc/hosts:/etc/hosts "
                        f"-b {termux_home}/.local/glibc:/lib "
                        f"{termux_home}/.local/glibc/ld-linux-aarch64.so.1 {termux_home}/.local/bin/agy status"
                    )
                    env = os.environ.copy()
                    env["PATH"] = termux_usr + "/bin:" + env.get("PATH", "")
                    env["LD_LIBRARY_PATH"] = termux_usr + "/lib"
                    env["PYTHONHOME"] = termux_usr
                    env["HOME"] = termux_home
                else:
                    cmd_str = "agy status"
                    env = os.environ.copy()
                    
                try:
                    res = subprocess.run(cmd_str, shell=True, capture_output=True, text=True, env=env, timeout=5)
                    output = res.stdout.strip()
                    if res.returncode == 0 and "not signed in" not in output:
                        status = "connected"
                except:
                    pass
            elif llm_backend != "agy":
                token = ENV_VARS.get("GOOGLE_ACCESS_TOKEN", "")
                refresh_token = ENV_VARS.get("GOOGLE_REFRESH_TOKEN", "")
                if token or refresh_token:
                    status = "connected"
                    
            self._send_json({
                "status": status,
                "gemini_key": "",
                "gemini_key_configured": bool(gemini_key),
                "ai_url": ai_url,
                "ai_key": "",
                "ai_key_configured": bool(ai_key),
                "ai_model": ai_model,
                "llm_backend": llm_backend
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
            # project_id=all or missing → 全部工作区资产（更实用）
            project_id = query_params.get("project_id", "all")
            type_filter = query_params.get("type_filter", "all")
            rows = db.list_artifacts(project_id, type_filter)
            # 附加展示字段，减轻前端压力
            for r in rows:
                content = r.get("content_url") or ""
                r["size"] = len(content)
                r["lines"] = content.count("\n") + 1 if content and r.get("type") == "code" else 0
                r["lang"] = (r.get("key_prompt") or "").strip()
            self._send_json(rows)

        # --- AI OS: entry / memory / digests ---
        elif req_path == "/api/aios/status":
            try:
                if embedded_mode():
                    # The Termux snapshot probes shell commands and notification APIs.
                    # Keep memory management available without launching either.
                    snap = {
                        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "memories": len(db.list_memories(limit=200)),
                    }
                    notification = {"available": False,
                                    "tip": "独立版通知与主动简报待原生适配"}
                    panel = f"http://127.0.0.1:{PORT}/"
                else:
                    import ai_os
                    snap = ai_os.collect_system_snapshot()
                    notification = snap.get("notification") or ai_os.probe_notification()
                    panel = ai_os.PANEL_URL
                self._send_json({
                    "ok": True,
                    "panel": panel,
                    "snapshot": snap,
                    "notification": notification,
                    "memories": db.list_memories(limit=40),
                    "digests": db.list_digests(limit=10),
                    "recent_chats": db.list_recent_chats(limit=5),
                })
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)

        elif req_path == "/api/aios/memories":
            try:
                import urllib.parse
                q = {}
                if "?" in self.path:
                    for item in self.path.split("?", 1)[1].split("&"):
                        if "=" in item:
                            k, v = item.split("=", 1)
                            q[k] = urllib.parse.unquote(v)
                kind = q.get("kind", "all")
                limit = int(q.get("limit", "50") or 50)
                search = q.get("q") or q.get("search") or ""
                self._send_json({
                    "ok": True,
                    "items": db.list_memories(kind=kind, limit=limit, q=search or None),
                })
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)

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
                    "token": "",
                    "token_configured": True,
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

        elif req_path in ["/live2dcubismcore.min.js", "/pixi.min.js",
                          "/pixi-unsafe-eval.min.js", "/pixi-live2d-display.min.js"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.end_headers()
            
            js_path = pathlib.Path(__file__).parent / req_path.lstrip("/")
            if js_path.exists():
                self.wfile.write(js_path.read_bytes())
            else:
                self.wfile.write(b"")
        elif req_path.startswith("/Hiyori/"):
            self._serve_asset(req_path)
        elif req_path == "/api/system/extensions":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()

            extensions = []

            # Report only skills actually present on the device.
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
                                        "enabled": True,
                                        "status": "detected",
                                        "icon": "🧠"
                                    })

            # A file on disk is "detected", not proof that an integration is online.
            plugins = [
                ("search", "实时全网检索", "search_web.py", "本地搜索脚本已检测到。", "🔍"),
                ("bilibili", "B站视频摘要", "bilibili_summary.py", "本地视频摘要脚本已检测到。", "📺"),
            ]
            for plugin_id, name, filename, description, icon in plugins:
                if (pathlib.Path(__file__).parent / "plugins" / filename).is_file():
                    extensions.append({
                        "id": plugin_id,
                        "name": name,
                        "type": "plugin",
                        "description": description,
                        "enabled": True,
                        "status": "detected",
                        "icon": icon,
                    })

            # No MCP client is wired into this server yet; don't claim one is online.
            self.wfile.write(json.dumps(extensions).encode('utf-8'))
        else:
            self._serve_asset(req_path)

    def do_DELETE(self):
        if not self._request_allowed(mutation=True):
            return
        req_path = self.path.split("?")[0]
        if req_path.startswith("/api/artifacts/"):
            artifact_id = req_path.split("/")[-1]
            try:
                db.delete_artifact(artifact_id)
                self._send_json({"status": "success"})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        elif req_path.startswith("/api/aios/memories/"):
            memory_id = req_path.split("/")[-1]
            try:
                db.delete_memory(memory_id)
                self._send_json({"ok": True})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
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
        global active_auth_process
        if not self._request_allowed(mutation=True):
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json({"error": "Invalid Content-Length"}, 400)
            return
        if content_length < 0 or content_length > MAX_REQUEST_BYTES:
            self._send_json({"error": "Request exceeds 12 MB"}, 413)
            return
        post_data = self.rfile.read(content_length)
        req_path = self.path.split("?", 1)[0]

        # ---- Streaming chat (SSE) ----
        if req_path == "/api/chat/stream":
            sse_started = False
            try:
                req_json = json.loads(post_data.decode("utf-8") or "{}")
                user_msg = req_json.get("message", "")
                history = req_json.get("history", [])
                attachments = req_json.get("attachments", [])

                if embedded_mode() and attachments:
                    self._send_json({"error": "Attachments are not yet supported in the standalone Android app"}, 501)
                    return
                if attachments:
                    uploads_dir = pathlib.Path.home() / "micro-agi-mvp" / "uploads"
                    uploads_dir.mkdir(parents=True, exist_ok=True)
                    content_list = [{"type": "text", "text": user_msg}]
                    saved_files_text = []
                    for att in attachments:
                        file_name = att.get("name", "unnamed_file")
                        file_type = att.get("type", "")
                        save_path, file_data_b64 = self._save_attachment(uploads_dir, att)
                        saved_files_text.append(str(save_path))
                        if file_type.startswith("image/"):
                            data_uri = f"data:{file_type};base64,{file_data_b64}"
                            content_list.append({
                                "type": "image_url",
                                "image_url": {"url": data_uri},
                            })
                    if saved_files_text:
                        append_txt = "\n\n[System Note: User has attached files to this message."
                        has_image = any(
                            f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))
                            for f in saved_files_text
                        )
                        if has_image:
                            append_txt += " You CAN see the attached images directly in this message!"
                        append_txt += " Files saved at:]\n"
                        for p in saved_files_text:
                            append_txt += f"- {p}\n"
                        content_list[0]["text"] += append_txt
                    if len(content_list) == 1:
                        user_msg = content_list[0]["text"]
                    else:
                        user_msg = content_list

                project_id = req_json.get("project_id", "")
                chat_id = req_json.get("chat_id", "")
                if not project_id:
                    projects = db.list_projects()
                    if projects:
                        project_id = projects[0]["project_id"]
                    else:
                        project_id = db.create_project("默认工作区", "系统初始化的默认全局工作区")
                if not chat_id:
                    chat_id = db.create_chat(project_id, "新建对话")
                else:
                    db.update_chat_time(chat_id)

                db_user_msg = user_msg
                if isinstance(user_msg, list):
                    for item in user_msg:
                        if isinstance(item, dict) and item.get("type") == "text":
                            db_user_msg = item.get("text", "")
                            break
                db.save_message(chat_id, "user", db_user_msg)
                memories_added = []
                try:
                    import ai_os
                    if isinstance(db_user_msg, str):
                        memories_added = ai_os.try_extract_memory_from_user_text(db_user_msg) or []
                except Exception:
                    memories_added = []

                self._begin_sse()
                sse_started = True
                self._sse_send({
                    "type": "meta",
                    "chat_id": chat_id,
                    "project_id": project_id,
                    "memories_added": memories_added,
                })
                final_done = None
                for event in start_agent_run_stream(user_msg, history, project_id, chat_id):
                    if event.get("type") == "done":
                        final_done = event
                        event = dict(event)
                        event["chat_id"] = chat_id
                    self._sse_send(event)
                if final_done and final_done.get("status") == "completed":
                    db.save_message(chat_id, "assistant", final_done.get("response", ""))
                self._sse_send({"type": "end"})
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return
            except Exception as e:
                if not embedded_mode():
                    traceback.print_exc()
                try:
                    if not sse_started:
                        self._begin_sse()
                    self._sse_send({"type": "error", "error":
                                    "聊天请求失败，请重试" if embedded_mode() else str(e)})
                    self._sse_send({"type": "end"})
                except Exception:
                    pass
            return

        # ---- Streaming approve (SSE) ----
        if req_path == "/api/approve/stream":
            sse_started = False
            try:
                req_json = json.loads(post_data.decode("utf-8") or "{}")
                approved = req_json.get("approved", True)
                edited_command = req_json.get("edited_command", "")
                chat_id = req_json.get("chat_id", "")
                self._begin_sse()
                sse_started = True
                final_done = None
                for event in resume_agent_run_stream(approved, edited_command, chat_id):
                    if event.get("type") == "done":
                        final_done = event
                        event = dict(event)
                        event["chat_id"] = chat_id
                    self._sse_send(event)
                if final_done and final_done.get("status") == "completed":
                    if chat_id:
                        db.save_message(chat_id, "assistant", final_done.get("response", ""))
                self._sse_send({"type": "end"})
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return
            except Exception as e:
                traceback.print_exc()
                try:
                    if not sse_started:
                        self._begin_sse()
                    self._sse_send({"type": "error", "error": str(e)})
                    self._sse_send({"type": "end"})
                except Exception:
                    pass
            return

        # --- AI OS POST ---
        if req_path == "/api/aios/entry/refresh":
            try:
                import ai_os
                data = ai_os.refresh_control_entry()
                # Surface notification success clearly for UI toast
                notif = data.get("notification_detail") or {}
                self._send_json({
                    "ok": True,
                    **data,
                    "message": notif.get("reason") or ("通知栏已刷新" if data.get("notification") else "状态已刷新，通知可能失败"),
                })
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
            return

        if req_path == "/api/aios/digest":
            try:
                import ai_os
                req_json = json.loads(post_data.decode("utf-8") or "{}")
                kind = req_json.get("kind", "now")
                force = bool(req_json.get("force", False))
                push = bool(req_json.get("push", True))
                data = ai_os.send_digest(kind=kind, force=force, push=push)
                self._send_json(data)
            except Exception as e:
                traceback.print_exc()
                self._send_json({"ok": False, "error": str(e)}, 500)
            return

        if req_path == "/api/aios/memories":
            try:
                req_json = json.loads(post_data.decode("utf-8") or "{}")
                content = (req_json.get("content") or "").strip()
                if not content:
                    self._send_json({"ok": False, "error": "content required"}, 400)
                    return
                mid = db.add_memory(
                    content,
                    kind=req_json.get("kind") or "fact",
                    importance=int(req_json.get("importance") or 1),
                    source=req_json.get("source") or "user",
                )
                self._send_json({"ok": True, "memory_id": mid})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
            return

        if req_path == "/api/aios/memories/delete":
            try:
                req_json = json.loads(post_data.decode("utf-8") or "{}")
                mid = req_json.get("memory_id") or ""
                if not mid:
                    self._send_json({"ok": False, "error": "memory_id required"}, 400)
                    return
                db.delete_memory(mid)
                self._send_json({"ok": True})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
            return

        if req_path == "/api/aios/memories/pin":
            try:
                req_json = json.loads(post_data.decode("utf-8") or "{}")
                mid = req_json.get("memory_id") or ""
                if not mid:
                    self._send_json({"ok": False, "error": "memory_id required"}, 400)
                    return
                pinned = bool(req_json.get("pinned", True))
                ok = db.pin_memory(mid, pinned=pinned)
                self._send_json({"ok": bool(ok), "pinned": pinned})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
            return

        if self.path == "/api/chat" or req_path == "/api/chat":
            try:
                req_json = json.loads(post_data.decode('utf-8'))
                user_msg = req_json.get("message", "")
                history = req_json.get("history", [])
                attachments = req_json.get("attachments", [])

                if embedded_mode() and attachments:
                    self._send_json({"error": "Attachments are not yet supported in the standalone Android app"}, 501)
                    return
                if attachments:
                    uploads_dir = pathlib.Path.home() / "micro-agi-mvp" / "uploads"
                    uploads_dir.mkdir(parents=True, exist_ok=True)
                    
                    content_list = [{"type": "text", "text": user_msg}]
                    saved_files_text = []
                    
                    for att in attachments:
                        file_name = att.get("name", "unnamed_file")
                        file_type = att.get("type", "")
                        save_path, file_data_b64 = self._save_attachment(uploads_dir, att)
                        saved_files_text.append(str(save_path))
                            
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

                # Do not put private chat text into Android logcat or desktop logs.
                print("User Request received")
                
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
                try:
                    import ai_os
                    if isinstance(db_user_msg, str):
                        ai_os.try_extract_memory_from_user_text(db_user_msg)
                except Exception:
                    pass

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
                if embedded_mode():
                    self._send_json({"error": "聊天请求失败，请重试"}, 500)
                else:
                    traceback.print_exc()
                    self._send_json({"error": str(e)}, 500)

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
                chat_id = req_json.get("chat_id", "")

                print(f"Approval received: {approved} (edited: '{edited_command}')")
                result = resume_agent_run(approved, edited_command, chat_id)

                if result.get("status") == "completed":
                    if chat_id:
                        db.save_message(chat_id, "assistant", result.get("response", ""))
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
                if status not in ("on", "off"):
                    self._send_json({"error": "Invalid torch status"}, 400)
                    return
                res = subprocess.run(["termux-torch", status], capture_output=True, text=True, timeout=5)
                self._send_json({"ok": res.returncode == 0, "error": res.stderr.strip() if res.returncode else ""})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif self.path == "/api/hardware/vibrate":
            try:
                req_json = json.loads(post_data.decode('utf-8'))
                duration = int(req_json.get("duration", 200))
                if not 1 <= duration <= 5000:
                    self._send_json({"error": "Invalid vibration duration"}, 400)
                    return
                res = subprocess.run(["termux-vibrate", "-d", str(duration)], capture_output=True, text=True, timeout=5)
                self._send_json({"ok": res.returncode == 0, "error": res.stderr.strip() if res.returncode else ""})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif self.path == "/api/system/command":
            if embedded_mode() or ENV_VARS.get("ENABLE_SYSTEM_COMMANDS", "false").lower() != "true":
                self._send_json({"error": "Web terminal is disabled"}, 403)
                return
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

        elif self.path == "/api/system/auth/init":
            try:
                import pty
                if active_auth_process:
                    try:
                        os.close(active_auth_process[0])
                    except:
                        pass
                    try:
                        active_auth_process[1].terminate()
                    except:
                        pass
                    active_auth_process = None
                
                termux_home = "/data/data/com.termux/files/home"
                termux_usr = "/data/data/com.termux/files/usr"
                
                cmd_args = [
                    f"{termux_usr}/bin/proot",
                    "-b", f"{termux_usr}/etc/tls:/etc/ssl/certs",
                    "-b", f"{termux_usr}/etc/resolv.conf:/etc/resolv.conf",
                    "-b", f"{termux_usr}/etc/hosts:/etc/hosts",
                    "-b", termux_home,
                    "-b", f"{termux_home}/.local/glibc:/lib",
                    f"{termux_home}/.local/glibc/ld-linux-aarch64.so.1",
                    f"{termux_home}/.local/bin/agy"
                ]
                
                env = os.environ.copy()
                env["LANG"] = "C.UTF-8"
                env["LANGUAGE"] = "C.UTF-8"
                env["LC_ALL"] = "C.UTF-8"
                env["PATH"] = termux_usr + "/bin:" + env.get("PATH", "")
                env["LD_LIBRARY_PATH"] = termux_usr + "/lib"
                env["PYTHONHOME"] = termux_usr
                env["HOME"] = termux_home
                
                master_fd, slave_fd = pty.openpty()
                proc = subprocess.Popen(
                    cmd_args,
                    shell=False,
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    close_fds=True,
                    env=env
                )
                os.close(slave_fd)
                
                active_auth_process = (master_fd, proc)
                
                time.sleep(0.5)
                os.write(master_fd, b"1\n")
                
                auth_url = ""
                timeout_limit = time.time() + 10
                buffer = ""
                while time.time() < timeout_limit:
                    try:
                        r = os.read(master_fd, 1024).decode('utf-8', errors='ignore')
                        if not r:
                            break
                        buffer += r
                        if "https://" in buffer:
                            urls = re.findall(r'https://\S+', buffer)
                            if urls:
                                auth_url = urls[0]
                                break
                    except OSError:
                        break
                        
                if auth_url:
                    self._send_json({"ok": True, "url": auth_url})
                else:
                    self._send_json({"ok": False, "message": "Failed to retrieve OAuth URL from TTY buffer."})
            except Exception as e:
                traceback.print_exc()
                self._send_json({"ok": False, "message": str(e)}, 500)

        elif self.path == "/api/system/auth/confirm":
            try:
                if not active_auth_process:
                    self._send_json({"ok": False, "message": "No active authorization session. Please initialize again."})
                    return
                    
                req_json = json.loads(post_data.decode('utf-8'))
                code = req_json.get("code", "").strip()
                if not code:
                    self._send_json({"ok": False, "message": "Verification code is empty"})
                    return
                    
                master_fd, proc = active_auth_process
                os.write(master_fd, f"{code}\n".encode('utf-8'))
                
                time.sleep(3)
                
                try:
                    os.close(master_fd)
                except:
                    pass
                try:
                    proc.terminate()
                except:
                    pass
                active_auth_process = None
                
                self._send_json({"ok": True, "message": "Google Credentials submitted to agy client successfully!"})
            except Exception as e:
                traceback.print_exc()
                self._send_json({"ok": False, "message": str(e)}, 500)

        elif self.path == "/api/hardware/clipboard":
            try:
                req_json = json.loads(post_data.decode('utf-8'))
                text = req_json.get("text", "")
                proc = subprocess.Popen(["termux-clipboard-set"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                stdout, stderr = proc.communicate(input=text, timeout=5)
                self._send_json({"ok": proc.returncode == 0, "error": stderr.strip() if proc.returncode else ""})
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
            self._send_json({"error": "Public tunnel is disabled until remote authentication is implemented"}, 403)

        elif self.path == "/api/system/save_gemini_key":
            try:
                req_json = json.loads(post_data.decode('utf-8'))
                if not isinstance(req_json, dict) or any(
                    not isinstance(req_json.get(name, ""), str)
                    for name in ("gemini_key", "ai_url", "ai_key", "ai_model")
                ):
                    self._send_json({"error": "Invalid model configuration"}, 400)
                    return
                gemini_key = req_json.get("gemini_key", "").strip()
                ai_url = req_json.get("ai_url", "").strip()
                ai_key = req_json.get("ai_key", "").strip()
                ai_model = req_json.get("ai_model", "").strip()
                if embedded_mode() and (len(gemini_key) > 512 or any(
                    c in '\\"' or ord(c) < 32 or ord(c) == 127 for c in gemini_key
                )):
                    self._send_json({"error": "Invalid Gemini API Key format"}, 400)
                    return
                if embedded_mode() and (ai_url or ai_key or ai_model):
                    try:
                        parsed_model_url = urlparse.urlsplit(ai_url)
                    except ValueError:
                        self._send_json({"error": "Invalid model URL"}, 400)
                        return
                    if (gemini_key or parsed_model_url.scheme != "https"
                            or not parsed_model_url.hostname
                            or parsed_model_url.username or parsed_model_url.password
                            or parsed_model_url.query or parsed_model_url.fragment
                            or not parsed_model_url.path.endswith("/chat/completions")
                            or not ai_model or not ai_key
                            or len(ai_url) > 2048 or len(ai_key) > 512 or len(ai_model) > 200
                            or any(c in '\\"' or ord(c) < 32 or ord(c) == 127
                                   for c in ai_url + ai_key + ai_model)):
                        self._send_json({"error": "Provide an HTTPS chat/completions URL, model and API Key"}, 400)
                        return
                
                config_to_save = {}
                config_to_save["GEMINI_API_KEY"] = gemini_key
                if embedded_mode() and gemini_key:
                    config_to_save["LLM_BACKEND"] = "gemini"
                    config_to_save.update({"AI_URL": "", "AI_KEY": "",
                                           "AI_MODEL": DEFAULT_GEMINI_MODEL})
                elif embedded_mode() and ai_url:
                    config_to_save.update({"LLM_BACKEND": "openai",
                                           "GOOGLE_ACCESS_TOKEN": "",
                                           "GOOGLE_REFRESH_TOKEN": ""})
                if ai_url:
                    config_to_save["AI_URL"] = ai_url
                if ai_key:
                    config_to_save["AI_KEY"] = ai_key
                if ai_model:
                    config_to_save["AI_MODEL"] = ai_model
                    
                if save_env_config(config_to_save):
                    self._send_json({"status": "success"})
                else:
                    self._send_json({"error": "Could not save model configuration"}, 500)
            except Exception as e:
                self._send_json({"error": "Could not save model configuration"
                                 if embedded_mode() else str(e)}, 500)
                
        elif self.path == "/api/system/google_logout":
            try:
                save_env_config({
                    "GOOGLE_ACCESS_TOKEN": "",
                    "GOOGLE_REFRESH_TOKEN": ""
                })
                self._send_json({"status": "success"})
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

class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        # Browser navigation often closes in-flight asset/SSE connections.
        # These are expected disconnects, not server faults worth filling logs with.
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError,
                                          ConnectionAbortedError, TimeoutError)):
            return
        super().handle_error(request, client_address)


class EmbeddedHTTPServer(ThreadingHTTPServer):
    """Bound pre-auth connections from other apps on the same Android device."""

    MAX_ACTIVE_REQUESTS = 24
    REQUEST_TIMEOUT_SECONDS = 10

    def __init__(self, *args, **kwargs):
        self._request_slots = threading.BoundedSemaphore(self.MAX_ACTIVE_REQUESTS)
        super().__init__(*args, **kwargs)

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(self.REQUEST_TIMEOUT_SECONDS)
        return request, address

    def process_request(self, request, client_address):
        if not self._request_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._request_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()

class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global active_auth_process
        from urllib.parse import urlparse, parse_qs
        parsed_path = urlparse(self.path)
        params = parse_qs(parsed_path.query)
        
        code = params.get('code', [''])[0]
        if code:
            try:
                if active_auth_process:
                    master_fd, proc = active_auth_process
                    os.write(master_fd, f"{code}\n".encode('utf-8'))
                    time.sleep(3)
                    try: os.close(master_fd)
                    except: pass
                    try: proc.terminate()
                    except: pass
                    active_auth_process = None
            except Exception as e:
                print(f"Error submitting OAuth code in background: {e}")
        
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        html_content = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Google 授权成功</title>
    <style>
        body { margin: 0; padding: 0; background: #0f172a; color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; text-align: center; }
        .card { background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 20px; padding: 40px 30px; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5), 0 0 30px rgba(56,189,248,0.2); max-width: 90%; width: 360px; }
        .icon { font-size: 64px; margin-bottom: 20px; animation: bounce 1s infinite alternate; }
        @keyframes bounce { from { transform: translateY(0); } to { transform: translateY(-10px); } }
        h1 { font-size: 22px; margin: 0 0 10px 0; color: #38bdf8; }
        p { font-size: 15px; color: #94a3b8; line-height: 1.6; margin: 0 0 25px 0; }
        .btn { background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%); color: #fff; border: none; padding: 12px 24px; border-radius: 12px; font-size: 16px; font-weight: bold; cursor: pointer; box-shadow: 0 10px 15px -3px rgba(2, 132, 199, 0.4); text-decoration: none; display: inline-block; }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">🎉</div>
        <h1>Google 账号授权绑定成功！</h1>
        <p>Antigravity CLI (agy) 已在手机终端底层完成深度绑定与智力融合！</p>
        <div class="btn" onclick="window.close(); history.back();">返回 App 控制台</div>
    </div>
</body>
</html>"""
        self.wfile.write(html_content.encode('utf-8'))
    def log_message(self, format, *args):
        pass

def run_oauth_server():
    try:
        oauthd = ThreadingHTTPServer((HOST, 8085), OAuthCallbackHandler)
        print("Local OAuth Callback Server running on port 8085")
        oauthd.serve_forever()
    except Exception as e:
        print(f"Error starting OAuth callback server on 8085: {e}")

def create_embedded_server():
    """Reserve an OS-assigned loopback port before revealing it to Android."""
    if not embedded_mode():
        raise RuntimeError("Embedded server requires Android mode")
    global PORT
    httpd = EmbeddedHTTPServer((HOST, 0), AgentMVPHandler)
    PORT = httpd.server_address[1]
    return httpd


def run_server(httpd=None):
    if httpd is None:
        server_class = EmbeddedHTTPServer if embedded_mode() else ThreadingHTTPServer
        httpd = server_class((HOST, PORT), AgentMVPHandler)
    if not embedded_mode():
        threading.Thread(target=run_oauth_server, daemon=True).start()
        threading.Thread(target=wechat_long_poll_daemon, daemon=True).start()
        threading.Thread(target=battery_monitor_daemon, daemon=True).start()
        try:
            import ai_os
            ai_os.start_aios_daemons()
        except Exception as exc:
            print(f"[AIOS] daemon start failed: {exc}")
    print(f"==================================================")
    print(f"Micro-AGI MVP Server is running on port {PORT}")
    print(f"Local URL: http://localhost:{PORT}")
    print(f"Press Ctrl+C to terminate.")
    print(f"==================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        httpd.server_close()

if __name__ == "__main__":
    run_server()
