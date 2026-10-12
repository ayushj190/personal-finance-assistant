from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

import config
from db import database


class TestNavigationSmoke(unittest.TestCase):
    """AC-2, AC-4, AC-10: Automated smoke tests for native top navigation and privacy toggle persistence."""

    def setUp(self):
        import sys
        from streamlit.delta_generator import DeltaGenerator, context_dg_stack
        context_dg_stack.set((DeltaGenerator(),))
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.temp_db_path = Path(self.temp_dir.name) / "test_smoke.db"
        database.migrate(self.temp_db_path)

        self._orig_db_paths = {}
        for name, mod in list(sys.modules.items()):
            if hasattr(mod, "DB_PATH"):
                self._orig_db_paths[name] = getattr(mod, "DB_PATH")
                setattr(mod, "DB_PATH", self.temp_db_path)

        self.patches = [
            patch.object(config, "DB_PATH", self.temp_db_path),
            patch("services.task_coordinator.coordinator.submit"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        import sys
        from streamlit.delta_generator import DeltaGenerator, context_dg_stack
        context_dg_stack.set((DeltaGenerator(),))
        for p in reversed(self.patches):
            p.stop()
        for name, orig in self._orig_db_paths.items():
            if name in sys.modules:
                setattr(sys.modules[name], "DB_PATH", orig)
        self.temp_dir.cleanup()

    def test_all_seven_pages_render_without_exception(self):
        """AC-4, AC-10: Verify all 7 pages are reachable and render without exceptions."""
        app_path = Path(__file__).resolve().parent.parent / "app.py"
        at = AppTest.from_file(app_path)
        at.run(timeout=10)
        self.assertEqual(len(at.exception), 0, f"Dashboard threw: {at.exception}")

        expected_pages = [
            "Dashboard",
            "Spending",
            "Investments",
            "Mortgage",
            "Transactions",
            "Tax Analysis",
            "Settings",
        ]
        registered_names = [info.get("page_name") for info in at._registered_pages.values()]
        for expected in expected_pages:
            self.assertIn(expected, registered_names, f"Page {expected} not registered in st.navigation")

        for page_hash, info in at._registered_pages.items():
            page_name = info.get("page_name")
            at._page_hash = page_hash
            at.run(timeout=10)
            self.assertEqual(
                len(at.exception),
                0,
                f"Page '{page_name}' threw exception during execution: {at.exception}",
            )

    def test_privacy_toggle_persists_across_page_navigation(self):
        """AC-2: Verify privacy toggle starts hidden, unmasks on toggle, and persists across page switching."""
        app_path = Path(__file__).resolve().parent.parent / "app.py"
        at = AppTest.from_file(app_path)
        at.run(timeout=10)

        # Initial state should be hidden (True)
        self.assertTrue(at.session_state.get("hide_amounts"))
        self.assertTrue(at.session_state.get("global_privacy_toggle"))

        # Toggle privacy switch to unmask (False)
        privacy_toggle = at.toggle(key="global_privacy_toggle")
        self.assertIsNotNone(privacy_toggle)
        privacy_toggle.set_value(False).run(timeout=10)

        self.assertFalse(at.session_state.get("hide_amounts"))
        self.assertFalse(at.session_state.get("global_privacy_toggle"))

        # Switch to Spending page and verify unmasked state persists
        spending_hash = next(
            h for h, info in at._registered_pages.items() if info.get("page_name") == "Spending"
        )
        at._page_hash = spending_hash
        at.run(timeout=10)

        self.assertFalse(at.session_state.get("hide_amounts"))
        self.assertFalse(at.session_state.get("global_privacy_toggle"))
        self.assertEqual(len(at.exception), 0)

        # Re-mask amounts and switch to Investments
        privacy_toggle = at.toggle(key="global_privacy_toggle")
        privacy_toggle.set_value(True).run(timeout=10)
        self.assertTrue(at.session_state.get("hide_amounts"))

        inv_hash = next(
            h for h, info in at._registered_pages.items() if info.get("page_name") == "Investments"
        )
        at._page_hash = inv_hash
        at.run(timeout=10)

        self.assertTrue(at.session_state.get("hide_amounts"))
        self.assertTrue(at.session_state.get("global_privacy_toggle"))
        self.assertEqual(len(at.exception), 0)

    def test_top_navbar_actions_and_clutter_cleanup_css(self):
        """Verify CSS hides Streamlit dev/status clutter and styles the 3-dots actions menu."""
        css_path = Path("ui/theme/common.css")
        self.assertTrue(css_path.exists())
        content = css_path.read_text(encoding="utf-8")
        self.assertIn('[data-testid="stStatusWidget"]', content)
        self.assertIn('[data-testid="stDeployButton"]', content)
        self.assertIn('.st-key-top_navbar_actions', content)
        self.assertIn('position: fixed', content)


if __name__ == "__main__":
    unittest.main()
