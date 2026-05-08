# 🔍 CodeSense AI

> Autonomous multi-agent code intelligence platform — 6 specialized AI agents review every pull request in parallel, automatically.

[![CI](https://github.com/DadaMastan-code/codesense-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/DadaMastan-code/codesense-ai/actions/workflows/ci.yml)
[![Self-Review](https://github.com/DadaMastan-code/codesense-ai/actions/workflows/self-review.yml/badge.svg)](https://github.com/DadaMastan-code/codesense-ai/actions/workflows/self-review.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-orchestration-purple.svg)](https://github.com/langchain-ai/langgraph)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## What It Does

CodeSense AI runs **6 specialized agents in parallel** on every GitHub pull request:

| Agent | What it checks |
|---|---|
| 🔒 **Security** | OWASP Top 10, SQL injection, XSS, hardcoded secrets, insecure functions |
| ⚡ **Performance** | Big-O complexity, N+1 queries, memory leaks, blocking I/O in async code |
| 🏗️ **Architecture** | SOLID principles, God classes, design pattern opportunities, coupling |
| 🧪 **Tests** | Coverage gaps, missing edge cases, generates ready-to-run test files |
| 📝 **Docs** | Missing docstrings, outdated comments, missing type hints — auto-generates them |
| 🔧 **AutoFix** | Generates a unified diff with all fixes applied — paste-ready code |

Results appear as a structured comment directly on the PR — automatically, without you doing anything.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      CodeSense AI Platform                   │
│                                                              │
│   INPUT LAYER                                                │
│   ┌─────────────┐   ┌─────────────┐   ┌──────────────┐      │
│   │ Streamlit   │   │  FastAPI    │   │  GitHub      │      │
│   │ Web UI      │   │  REST API   │   │  Webhook     │      │
│   └──────┬──────┘   └──────┬──────┘   └──────┬───────┘      │
│          └─────────────────┴─────────────────┘               │
│                             │                                │
│   ORCHESTRATION LAYER (LangGraph StateGraph)                 │
│                             ▼                                │
│   ┌────────┐ ┌──────┐ ┌──────┐ ┌───────┐ ┌──────┐          │
│   │Security│ │ Perf │ │ Arch │ │ Tests │ │ Docs │          │
│   │ Agent  │ │Agent │ │Agent │ │ Agent │ │Agent │          │
│   └────┬───┘ └──┬───┘ └──┬───┘ └──┬────┘ └──┬───┘          │
│        └────────┴─────────┴────────┴──────────┘              │
│                             │ fan-in (all 5 complete)        │
│                             ▼                                │
│                    ┌─────────────────┐                       │
│                    │  AutoFix Agent  │                       │
│                    └────────┬────────┘                       │
│                             │                                │
│   STORAGE LAYER              ▼                               │
│   ┌──────────────────────────────────────────────────────┐   │
│   │  Evolution Tracker (SQLite)                          │   │
│   │  PR #1: 67/100 → PR #10: 82/100 → PR #25: 94/100   │   │
│   └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

**Tech stack:** FastAPI · LangGraph · Groq (llama-3.3-70b) · LangSmith · Streamlit · SQLite · Docker · GitHub Actions

---

## GitHub Webhook — Set It and Forget It

Set up once; every PR gets reviewed automatically in ~15 seconds.

### 5-step setup

**1. Get a GitHub token**
Settings → Developer settings → Personal access tokens → New token
Scopes: `repo`, `write:discussion`

**2. Generate a webhook secret**
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

**3. Add secrets to your repo**
Settings → Secrets and variables → Actions:
- `GROQ_API_KEY` — get free at [console.groq.com](https://console.groq.com)
- `GITHUB_WEBHOOK_SECRET` — generated above
- `GITHUB_TOKEN` — your personal access token

**4. Deploy the backend** (see [Deployment](#deployment)) and note the URL

**5. Add webhook in your GitHub repo**
Settings → Webhooks → Add webhook:
- Payload URL: `https://your-backend.render.com/webhook/github`
- Content type: `application/json`
- Secret: your generated secret
- Events: Pull requests only ✓

That's it. Open a PR and watch the review appear automatically.

---

## GitHub Self-Review

The meta-feature: **CodeSense AI reviews its own pull requests using itself.**

The `.github/workflows/self-review.yml` workflow:
1. Spins up the FastAPI backend in the CI runner
2. Fetches the PR diff (Python, JS, TS, Java, Go, Rust files)
3. Runs all 6 agents via the local API
4. Posts a full structured review comment on the PR

This activates automatically on every PR to `main`. Add `GROQ_API_KEY` as a GitHub Actions secret to enable it.

---

## Evolution Dashboard

Track code quality across pull requests over time:

```
Score
100 │                              ●──●
 90 │              ●──●──●
 80 │    ●──●──●
 70 │ ●
 60 │
    └────────────────────────────────▶ PRs over time
    PR1  PR5  PR10  PR15  PR20  PR25
```

Every webhook-triggered PR review is saved to SQLite. The **📊 Evolution** page in the Streamlit sidebar shows:
- Overall score trend with colour-coded bands (Excellent / Good / Needs Work / Critical)
- Per-agent score breakdown (Security, Performance, Architecture, Docs)
- Critical issues per review (stacked bar chart)
- Full review history table

**API endpoints:**
```
GET /evolution/repos          — list all tracked repos
GET /evolution/history        — full history (filter by ?repo=owner/repo)
```

---

## LangSmith Tracing (Optional)

Full observability for every agent call — token usage, latency, and traces in [LangSmith](https://smith.langchain.com):

```env
LANGSMITH_API_KEY=your_key_here
LANGSMITH_PROJECT=codesense-ai
LANGSMITH_TRACING_ENABLED=true
```

When configured, every LangGraph node execution is traced automatically. If not set, tracing is silently skipped — zero overhead.

---

## Quick Start

### Prerequisites
- Python 3.11+
- Groq API key (free at [console.groq.com](https://console.groq.com)) OR OpenAI key

### 1. Clone & install
```bash
git clone https://github.com/DadaMastan-code/codesense-ai.git
cd codesense-ai
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure
```bash
cp .env.example .env
# Edit .env — add your GROQ_API_KEY at minimum
```

### 3. Run
```bash
# Terminal 1: Backend
uvicorn backend.main:app --reload

# Terminal 2: Frontend
streamlit run frontend/app.py
```

Open [http://localhost:8501](http://localhost:8501) — paste code, click Analyse.

### Docker Compose
```bash
docker compose -f docker/docker-compose.yml up
```

---

## API Reference

Interactive docs: `http://localhost:8000/docs`

| Endpoint | Method | Description |
|---|---|---|
| `/analyze` | POST | Full 6-agent analysis (parallel via LangGraph) |
| `/analyze/stream` | POST | Server-Sent Events — results agent by agent |
| `/fix` | POST | AutoFix only — pass issue list |
| `/generate-tests` | POST | Test generation only |
| `/webhook/github` | POST | GitHub PR webhook handler |
| `/evolution/history` | GET | Quality score history |
| `/evolution/repos` | GET | List tracked repositories |
| `/health` | GET | Health check |

### Example request
```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "code": "query = f\"SELECT * FROM users WHERE id={user_id}\"",
    "language": "python",
    "context": "auth handler"
  }'
```

---

## Deployment

### Backend → Render (free tier)

1. New **Web Service** on [render.com](https://render.com) — connect this repo
2. Build: `pip install -r requirements.txt`
3. Start: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
4. Env vars: `GROQ_API_KEY`, `GITHUB_WEBHOOK_SECRET`, `GITHUB_TOKEN`

### Frontend → Streamlit Cloud (free)

1. [share.streamlit.io](https://share.streamlit.io) — connect this repo
2. Main file: `frontend/app.py`
3. Update `API_BASE` in `frontend/app.py` to your Render URL

---

## Project Structure

```
codesense-ai/
├── backend/
│   ├── agents/
│   │   ├── security_agent.py       # OWASP Top 10 checker
│   │   ├── performance_agent.py    # Big-O + memory analyzer
│   │   ├── architecture_agent.py   # SOLID + design patterns
│   │   ├── test_agent.py           # Coverage + test generator
│   │   ├── doc_agent.py            # Docstring generator
│   │   └── fix_agent.py            # AutoFix diff generator
│   ├── api/
│   │   ├── github_webhook.py       # GitHub PR webhook + comment bot
│   │   └── evolution_route.py      # Quality history endpoints
│   ├── evolution/
│   │   └── tracker.py              # SQLite per-PR quality tracking
│   ├── pipelines/
│   │   └── orchestrator.py         # LangGraph StateGraph (parallel fan-out)
│   ├── utils/
│   │   ├── llm_client.py           # Groq / OpenAI client with fallback
│   │   ├── tracing.py              # LangSmith tracing (optional no-op)
│   │   └── ...
│   ├── models/schemas.py           # Pydantic v2 schemas
│   ├── config.py                   # Settings (pydantic-settings)
│   └── main.py                     # FastAPI app
├── frontend/
│   ├── app.py                      # Main analyzer UI
│   └── pages/
│       └── 📊_Evolution.py         # Evolution dashboard
├── tests/
├── docker/
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── docker-compose.yml
├── .github/workflows/
│   ├── ci.yml                      # Test → lint → mypy → docker build
│   └── self-review.yml             # CodeSense reviews its own PRs ✨
└── requirements.txt
```

---

## What Makes This Different

| Basic Code Linters | CodeSense AI |
|---|---|
| Rule-based checks only | AI reasoning about context and intent |
| One dimension (style OR security) | 6 dimensions simultaneously in parallel |
| No explanation of WHY | Detailed reasoning + OWASP references for every finding |
| Manual trigger only | Automatic on every GitHub PR via webhook |
| No memory across PRs | Evolution tracking — sees quality patterns over time |
| Static suggestions | Auto-fix with unified diff — paste-ready |

---

## License

MIT — see [LICENSE](LICENSE)

---

<div align="center">
  Built with FastAPI · LangGraph · Groq (llama-3.3-70b) · Streamlit<br>
  <a href="https://github.com/DadaMastan-code/codesense-ai">⭐ Star this repo if it helped you</a>
</div>
