"""CodeSense AI — Evolution Dashboard: code quality over time."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

st.set_page_config(
    page_title="CodeSense AI — Evolution",
    page_icon="📊",
    layout="wide",
)

API_BASE = "http://localhost:8000"

st.markdown("# 📊 Code Quality Evolution")
st.markdown("Track how your codebase quality changes across pull requests over time.")
st.divider()

# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    try:
        repos_resp = requests.get(f"{API_BASE}/evolution/repos", timeout=5)
        repos_resp.raise_for_status()
        available_repos = repos_resp.json().get("repos", [])
    except Exception:
        available_repos = []

    repo_options = ["All repositories"] + available_repos
    selected_repo = st.selectbox("Repository", repo_options)
    limit = st.slider("Max data points", 10, 500, 100)

# ── Fetch data ────────────────────────────────────────────────────────────────
params: dict = {"limit": limit}
if selected_repo != "All repositories":
    params["repo"] = selected_repo

try:
    resp = requests.get(f"{API_BASE}/evolution/history", params=params, timeout=10)
    resp.raise_for_status()
    records = resp.json().get("records", [])
except requests.exceptions.ConnectionError:
    st.error("Cannot connect to the backend. Make sure the API is running on port 8000.")
    st.stop()
except Exception as e:
    st.error(f"Failed to load evolution data: {e}")
    st.stop()

if not records:
    st.info(
        "No evolution data yet. Once GitHub webhook reviews run (or you analyze code via the API), "
        "scores will appear here automatically."
    )
    st.markdown("### How to populate this dashboard")
    st.markdown(
        """
        1. **GitHub Webhook** — Set up the webhook in your repo settings. Every PR review is saved automatically.
        2. **Manual trigger** — Use the main analyzer and the scores are recorded per session.

        See the [README](https://github.com/DadaMastan-code/codesense-ai#github-webhook-setup) for setup instructions.
        """
    )
    st.stop()

df = pd.DataFrame(records)
df["timestamp"] = pd.to_datetime(df["timestamp"])
df = df.sort_values("timestamp")

# ── KPI row ───────────────────────────────────────────────────────────────────
col1, col2, col3, col4, col5 = st.columns(5)
latest = df.iloc[-1]
first = df.iloc[0]

col1.metric("Total Reviews", len(df))
col2.metric("Latest Score", f"{latest['overall_score']:.0f}/100",
            delta=f"{latest['overall_score'] - first['overall_score']:+.0f} since first")
col3.metric("Best Score", f"{df['overall_score'].max():.0f}/100")
col4.metric("Avg Security", f"{df['security_score'].mean():.0f}/100")
col5.metric("Total Critical Issues", int(df["critical_issues"].sum()))

st.divider()

# ── Overall score trend ───────────────────────────────────────────────────────
st.subheader("Overall Quality Score Over Time")

fig_overall = go.Figure()
fig_overall.add_trace(go.Scatter(
    x=df["timestamp"],
    y=df["overall_score"],
    mode="lines+markers",
    name="Overall",
    line=dict(color="#6366f1", width=2),
    marker=dict(size=6),
    hovertemplate="<b>%{y:.1f}/100</b><br>%{x|%Y-%m-%d %H:%M}<extra></extra>",
))
# Add reference bands
fig_overall.add_hrect(y0=90, y1=100, fillcolor="#dcfce7", opacity=0.3, line_width=0, annotation_text="Excellent")
fig_overall.add_hrect(y0=70, y1=90, fillcolor="#dbeafe", opacity=0.3, line_width=0, annotation_text="Good")
fig_overall.add_hrect(y0=40, y1=70, fillcolor="#fef9c3", opacity=0.3, line_width=0, annotation_text="Needs Work")
fig_overall.add_hrect(y0=0, y1=40, fillcolor="#fee2e2", opacity=0.3, line_width=0, annotation_text="Critical")
fig_overall.update_layout(
    yaxis=dict(range=[0, 105], title="Score"),
    xaxis_title="Time",
    height=320,
    margin=dict(l=10, r=10, t=20, b=10),
    showlegend=False,
)
st.plotly_chart(fig_overall, use_container_width=True)

# ── Per-agent breakdown ───────────────────────────────────────────────────────
st.subheader("Agent Score Breakdown Over Time")

fig_agents = go.Figure()
agent_cols = [
    ("security_score", "🔒 Security", "#ef4444"),
    ("performance_score", "⚡ Performance", "#f97316"),
    ("architecture_score", "🏗️ Architecture", "#8b5cf6"),
    ("docs_score", "📝 Docs", "#06b6d4"),
]
for col, label, color in agent_cols:
    if col in df.columns:
        fig_agents.add_trace(go.Scatter(
            x=df["timestamp"],
            y=df[col],
            mode="lines+markers",
            name=label,
            line=dict(color=color, width=2),
            marker=dict(size=5),
        ))

fig_agents.update_layout(
    yaxis=dict(range=[0, 105], title="Score"),
    height=320,
    margin=dict(l=10, r=10, t=20, b=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)
st.plotly_chart(fig_agents, use_container_width=True)

# ── Issues trend ──────────────────────────────────────────────────────────────
col_issues, col_dist = st.columns(2)

with col_issues:
    st.subheader("Issues Found Per Review")
    fig_issues = go.Figure()
    if "critical_issues" in df.columns:
        fig_issues.add_trace(go.Bar(
            x=df["timestamp"], y=df["critical_issues"],
            name="Critical", marker_color="#ef4444",
        ))
    if "total_issues" in df.columns:
        fig_issues.add_trace(go.Bar(
            x=df["timestamp"],
            y=df["total_issues"] - df.get("critical_issues", 0),
            name="Other", marker_color="#94a3b8",
        ))
    fig_issues.update_layout(
        barmode="stack", height=280, showlegend=True,
        margin=dict(l=10, r=10, t=20, b=10),
    )
    st.plotly_chart(fig_issues, use_container_width=True)

with col_dist:
    st.subheader("Score Distribution")
    fig_hist = px.histogram(
        df, x="overall_score", nbins=20,
        color_discrete_sequence=["#6366f1"],
        labels={"overall_score": "Overall Score"},
    )
    fig_hist.update_layout(height=280, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig_hist, use_container_width=True)

# ── Data table ────────────────────────────────────────────────────────────────
st.subheader("Review History")
display_cols = ["timestamp", "repo", "pr_number", "pr_title", "overall_score",
                "security_score", "performance_score", "architecture_score",
                "docs_score", "critical_issues", "total_issues", "language"]
display_cols = [c for c in display_cols if c in df.columns]
st.dataframe(
    df[display_cols].sort_values("timestamp", ascending=False).head(50),
    use_container_width=True,
    hide_index=True,
)

st.divider()
st.markdown(
    "<div style='text-align:center;color:#94a3b8;font-size:0.85rem;'>"
    "Evolution tracked by CodeSense AI · "
    "<a href='https://github.com/DadaMastan-code/codesense-ai'>GitHub</a>"
    "</div>",
    unsafe_allow_html=True,
)
