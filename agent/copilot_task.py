import threading
from typing import Any
from agent.copilot import run_copilot


class CopilotTask:
    """Threaded background execution task for Copilot turns.

    Runs LLM inference and tool calling asynchronously in a background thread so that
    Streamlit UI reruns (such as toggling 'Hide values') do not abort or cancel the execution.
    """

    def __init__(
        self,
        prompt: str,
        history: list[dict[str, Any]] | None = None,
        uploaded_files: list[dict[str, Any]] | None = None,
    ):
        self.prompt = prompt
        self.history = history or []
        self.uploaded_files = uploaded_files
        self.status: str = "thinking"  # "thinking" | "typing" | "completed" | "error"
        self.chunks: list[str] = []
        self.figure: Any = None
        self.df: Any = None
        self.form_request: Any = None
        self.citations: Any = None
        self.diagnostics: list[dict[str, Any]] = []
        self.error: str | None = None
        self._lock = threading.Lock()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        self.thread = threading.Thread(
            target=self._run, daemon=True, name="copilot-task-worker"
        )
        try:
            from streamlit.runtime.scriptrunner import add_script_run_ctx

            add_script_run_ctx(self.thread)
        except Exception:
            pass
        self.thread.start()

    def _run(self) -> None:
        try:
            res = run_copilot(
                user_message=self.prompt,
                history=self.history,
                uploaded_files=self.uploaded_files,
            )
            with self._lock:
                self.figure = res.get("figure")
                self.df = res.get("df")
                self.form_request = res.get("form_request")
                self.citations = res.get("citations")
                self.diagnostics = res.get("diagnostics") or []
                self.status = "typing"

            stream = res.get("stream", [])
            for chunk in stream:
                with self._lock:
                    self.chunks.append(chunk)

            with self._lock:
                self.status = "completed"
        except Exception as e:
            with self._lock:
                self.error = str(e)
                self.status = "error"
