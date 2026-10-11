from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import threading
from typing import Any, Callable, Optional


class TaskStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"


@dataclass
class TaskState:
    name: str
    status: TaskStatus = TaskStatus.IDLE
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    progress: float = 0.0
    message: str = ""
    error: Optional[str] = None
    result: Any = None


class TaskCoordinator:
    """Thread-safe coordinator decoupling background workers from Streamlit session state."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tasks: dict[str, TaskState] = {}
        self._threads: dict[str, threading.Thread] = {}

    def get_state(self, name: str) -> TaskState:
        with self._lock:
            if name not in self._tasks:
                self._tasks[name] = TaskState(name=name)
            t = self._tasks[name]
            # Return shallow copy
            return TaskState(
                name=t.name,
                status=t.status,
                started_at=t.started_at,
                finished_at=t.finished_at,
                progress=t.progress,
                message=t.message,
                error=t.error,
                result=t.result,
            )

    def is_running(self, name: str) -> bool:
        with self._lock:
            state = self._tasks.get(name)
            return state is not None and state.status == TaskStatus.RUNNING

    def update_progress(self, name: str, progress: float, message: str = "") -> None:
        with self._lock:
            if name in self._tasks:
                self._tasks[name].progress = progress
                if message:
                    self._tasks[name].message = message

    def submit(
        self,
        name: str,
        target: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> bool:
        """Submit a background job safely. Returns True if started, False if already running."""
        with self._lock:
            if self.is_running(name):
                return False

            state = TaskState(
                name=name,
                status=TaskStatus.RUNNING,
                started_at=datetime.now(),
                message="Started",
            )
            self._tasks[name] = state

        def worker() -> None:
            try:
                res = target(*args, **kwargs)
                with self._lock:
                    self._tasks[name].status = TaskStatus.SUCCESS
                    self._tasks[name].finished_at = datetime.now()
                    self._tasks[name].progress = 1.0
                    self._tasks[name].result = res
                    self._tasks[name].message = "Completed successfully"
            except Exception as exc:
                with self._lock:
                    self._tasks[name].status = TaskStatus.ERROR
                    self._tasks[name].finished_at = datetime.now()
                    self._tasks[name].error = str(exc)
                    self._tasks[name].message = f"Failed: {exc}"

        thread = threading.Thread(target=worker, name=f"TaskCoordinator-{name}", daemon=True)
        with self._lock:
            self._threads[name] = thread
        thread.start()
        return True


# Global singleton instance for application wide usage
coordinator = TaskCoordinator()
