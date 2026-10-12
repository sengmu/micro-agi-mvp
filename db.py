import sqlite3
import uuid
import os
from pathlib import Path


def resolve_db_path(data_dir=None):
    """Keep desktop storage unchanged; Android supplies an app-private data directory."""
    if data_dir is None:
        data_dir = os.environ.get("MICRO_AGI_DATA_DIR")
    if not data_dir:
        return os.path.join(os.path.dirname(__file__), "micro_agi.db")
    target = Path(data_dir)
    if not target.is_absolute():
        raise ValueError("MICRO_AGI_DATA_DIR must be an absolute path")
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    return str(target / "micro_agi.db")


DB_PATH = resolve_db_path()

def get_connection():
    # 开启外键约束开关
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = 1")
    # 让查询结果以字典形式返回
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # 2.1 项目表 (Projects)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY,
            project_name TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 2.2 对话会话表 (Chats)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            chat_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            title TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
        )
    """)
    
    # 2.3 成果资产表 (Artifacts)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS artifacts (
            artifact_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            chat_id TEXT,
            node_id TEXT,
            title TEXT,
            type TEXT,
            content_url TEXT,
            preview_text TEXT,
            key_prompt TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
            FOREIGN KEY (chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE
        )
    """)

    # 2.4 对话消息记录表 (Messages)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            message_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE
        )
    """)

    # 2.5 长期记忆（跨会话，本地）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            memory_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL DEFAULT 'fact',
            content TEXT NOT NULL,
            importance INTEGER DEFAULT 1,
            source TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2.6 主动日报发送记录（防重复）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS digests (
            digest_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            day TEXT NOT NULL,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(kind, day)
        )
    """)
    
    # 初始化一个默认项目，避免冷启动没有归属
    cursor.execute("SELECT COUNT(*) FROM projects")
    if cursor.fetchone()[0] == 0:
        pid = str(uuid.uuid4())
        cursor.execute("INSERT INTO projects (project_id, project_name, description) VALUES (?, ?, ?)", 
                       (pid, "默认工作区", "系统初始化的默认全局工作区"))
        
    conn.commit()
    conn.close()

# ==========================================
# CRUD: Projects
# ==========================================
def create_project(name: str, description: str = "") -> str:
    conn = get_connection()
    pid = str(uuid.uuid4())
    conn.execute("INSERT INTO projects (project_id, project_name, description) VALUES (?, ?, ?)", (pid, name, description))
    conn.commit()
    conn.close()
    return pid

def list_projects():
    conn = get_connection()
    cur = conn.execute("SELECT * FROM projects ORDER BY created_at DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def get_project(pid: str):
    conn = get_connection()
    cur = conn.execute("SELECT * FROM projects WHERE project_id = ?", (pid,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

# ==========================================
# CRUD: Chats
# ==========================================
def create_chat(project_id: str, title: str) -> str:
    conn = get_connection()
    cid = str(uuid.uuid4())
    conn.execute("INSERT INTO chats (chat_id, project_id, title) VALUES (?, ?, ?)", (cid, project_id, title))
    conn.commit()
    conn.close()
    return cid

def list_chats(project_id: str):
    conn = get_connection()
    cur = conn.execute("SELECT * FROM chats WHERE project_id = ? ORDER BY updated_at DESC", (project_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def update_chat_time(chat_id: str):
    conn = get_connection()
    conn.execute("UPDATE chats SET updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()

# ==========================================
# CRUD: Artifacts (成果箱)
# ==========================================
def create_artifact(project_id: str, chat_id: str, node_id: str, title: str, type_enum: str, content_url: str, preview_text: str, key_prompt: str) -> str:
    conn = get_connection()
    aid = str(uuid.uuid4())
    conn.execute("""
        INSERT INTO artifacts (artifact_id, project_id, chat_id, node_id, title, type, content_url, preview_text, key_prompt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (aid, project_id, chat_id, node_id, title, type_enum, content_url, preview_text, key_prompt))
    conn.commit()
    conn.close()
    return aid

def list_artifacts(project_id: str = None, type_filter: str = None):
    """List artifacts. If project_id is empty/None/'all', return across all projects."""
    conn = get_connection()
    tf = (type_filter or "").strip()
    if tf in ("", "all", "undefined", "null"):
        tf = None
    pid = (project_id or "").strip()
    if pid in ("", "all", "undefined", "null"):
        pid = None

    if pid and tf:
        cur = conn.execute(
            "SELECT * FROM artifacts WHERE project_id = ? AND type = ? ORDER BY created_at DESC",
            (pid, tf),
        )
    elif pid:
        cur = conn.execute(
            "SELECT * FROM artifacts WHERE project_id = ? ORDER BY created_at DESC",
            (pid,),
        )
    elif tf:
        cur = conn.execute(
            "SELECT * FROM artifacts WHERE type = ? ORDER BY created_at DESC",
            (tf,),
        )
    else:
        cur = conn.execute("SELECT * FROM artifacts ORDER BY created_at DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def get_artifact(aid: str):
    conn = get_connection()
    cur = conn.execute("SELECT * FROM artifacts WHERE artifact_id = ?", (aid,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def delete_artifact(aid: str):
    conn = get_connection()
    conn.execute("DELETE FROM artifacts WHERE artifact_id = ?", (aid,))
    conn.commit()
    conn.close()

# New CRUD helpers for Chat History Management
def delete_chat(chat_id: str):
    conn = get_connection()
    conn.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()

def rename_chat(chat_id: str, title: str):
    conn = get_connection()
    conn.execute("UPDATE chats SET title = ? WHERE chat_id = ?", (title, chat_id))
    conn.commit()
    conn.close()

def save_message(chat_id: str, role: str, content: str):
    conn = get_connection()
    conn.execute("INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)", (chat_id, role, content))
    conn.commit()
    conn.close()

def get_chat_messages(chat_id: str):
    conn = get_connection()
    cur = conn.execute("SELECT role, content FROM messages WHERE chat_id = ? ORDER BY message_id ASC", (chat_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

# ==========================================
# CRUD: Memories (长期记忆)
# ==========================================
def find_similar_memory(content: str):
    """Exact match for dedup (strip, case-insensitive)."""
    content = (content or "").strip()
    if not content:
        return None
    conn = get_connection()
    cur = conn.execute(
        "SELECT * FROM memories WHERE lower(trim(content)) = lower(?) LIMIT 1",
        (content,),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def add_memory(content: str, kind: str = "fact", importance: int = 1, source: str = "user", dedup: bool = True) -> str:
    content = (content or "").strip()
    if not content:
        raise ValueError("empty memory")
    if dedup:
        existing = find_similar_memory(content)
        if existing:
            mid = existing["memory_id"]
            imp = max(int(existing.get("importance") or 1), int(importance or 1))
            update_memory(mid, content=content, importance=imp, kind=kind or existing.get("kind"))
            return mid
    conn = get_connection()
    mid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO memories (memory_id, kind, content, importance, source) VALUES (?, ?, ?, ?, ?)",
        (mid, kind or "fact", content, int(importance or 1), source or "user"),
    )
    conn.commit()
    conn.close()
    return mid

def list_memories(kind: str = None, limit: int = 50, q: str = None):
    conn = get_connection()
    limit = int(limit or 50)
    q = (q or "").strip()
    if kind and kind not in ("", "all") and q:
        cur = conn.execute(
            "SELECT * FROM memories WHERE kind = ? AND content LIKE ? "
            "ORDER BY importance DESC, updated_at DESC LIMIT ?",
            (kind, f"%{q}%", limit),
        )
    elif kind and kind not in ("", "all"):
        cur = conn.execute(
            "SELECT * FROM memories WHERE kind = ? ORDER BY importance DESC, updated_at DESC LIMIT ?",
            (kind, limit),
        )
    elif q:
        cur = conn.execute(
            "SELECT * FROM memories WHERE content LIKE ? "
            "ORDER BY importance DESC, updated_at DESC LIMIT ?",
            (f"%{q}%", limit),
        )
    else:
        cur = conn.execute(
            "SELECT * FROM memories ORDER BY importance DESC, updated_at DESC LIMIT ?",
            (limit,),
        )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def pin_memory(memory_id: str, pinned: bool = True) -> bool:
    """Pin = importance 5; unpin = importance 2."""
    return update_memory(memory_id, importance=5 if pinned else 2)

def list_recent_chats(limit: int = 5):
    conn = get_connection()
    cur = conn.execute(
        "SELECT chat_id, title, updated_at FROM chats ORDER BY updated_at DESC LIMIT ?",
        (int(limit),),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def list_recent_user_messages(limit: int = 8, max_len: int = 80):
    """Recent user lines across chats for digest context."""
    conn = get_connection()
    cur = conn.execute(
        "SELECT content, created_at FROM messages WHERE role = 'user' "
        "ORDER BY created_at DESC LIMIT ?",
        (int(limit),),
    )
    rows = []
    for r in cur.fetchall():
        c = (r["content"] or "").strip().replace("\n", " ")
        if len(c) > max_len:
            c = c[: max_len - 1] + "…"
        if c:
            rows.append({"content": c, "created_at": r["created_at"]})
    conn.close()
    return rows

def count_artifacts(days: int = 1) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT COUNT(*) AS n FROM artifacts WHERE created_at >= datetime('now', ?)",
            (f"-{int(days)} day",),
        )
        n = cur.fetchone()["n"]
    except Exception:
        n = 0
    conn.close()
    return int(n or 0)

def delete_memory(memory_id: str):
    conn = get_connection()
    conn.execute("DELETE FROM memories WHERE memory_id = ?", (memory_id,))
    conn.commit()
    conn.close()

def update_memory(memory_id: str, content: str = None, importance: int = None, kind: str = None):
    conn = get_connection()
    row = conn.execute("SELECT * FROM memories WHERE memory_id = ?", (memory_id,)).fetchone()
    if not row:
        conn.close()
        return False
    c = content if content is not None else row["content"]
    imp = importance if importance is not None else row["importance"]
    k = kind if kind is not None else row["kind"]
    conn.execute(
        "UPDATE memories SET content = ?, importance = ?, kind = ?, updated_at = CURRENT_TIMESTAMP WHERE memory_id = ?",
        (c, int(imp), k, memory_id),
    )
    conn.commit()
    conn.close()
    return True

def memory_prompt_block(limit: int = 20) -> str:
    rows = list_memories(limit=limit)
    if not rows:
        return ""
    lines = ["USER LONG-TERM MEMORY (local, trusted facts — use when relevant):"]
    for r in rows:
        lines.append(f"- [{r.get('kind') or 'fact'}] {r.get('content')}")
    return "\n".join(lines)

# ==========================================
# Digests (主动日报去重)
# ==========================================
def digest_already_sent(kind: str, day: str) -> bool:
    conn = get_connection()
    cur = conn.execute("SELECT 1 FROM digests WHERE kind = ? AND day = ?", (kind, day))
    ok = cur.fetchone() is not None
    conn.close()
    return ok

def save_digest(kind: str, day: str, content: str) -> str:
    conn = get_connection()
    did = str(uuid.uuid4())
    try:
        conn.execute(
            "INSERT INTO digests (digest_id, kind, day, content) VALUES (?, ?, ?, ?)",
            (did, kind, day, content),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.execute(
            "UPDATE digests SET content = ?, created_at = CURRENT_TIMESTAMP WHERE kind = ? AND day = ?",
            (content, kind, day),
        )
        conn.commit()
        cur = conn.execute("SELECT digest_id FROM digests WHERE kind = ? AND day = ?", (kind, day))
        row = cur.fetchone()
        did = row["digest_id"] if row else did
    conn.close()
    return did

def list_digests(limit: int = 14):
    conn = get_connection()
    cur = conn.execute("SELECT * FROM digests ORDER BY created_at DESC LIMIT ?", (int(limit),))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

# Initialize DB on load to auto-apply schemas
init_db()

if __name__ == "__main__":
    print("Database schema initialized successfully.")
