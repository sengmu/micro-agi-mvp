"""Start the bundled Micro-AGI service inside the Android app process."""

import os
import json
from pathlib import Path
import secrets
import threading


_lock = threading.Lock()
_server_thread = None
_session_token = None
_server = None


def start():
    """Return quickly; Android waits for the embedded health response separately."""
    global _server_thread, _session_token, _server
    with _lock:
        if _server_thread is not None and _server_thread.is_alive():
            return json.dumps({"token": _session_token,
                               "port": _server.server_address[1]})
        home = Path(os.environ["HOME"])
        if not home.is_absolute():
            raise RuntimeError("Android private storage path is unavailable")
        os.environ["MICRO_AGI_DATA_DIR"] = str(home)
        os.environ["MICRO_AGI_EMBEDDED"] = "1"
        _session_token = secrets.token_urlsafe(32)
        # Import only after setting the writable DB path: db initializes on import.
        from app import create_embedded_server, run_server, set_embedded_session_token
        set_embedded_session_token(_session_token)
        _server = create_embedded_server()
        _server_thread = threading.Thread(
            target=run_server, args=(_server,),
            name="micro-agi-embedded-http", daemon=True)
        _server_thread.start()
        return json.dumps({"token": _session_token,
                           "port": _server.server_address[1]})
