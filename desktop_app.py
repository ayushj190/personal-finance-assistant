"""Standalone desktop application runner wrapping headless Streamlit with pywebview."""
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


def resolve_data_directory() -> Path:
    """Resolve and create application support data directory (AC-3)."""
    if os.environ.get("PFA_DATA_DIR"):
        data_dir = Path(os.environ["PFA_DATA_DIR"])
    elif sys.platform == "darwin":
        data_dir = Path.home() / "Library" / "Application Support" / "PersonalFinanceAssistant"
    else:
        # Cross platform fallback
        data_dir = Path(__file__).resolve().parent / "data"

    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def find_open_port() -> int:
    """Find an available TCP port on loopback socket."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return sock.getsockname()[1]


def get_app_script_path() -> Path:
    """Resolve absolute path to app.py in source or PyInstaller bundle."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        candidate = base / "app.py"
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parent / "app.py"


def run_streamlit_server(app_path: Path, port: int) -> None:
    """Launch headless Streamlit server on dedicated loopback port."""
    from streamlit.web import cli as stcli

    sys.argv = [
        "streamlit",
        "run",
        str(app_path),
        "--server.headless=true",
        "--server.address=127.0.0.1",
        f"--server.port={port}",
        "--browser.gatherUsageStats=false",
        "--global.developmentMode=false",
    ]
    stcli.main()


def wait_for_server(port: int, timeout: float = 10.0) -> bool:
    """Poll health endpoint until HTTP 200 or timeout."""
    url = f"http://127.0.0.1:{port}/_stcore/health"
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PFA-Desktop"})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


def launch_desktop() -> None:
    """Bootstrap application directories, start server, and display native window (AC-1, AC-2)."""
    data_dir = resolve_data_directory()
    os.environ["PFA_DATA_DIR"] = str(data_dir)
    os.environ["PFA_DESKTOP"] = "1"

    port = find_open_port()
    app_path = get_app_script_path()

    server_thread = threading.Thread(
        target=run_streamlit_server,
        args=(app_path, port),
        daemon=True,
        name="StreamlitDesktopServer",
    )
    server_thread.start()

    if not wait_for_server(port, timeout=10.0):
        print("Error: Streamlit headless server did not start within timeout.", file=sys.stderr)
        sys.exit(1)

    try:
        import webview
    except ImportError:
        print("Error: pywebview is not installed. Install requirements-desktop.txt first.", file=sys.stderr)
        sys.exit(1)

    url = f"http://127.0.0.1:{port}"
    window = webview.create_window(
        title="Personal Finance Assistant",
        url=url,
        width=1280,
        height=840,
        min_size=(960, 640),
    )

    def on_closed() -> None:
        # Cleanly terminate process and all daemon threads immediately
        os._exit(0)

    window.events.closed += on_closed
    webview.start()
    os._exit(0)


if __name__ == "__main__":
    launch_desktop()
