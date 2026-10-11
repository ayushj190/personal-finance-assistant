import unittest
from unittest.mock import patch
from agent.copilot_task import CopilotTask


class TestCopilotTask(unittest.TestCase):
    @patch("agent.copilot_task.run_copilot")
    def test_copilot_task_lifecycle(self, mock_run):
        def _dummy_stream():
            yield "Hello "
            yield "world!"

        mock_run.return_value = {
            "role": "assistant",
            "stream": _dummy_stream(),
            "figure": None,
            "df": None,
            "form_request": None,
        }

        task = CopilotTask("Hi", history=[])
        self.assertEqual(task.status, "thinking")
        task.start()

        task.thread.join(timeout=2.0)
        self.assertEqual(task.status, "completed")
        self.assertEqual(task.chunks, ["Hello ", "world!"])
        self.assertIsNone(task.error)

    @patch("agent.copilot_task.run_copilot")
    def test_copilot_task_error(self, mock_run):
        mock_run.side_effect = RuntimeError("Ollama connection failed")

        task = CopilotTask("Hi", history=[])
        task.start()
        task.thread.join(timeout=2.0)

        self.assertEqual(task.status, "error")
        self.assertIn("Ollama connection failed", task.error)
