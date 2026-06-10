# Contributing to React GitHub Agent

Thanks for your interest! Here's everything you need to get started.

## Development Setup

```bash
git clone https://github.com/Darsh-Nandu/React-Github-Agent.git
cd React-Github-Agent

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-cov black pylint bandit

cp .env.example .env             # fill in your keys
```

## Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=agent --cov=github_tools --cov=mcp_server --cov-report=term-missing

# Single file
pytest tests/test_github_toolkit.py -v
```

No real API keys are needed for tests — everything is mocked.

## Code Style

This project uses **Black** (line length 100) for formatting and **Pylint** for linting.

```bash
# Format
black .

# Lint
pylint agent/ github_tools/ mcp_server/ main.py
```

CI will check Black formatting on every PR. Please run `black .` before pushing.

## Making a Change

1. Fork the repo and create a branch: `git checkout -b feature/my-change`
2. Write your code and add tests for new behaviour.
3. Make sure `pytest` and `black --check .` both pass locally.
4. Open a Pull Request with a clear description of what changed and why.

## Adding a New GitHub Tool

1. Add a `@tool`-decorated function in `github_tools/github_toolkit.py`.
2. Add at least two tests in `tests/test_github_toolkit.py` (happy path + error path).
3. Document it in the **Tools** table in `README.md`.

## Adding a New MCP Tool

1. Add a `@mcp.tool()`-decorated function in `mcp_server/server.py`.
2. Add tests in `tests/test_mcp_server.py`.

## Reporting Bugs

Open a GitHub Issue with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Python version and OS

## Questions?

Open a Discussion or drop a comment on a relevant Issue.
