"""Shared helpers for the Streamlit UI.

Importing this module puts the engine (SAS2PY/) on sys.path, so every page can
`import _lib` and then use the engine's service layer directly. Nothing here
talks to an LLM by itself -- it only wires the UI to `convert_program` and the
knowledge_v2 cards.
"""
from __future__ import annotations

import sys
from pathlib import Path

# ui/ lives inside SAS2PY/, so SAS2PY is one level up and the repo root is two.
SAS2PY = Path(__file__).resolve().parents[1]
REPO = SAS2PY.parents[0]
if str(SAS2PY) not in sys.path:
    sys.path.insert(0, str(SAS2PY))

ARCHIVE_DIR = REPO / "archive" / "legacy_conversions"  # legacy root (pre-workspaces)
WORKSPACES_DIR = REPO / "Workspaces"                 # per-user home folders
KNOWLEDGE_V2_DIR = SAS2PY / "semantic_layer" / "knowledge_v2"
LEARNING_DIR = REPO / "data" / "learning"
USERS_FILE = REPO / "data" / "users" / "users.json"

import streamlit as st
import streamlit.components.v1 as components

from config.models import FREE_MODELS, ModelChoice
from config.settings import LLMConfig
from src.llm.factory import get_client

import auth as _auth
import profiles as _profiles
import store as _store
import theme as _theme
import db as _db


def _load_secret_keys_into_env() -> None:
    """Copy provider API keys from Streamlit secrets into the environment once.

    On the cloud the Groq key lives in st.secrets; the LLM factory reads keys from
    environment variables, so we bridge the two here without ever writing the key
    to disk. Existing env vars (local dev) always win and are never overwritten.
    """
    import os

    env_names = {m.env for m in FREE_MODELS if getattr(m, "env", None)}
    try:
        for name in env_names:
            if not os.getenv(name) and name in st.secrets:
                os.environ[name] = str(st.secrets[name])
    except Exception:
        pass  # no secrets file locally -> nothing to bridge


_load_secret_keys_into_env()


# --------------------------------------------------------------------------- #
# Accounts + per-page setup
# --------------------------------------------------------------------------- #
def user_store():
    """Postgres-backed when DATABASE_URL is configured, else local JSON."""
    if _db.configured():
        import pg_stores
        return pg_stores.PgUserStore()
    return _auth.UserStore(USERS_FILE)


def profile_store():
    if _db.configured():
        import pg_stores
        return pg_stores.PgProfileStore()
    return _profiles.ProfileStore(WORKSPACES_DIR)


def history_store():
    if _db.configured():
        import pg_stores
        return pg_stores.PgHistoryStore(WORKSPACES_DIR)
    return _store.HistoryStore(WORKSPACES_DIR)


def _run_history_migration_once() -> None:
    """Move legacy Conversions_Archive/<user>/* into Workspaces/<user>/conversions/.

    Guarded by a marker file so it runs at most once, and only touches folders
    that match a real username (un-scoped sample runs are left in place). Skipped
    entirely on the Postgres backend, where there is no local legacy tree.
    """
    if _db.configured():
        return
    marker = WORKSPACES_DIR / ".migrated_v1"
    if marker.exists():
        return
    try:
        WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
        usernames = [u.username for u in user_store().list_users()]
        _profiles.migrate_legacy_history(ARCHIVE_DIR, profile_store(), usernames)
        marker.write_text("done", encoding="utf-8")
    except OSError:
        pass  # migration is best-effort; never block the app


def ensure_profile(user: dict) -> None:
    """Create/refresh the signed-in user's workspace folder + account card."""
    try:
        record = user_store().get(user["username"])
        profile_store().ensure(
            user["username"],
            user.get("display_name", user["username"]),
            record.created_at if record else "",
        )
    except OSError:
        pass


def current_user() -> dict | None:
    return st.session_state.get("auth_user")


# Usernames with full knowledge-base authority. Everyone else's approvals are
# queued for an admin to confirm before they take effect.
ADMIN_USERNAMES = {"rahul"}


def is_admin(user: dict | None) -> bool:
    return bool(user) and user.get("username", "") in ADMIN_USERNAMES


def _login_screen() -> None:
    """Render the sign-in / create-account screen and stop the page."""
    _theme.apply_theme()
    _theme.sidebar_brand()
    _theme.hero("Slither", "Sign in to convert your SAS programs to Python and keep your history.", "🐍")
    users = user_store()
    signin, signup = st.tabs(["Sign in", "Create account"])

    with signin:
        with st.form("signin"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("Sign in", type="primary"):
                try:
                    user = users.verify(u, p)
                    st.session_state["auth_user"] = {
                        "username": user.username, "display_name": user.display_name
                    }
                    st.rerun()
                except _auth.AuthError as exc:
                    st.error(str(exc))

    with signup:
        with st.form("signup"):
            u = st.text_input("Choose a username", help="3–32 chars: lowercase letters, numbers, underscore.")
            d = st.text_input("Display name (optional)")
            p = st.text_input("Choose a password", type="password", help="At least 8 characters.")
            if st.form_submit_button("Create account", type="primary"):
                try:
                    user = users.create(u, p, d or None)
                    st.session_state["auth_user"] = {
                        "username": user.username, "display_name": user.display_name
                    }
                    st.success("Account created.")
                    st.rerun()
                except _auth.AuthError as exc:
                    st.error(str(exc))

    st.stop()


def require_login() -> dict:
    """Return the current user, or render the login screen and stop the page."""
    user = current_user()
    if not user:
        _login_screen()
    _run_history_migration_once()
    ensure_profile(user)  # type: ignore[arg-type]
    return user  # type: ignore[return-value]


def _sidebar_user(user: dict) -> None:
    with st.sidebar:
        st.markdown(f"**👤 {user['display_name']}**")
        if st.button("Sign out", use_container_width=True):
            for k in ("auth_user",):
                st.session_state.pop(k, None)
            st.rerun()
        st.divider()


def page_setup(title: str, subtitle: str = "", icon: str = "🧭") -> dict:
    """Standard header for every page: theme, login gate, brand, user chip, hero."""
    user = require_login()
    brand_slot = st.sidebar.container()   # reserve the top-of-sidebar slot for the logo
    theme = _theme.current_theme()        # Streamlit owns the theme (⋮ menu → Settings)
    _theme.apply_theme(theme)             # keep our custom CSS in step with it
    _theme.sidebar_brand(theme, slot=brand_slot)
    _sidebar_user(user)
    _theme.hero(title, subtitle, icon)
    return user


# Re-export theme helpers so pages only import `_lib`.
FAVICON = _theme.FAVICON
hero = _theme.hero
pill = _theme.pill
metric_card = _theme.metric_card


# --------------------------------------------------------------------------- #
# Model / provider selection (driven entirely by config/models.py, so adding a
# new provider there makes it show up here automatically).
# --------------------------------------------------------------------------- #
def _model_index() -> dict[str, ModelChoice]:
    return {m.label: m for m in FREE_MODELS}


def _keep(key: str, default) -> None:
    """Make a sidebar widget's value survive page navigation.

    Streamlit garbage-collects widget-keyed state when the widget isn't rendered
    (e.g. while you're on another page). We mirror the live value into a plain
    shadow key that is never cleaned up, and restore the widget key from it when
    it goes missing -- so the API key, model, and options no longer reset when
    you leave and come back to the Convert page.
    """
    shadow = "_keep_" + key
    if key in st.session_state:
        st.session_state[shadow] = st.session_state[key]
    else:
        st.session_state[key] = st.session_state.get(shadow, default)


def sidebar_config() -> dict:
    """Render the shared model/options sidebar and return the chosen settings.

    Every widget is seeded from a persistent shadow key (see ``_keep``) so its
    value is kept in ``st.session_state`` across page navigation and reruns
    within the session. The API key is held in session state only -- never
    written to disk.
    """
    st.sidebar.header("Model")
    index = _model_index()
    labels = list(index)

    _keep("cfg_model", labels[0])
    if st.session_state.get("cfg_model") not in labels:   # model list changed
        st.session_state["cfg_model"] = labels[0]
    label = st.sidebar.selectbox("Model", labels, key="cfg_model")
    choice = index[label]
    st.sidebar.caption(f"provider: `{choice.provider}` · key env: `{choice.env}`")

    _keep("cfg_api_key", "")
    api_key = st.sidebar.text_input(
        "API key",
        type="password",
        key="cfg_api_key",
        help="Held only for this session; never written to disk. "
        "Leave blank to fall back to the provider's environment variable.",
    )

    st.sidebar.header("Options")
    _keep("cfg_max_attempts", 3)
    max_attempts = st.sidebar.slider("Max debug attempts per step", 1, 5, key="cfg_max_attempts")
    _keep("cfg_use_v2", False)
    use_v2 = st.sidebar.checkbox(
        "Augment with knowledge_v2", key="cfg_use_v2",
        help="Append the structured rule cards for stats/modelling steps.",
    )
    _keep("cfg_use_learning", False)
    use_learning = st.sidebar.checkbox(
        "Use learning memory", key="cfg_use_learning",
        help="Read/write JSON memory so the converter improves across runs.",
    )
    _keep("cfg_optimize", True)
    optimize = st.sidebar.checkbox(
        "Refine final code", key="cfg_optimize",
        help="After every step passes, make one extra LLM pass to consolidate imports, "
        "remove repetition via functions, and tidy the pipeline — then re-run QC. "
        "The refactor is only kept if all outputs still match.",
    )
    return {
        "choice": choice,
        "api_key": (api_key or "").strip() or None,
        "max_attempts": max_attempts,
        "use_v2": use_v2,
        "use_learning": use_learning,
        "optimize": optimize,
    }


def build_client(choice: ModelChoice, api_key: str | None):
    """Build an LLM client for the chosen model, keyed by the UI-entered key."""
    cfg = LLMConfig(
        provider=choice.provider,
        model=choice.model,
        api_key=api_key,        # None -> factory falls back to the env var
        max_tokens=1536,
        reasoning_effort="low",
    )
    return get_client(cfg)


# --------------------------------------------------------------------------- #
# Small utilities
# --------------------------------------------------------------------------- #
def save_upload(uploaded, dest_dir: Path) -> Path:
    """Persist a Streamlit UploadedFile to dest_dir and return the path."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / uploaded.name
    dest.write_bytes(uploaded.getbuffer())
    return dest


def mermaid_from_markdown(md_text: str) -> str:
    """Extract the mermaid body from an er_diagram.md ```mermaid block."""
    if "```mermaid" in md_text:
        body = md_text.split("```mermaid", 1)[1]
        return body.split("```", 1)[0].strip()
    return md_text.strip()


def render_mermaid(code: str, height: int = 520) -> None:
    """Render mermaid source in the page using the mermaid CDN (no extra deps)."""
    html = (
        "<div class='mermaid'>" + code + "</div>"
        "<script type='module'>"
        "import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';"
        "mermaid.initialize({ startOnLoad: true });"
        "</script>"
    )
    components.html(html, height=height, scrolling=True)


def status_badge(status: str) -> str:
    """Return a colored emoji + label for a step/QC status."""
    return {
        "passed": "🟢 passed",
        "unverified": "🟡 unverified",
        "failed": "🔴 failed",
        "skipped": "⚪ skipped",
    }.get(status, status)
