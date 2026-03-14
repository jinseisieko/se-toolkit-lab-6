# Task 3 Plan: The System Agent

## Overview

Extend the Task 2 agent with a `query_api` tool that can query the deployed backend API. This enables the agent to answer both static system questions (framework, ports) and data-dependent queries (item count, scores).

## LLM Provider

**Provider**: Qwen Code API (same as Tasks 1-2)
- Already configured in `.env.agent.secret`
- Model: `qwen3-coder-plus`

## New Tool: `query_api`

### Purpose

Query the deployed backend API to get real-time data or verify system behavior.

### Parameters

- `method` (string): HTTP method (GET, POST, etc.)
- `path` (string): API endpoint path (e.g., `/items/`)
- `body` (string, optional): JSON request body for POST/PUT requests

### Returns

JSON string with:
- `status_code`: HTTP status code
- `body`: Response body as JSON or text

### Authentication

Uses `LMS_API_KEY` from `.env.docker.secret` (or environment variable).

Header: `Authorization: Bearer <LMS_API_KEY>`

### Implementation

```python
def query_api(method: str, path: str, body: str | None = None) -> str:
    """Query the backend API."""
    base_url = os.environ.get("AGENT_API_BASE_URL", "http://localhost:42002")
    lms_api_key = os.environ.get("LMS_API_KEY", "")
    
    url = f"{base_url}{path}"
    headers = {
        "Authorization": f"Bearer {lms_api_key}",
        "Content-Type": "application/json",
    }
    
    # Make request with httpx
    # Return JSON with status_code and body
```

## Tool Schema (OpenAI Function Calling)

```python
{
    "type": "function",
    "function": {
        "name": "query_api",
        "description": "Query the backend API. Use for data queries (item count, scores) or to check system behavior (status codes, errors).",
        "parameters": {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "description": "HTTP method (GET, POST, etc.)"
                },
                "path": {
                    "type": "string",
                    "description": "API endpoint path (e.g., '/items/')"
                },
                "body": {
                    "type": "string",
                    "description": "JSON request body (optional, for POST/PUT)"
                }
            },
            "required": ["method", "path"]
        }
    }
}
```

## Environment Variables

The agent must read all configuration from environment variables:

| Variable | Purpose | Source | Default |
|----------|---------|--------|---------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` | - |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` | - |
| `LLM_MODEL` | Model name | `.env.agent.secret` | `qwen3-coder-plus` |
| `LMS_API_KEY` | Backend API key for query_api | `.env.docker.secret` | - |
| `AGENT_API_BASE_URL` | Base URL for query_api | Environment | `http://localhost:42002` |

**Important**: The autochecker injects its own values. Never hardcode these.

## Updated System Prompt

The system prompt must guide the LLM to choose the right tool:

```
You are a documentation and system agent that answers questions about a software engineering project.

You have access to three tools:
- list_files: List files in a directory
- read_file: Read the contents of a file
- query_api: Query the backend API

To answer a question:

1. For wiki/documentation questions (e.g., "How do I..."):
   - Use list_files to discover relevant wiki files
   - Use read_file to read specific files
   - Include source as: wiki/filename.md#section-anchor

2. For system fact questions (e.g., "What framework...", "What port..."):
   - Use read_file to check source code or config files
   - Look in backend/, docker-compose.yml, .env files

3. For data queries (e.g., "How many items...", "What is the score..."):
   - Use query_api to query the backend
   - Common endpoints: /items/, /analytics/...

4. For bug diagnosis:
   - Use query_api to reproduce the error
   - Use read_file to find the buggy code
   - Explain the root cause

Always include the source reference when reading files.
For API queries, include the endpoint in the source.
```

## Agentic Loop

The agentic loop remains the same as Task 2:
1. Send question + tools to LLM
2. If tool_calls present, execute and feed back
3. If text answer, extract source and return
4. Max 10 tool calls

## Benchmark Questions

The `run_eval.py` script tests 10 questions:

| # | Question | Tool(s) Required | Expected Answer |
|---|----------|------------------|-----------------|
| 0 | Branch protection steps | read_file | branch, protect |
| 1 | SSH connection steps | read_file | ssh/key/connect |
| 2 | Python web framework | read_file | FastAPI |
| 3 | API router modules | list_files | items, interactions, analytics, pipeline |
| 4 | Item count in database | query_api | number > 0 |
| 5 | Status code without auth | query_api | 401/403 |
| 6 | Completion-rate error | query_api, read_file | ZeroDivisionError |
| 7 | Top-learners error | query_api, read_file | TypeError/None |
| 8 | Request lifecycle | read_file | Caddy → FastAPI → auth → router → ORM → PostgreSQL |
| 9 | ETL idempotency | read_file | external_id check, duplicates skipped |

## Iteration Strategy

1. **First run**: Run `run_eval.py` to see initial score
2. **Analyze failures**: For each failure, check:
   - Did the agent use the right tool?
   - Did the tool return the right data?
   - Did the LLM interpret the data correctly?
3. **Fix issues**:
   - Tool description too vague → improve description
   - Wrong tool selected → improve system prompt
   - Tool bug → fix implementation
4. **Re-run**: Iterate until all 10 pass

## Files to Update/Create

1. `plans/task-3.md` - This plan
2. `agent.py` - Add query_api tool, update system prompt, add env vars
3. `AGENT.md` - Update with query_api documentation and lessons learned
4. `tests/test_agent.py` - Add 2 new tests for query_api

## Dependencies

All required dependencies already in `pyproject.toml`:
- `httpx` - HTTP client (for both LLM and API)
- `pydantic-settings` - Configuration
