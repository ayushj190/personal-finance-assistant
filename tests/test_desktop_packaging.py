"""Automated tests for standalone macOS application packaging (spec 0023)."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import core.config as config
from ui.desktop_navigation import get_desktop_pages, is_desktop_mode
import desktop_app


class TestDesktopPackaging(unittest.TestCase):
    """Test desktop configurations, navigation restrictions, and lifecycle helpers."""

    def test_config_pfa_data_dir_override(self) -> None:
        """AC-3: Explicit PFA_DATA_DIR environment variable redirects DATA_DIR."""
        target_dir = Path("/tmp/custom_pfa_data")
        with patch.dict(os.environ, {"PFA_DATA_DIR": str(target_dir)}):
            resolved = config.get_default_data_dir()
            self.assertEqual(resolved, target_dir)

    def test_config_macos_desktop_directory_resolution(self) -> None:
        """AC-3: In desktop mode on darwin, resolves to ~/Library/Application Support/PersonalFinanceAssistant."""
        with patch.dict(os.environ, {"PFA_DESKTOP": "1"}, clear=False):
            if "PFA_DATA_DIR" in os.environ:
                del os.environ["PFA_DATA_DIR"]
            with patch("sys.platform", "darwin"):
                with patch.object(config, "DESKTOP", True):
                    resolved = config.get_default_data_dir()
                    expected = Path.home() / "Library" / "Application Support" / "PersonalFinanceAssistant"
                    self.assertEqual(resolved, expected)

    def test_desktop_navigation_page_inventory(self) -> None:
        """AC-5: Desktop navigation exposes Dashboard, Spending, Transactions, and Settings only."""
        with patch.dict(os.environ, {"PFA_DESKTOP": "1"}):
            self.assertTrue(is_desktop_mode())
            from streamlit.testing.v1 import AppTest
            app_path = Path(__file__).resolve().parent.parent / "app.py"
            at = AppTest.from_file(str(app_path))
            at.run(timeout=10)
            self.assertEqual(len(at.exception), 0)
            registered_names = [info.get("page_name") for info in at._registered_pages.values()]
            self.assertEqual(registered_names, ["Dashboard", "Spending", "Transactions", "Settings"])
            self.assertNotIn("Investments", registered_names)
            self.assertNotIn("Mortgage", registered_names)
            self.assertNotIn("Tax Analysis", registered_names)

    def test_desktop_runner_port_finder(self) -> None:
        """AC-1: Loopback socket finds an open TCP port on loopback."""
        port = desktop_app.find_open_port()
        self.assertIsInstance(port, int)
        self.assertGreater(port, 1024)

    def test_desktop_runner_wait_for_server_success(self) -> None:
        """AC-1: Server poller detects HTTP 200 health status."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            ready = desktop_app.wait_for_server(port=8501, timeout=1.0)
            self.assertTrue(ready)

    def test_desktop_runner_wait_for_server_timeout(self) -> None:
        """AC-1: Server poller times out when port unreachable."""
        with patch("urllib.request.urlopen", side_effect=ConnectionRefusedError):
            ready = desktop_app.wait_for_server(port=9999, timeout=0.2)
            self.assertFalse(ready)

    def test_desktop_requirements_profile(self) -> None:
        """AC-4: requirements-desktop.txt excludes heavy ML and broker libraries."""
        req_path = Path(__file__).resolve().parent.parent / "requirements-desktop.txt"
        self.assertTrue(req_path.exists(), "requirements-desktop.txt must exist")
        content = req_path.read_text(encoding="utf-8").lower()

        # Core required dependencies present
        self.assertIn("streamlit", content)
        self.assertIn("plotly", content)
        self.assertIn("pandas", content)
        self.assertIn("pywebview", content)
        self.assertIn("pyinstaller", content)

        # Machine learning dependencies strictly absent
        self.assertNotIn("ollama", content)
        self.assertNotIn("fastembed", content)
        self.assertNotIn("sqlite-vec", content)
        self.assertNotIn("pytr", content)

    def test_pyinstaller_spec_excludes_ml(self) -> None:
        """AC-4, AC-6: desktop_app.spec defines excludes for ML packages and bundle info."""
        spec_path = Path(__file__).resolve().parent.parent / "desktop_app.spec"
        self.assertTrue(spec_path.exists())
        content = spec_path.read_text(encoding="utf-8")

        self.assertIn('"ollama"', content)
        self.assertIn('"fastembed"', content)
        self.assertIn('"sqlite_vec"', content)
        self.assertIn("Personal Finance Assistant.app", content)
        self.assertIn("com.ayush.personalfinanceassistant", content)

    def test_build_mac_script_has_gatekeeper_docs(self) -> None:
        """AC-6: Packaging script includes Gatekeeper quickstart bypass instructions."""
        script_path = Path(__file__).resolve().parent.parent / "scripts" / "build_mac.sh"
        self.assertTrue(script_path.exists())
        content = script_path.read_text(encoding="utf-8")
        self.assertIn("QUICKSTART_GATEKEEPER.txt", content)
        self.assertIn("xattr -cr", content)
        self.assertIn("hdiutil create", content)


if __name__ == "__main__":
    unittest.main()
