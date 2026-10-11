"""Vector brand logos for financial institutions."""
import html

_LOGOS: dict[str, str] = {
    "abn": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="{size}" height="{size}">
  <rect width="24" height="24" rx="5" fill="#008269"/>
  <path d="M4 18 L12 6 L20 18 Z" fill="#FDB813"/>
  <path d="M12 6 L20 18 L12 18 Z" fill="#008269"/>
</svg>""",
    "revolut": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="{size}" height="{size}">
  <rect width="24" height="24" rx="5" fill="#191C1F"/>
  <path d="M7 6 h5.5 c2.5 0 4 1.5 4 3.5 c0 1.6 -1 2.8 -2.4 3.2 L17 18 h-2.5 l-2.5 -5 H9.2 v5 H7 V6 z M9.2 8 v3 h3.2 c1.2 0 2 -0.6 2 -1.5 s-0.8 -1.5 -2 -1.5 H9.2 z" fill="#FFFFFF"/>
</svg>""",
    "etoro": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="{size}" height="{size}">
  <rect width="24" height="24" rx="5" fill="#12C175"/>
  <path d="M6 7.5 C6 5.5 8 5 9 6.5 C10 8 11.5 10 12 10.5 C12.5 10 14 8 15 6.5 C16 5 18 5.5 18 7.5 C18 11 15 13.5 13 14.5 L13 19 C13 19.5 12.5 20 12 20 C11.5 20 11 19.5 11 19 L11 14.5 C9 13.5 6 11 6 7.5 Z" fill="#FFFFFF"/>
</svg>""",
    "trade republic": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="{size}" height="{size}">
  <rect width="24" height="24" rx="5" fill="#111827"/>
  <path d="M6 7 h12 v2.5 H6 z M10.5 9.5 h3 V17 h-3 z M6 14.5 h4.5 V17 H6 z" fill="#FFFFFF"/>
</svg>""",
    "ing": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="{size}" height="{size}">
  <rect width="24" height="24" rx="5" fill="#FF6200"/>
  <path d="M7 16 C6 14 7 11 9 9.5 C11 8 13.5 8 15 9.5 C16.5 11 18 11.5 18 13 C18 15.5 15.5 16.5 13 16.5 L7 16 Z M11 11.5 C10.5 11.5 10 12 10 12.5 C10 13 10.5 13.5 11 13.5 C11.5 13.5 12 13 12 12.5 C12 12 11.5 11.5 11 11.5 Z" fill="#FFFFFF"/>
</svg>""",
    "rabobank": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="{size}" height="{size}">
  <rect width="24" height="24" rx="5" fill="#000066"/>
  <circle cx="12" cy="8.5" r="3" fill="#FD5F00"/>
  <path d="M6 18 C6 14 9 12.5 12 12.5 C15 12.5 18 14 18 18 Z" fill="#FD5F00"/>
</svg>""",
    "bunq": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="{size}" height="{size}">
  <rect width="24" height="24" rx="5" fill="#1E293B"/>
  <circle cx="12" cy="12" r="7" fill="none" stroke="#38BDF8" stroke-width="2"/>
  <circle cx="12" cy="12" r="4" fill="none" stroke="#FBBF24" stroke-width="2"/>
</svg>""",
    "default": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="{size}" height="{size}">
  <rect width="24" height="24" rx="5" fill="#334155"/>
  <path d="M4 10 L12 5 L20 10 H4 Z M6 11 H8 V17 H6 Z M11 11 H13 V17 H11 Z M16 11 H18 V17 H16 Z M4 18 H20 V20 H4 Z" fill="#FFFFFF"/>
</svg>"""
}


def get_institution_logo_svg(institution: str | None, size: int = 22) -> str:
    """Return an inline SVG markup for the institution logo."""
    inst = (institution or "").lower()
    svg_template = _LOGOS["default"]
    for key, template in _LOGOS.items():
        if key != "default" and key in inst:
            svg_template = template
            break
    return svg_template.format(size=size)
