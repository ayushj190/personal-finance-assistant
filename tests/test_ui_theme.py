import re
import unittest
from unittest.mock import patch

import plotly.graph_objects as go
import plotly.io as pio

import ui.theme as theme
from ui.components import finance_card, metric_callout, section_divider
from ui.theme import (
    AMBER,
    COLOR_CASH,
    COLOR_DISCRETIONARY,
    COLOR_FIXED,
    COLOR_INCOME,
    COLOR_INVESTMENT,
    COLOR_LIABILITY,
    COLOR_PALETTE,
    COLOR_SAVINGS,
    COLOR_UNCATEGORIZED,
    EMERALD,
    FINANCIAL_COLOR_MAP,
    FONT_FAMILY_MONO,
    FONT_FAMILY_SANS,
    FONT_SIZE_BASE,
    FONT_SIZE_LG,
    FONT_SIZE_SM,
    FONT_SIZE_XL,
    FONT_SIZE_XS,
    FONT_SIZE_2XL,
    RADIUS_LG,
    RADIUS_MD,
    RADIUS_SM,
    ROSE,
    SEMANTIC_FINANCIAL_COLORS,
    SKY,
    SLATE,
    SPACE_2XL,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    SPACE_XS,
    TEAL,
    VIOLET,
    get_financial_color,
    hex_to_rgba,
    inject_custom_css,
    register_plotly_theme,
    render_chart,
)


class TestUIThemeTokens(unittest.TestCase):
    def test_color_tokens_defined(self):
        self.assertEqual(TEAL, "#2DD4BF")
        self.assertEqual(VIOLET, "#A78BFA")
        self.assertEqual(AMBER, "#FBBF24")
        self.assertEqual(ROSE, "#FB7185")
        self.assertEqual(SKY, "#38BDF8")
        self.assertEqual(EMERALD, "#34D399")
        self.assertEqual(SLATE, "#94A3B8")
        self.assertTrue(len(COLOR_PALETTE) >= 7)

    def test_semantic_financial_signals(self):
        self.assertEqual(COLOR_INCOME, EMERALD)
        self.assertEqual(COLOR_FIXED, ROSE)
        self.assertEqual(COLOR_DISCRETIONARY, AMBER)
        self.assertEqual(COLOR_SAVINGS, TEAL)
        self.assertEqual(COLOR_CASH, TEAL)
        self.assertEqual(COLOR_INVESTMENT, SKY)
        self.assertEqual(COLOR_LIABILITY, ROSE)
        self.assertEqual(COLOR_UNCATEGORIZED, SLATE)

        self.assertEqual(SEMANTIC_FINANCIAL_COLORS["income"], COLOR_INCOME)
        self.assertEqual(SEMANTIC_FINANCIAL_COLORS["fixed"], COLOR_FIXED)
        self.assertEqual(SEMANTIC_FINANCIAL_COLORS["cash"], COLOR_CASH)
        self.assertEqual(SEMANTIC_FINANCIAL_COLORS["investment"], COLOR_INVESTMENT)
        self.assertEqual(SEMANTIC_FINANCIAL_COLORS["liability"], COLOR_LIABILITY)

    def test_spacing_scale_adheres_to_8px_modular(self):
        self.assertEqual(SPACE_XS, 4)
        self.assertEqual(SPACE_SM, 8)
        self.assertEqual(SPACE_MD, 12)
        self.assertEqual(SPACE_LG, 16)
        self.assertEqual(SPACE_XL, 24)
        self.assertEqual(SPACE_2XL, 32)

    def test_border_radii_scale(self):
        self.assertEqual(RADIUS_SM, 8)
        self.assertEqual(RADIUS_MD, 12)
        self.assertEqual(RADIUS_LG, 16)

    def test_typography_tokens(self):
        self.assertIn("Inter", FONT_FAMILY_SANS)
        self.assertIn("JetBrains Mono", FONT_FAMILY_MONO)
        self.assertEqual(FONT_SIZE_XS, "0.75rem")
        self.assertEqual(FONT_SIZE_SM, "0.875rem")
        self.assertEqual(FONT_SIZE_BASE, "1rem")
        self.assertEqual(FONT_SIZE_LG, "1.125rem")
        self.assertEqual(FONT_SIZE_XL, "1.25rem")
        self.assertEqual(FONT_SIZE_2XL, "1.5rem")

    def test_hex_to_rgba_helper(self):
        rgba = hex_to_rgba("#2DD4BF", 0.5)
        self.assertEqual(rgba, "rgba(45, 212, 191, 0.5)")

        rgba_full = hex_to_rgba("#FB7185", 1.0)
        self.assertEqual(rgba_full, "rgba(251, 113, 133, 1.0)")

    def test_get_financial_color(self):
        self.assertEqual(get_financial_color("income"), COLOR_INCOME)
        self.assertEqual(get_financial_color("INCOME"), COLOR_INCOME)
        self.assertEqual(get_financial_color("cash"), COLOR_CASH)
        self.assertEqual(get_financial_color("investment"), COLOR_INVESTMENT)
        self.assertEqual(get_financial_color("liability"), COLOR_LIABILITY)
        self.assertEqual(get_financial_color("unknown_thing"), COLOR_UNCATEGORIZED)


class TestCSSCustomProperties(unittest.TestCase):
    def setUp(self):
        self.common_css = theme.COMMON_CSS_FILE.read_text(encoding="utf-8")
        self.dark_css = theme.DARK_CSS_FILE.read_text(encoding="utf-8")
        self.light_css = theme.LIGHT_CSS_FILE.read_text(encoding="utf-8")

    def test_common_css_tokens(self):
        # Spacing scale
        self.assertIn(f"--space-xs: {SPACE_XS}px;", self.common_css)
        self.assertIn(f"--space-sm: {SPACE_SM}px;", self.common_css)
        self.assertIn(f"--space-md: {SPACE_MD}px;", self.common_css)
        self.assertIn(f"--space-lg: {SPACE_LG}px;", self.common_css)
        self.assertIn(f"--space-xl: {SPACE_XL}px;", self.common_css)
        self.assertIn(f"--space-2xl: {SPACE_2XL}px;", self.common_css)

        # Radii
        self.assertIn(f"--radius-sm: {RADIUS_SM}px;", self.common_css)
        self.assertIn(f"--radius-md: {RADIUS_MD}px;", self.common_css)
        self.assertIn(f"--radius-lg: {RADIUS_LG}px;", self.common_css)

        # Semantic financial signals parity
        self.assertIn(f"--color-income: {COLOR_INCOME};", self.common_css)
        self.assertIn(f"--color-fixed: {COLOR_FIXED};", self.common_css)
        self.assertIn(f"--color-discretionary: {COLOR_DISCRETIONARY};", self.common_css)
        self.assertIn(f"--color-savings: {COLOR_SAVINGS};", self.common_css)
        self.assertIn(f"--color-cash: {COLOR_CASH};", self.common_css)
        self.assertIn(f"--color-investment: {COLOR_INVESTMENT};", self.common_css)
        self.assertIn(f"--color-liability: {COLOR_LIABILITY};", self.common_css)
        self.assertIn(f"--color-uncategorized: {COLOR_UNCATEGORIZED};", self.common_css)

    def test_common_css_containers_and_typography(self):
        self.assertIn(".finance-card", self.common_css)
        self.assertIn(".metric-card", self.common_css)
        self.assertIn(".section-divider", self.common_css)
        self.assertIn(".tabular-nums", self.common_css)
        self.assertIn("tabular-nums", self.common_css)

    def test_dark_and_light_theme_semantic_properties(self):
        for css in [self.dark_css, self.light_css]:
            self.assertIn("--bg-primary:", css)
            self.assertIn("--bg-surface:", css)
            self.assertIn("--bg-surface-elevated:", css)
            self.assertIn("--border-subtle:", css)
            self.assertIn("--text-primary:", css)
            self.assertIn("--text-secondary:", css)
            self.assertIn("--text-muted:", css)

    def test_inject_custom_css_dark(self):
        with patch("streamlit.session_state", {"theme": "dark"}), patch(
            "streamlit.markdown"
        ) as mock_md:
            inject_custom_css()
            mock_md.assert_called_once()
            injected = mock_md.call_args[0][0]
            self.assertIn("<style>", injected)
            self.assertIn("--bg-primary", injected)
            self.assertIn("--space-lg", injected)

    def test_inject_custom_css_light(self):
        with patch("streamlit.session_state", {"theme": "light"}), patch(
            "streamlit.markdown"
        ) as mock_md:
            inject_custom_css()
            mock_md.assert_called_once()
            injected = mock_md.call_args[0][0]
            self.assertIn("<style>", injected)
            self.assertIn("--bg-primary", injected)
            self.assertIn("#F8FAFC", injected)


class TestPlotlyTheme(unittest.TestCase):
    def test_register_plotly_theme(self):
        with patch("streamlit.session_state", {"theme": "dark"}):
            register_plotly_theme()
            self.assertIn("pfa_theme", pio.templates)
            template = pio.templates["pfa_theme"]
            self.assertEqual(template.layout.paper_bgcolor, "rgba(0,0,0,0)")
            self.assertEqual(template.layout.plot_bgcolor, "rgba(0,0,0,0)")
            self.assertEqual(list(template.layout.colorway), COLOR_PALETTE)
            self.assertIn("Inter", template.layout.font.family)

    def test_render_chart(self):
        fig = go.Figure()
        with patch("streamlit.plotly_chart") as mock_chart:
            render_chart(fig)
            mock_chart.assert_called_once()
            called_fig = mock_chart.call_args[0][0]
            self.assertEqual(called_fig.layout.paper_bgcolor, "rgba(0,0,0,0)")
            self.assertEqual(called_fig.layout.plot_bgcolor, "rgba(0,0,0,0)")
            self.assertIsNotNone(called_fig.layout.template)


class TestUIComponentsHelpers(unittest.TestCase):
    def test_finance_card_context_manager(self):
        with patch("streamlit.container") as mock_container, patch("streamlit.markdown") as mock_md:
            with finance_card(title="Assets", subtitle="Current holdings"):
                pass
            mock_container.assert_called_once_with(border=True)
            mock_md.assert_called_once()
            self.assertIn("Assets", mock_md.call_args[0][0])
            self.assertIn("Current holdings", mock_md.call_args[0][0])

    def test_metric_callout_helper(self):
        with patch("ui.components.kpi_card") as mock_kpi:
            metric_callout("Net Worth", "€10,000", "+5%", "Annual change")
            mock_kpi.assert_called_once_with(
                title="Net Worth",
                value_str="€10,000",
                delta_str="+5%",
                subtext="Annual change",
            )

    def test_section_divider_helper(self):
        with patch("streamlit.markdown") as mock_md:
            section_divider()
            mock_md.assert_called_once_with("<hr class='section-divider'/>", unsafe_allow_html=True)


if __name__ == "__main__":
    unittest.main()
