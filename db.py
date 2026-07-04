import sqlite3
import uuid
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "micro_agi.db")

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

def list_artifacts(project_id: str, type_filter: str = None):
    conn = get_connection()
    if type_filter and type_filter != "all":
        cur = conn.execute("SELECT * FROM artifacts WHERE project_id = ? AND type = ? ORDER BY created_at DESC", (project_id, type_filter))
    else:
        cur = conn.execute("SELECT * FROM artifacts WHERE project_id = ? ORDER BY created_at DESC", (project_id,))
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

# Initialize DB on load to auto-apply schemas
init_db()

if __name__ == "__main__":
    print("Database schema initialized successfully.")
