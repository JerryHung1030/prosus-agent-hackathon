# Prosus Agentic AI Framework

A modular, extensible framework for building and demoing multi‑agent AI systems (CrewAI + Streamlit) with a real‑time reasoning log.

## Core features

- Modular architecture: Agents, Tasks, and Tools are decoupled for rapid iteration.
- Agent factory: `src/crew_factory.py` assembles different “crews” (e.g., research, finance) on demand.
- Interactive UI: `app.py` lets you pick a crew and set a goal, and shows a structured reasoning log.
- Pluggable tools: Central registry in `src/tools/__init__.py` makes adding/removing tools easy.
- Built‑in RAG: `ingest.py` handles multiple data types (csv/json/md) and persists to a local Chroma DB.

---

## Quickstart

1) Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate  # Windows: .\venv\Scripts\activate
```

2) Install dependencies

```bash
pip install -r requirements.txt
```

3) Configure environment

Create a `.env` file in the repo root with your keys:

```
OPENAI_API_KEY="sk-..."
TAVILY_API_KEY="tvly-..."
```

4) Ingest data (one‑time or when data changes)

```bash
python ingest.py
```

5) Run the app

```bash
streamlit run app.py
```

---

## How it works

- Streamlit UI (`app.py`) builds a StreamlitCallbackHandler and passes it into the factory runner.
- The crew factory (`src/crew_factory.py`) creates agents and injects per‑agent `step_callback` functions derived from the Streamlit handler, so each step renders in the log.
- Tasks (`src/tasks/*.py`) are created with explicit Agent instances (no global singletons) to keep wiring clean and testable.
- Tools live in `src/tools/` and are registered in `src/tools/__init__.py` for simple composition.

Minimal flow
1. User sets goal in UI → 2. Factory builds agents + tasks → 3. Crew runs sequentially → 4. Step callbacks stream thoughts/actions/observations → 5. UI shows final report.

Project structure (excerpt)

```
src/
  agents/
    research_agents.py     # Agent factory functions
  tasks/
    research_tasks.py      # Task factory functions; take Agent as arg
  tools/
    rag_tool.py            # Internal knowledge (Chroma + OpenAI embeddings)
    web_search_tool.py     # Tavily web search tool
  utils/
    streamlit_callback.py  # Streamlit handler + step callback adapter
  crew_factory.py          # Builds crews, injects step callbacks
  main.py                  # Entrypoint used by app.py
```

---

## Extend the framework

### 1) Add a new Tool (e.g., Fraud API)

1. Create `src/tools/fraud_tool.py` and implement a `BaseTool` subclass.
2. Instantiate it and register in `src/tools/__init__.py`:

```python
from .rag_tool import rag_search_tool
from .web_search_tool import web_search_tool
from .fraud_tool import fraud_api_tool  # new

all_tools = [rag_search_tool, web_search_tool, fraud_api_tool]
```

### 2) Add a new Agent

Create a factory function in `src/agents/finance_agents.py` (new) or extend an existing file:

```python
from crewai import Agent
from src.tools import all_tools

def create_fraud_agent(step_callback=None) -> Agent:
    return Agent(
        role="Fraud Analyst",
        goal="Analyze transactions for fraud",
        tools=all_tools,
        allow_delegation=False,
        verbose=True,
        step_callback=step_callback,  # per‑agent callable used for UI streaming
    )
```

### 3) Add a new Task

Tasks take an Agent instance to keep wiring explicit:

```python
from crewai import Task

def create_fraud_task(agent):
    return Task(
        description="Analyze recent transactions and flag potential fraud.",
        expected_output="A concise fraud risk report with recommendations.",
        agent=agent,
    )
```

### 4) Add a new Crew

Wire it in `src/crew_factory.py`:

```python
from .utils.streamlit_callback import create_step_callback
from .agents.finance_agents import create_fraud_agent, create_audit_agent
from .tasks.finance_tasks import create_fraud_task, create_audit_task

def get_crew(crew_type: str, user_goal: str, streamlit_callback=None):
    # Build per‑agent step callbacks if Streamlit is present
    fraud_cb = audit_cb = None
    if streamlit_callback is not None:
        fraud_cb = create_step_callback(streamlit_callback, "fraud_agent")
        audit_cb = create_step_callback(streamlit_callback, "audit_agent")

    if crew_type == "finance":
        fraud_agent = create_fraud_agent(step_callback=fraud_cb)
        audit_agent = create_audit_agent(step_callback=audit_cb)

        agents = [fraud_agent, audit_agent]
        tasks = [create_fraud_task(fraud_agent), create_audit_task(audit_agent)]
        # ... assemble Crew as in the research crew
```

Finally, add the new crew to the dropdown in `app.py`.

---

## Configuration

- OPENAI_API_KEY: required for embeddings/LLM usage.
- TAVILY_API_KEY: required for web search (`web_search_tool.py`).
- Vector DB path: defaults to `db/` in `rag_tool.py`.

---

## Troubleshooting

- Reasoning log is empty
  - Ensure agents are created via the factory so each gets a `step_callback` injected.
  - Keep `verbose=True` on the Crew and Agents.
  - Use the Streamlit app’s “Run AI Crew” button (it wires the handler correctly).

- “Vector store not found” for RAG
  - Run `python ingest.py` after placing files in the `data/` folder.
---

## Notes for hackathon teams

- Prefer small, composable tools; keep tool side‑effects minimal and return text.
- Start with one crew and two agents (researcher/writer), then iterate.
- Add basic tests around your tool classes and task assembly to catch wiring errors early.