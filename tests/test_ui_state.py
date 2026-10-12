import unittest
from unittest.mock import MagicMock, patch
import streamlit as st

from ui import state
from ui.state import K


class TestUIState(unittest.TestCase):
    def setUp(self):
        # Clear or mock session_state for test isolation
        if hasattr(st, "session_state"):
            for k in list(st.session_state.keys()):
                del st.session_state[k]

    def test_constants_defined(self):
        self.assertEqual(K.THEME, "theme")
        self.assertEqual(K.PRIVACY_HIDDEN, "hide_amounts")
        self.assertEqual(K.GLOBAL_PRIVACY_TOGGLE, "global_privacy_toggle")
        self.assertEqual(K.COPILOT_HISTORY, "copilot_history")
        self.assertTrue(hasattr(K, "DASHBOARD_SANKEY_DRILLDOWN"))
        self.assertTrue(hasattr(K, "TV_WATCHLIST_MINIMIZED"))

    def test_get_set_has_delete(self):
        self.assertFalse(state.has(K.THEME))
        self.assertEqual(state.get(K.THEME, "default_val"), "default_val")

        state.set(K.THEME, "light")
        self.assertTrue(state.has(K.THEME))
        self.assertEqual(state.get(K.THEME), "light")

        state.delete(K.THEME)
        self.assertFalse(state.has(K.THEME))

    def test_init_defaults(self):
        state.init_defaults()
        self.assertEqual(state.get(K.THEME), "dark")
        self.assertTrue(state.get(K.PRIVACY_HIDDEN))
        self.assertTrue(state.get(K.GLOBAL_PRIVACY_TOGGLE))
        self.assertEqual(state.get(K.COPILOT_HISTORY), [])


if __name__ == "__main__":
    unittest.main()
