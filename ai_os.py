"""
AI OS helpers: unified entry notification, system snapshot, proactive digests.
Designed for Termux on Android (Seeker).
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

import db

HOME = Path.home()
MVP_DIR = Path(__file__).resolve().parent
PANEL_URL = os.environ.get("AIOS_PANEL_URL", "http://127.0.0.1:8087/")
API_BASE = os.environ.get("AIOS_API_BASE", "http://127.0.0.1:8087")
NOTIF_ID = "micro-agi-os"

_daemon_started = False
_lock = threading.Lock()
_notif_lock = threading.Lock()
_notif_busy = False


def _run(cmd: str, timeout: int = 8) -> tuple[int, str]:
    """Return (returncode, combined_output). On exception returncode=-1.
    Uses a new process group so timeout can kill hung termux-api children.
    """
    try:
        r = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(HOME),
            start_new_session=True,
        )
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        return r.returncode, out
    except subprocess.TimeoutExpired as e:
        # Best-effort: kill process group
        try:
            if e.process is not None:
                import os as _os
                import signal
                _os.killpg(e.process.pid, signal.SIGKILL)
        except Exception:
            pass
        return -1, "err: timeout"
    except Exception as e:
        return -1, f"err: {e}"


def _which(name: str) -> bool:
    return shutil.which(name) is not None


def probe_notification() -> dict:
    """Diagnose Termux:API notification capability without spamming tray."""
    has_cmd = _which("termux-notification")
    has_battery = _which("termux-battery-status")
    has_open = _which("termux-open-url")
    tip = ""
    if not has_cmd:
        tip = "未找到 termux-notification。请安装 Termux:API 应用与包: pkg install termux-api"
    elif not has_battery:
        tip = "termux-api 命令不完整，部分硬件状态可能不可用"
    else:
        tip = "Termux:API 可用；若通知不显示，请检查系统通知权限与省电限制"
    return {
        "termux_notification": has_cmd,
        "termux_battery": has_battery,
        "termux_open_url": has_open,
        "available": has_cmd,
        "tip": tip,
    }


def collect_system_snapshot() -> dict:
    """Lightweight phone health snapshot for digests / control bar."""
    snap = {
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "battery": None,
        "disk_home_free_gb": None,
        "disk_data_use_pct": None,
        "loadavg": None,
        "services": {},
        "memories": 0,
        "recent_chats": 0,
        "artifacts_24h": 0,
        "notification": probe_notification(),
    }

    # battery (short timeout — termux-api may hang without plugin)
    if _which("termux-battery-status"):
        code, raw = _run("termux-battery-status", timeout=2)
        try:
            b = json.loads(raw)
            snap["battery"] = {
                "percentage": b.get("percentage"),
                "status": b.get("status"),
                "temperature": b.get("temperature"),
            }
        except Exception:
            if raw and not raw.startswith("err:") and code == 0:
                snap["battery"] = {"raw": raw[:120]}

    # disk
    try:
        usage = shutil.disk_usage(str(HOME))
        snap["disk_home_free_gb"] = round(usage.free / (1024 ** 3), 2)
        snap["disk_data_use_pct"] = round(usage.used / max(usage.total, 1) * 100, 1)
    except Exception:
        pass

    # load
    try:
        with open("/proc/loadavg", "r") as f:
            parts = f.read().split()
            snap["loadavg"] = parts[0] if parts else None
    except Exception:
        pass

    # services (best-effort process sniff)
    _, ps = _run("ps -A -o pid,cmd", timeout=5)

    def alive(pat: str) -> bool:
        return bool(re.search(pat, ps, re.I))

    snap["services"] = {
        "micro_agi": alive(r"python(?:3)?\s+app\.py"),
        "xbot": alive(r"node\s+server\.js") or alive(r"xbot-deploy"),
        "swapbot": alive(r"node\s+agent\.js") or alive(r"swapbot"),
        "proxy": alive(r"mihomo"),
        "wake": alive(r"wake_word_daemon"),
    }

    try:
        snap["memories"] = len(db.list_memories(limit=200))
    except Exception:
        snap["memories"] = 0

    try:
        snap["recent_chats"] = len(db.list_recent_chats(limit=20))
    except Exception:
        snap["recent_chats"] = 0

    try:
        snap["artifacts_24h"] = db.count_artifacts(days=1)
    except Exception:
        snap["artifacts_24h"] = 0

    return snap


def _context_lines_for_digest(kind: str) -> list[str]:
    """Pull chats / memories / recent asks into digest body."""
    extra: list[str] = []
    try:
        chats = db.list_recent_chats(limit=4)
        if chats:
            titles = []
            for c in chats:
                t = (c.get("title") or "未命名").strip()
                if len(t) > 28:
                    t = t[:27] + "…"
                titles.append(t)
            extra.append("最近对话: " + " · ".join(titles))
    except Exception:
        pass

    try:
        mems = db.list_memories(limit=4)
        if mems:
            bits = []
            for m in mems:
                c = (m.get("content") or "").strip()
                if len(c) > 36:
                    c = c[:35] + "…"
                if c:
                    bits.append(c)
            if bits:
                extra.append("关键记忆: " + "；".join(bits[:3]))
    except Exception:
        pass

    try:
        msgs = db.list_recent_user_messages(limit=3, max_len=48)
        if msgs and kind in ("evening", "now", "midday"):
            asks = [m["content"] for m in msgs if m.get("content")]
            if asks:
                extra.append("近期你说过: " + " / ".join(asks[:2]))
    except Exception:
        pass

    try:
        n_art = db.count_artifacts(days=1)
        if n_art:
            extra.append(f"近 24h 成果资产: {n_art} 条")
    except Exception:
        pass

    return extra


def format_digest(kind: str, snap: dict | None = None) -> str:
    snap = snap or collect_system_snapshot()
    bat = snap.get("battery") or {}
    bat_s = f"{bat.get('percentage', '?')}% {bat.get('status', '')}".strip()
    svc = snap.get("services") or {}
    svc_s = " · ".join(f"{k}{'✅' if v else '❌'}" for k, v in svc.items())
    free_gb = snap.get("disk_home_free_gb")
    use_pct = snap.get("disk_data_use_pct")
    load = snap.get("loadavg")
    mem_n = snap.get("memories", 0)

    if kind == "morning":
        title = "☀️ 日和 · 早间简报"
        tip = "今天优先做哪 3 件事？直接对我说即可。"
    elif kind == "midday":
        title = "🌤️ 日和 · 午间状态"
        tip = "需要我帮你摘要进度或整理待办吗？"
    elif kind == "evening":
        title = "🌙 日和 · 晚间回顾"
        tip = "今天有什么值得写进长期记忆的？说「记住：…」"
    elif kind == "urgent":
        title = "🚨 日和 · 紧急提醒"
        tip = "建议先处理磁盘或异常服务。"
    else:
        title = "📋 日和 · 即时状态"
        tip = "面板: " + PANEL_URL

    lines = [
        title,
        f"时间: {snap.get('time')}",
        f"电量: {bat_s or '未知'}",
        f"磁盘: 已用 {use_pct}% · 剩余约 {free_gb} GB" if free_gb is not None else "磁盘: 未知",
        f"负载: {load or '未知'}",
        f"服务: {svc_s or '未知'}",
        f"长期记忆: {mem_n} 条 · 会话约 {snap.get('recent_chats', 0)} 个",
    ]

    # urgency hints
    alerts = []
    try:
        if use_pct is not None and float(use_pct) >= 92:
            alerts.append("磁盘紧张（≥92%）")
        if bat.get("percentage") is not None and int(bat["percentage"]) <= 15:
            alerts.append("电量偏低（≤15%）")
        for name, ok in svc.items():
            if name in ("micro_agi", "proxy") and not ok:
                alerts.append(f"{name} 未运行")
        notif = snap.get("notification") or {}
        if notif and not notif.get("available"):
            alerts.append("系统通知不可用（缺 Termux:API）")
    except Exception:
        pass
    if alerts:
        lines.insert(2, "⚠️ " + "；".join(alerts))

    for line in _context_lines_for_digest(kind):
        lines.append(line)

    lines.append(tip)
    return "\n".join(lines)


def push_notification(title: str, content: str, ongoing: bool = False) -> dict:
    """
    Push Android notification via termux-notification.
    Returns {ok, reason, available}.
    Serialized + short timeout to avoid stacking hung termux-api processes.
    """
    global _notif_busy
    probe = probe_notification()
    if not probe["available"]:
        print("[AIOS] termux-notification 不可用")
        return {
            "ok": False,
            "available": False,
            "reason": probe["tip"],
        }

    if not _notif_lock.acquire(blocking=False):
        return {
            "ok": False,
            "available": True,
            "reason": "上一条通知仍在处理，请稍后再试",
            "busy": True,
        }

    try:
        _notif_busy = True
        open_action = f"termux-open-url '{PANEL_URL}'"
        digest_action = (
            f"curl -s -X POST '{API_BASE}/api/aios/digest' "
            f"-H 'Content-Type: application/json' "
            f"-d '{{\"kind\":\"now\",\"push\":true,\"force\":true}}' >/dev/null"
        )
        safe_title = title.replace("'", "′")[:40]
        safe_content = content.replace("'", "′")[:180]
        # Prefer argv list without shell when possible for cleaner kill; still use shell
        # because button actions need quoting. Keep timeout tight (2.5s).
        cmd = (
            f"termux-notification --id {NOTIF_ID} "
            f"--title '{safe_title}' --content '{safe_content}' --priority high "
            f"--button1 '打开面板' --button1-action \"{open_action}\" "
            f"--button2 '即时简报' --button2-action \"{digest_action}\""
        )
        if ongoing:
            cmd += " --ongoing --alert-once"
        # Prefer coreutils `timeout` so termux-api IPC cannot hang the server thread
        if _which("timeout"):
            cmd = f"timeout -k 1 2 {cmd}"
            code, out = _run(cmd, timeout=5)
        else:
            code, out = _run(cmd, timeout=3)
        if code != 0 or (out and out.startswith("err:")):
            reason = out or f"exit {code}"
            print(f"[AIOS] notification fail: {reason}")
            if code == -1 or "timeout" in reason or "not found" in reason.lower():
                return {
                    "ok": False,
                    "available": True,
                    "reason": f"通知调用失败: {reason}。请检查 Termux:API 权限与通知开关。",
                }
            if code != 0:
                return {
                    "ok": False,
                    "available": True,
                    "reason": f"通知返回码 {code}: {reason[:120]}",
                }
        return {
            "ok": True,
            "available": True,
            "reason": "已写入通知栏",
        }
    finally:
        _notif_busy = False
        _notif_lock.release()


def refresh_control_entry(snap: dict | None = None) -> dict:
    """Unified entry: sticky notification as always-on control bar."""
    snap = snap or collect_system_snapshot()
    bat = (snap.get("battery") or {}).get("percentage", "?")
    free_gb = snap.get("disk_home_free_gb", "?")
    svc = snap.get("services") or {}
    ok_n = sum(1 for v in svc.values() if v)
    title = "日和 AI · 控制台"
    content = f"电{bat}% · 盘剩{free_gb}G · 服务{ok_n}/{len(svc)} · 记忆{snap.get('memories', 0)}"
    notif = push_notification(title, content, ongoing=True)
    return {
        "title": title,
        "content": content,
        "snapshot": snap,
        "notification": notif.get("ok", False),
        "notification_detail": notif,
    }


def maybe_push_wechat(text: str) -> bool:
    """Best-effort WeChat push via wxclawbot CLI if configured."""
    try:
        env_path = MVP_DIR / ".env"
        to_user = ""
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("WXCLAW_DEFAULT_TO="):
                    to_user = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
        if not to_user:
            return False
        if _which("wxclawbot"):
            safe = text[:1200].replace("'", "′")
            _run(f"wxclawbot send --to '{to_user}' --text '{safe}'", timeout=20)
            return True
    except Exception as e:
        print(f"[AIOS] wechat push skip: {e}")
    return False


def send_digest(kind: str = "now", force: bool = False, push: bool = True) -> dict:
    kind = (kind or "now").strip().lower()
    if kind not in ("morning", "midday", "evening", "urgent", "now"):
        kind = "now"
    day = datetime.date.today().isoformat()
    snap = collect_system_snapshot()

    # auto urgent upgrade
    use_pct = snap.get("disk_data_use_pct")
    bat = (snap.get("battery") or {}).get("percentage")
    if kind == "now":
        try:
            if (use_pct is not None and float(use_pct) >= 95) or (
                bat is not None and int(bat) <= 10
            ):
                kind_label = "urgent"
            else:
                kind_label = "now"
        except Exception:
            kind_label = "now"
    else:
        kind_label = kind

    if kind_label != "now" and not force and db.digest_already_sent(kind_label, day):
        # still return preview content
        text = format_digest(kind_label, snap)
        return {
            "ok": True,
            "skipped": True,
            "reason": f"{kind_label} already sent for {day}",
            "kind": kind_label,
            "content": text,
            "notification": False,
            "snapshot": snap,
        }

    text = format_digest(kind_label if kind_label != "now" else "now", snap)
    if kind_label != "now":
        db.save_digest(kind_label, day, text)
    else:
        db.save_digest(
            "now",
            day + "T" + datetime.datetime.now().strftime("%H%M%S"),
            text,
        )

    notif_detail = {"ok": False, "available": False, "reason": "未推送"}
    wechat_ok = False
    if push:
        notif_detail = push_notification(
            text.split("\n", 1)[0][:40],
            " | ".join(text.split("\n")[1:4])[:160],
            ongoing=False,
        )
        # also refresh sticky control entry (best-effort)
        try:
            refresh_control_entry(snap)
        except Exception:
            pass
        wechat_ok = maybe_push_wechat(text)

    return {
        "ok": True,
        "skipped": False,
        "kind": kind_label,
        "content": text,
        "notification": bool(notif_detail.get("ok")),
        "notification_detail": notif_detail,
        "wechat": wechat_ok,
        "snapshot": snap,
        "preview_only": not push,
    }


def try_extract_memory_from_user_text(text: str) -> list:
    """Parse '记住：xxx' / '记住 xxx' / multi-line into memory rows."""
    if not text or not isinstance(text, str):
        return []
    created = []
    patterns = [
        r"记住[:：]\s*(.+)",
        r"请记住[:：]?\s*(.+)",
        r"记一下[:：]?\s*(.+)",
        r"帮我记住[:：]?\s*(.+)",
        r"记着[:：]?\s*(.+)",
        r"别忘了[:：]?\s*(.+)",
        r"remember(?:\s+that)?[:：]?\s*(.+)",
        r"note(?:\s+that)?[:：]?\s*(.+)",
    ]
    # Also whole-message form without line breaks: 「记住 我不吃香菜」
    candidates = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            candidates.append(line)
    # single blob fallback
    blob = text.strip()
    if blob and blob not in candidates:
        candidates.append(blob)

    seen = set()
    for line in candidates:
        for pat in patterns:
            m = re.search(pat, line, flags=re.I)
            if not m:
                continue
            content = m.group(1).strip().strip("。.;；!！?？\"'“”")
            # stop at sentence boundary if too long run-on
            if "。" in content and len(content) > 80:
                content = content.split("。", 1)[0].strip()
            key = content.casefold()
            if key in seen:
                break
            if 2 <= len(content) <= 500:
                try:
                    mid = db.add_memory(content, kind="fact", importance=2, source="auto")
                    created.append({"memory_id": mid, "content": content})
                    seen.add(key)
                except Exception as e:
                    print(f"[AIOS] memory extract fail: {e}")
            break
    return created


def proactive_daemon_loop(stop_event: threading.Event | None = None):
    """Background: sticky entry refresh + morning/midday/evening digests."""
    print("[AIOS] proactive daemon started")
    last_entry = 0
    while True:
        if stop_event and stop_event.is_set():
            break
        try:
            now = datetime.datetime.now()
            # sticky control entry every 15 min
            if time.time() - last_entry > 15 * 60:
                refresh_control_entry()
                last_entry = time.time()

            hour, minute = now.hour, now.minute
            day = now.date().isoformat()
            slots = [
                ("morning", 8, 0),
                ("midday", 12, 30),
                ("evening", 21, 0),
            ]
            for kind, h, m in slots:
                if hour == h and minute >= m and minute < m + 3:
                    if not db.digest_already_sent(kind, day):
                        print(f"[AIOS] sending scheduled digest: {kind}")
                        send_digest(kind=kind, force=False, push=True)

            if minute in (5, 35):
                snap = collect_system_snapshot()
                use_pct = snap.get("disk_data_use_pct")
                if use_pct is not None and float(use_pct) >= 95:
                    if not db.digest_already_sent("urgent", day):
                        send_digest(kind="urgent", force=False, push=True)
        except Exception as e:
            print(f"[AIOS] daemon error: {e}")
        for _ in range(60):
            if stop_event and stop_event.is_set():
                break
            time.sleep(1)


def start_aios_daemons():
    global _daemon_started
    with _lock:
        if _daemon_started:
            return
        _daemon_started = True
        t = threading.Thread(target=proactive_daemon_loop, daemon=True, name="aios-proactive")
        t.start()

        def _initial():
            try:
                # Delay so HTTP server binds first; never block request threads
                time.sleep(2)
                refresh_control_entry()
            except Exception as e:
                print(f"[AIOS] initial entry failed: {e}")

        threading.Thread(target=_initial, daemon=True, name="aios-initial-entry").start()
