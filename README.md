# SWE AI Orchestrator

A multi-agent AI system that generates **production-ready, full-stack projects** from a single natural-language description. Describe what you want to build and the orchestrator takes it through the entire software development lifecycle — requirements, architecture, implementation, testing, and monitoring — producing a runnable project you can start with one command or deploy to Vercel.

## What It Does

You type something like:

> "Create a product inventory app where I can upload products with quantity and sell them"

The orchestrator spins up **five specialized AI agents** that work together:

| Step | Agent | Output |
|------|-------|--------|
| 1 | **Requirements** | Structured requirements document |
| 2 | **System Design** | Full Engineering Review Document (ERD) with architecture, API contracts, data models, and tech choices |
| 3 | **Coding** | Complete frontend (React), backend (Express), worker (RabbitMQ consumer), database schema, startup script, Vercel configs |
| 4 | **Testing** | Validates project structure, dependencies, and configuration; writes and runs tests |
| 5 | **Monitoring** | Prometheus metrics, Grafana dashboards, alerting rules |

A **Supervisor agent** coordinates the pipeline, automatically looping back when issues are detected (e.g., failed tests route back to coding for fixes).

### Human-in-the-Loop

The orchestrator **pauses before coding** and displays the full requirements and system design for your review. You can:
- **Continue** — approve the design and proceed to implementation
- **Give feedback** — the design agent re-runs incorporating your notes
- **Quit** — stop and come back later

### Real-Time Progress

Every agent shows live progress as it works:

```
▸ Supervisor [3/12]: coding

┌────────────────────────────────────────────────────────────┐
│                          CODING                            │
└────────────────────────────────────────────────────────────┘
  ⠹ Generating code (8s)
  ✓ coding responded (9.1s)
  ✎ write  backend/package.json (842 bytes)
  ✎ write  backend/src/index.js (3,204 bytes)
  ✎ write  frontend/src/App.js (2,106 bytes)
  ⏳ coding thinking… (tool round 1)
  ✓ coding responded (6.3s)
  ✎ write  start.sh (2,841 bytes)
  ✓ coding complete (22.5s, 14 files written)
```

## Architecture

```
User Input
    │
    ▼
┌──────────────┐
│  Supervisor   │◄────────────────────────────────┐
│  (router)     │                                  │
└──────┬───────┘                                   │
       │ routes to next agent                      │
       ├──► Requirements Agent  ───────────────────┤
       ├──► System Design Agent ───────────────────┤
       ├──► Coding Agent        ───────────────────┤
       ├──► Testing Agent       ───────────────────┤
       ├──► Monitoring Agent    ───────────────────┘
       └──► FINISH
```

Built with [LangGraph](https://github.com/langchain-ai/langgraph) for agent orchestration and [OpenAI](https://openai.com/) models for generation.

## Quick Start

### Prerequisites

- **Python 3.11+**
- **OpenAI API key** ([get one here](https://platform.openai.com/api-keys))

### Install

```bash
git clone https://github.com/kyberis/swe-ai-orchestrator.git
cd swe-ai-orchestrator

pip install -e .
```

### Configure

```bash
cp .env.example .env
```

Open `.env` and paste your OpenAI API key:

```
OPENAI_API_KEY=sk-your-key-here
```

### Run

```bash
python main.py
```

The CLI will:
1. Ask if you want to create a **new project** or modify an **existing** one
2. Prompt you to describe what you want to build
3. Run through the agent pipeline with live progress
4. Pause at the design stage for your review
5. Generate all files into `projects/<project-name>/`

### Start the Generated Project

Every generated project includes a `start.sh` that installs dependencies and starts all services:

```bash
cd projects/<project-name>
chmod +x start.sh
./start.sh
```

This starts the frontend, backend, worker, database, message broker, Prometheus, and Grafana — all locally via Homebrew services.

## Generated Project Structure

Each project the orchestrator creates includes:

```
projects/<name>/
├── frontend/          # React app (Create React App)
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── vercel.json    # Vercel deployment config
├── backend/           # Express.js API server
│   ├── src/
│   ├── package.json
│   └── vercel.json    # Vercel serverless config
├── worker/            # RabbitMQ consumer
│   ├── src/
│   └── package.json
├── database.sql       # PostgreSQL schema
├── prometheus.yml     # Prometheus scrape config
├── start.sh           # One-command local startup
├── ERD.md             # Engineering Review Document
├── README.md          # Project docs with original prompt
└── .env.example       # Environment variables template
```

## Model Configuration

Each agent uses the best model for its task by default. You can override any of them:

| Agent | Default | Env Variable |
|-------|---------|--------------|
| Supervisor | `gpt-4o` | `OPENAI_MODEL_SUPERVISOR` |
| Requirements | `gpt-4o` | `OPENAI_MODEL_REQUIREMENTS` |
| System Design | `o4-mini` | `OPENAI_MODEL_SYSTEM_DESIGN` |
| Coding | `o4-mini` | `OPENAI_MODEL_CODING` |
| Testing | `gpt-4o` | `OPENAI_MODEL_TESTING` |
| Monitoring | `gpt-4o` | `OPENAI_MODEL_MONITORING` |

Set `OPENAI_MODEL` to change all agents at once. Per-agent variables take priority.

```bash
# Use o3 for coding (most capable)
OPENAI_MODEL_CODING=o3

# Use a single model for everything
OPENAI_MODEL=gpt-4o
```

## Other Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_ITERATIONS` | `12` | Max supervisor routing cycles before forcing completion |

## Project Layout (This Repo)

```
├── main.py                           # CLI entry point
├── src/orchestrator/
│   ├── graph.py                      # LangGraph assembly + supervisor
│   ├── llm.py                        # LLM factory with retry logic
│   ├── state.py                      # Shared state schema
│   ├── progress.py                   # Real-time progress logging
│   ├── prompts/templates.py          # All agent system prompts
│   ├── agents/
│   │   ├── requirements.py           # Requirements gathering
│   │   ├── system_design.py          # Architecture & ERD
│   │   ├── coding.py                 # Code generation
│   │   ├── testing.py                # Validation & tests
│   │   └── monitoring.py             # Observability config
│   └── tools/
│       ├── file_tools.py             # read/write/list files
│       ├── test_tools.py             # run tests & commands
│       └── monitoring_tools.py       # monitoring helpers
├── projects/                         # Generated projects live here
├── pyproject.toml                    # Python packaging
└── .env.example                      # Environment template
```

## License

MIT
