"""Admin-only Users page: browse every account's workspace folder.

Shows each user's non-secret profile (from ``Workspaces/<username>/account.json``)
plus their conversion history. Password hashes never leave the secured auth store,
so nothing sensitive is displayed here. Non-admins are gently redirected.
"""
from __future__ import annotations

import _lib
import streamlit as st

st.set_page_config(page_title="Users · Slither", page_icon=_lib.FAVICON, layout="wide")
user = _lib.page_setup("Users", "Every account and their conversions in one place.", "👥")

if not _lib.is_admin(user):
    st.info("This area is for administrators.")
    st.stop()

users = _lib.user_store().list_users()
profiles = _lib.profile_store()
hist = _lib.history_store()

if not users:
    st.info("No accounts yet.")
    st.stop()

# Overview table -------------------------------------------------------------- #
rows = []
for u in users:
    jobs = hist.list_jobs(u.username)
    rows.append(
        {
            "Username": u.username,
            "Display name": u.display_name,
            "Created": (u.created_at or "")[:10],
            "Conversions": str(len(jobs)),
        }
    )
st.dataframe(rows, hide_index=True, width="stretch")
st.caption(f"Workspaces root: `{_lib.WORKSPACES_DIR}`")
st.divider()

# Per-user detail ------------------------------------------------------------- #
names = [u.username for u in users]
pick = st.selectbox(
    "Inspect a user",
    range(len(names)),
    format_func=lambda i: f"{users[i].display_name} ({names[i]})",
)
chosen = users[pick]

account = profiles.read_account(chosen.username) or {
    "username": chosen.username,
    "display_name": chosen.display_name,
    "created_at": chosen.created_at,
}
col_a, col_b = st.columns([1, 1])
with col_a:
    st.markdown("**Account card** — `account.json`")
    st.json(account)
with col_b:
    st.markdown("**Credentials**")
    st.write(f"- Username: `{chosen.username}`")
    st.write(f"- Display name: {chosen.display_name}")
    st.write(f"- Created: {chosen.created_at or '—'}")
    st.caption(
        "Password is stored as a salted PBKDF2-HMAC-SHA256 hash in "
        "`data/users/users.json` and is never shown or copied here."
    )

st.divider()
st.markdown("**Conversions**")
jobs = hist.list_jobs(chosen.username)
if not jobs:
    st.info("This user hasn't run any conversions yet.")
else:
    job_rows = [
        {
            "When": j.created_display,
            "Program": j.sas_name,
            "Status": j.status,
            "Model": j.model,
            "Steps passed": f"{j.n_passed}/{j.n_steps}",
        }
        for j in jobs
    ]
    st.dataframe(job_rows, hide_index=True, width="stretch")
    st.caption(f"Folder: `{profiles.conversions_dir(chosen.username)}`")
