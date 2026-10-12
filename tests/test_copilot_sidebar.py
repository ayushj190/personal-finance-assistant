import unittest
from unittest.mock import MagicMock
from streamlit.testing.v1 import AppTest
from agent.copilot_task import CopilotTask


def _render_sidebar_app():
    from ui.copilot_sidebar import render_copilot_sidebar
    render_copilot_sidebar()


class TestCopilotSidebar(unittest.TestCase):
    def test_copilot_sidebar_thinking_does_not_block(self):
        """Verify that when a task is in 'thinking' status, the sidebar renders immediately without blocking."""
        at = AppTest.from_function(_render_sidebar_app)
        task = MagicMock(spec=CopilotTask)
        task.status = "thinking"
        at.session_state["copilot_active_task"] = task

        # Must run and complete promptly without hanging
        at.run()
        self.assertIn("copilot_active_task", at.session_state)
        self.assertEqual(at.session_state["copilot_active_task"].status, "thinking")

    def test_copilot_sidebar_completion_updates_history(self):
        """Verify that when a task reaches 'completed', it appends to history and cleans up."""
        at = AppTest.from_function(_render_sidebar_app)
        task = MagicMock(spec=CopilotTask)
        task.status = "completed"
        task.chunks = ["Here is the financial summary."]
        task.figure = None
        task.df = None
        task.form_request = None
        task._lock = MagicMock()
        task._lock.__enter__.return_value = None
        task._lock.__exit__.return_value = None

        at.session_state["copilot_active_task"] = task
        at.run()

        self.assertNotIn("copilot_active_task", at.session_state)
        self.assertEqual(len(at.session_state["copilot_history"]), 1)
        self.assertEqual(
            at.session_state["copilot_history"][0]["content"],
            "Here is the financial summary."
        )

    def test_copilot_sidebar_error_handling(self):
        """Verify that errors in active task are captured and cleared."""
        at = AppTest.from_function(_render_sidebar_app)
        task = MagicMock(spec=CopilotTask)
        task.status = "error"
        task.error = "Connection timed out"

        at.session_state["copilot_active_task"] = task
        at.run()

        self.assertNotIn("copilot_active_task", at.session_state)
        self.assertEqual(len(at.session_state["copilot_history"]), 1)
        self.assertIn("Connection timed out", at.session_state["copilot_history"][0]["content"])


    def test_copilot_sidebar_layout_css(self):
        """Verify that copilot chat history and sidebar container have flex and scroll styles."""
        from pathlib import Path
        css_path = Path("ui/theme/common.css")
        self.assertTrue(css_path.exists())
        content = css_path.read_text(encoding="utf-8")
        self.assertIn(".st-key-copilot_chat_history", content)
        self.assertIn("overflow-y: auto", content)
        self.assertIn("div:has(.st-key-copilot_chat_history)", content)
        self.assertIn(".st-key-copilot_chat_input", content)
        self.assertIn("box-sizing: border-box", content)
        self.assertIn("flex-shrink: 0", content)
        self.assertIn(".st-key-copilot_chat_history::-webkit-scrollbar-thumb", content)
        self.assertIn("overscroll-behavior: contain", content)
        self.assertIn("-webkit-overflow-scrolling: touch", content)
        self.assertIn("margin-top: auto", content)
        self.assertIn("100dvh", content)

    def test_copilot_sidebar_multiple_messages(self):
        """Verify that the sidebar renders with multiple messages without crashing."""
        at = AppTest.from_function(_render_sidebar_app)
        at.session_state["copilot_history"] = [
            {"role": "user", "content": f"User question {i}"} if i % 2 == 0
            else {"role": "assistant", "content": f"Assistant response {i} " + "details " * 20}
            for i in range(8)
        ]
        at.run()
        self.assertEqual(len(at.chat_message), 8)


if __name__ == "__main__":
    unittest.main()

