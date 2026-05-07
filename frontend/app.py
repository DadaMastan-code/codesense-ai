"""CodeSense AI — Streamlit frontend."""
from __future__ import annotations

import json
import time
from typing import Any

import plotly.graph_objects as go
import requests
import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CodeSense AI",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

API_BASE = "http://localhost:8000"

# ── Sample code snippets ───────────────────────────────────────────────────────
SAMPLES: dict[str, str] = {
    "Python – Vulnerable Login": '''\
import sqlite3
import hashlib

def login(username, password):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    # Vulnerable to SQL injection
    query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
    cursor.execute(query)
    user = cursor.fetchone()
    if user:
        return {"status": "ok", "user": user}
    return {"status": "error"}

def hash_password(password):
    # Using weak MD5 hashing
    return hashlib.md5(password.encode()).hexdigest()

def get_all_users(admin_id):
    conn = sqlite3.connect("users.db")
    # No authentication check — any caller can list users
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    return cursor.fetchall()
''',
    "Python – O(n²) Performance": '''\
def find_duplicates(items):
    duplicates = []
    for i in range(len(items)):
        for j in range(len(items)):
            if i != j and items[i] == items[j]:
                if items[i] not in duplicates:
                    duplicates.append(items[i])
    return duplicates

def get_user_posts(user_ids):
    import sqlite3
    conn = sqlite3.connect("blog.db")
    posts = []
    for uid in user_ids:   # N+1 query problem
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM posts WHERE user_id = {uid}")
        posts.extend(cursor.fetchall())
    return posts

def flatten(nested):
    result = ""
    for lst in nested:
        for item in lst:
            result = result + str(item) + ","  # string concat in loop
    return result
''',
    "JavaScript – XSS & Secrets": '''\
const API_KEY = "sk-prod-abc123xyz789-secret";
const DB_PASSWORD = "hunter2";

function renderUserInput(input) {
    // Stored XSS vulnerability
    document.getElementById("output").innerHTML = input;
}

async function fetchUserData(userId) {
    const res = await fetch(`/api/users/${userId}`);
    const data = await res.json();
    // No error handling, no auth check
    return data;
}

function processItems(items) {
    var results = [];
    for (var i = 0; i < items.length; i++) {
        for (var j = 0; j < items.length; j++) {
            if (items[i].id === items[j].parentId) {
                results.push({...items[i], child: items[j]});
            }
        }
    }
    return results;
}
''',
    "Python – God Class": '''\
class Application:
    def __init__(self):
        self.db = None
        self.users = []
        self.orders = []
        self.config = {}

    def connect_database(self, url):
        import psycopg2
        self.db = psycopg2.connect(url)

    def create_user(self, name, email, password):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO users VALUES (%s, %s, %s)", (name, email, password))

    def send_email(self, to, subject, body):
        import smtplib
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.sendmail("app@example.com", to, body)

    def process_payment(self, amount, card_number, cvv):
        # Payment logic mixed in with everything else
        if len(str(card_number)) == 16:
            return {"status": "charged", "amount": amount}

    def generate_report(self, report_type):
        if report_type == "sales":
            return sum(o["amount"] for o in self.orders)
        elif report_type == "users":
            return len(self.users)
        elif report_type == "inventory":
            return {"items": 42}

    def backup_database(self):
        import subprocess
        subprocess.run(f"pg_dump mydb > backup.sql", shell=True)
''',
    "Java – Missing Error Handling": '''\
import java.io.*;
import java.net.*;
import java.sql.*;

public class DataProcessor {
    private static String dbUrl = "jdbc:mysql://localhost/mydb?user=root&password=root123";

    public String readFile(String path) throws Exception {
        BufferedReader reader = new BufferedReader(new FileReader(path));
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) {
            sb.append(line);
        }
        // reader never closed — resource leak
        return sb.toString();
    }

    public Object fetchData(String userId) throws Exception {
        Connection conn = DriverManager.getConnection(dbUrl);
        Statement stmt = conn.createStatement();
        // SQL injection + connection never closed
        ResultSet rs = stmt.executeQuery("SELECT * FROM users WHERE id=" + userId);
        return rs.next() ? rs.getObject(1) : null;
    }

    public void processAll(String[] ids) {
        for (String id : ids) {
            try {
                Object data = fetchData(id);
                System.out.println(data);
            } catch (Exception e) {
                // Swallowing exceptions silently
            }
        }
    }
}
''',
}

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .main-title { font-size: 2.8rem; font-weight: 800; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  .tagline { color: #64748b; font-size: 1.1rem; margin-top: -0.5rem; }
  .score-badge { display: inline-block; padding: 0.3rem 0.9rem; border-radius: 999px; font-weight: 700; font-size: 1rem; }
  .badge-excellent { background: #dcfce7; color: #166534; }
  .badge-good { background: #dbeafe; color: #1e40af; }
  .badge-needs_work { background: #fef9c3; color: #854d0e; }
  .badge-critical { background: #fee2e2; color: #991b1b; }
  .agent-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 1rem; margin: 0.5rem 0; }
  .severity-critical { color: #dc2626; font-weight: 700; }
  .severity-high { color: #ea580c; font-weight: 700; }
  .severity-medium { color: #d97706; font-weight: 600; }
  .severity-low { color: #65a30d; font-weight: 600; }
  .severity-info { color: #6366f1; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────
def severity_badge(severity: str) -> str:
    colours = {
        "CRITICAL": "🔴",
        "HIGH": "🟠",
        "MEDIUM": "🟡",
        "LOW": "🟢",
        "INFO": "🔵",
    }
    return colours.get(severity.upper(), "⚪")


def score_colour(score: float) -> str:
    if score >= 90:
        return "badge-excellent"
    if score >= 70:
        return "badge-good"
    if score >= 40:
        return "badge-needs_work"
    return "badge-critical"


def gauge_chart(score: float, title: str = "CodeSense Score") -> go.Figure:
    rating_colour = "#22c55e" if score >= 90 else "#3b82f6" if score >= 70 else "#f59e0b" if score >= 40 else "#ef4444"
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        domain={"x": [0, 1], "y": [0, 1]},
        title={"text": title, "font": {"size": 18}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1},
            "bar": {"color": rating_colour},
            "steps": [
                {"range": [0, 40], "color": "#fee2e2"},
                {"range": [40, 70], "color": "#fef9c3"},
                {"range": [70, 90], "color": "#dbeafe"},
                {"range": [90, 100], "color": "#dcfce7"},
            ],
            "threshold": {"line": {"color": "black", "width": 2}, "thickness": 0.75, "value": score},
        },
    ))
    fig.update_layout(height=250, margin=dict(l=20, r=20, t=40, b=20))
    return fig


def call_api(endpoint: str, payload: dict) -> dict | None:
    try:
        resp = requests.post(f"{API_BASE}{endpoint}", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to the backend. Make sure the API is running on port 8000.")
        return None
    except requests.exceptions.HTTPError as e:
        st.error(f"API error: {e.response.text}")
        return None
    except Exception as e:
        st.error(f"Unexpected error: {e}")
        return None


def stream_analysis(code: str, language: str | None, context: str | None):
    payload: dict[str, Any] = {"code": code}
    if language and language != "Auto-detect":
        payload["language"] = language.lower()
    if context:
        payload["context"] = context

    try:
        with requests.post(
            f"{API_BASE}/analyze/stream",
            json=payload,
            stream=True,
            timeout=120,
            headers={"Accept": "text/event-stream"},
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line and line.startswith(b"data: "):
                    raw = line[6:].decode()
                    if raw == "[DONE]":
                        return
                    yield json.loads(raw)
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to the backend. Make sure the API is running on port 8000.")


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<h1 class="main-title">🔍 CodeSense AI</h1>', unsafe_allow_html=True)
st.markdown('<p class="tagline">Code review powered by a team of AI agents — security, performance, architecture, tests & docs</p>', unsafe_allow_html=True)
st.divider()

# ── Layout ────────────────────────────────────────────────────────────────────
left, right = st.columns([1, 1], gap="large")

with left:
    st.subheader("Input")

    # Sample loader
    sample_choice = st.selectbox("Load a sample snippet", ["— choose —"] + list(SAMPLES.keys()))
    if sample_choice != "— choose —":
        st.session_state["code_input"] = SAMPLES[sample_choice]

    code = st.text_area(
        "Paste your code here",
        value=st.session_state.get("code_input", ""),
        height=380,
        placeholder="# Paste any code here — Python, JS, Java, Go, Rust, C++, ...",
        key="code_area",
    )

    lang_options = ["Auto-detect"] + [l.capitalize() for l in [
        "python", "javascript", "typescript", "java", "cpp", "csharp", "go", "rust", "php", "ruby", "swift", "kotlin"
    ]]
    col1, col2 = st.columns(2)
    with col1:
        language = st.selectbox("Language", lang_options)
    with col2:
        mode = st.radio("Mode", ["Full (6 agents)", "Quick (3 agents)"], horizontal=True)

    context = st.text_input(
        "Context (optional)",
        placeholder="e.g. 'This is a REST API authentication handler'",
    )

    use_streaming = st.toggle("Live streaming mode", value=True)

    analyze_btn = st.button("🚀 Analyse Code", type="primary", use_container_width=True, disabled=not code.strip())

# ── Analysis ──────────────────────────────────────────────────────────────────
with right:
    st.subheader("Results")

    if not analyze_btn:
        st.info("Paste your code on the left and click **Analyse Code** to begin.")
        st.stop()

    payload: dict[str, Any] = {"code": code}
    if language != "Auto-detect":
        payload["language"] = language.lower()
    if context:
        payload["context"] = context

    result: dict[str, Any] = {}
    agent_status: dict[str, str] = {
        "security": "⏳", "performance": "⏳", "architecture": "⏳",
        "tests": "⏳", "documentation": "⏳", "fix": "⏳",
    }

    # Progress display
    progress_cols = st.columns(6)
    progress_placeholders = {}
    for idx, name in enumerate(agent_status):
        with progress_cols[idx]:
            progress_placeholders[name] = st.empty()
            progress_placeholders[name].markdown(f"**{name.title()}**\n\n{agent_status[name]}")

    if use_streaming:
        with st.spinner("Agents working..."):
            for event in stream_analysis(code, language if language != "Auto-detect" else None, context or None):
                agent = event.get("agent", "")
                agent_result = event.get("result", {})
                if agent == "language_detected":
                    result["language"] = agent_result.get("language", "unknown")
                    continue
                result[agent] = agent_result
                if agent in agent_status:
                    agent_status[agent] = "✅"
                    progress_placeholders[agent].markdown(f"**{agent.title()}**\n\n✅")
    else:
        with st.spinner("Running all agents in parallel..."):
            api_result = call_api("/analyze", payload)
            if api_result:
                result = api_result
                for name in agent_status:
                    agent_status[name] = "✅"
                    progress_placeholders[name].markdown(f"**{name.title()}**\n\n✅")

    if not result:
        st.stop()

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tabs = st.tabs(["📊 Overview", "🔐 Security", "⚡ Performance", "🏗 Architecture", "🧪 Tests", "📚 Docs", "🔧 Fixed Code"])

    # ── Tab 1: Overview ───────────────────────────────────────────────────────
    with tabs[0]:
        score_data = result.get("score", {})
        total = score_data.get("total", 0)
        rating = score_data.get("rating", "NEEDS WORK")
        lang_detected = result.get("language", "unknown")

        col_gauge, col_meta = st.columns([1, 1])
        with col_gauge:
            st.plotly_chart(gauge_chart(total), use_container_width=True)
        with col_meta:
            st.markdown(f"**Language detected:** `{lang_detected}`")
            st.markdown(f"**Overall rating:** <span class='score-badge {score_colour(total)}'>{rating}</span>", unsafe_allow_html=True)
            elapsed = result.get("analysis_time_seconds", 0)
            if elapsed:
                st.markdown(f"**Analysis time:** {elapsed:.1f}s")

            # Mini score cards
            sub_scores = [
                ("🔐 Security", score_data.get("security", 0), 40),
                ("⚡ Performance", score_data.get("performance", 0), 30),
                ("🏗 Architecture", score_data.get("architecture", 0), 20),
                ("📚 Documentation", score_data.get("documentation", 0), 10),
            ]
            for label, val, weight in sub_scores:
                st.markdown(f"**{label}** (weight {weight}%): `{val:.0f}/100`")
                st.progress(val / 100)

        # Issue summary counts
        sec_count = len(result.get("security", {}).get("findings", []))
        perf_count = len(result.get("performance", {}).get("issues", []))
        arch_count = len(result.get("architecture", {}).get("suggestions", []))
        test_count = len(result.get("tests", {}).get("test_cases", []))

        cols = st.columns(4)
        cols[0].metric("Security Issues", sec_count, delta=None)
        cols[1].metric("Perf Issues", perf_count, delta=None)
        cols[2].metric("Arch Suggestions", arch_count, delta=None)
        cols[3].metric("Tests Generated", test_count, delta=None)

    # ── Tab 2: Security ───────────────────────────────────────────────────────
    with tabs[1]:
        sec = result.get("security", {})
        if sec.get("error"):
            st.error(f"Security analysis error: {sec['error']}")
        else:
            st.markdown(f"**Summary:** {sec.get('summary', 'No summary.')}")
            findings = sec.get("findings", [])
            if not findings:
                st.success("No security issues found.")
            for f in findings:
                sev = f.get("severity", "INFO")
                with st.expander(f"{severity_badge(sev)} [{sev}] {f.get('title', '')} — {f.get('owasp_category', '')}"):
                    st.markdown(f"**Description:** {f.get('description', '')}")
                    st.markdown(f"**Fix:** {f.get('fix_recommendation', '')}")
                    st.markdown(f"**OWASP Reference:** {f.get('owasp_reference', '')}")
                    if f.get("line_number"):
                        st.markdown(f"**Line:** {f['line_number']}")

    # ── Tab 3: Performance ────────────────────────────────────────────────────
    with tabs[2]:
        perf = result.get("performance", {})
        if perf.get("error"):
            st.error(f"Performance analysis error: {perf['error']}")
        else:
            st.markdown(f"**Summary:** {perf.get('summary', 'No summary.')}")

            complexity = perf.get("complexity_analysis", [])
            if complexity:
                st.markdown("#### Complexity Analysis")
                for c in complexity:
                    st.markdown(
                        f"- **`{c.get('function_name')}`** — Time: `{c.get('time_complexity')}`, Space: `{c.get('space_complexity')}` — {c.get('explanation', '')}"
                    )

            issues = perf.get("issues", [])
            if not issues:
                st.success("No performance issues found.")
            for issue in issues:
                sev = issue.get("severity", "INFO")
                with st.expander(f"{severity_badge(sev)} [{sev}] {issue.get('title', '')}"):
                    st.markdown(issue.get("description", ""))
                    if issue.get("before_code") or issue.get("after_code"):
                        bc, ac = st.columns(2)
                        with bc:
                            st.markdown("**Before**")
                            st.code(issue.get("before_code", ""), language="python")
                        with ac:
                            st.markdown("**After**")
                            st.code(issue.get("after_code", ""), language="python")
                    if issue.get("expected_improvement"):
                        st.success(f"Expected improvement: {issue['expected_improvement']}")

    # ── Tab 4: Architecture ───────────────────────────────────────────────────
    with tabs[3]:
        arch = result.get("architecture", {})
        if arch.get("error"):
            st.error(f"Architecture analysis error: {arch['error']}")
        else:
            rating_arch = arch.get("rating", "GOOD")
            st.markdown(f"**Rating:** `{rating_arch}`")
            st.markdown(f"**Summary:** {arch.get('summary', '')}")

            solid = arch.get("solid_principles", [])
            if solid:
                st.markdown("#### SOLID Principles")
                for p in solid:
                    icon = "✅" if p.get("passed") else "❌"
                    st.markdown(f"{icon} **{p.get('principle')}** — {p.get('explanation', '')}")

            patterns = arch.get("design_patterns", [])
            if patterns:
                st.markdown(f"**Suggested patterns:** {', '.join(patterns)}")

            suggestions = arch.get("suggestions", [])
            if not suggestions:
                st.success("No architecture issues found.")
            for s in suggestions:
                sev = s.get("severity", "INFO")
                with st.expander(f"{severity_badge(sev)} [{sev}] {s.get('title', '')}"):
                    st.markdown(s.get("description", ""))
                    if s.get("pattern_suggestion"):
                        st.info(f"Pattern to apply: {s['pattern_suggestion']}")

    # ── Tab 5: Tests ──────────────────────────────────────────────────────────
    with tabs[4]:
        tests = result.get("tests", {})
        if tests.get("error"):
            st.error(f"Test generation error: {tests['error']}")
        else:
            framework = tests.get("framework", "pytest")
            test_cases = tests.get("test_cases", [])
            st.markdown(f"**Framework:** `{framework}` | **Test cases:** {len(test_cases)}")

            untested = tests.get("untested_branches", [])
            if untested:
                st.warning("Untested branches:\n" + "\n".join(f"- {b}" for b in untested))

            if test_cases:
                st.markdown("#### Test cases")
                for tc in test_cases:
                    cat = tc.get("category", "")
                    icon = {"happy_path": "✅", "edge_case": "🔶", "error_case": "❌", "boundary": "🔵"}.get(cat, "⚪")
                    st.markdown(f"{icon} **`{tc.get('name')}`** — {tc.get('description', '')}")

            generated = tests.get("generated_code", "")
            if generated:
                st.markdown("#### Generated test file")
                ext = ".py" if framework == "pytest" else ".js"
                st.download_button(
                    f"⬇ Download test file ({ext})",
                    data=generated,
                    file_name=f"test_generated{ext}",
                    mime="text/plain",
                )
                st.code(generated, language="python" if framework == "pytest" else "javascript")

    # ── Tab 6: Documentation ──────────────────────────────────────────────────
    with tabs[5]:
        docs = result.get("documentation", {})
        if docs.get("error"):
            st.error(f"Documentation analysis error: {docs['error']}")
        else:
            summary = docs.get("plain_english_summary", "")
            if summary:
                st.info(f"**Plain English Summary:** {summary}")

            doc_issues = docs.get("issues", [])
            if doc_issues:
                st.markdown(f"**Documentation issues:** {len(doc_issues)}")
                for di in doc_issues:
                    st.markdown(f"- `{di.get('element')}` — {di.get('suggestion', '')}")

            documented = docs.get("documented_code", "")
            if documented:
                st.markdown("#### Documented code")
                lang_map = {"python": "python", "javascript": "javascript", "typescript": "typescript", "java": "java"}
                code_lang = lang_map.get(result.get("language", ""), "python")
                st.download_button(
                    "⬇ Download documented file",
                    data=documented,
                    file_name="documented_code.py",
                    mime="text/plain",
                )
                st.code(documented, language=code_lang)

    # ── Tab 7: Fixed Code ─────────────────────────────────────────────────────
    with tabs[6]:
        fix_data = result.get("fix", {})
        if fix_data.get("error"):
            st.error(f"Fix generation error: {fix_data['error']}")
        else:
            explanation = fix_data.get("explanation", "")
            if explanation:
                st.info(explanation)

            changes = fix_data.get("changes", [])
            if changes:
                st.markdown("**Changes made:**")
                for ch in changes:
                    st.markdown(f"- {ch}")

            fixed = fix_data.get("fixed_code", "")
            diff = fix_data.get("diff", "")

            if diff:
                st.markdown("#### Diff (original → fixed)")
                st.code(diff, language="diff")

            if fixed:
                st.markdown("#### Fixed code")
                st.download_button(
                    "⬇ Download fixed file",
                    data=fixed,
                    file_name="fixed_code.py",
                    mime="text/plain",
                )
                st.code(fixed, language=result.get("language", "python"))

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.markdown(
    "<div style='text-align:center; color:#94a3b8; font-size:0.85rem;'>"
    "Built with FastAPI + Groq (llama-3.3-70b) + Streamlit · "
    "<a href='https://github.com/your-username/codesense-ai'>GitHub</a>"
    "</div>",
    unsafe_allow_html=True,
)
