"""Theme + visual polish for the Streamlit UI.

An Essex Lake Group inspired light/dark palette (Essex blue #00A2E8 on a deep
navy #041C2C) injected as CSS, plus small HTML helpers for the brand logo, a
hero header, status pills, and metric cards.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).resolve().parent / "assets"
FAVICON = str(ASSETS / "essex-favicon.png")

# Essex brand constants (from essexlg.com).
_ESSEX_BLUE = "#00a2e8"
_ESSEX_BLUE_HI = "#33b5ed"
_ESSEX_NAVY = "#041c2c"

_PALETTES = {
    "light": {
        "bg": "#eef3f8",
        "panel": "#ffffff",
        "text": "#041c2c",
        "muted": "#5a6b7a",
        "border": "#d7e2ec",
        "accent": _ESSEX_BLUE,
        "accent2": _ESSEX_BLUE_HI,
        "shadow": "0 2px 10px rgba(4,28,44,.08)",
    },
    "dark": {
        "bg": "#041c2c",
        "panel": "#0a2739",
        "text": "#eaf3fa",
        "muted": "#8fa6b6",
        "border": "#143547",
        "accent": _ESSEX_BLUE_HI,
        "accent2": _ESSEX_BLUE,
        "shadow": "0 2px 12px rgba(0,0,0,.45)",
    },
}

_STATUS_STYLE = {
    "passed": ("#16a34a", "🟢"),
    "unverified": ("#d97706", "🟡"),
    "failed": ("#dc2626", "🔴"),
    "skipped": ("#6b7280", "⚪"),
}


def current_theme() -> str:
    """The active theme ('dark' or 'light'), inferred from Streamlit itself.

    Streamlit owns the theme now (dark by default via .streamlit/config.toml;
    switchable from the top-right ⋮ menu → Settings). Reading it here keeps our
    custom CSS and HTML helpers locked in step with the native components, and it
    persists across pages/reloads because the browser remembers the choice.
    """
    try:
        t = st.context.theme.type
        if t in ("dark", "light"):
            return t
    except Exception:
        pass
    return "dark"


def apply_theme(theme: str | None = None) -> None:
    """Inject the CSS for the active theme. Call once per page after set_page_config."""
    theme = theme or current_theme()
    p = _PALETTES.get(theme, _PALETTES["light"])
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;500;600;700;900&display=swap');
        :root {{
            --bg: {p['bg']}; --panel: {p['panel']}; --text: {p['text']};
            --muted: {p['muted']}; --border: {p['border']};
            --accent: {p['accent']}; --accent2: {p['accent2']}; --shadow: {p['shadow']};
            --navy: {_ESSEX_NAVY};
        }}
        html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"],
        .stButton > button, input, textarea, select {{
            font-family: 'Source Sans 3', -apple-system, 'Segoe UI', Roboto, sans-serif;
        }}
        [data-testid="stAppViewContainer"] {{ background: var(--bg); color: var(--text); }}
        /* Keep the header (and its top-right ⋮ settings menu) visible + themed. */
        [data-testid="stHeader"] {{ background: transparent; }}
        [data-testid="stToolbar"] svg,
        [data-testid="stMainMenu"] svg {{ color: var(--text) !important; fill: var(--text) !important; }}
        /* Trim Streamlit's large default headspace. */
        [data-testid="stAppViewContainer"] .block-container {{
            padding-top: 1.6rem !important; padding-bottom: 2rem !important;
        }}
        [data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{ padding-top: 1rem !important; }}
        [data-testid="stSidebar"] {{
            background: var(--panel); border-right: 1px solid var(--border);
        }}
        /* Native page-nav links (otherwise stay dark-on-navy in dark mode). */
        [data-testid="stSidebarNav"] a span,
        [data-testid="stSidebarNav"] a p,
        [data-testid="stSidebarNav"] * {{ color: var(--text) !important; }}
        [data-testid="stSidebarNav"] a:hover span {{ color: var(--accent) !important; }}
        [data-testid="stSidebarNav"] a[aria-current="page"] span {{
            color: var(--accent) !important; font-weight: 700;
        }}
        h1, h2, h3, h4 {{ font-weight: 700; letter-spacing: -.01em; }}
        /* Text elements inherit the theme colour (fixes dark-on-dark). */
        [data-testid="stAppViewContainer"] h1,
        [data-testid="stAppViewContainer"] h2,
        [data-testid="stAppViewContainer"] h3,
        [data-testid="stAppViewContainer"] h4,
        [data-testid="stAppViewContainer"] h5,
        [data-testid="stAppViewContainer"] h6,
        [data-testid="stAppViewContainer"] p,
        [data-testid="stAppViewContainer"] li,
        [data-testid="stAppViewContainer"] label,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] span,
        [data-testid="stMarkdownContainer"],
        [data-testid="stMarkdownContainer"] * {{ color: var(--text) !important; }}
        [data-testid="stCaptionContainer"],
        [data-testid="stCaptionContainer"] * {{ color: var(--muted) !important; }}
        /* Inline code + expander/tab headers. */
        code {{ color: var(--accent) !important; background: rgba(0,162,232,.12) !important; }}
        [data-baseweb="tab"] {{ color: var(--text) !important; }}
        [data-baseweb="tab-highlight"] {{ background: var(--accent) !important; }}
        summary, [data-testid="stExpander"] summary p {{ color: var(--text) !important; }}
        /* Form inputs. */
        [data-testid="stAppViewContainer"] input,
        [data-testid="stAppViewContainer"] textarea,
        [data-baseweb="select"] > div,
        [data-baseweb="input"] > div {{
            background: var(--panel) !important; color: var(--text) !important;
            border: 1px solid var(--border) !important; border-radius: 8px !important;
        }}
        /* Sidebar model dropdown + API key box need a visible outline too. */
        [data-testid="stSidebar"] [data-baseweb="select"] > div,
        [data-testid="stSidebar"] [data-baseweb="input"] > div,
        [data-testid="stSidebar"] [data-baseweb="base-input"] {{
            border: 1px solid var(--border) !important; border-radius: 8px !important;
            background: var(--panel) !important;
        }}
        /* Accent the outline when the field is focused so it reads as editable. */
        [data-baseweb="select"] > div:focus-within,
        [data-baseweb="input"] > div:focus-within {{
            border-color: var(--accent) !important;
            box-shadow: 0 0 0 2px rgba(0,162,232,.20) !important;
        }}
        /* Portaled overlays (dropdown menus, popovers, dialogs, tooltips) render
           OUTSIDE stAppViewContainer, so theme them explicitly to avoid
           white-on-white or invisible text when the palette is dark. */
        [data-baseweb="popover"] [role="listbox"],
        [data-baseweb="popover"] [data-baseweb="menu"],
        [data-baseweb="menu"] {{
            background: var(--panel) !important; border: 1px solid var(--border) !important;
        }}
        [data-baseweb="popover"] [role="option"],
        [data-baseweb="menu"] li,
        [data-baseweb="popover"] [role="option"] * {{ color: var(--text) !important; }}
        [data-baseweb="popover"] [role="option"]:hover,
        [data-baseweb="menu"] li:hover {{ background: rgba(0,162,232,.14) !important; }}
        [data-testid="stDialog"] > div,
        [role="dialog"] {{ background: var(--panel) !important; color: var(--text) !important; }}
        [role="tooltip"], [data-baseweb="tooltip"] {{
            background: var(--panel) !important; color: var(--text) !important;
            border: 1px solid var(--border) !important;
        }}
        /* Dataframes / tables inherit the theme surface + text. */
        [data-testid="stDataFrame"], [data-testid="stTable"] {{
            background: var(--panel) !important; color: var(--text) !important;
        }}
        .stButton > button[kind="primary"] {{
            background: var(--accent); border: 0; font-weight: 600; color: #fff !important;
            box-shadow: 0 2px 8px rgba(0,162,232,.35);
        }}
        .stButton > button[kind="primary"]:hover {{ background: {_ESSEX_BLUE_HI}; }}
        .stButton > button[kind="secondary"] {{
            background: var(--panel); color: var(--text) !important;
            border: 1px solid var(--border);
        }}
        .stButton > button[kind="secondary"]:hover {{ border-color: var(--accent); color: var(--accent) !important; }}
        /* Brand lockup in the sidebar. */
        [data-testid="stLogo"] {{ height: 3rem !important; width: auto !important; margin: .2rem 0 .1rem; }}
        .s2p-brand-tag {{ font-weight:700; font-size:1.02rem; color:var(--text); line-height:1.1; }}
        .s2p-brand-tag small {{ display:block; font-weight:500; font-size:.72rem;
            color:var(--muted); letter-spacing:.02em; }}
        .s2p-hero {{
            padding: 24px 28px; border-radius: 18px; margin-bottom: 16px;
            background: linear-gradient(120deg, var(--navy) 0%, var(--accent) 130%);
            color: #fff; box-shadow: var(--shadow);
            border: 1px solid rgba(255,255,255,.06);
        }}
        .s2p-hero h1 {{ margin: 0; font-size: 1.75rem; font-weight:900; color:#fff !important; }}
        .s2p-hero p {{ margin: 6px 0 0; opacity: .92; color:#eaf3fa !important; }}
        /* Force all hero text white regardless of the theme text-colour rules. */
        [data-testid="stMarkdownContainer"] .s2p-hero,
        [data-testid="stMarkdownContainer"] .s2p-hero * {{ color: #fff !important; }}
        .s2p-pill {{
            display: inline-block; padding: 2px 10px; border-radius: 999px;
            font-size: .78rem; font-weight: 600; color: #fff;
        }}
        .s2p-card {{
            background: var(--panel); border: 1px solid var(--border);
            border-radius: 14px; padding: 16px 18px; box-shadow: var(--shadow);
            border-top: 3px solid var(--accent);
        }}
        .s2p-card .big {{ font-size: 1.7rem; font-weight: 700; color: var(--text) !important; }}
        .s2p-card .lbl {{ color: var(--muted) !important; font-size: .82rem; text-transform: uppercase;
            letter-spacing: .04em; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def hero(title: str, subtitle: str = "", icon: str = "🧭") -> None:
    st.markdown(
        f"<div class='s2p-hero'><h1>{icon} {title}</h1>"
        + (f"<p>{subtitle}</p>" if subtitle else "")
        + "</div>",
        unsafe_allow_html=True,
    )


def pill(status: str) -> str:
    color, emoji = _STATUS_STYLE.get(status, ("#6b7280", "•"))
    return f"<span class='s2p-pill' style='background:{color}'>{emoji} {status}</span>"


def metric_card(label: str, value, help_text: str = "") -> None:
    st.markdown(
        f"<div class='s2p-card'><div class='lbl'>{label}</div>"
        f"<div class='big'>{value}</div>"
        + (f"<div style='color:var(--muted);font-size:.8rem'>{help_text}</div>" if help_text else "")
        + "</div>",
        unsafe_allow_html=True,
    )


def _logo_svg(theme: str) -> str:
    """Return the inline Essex wordmark SVG for the active theme (white on dark)."""
    name = "essex-logo-white.svg" if theme == "dark" else "essex-logo-black.svg"
    try:
        svg = (ASSETS / name).read_text(encoding="utf-8")
    except OSError:
        return ""
    if svg.lstrip().startswith("<?xml"):
        svg = svg.split("?>", 1)[1]
    return svg.strip()


def sidebar_brand(theme: str | None = None, slot=None) -> None:
    """Pin the Essex logo to the very top of the sidebar (above the page nav).

    ``st.logo`` renders above Streamlit's native navigation; the product tagline
    goes into ``slot`` (a reserved sidebar container) so it sits near the top too.
    """
    theme = theme or current_theme()
    logo = str(ASSETS / ("essex-logo-white.svg" if theme == "dark" else "essex-logo-black.svg"))
    try:
        st.logo(logo, size="large", link="https://essexlg.com")
    except Exception:
        pass
    target = slot if slot is not None else st.sidebar
    target.markdown(
        "<div class='s2p-brand-tag'>Slither<small>SAS → Python · Essex Lake Group</small></div>",
        unsafe_allow_html=True,
    )
    target.divider()
