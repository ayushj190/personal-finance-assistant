import threading
import uuid
from typing import Any
from agent.copilot import run_copilot


class CopilotJob:
    def __init__(self, job_id: str, prompt: str, history: list[dict[str, Any]] | None = None, uploaded_files: list[dict[str, Any]] | None = None):
        self.job_id = job_id
        self.prompt = prompt
        self.history = history or []
        self.uploaded_files = uploaded_files
        self.status = "running"  # "running" | "completed" | "error"
        self.accumulated_text = ""
        self.figure = None
        self.df = None
        self.sql = None
        self.form_request = None
        self.error = None
        self._lock = threading.Lock()

    def run(self) -> None:
        try:
            response = run_copilot(
                self.prompt,
                history=self.history,
                uploaded_files=self.uploaded_files,
            )

            with self._lock:
                self.figure = response.get("figure")
                self.df = response.get("df")
                self.sql = response.get("sql")
                if "form_request" in response:
                    self.form_request = response["form_request"]

            stream = response.get("stream", [])
            full_chunks = []
            if hasattr(stream, "__iter__") and not isinstance(stream, (str, bytes)):
                for chunk in stream:
                    full_chunks.append(chunk)
                    with self._lock:
                        self.accumulated_text = "".join(full_chunks)
            elif isinstance(stream, str):
                full_chunks.append(stream)
                with self._lock:
                    self.accumulated_text = stream

            with self._lock:
                self.status = "completed"
        except Exception as e:
            with self._lock:
                self.error = str(e)
                self.status = "error"

    def get_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "status": self.status,
                "accumulated_text": self.accumulated_text,
                "figure": self.figure,
                "df": self.df,
                "sql": self.sql,
                "form_request": self.form_request,
                "error": self.error,
            }


_jobs_lock = threading.Lock()
_jobs: dict[str, CopilotJob] = {}


def start_job(
    prompt: str,
    history: list[dict[str, Any]] | None = None,
    uploaded_files: list[dict[str, Any]] | None = None,
) -> str:
    job_id = str(uuid.uuid4())
    job = CopilotJob(job_id=job_id, prompt=prompt, history=history, uploaded_files=uploaded_files)
    with _jobs_lock:
        _jobs[job_id] = job

    worker_thread = threading.Thread(target=job.run, daemon=True, name=f"copilot-worker-{job_id[:8]}")
    worker_thread.start()
    return job_id


def get_job(job_id: str) -> CopilotJob | None:
    with _jobs_lock:
        return _jobs.get(job_id)


def remove_job(job_id: str) -> None:
    with _jobs_lock:
        _jobs.pop(job_id, None)
