# Agent Architecture (Task 3)

## Overview

This agent is a system assistant that answers questions about a software engineering project by reading documentation, querying the backend API, and analyzing source code. It uses an **agentic loop** with three tools (`read_file`, `list_files`, `query_api`) to iteratively gather information before providing an answer.

## LLM Provider

**Provider**: Qwen Code API (deployed on VM)

**Why Qwen Code?**

- 1000 free requests per day
- Works from Russia without VPN
- No credit card required
- OpenAI-compatible API with tool calling support

**Deployment**: The Qwen Code API is deployed on the VM at `http://10.93.25.13:42005/v1` using the `qwen-code-oai-proxy` service.

**Model**: `qwen3-coder-plus` — a strong coding model with excellent tool calling capabilities.

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Command Line   │ ──> │   agent.py   │ ──> │  Qwen Code API  │
│  "Question"     │     │  (CLI Tool)  │     │  (on VM)        │
└─────────────────┘     └──────────────┘     └─────────────────┘
                               │
                               v
                        ┌──────────────┐
                        │  JSON Output │
                        │  {"answer":  │
                        │   "source":  │
                        │   "tool_     │
                        │   calls":[]} │
                        └──────────────┘
                               │
                               v
                        ┌──────────────┐
                        │  Tools:      │
                        │  - read_file │
                        │  - list_files│
                        │  - query_api │
                        └──────────────┘
```

## Components

### 1. Settings (`Settings` class)

Loads configuration from environment variables using `pydantic-settings`:

**From `.env.agent.secret`:**

- `LLM_API_KEY` — API key for LLM authentication
- `LLM_API_BASE` — Base URL of the LLM API
- `LLM_MODEL` — Model name to use

**From environment or `.env.docker.secret`:**

- `LMS_API_KEY` — Backend API key for `query_api` authentication
- `AGENT_API_BASE_URL` — Base URL for backend API (default: `http://localhost:42002`)

### 2. Tools

#### `read_file(path: str) -> str`

Reads the contents of a file from the project repository.

**Parameters:**

- `path`: Relative path from project root (e.g., `wiki/git-workflow.md`, `backend/app/main.py`)

**Returns:** File contents as string, or error message if file doesn't exist.

**Security:**

- Validates path to prevent directory traversal attacks
- Uses `Path.resolve()` to ensure path is within project root

#### `list_files(path: str) -> str`

Lists files and directories at a given path.

**Parameters:**

- `path`: Relative directory path from project root (e.g., `wiki`, `backend/app/routers`)

**Returns:** Newline-separated list of entries.

**Security:**

- Same path validation as `read_file`
- Skips hidden files and common ignored directories

#### `query_api(method: str, path: str, body: str | None = None, use_auth: bool = True) -> str`

Queries the backend API to get real-time data or verify system behavior.

**Parameters:**

- `method`: HTTP method (GET, POST, PUT, DELETE)
- `path`: API endpoint path (e.g., `/items/`, `/analytics/completion-rate?lab=lab-99`)
- `body`: Optional JSON request body for POST/PUT requests
- `use_auth`: Whether to send authentication header (default: True). Set to False to test unauthenticated access.

**Returns:** JSON string with:

- `status_code`: HTTP status code
- `body`: Response body (parsed as JSON if possible)
- `error`: Error message if request failed

**Authentication:**

- Uses `LMS_API_KEY` from environment variable
- Header: `Authorization: Bearer <LMS_API_KEY>`
- Set `use_auth=False` to test unauthenticated endpoints

### 3. Tool Schema (OpenAI Function Calling)

Tools are defined as function schemas in the OpenAI-compatible format with detailed descriptions to guide the LLM's tool selection.

### 4. LLM Client (`LLMClient` class)

Handles HTTP communication with the LLM API:

- Uses `httpx` for HTTP requests
- Sends requests to `{LLM_API_BASE}/chat/completions`
- Supports tool calling via `tools` parameter
- 60-second timeout for requests

### 5. Agent (`Agent` class)

Orchestrates the agentic loop:

- Maintains conversation history with message roles: `system`, `user`, `assistant`, `tool`
- Implements the agentic loop (see below)
- Enforces maximum 10 tool calls per question
- Extracts source references from answers (wiki files, source code, config files)

### 6. CLI Entry Point (`main()` function)

- Parses command-line argument (the question)
- Loads settings from `.env.agent.secret` and `.env.docker.secret`
- Handles errors gracefully with informative messages to stderr
- Outputs valid JSON to stdout
- Returns exit code 0 on success, non-zero on failure

## Agentic Loop

The agentic loop allows the LLM to iteratively gather information using tools before providing a final answer.

### Flow

```
1. Send user question + system prompt + tool definitions to LLM
2. Parse LLM response:
   - If tool_calls present:
     a. Execute each tool (read_file, list_files, or query_api)
     b. Record tool call: {"tool": "...", "args": {...}, "result": "..."}
     c. Append tool results as 'tool' role messages
     d. If tool_calls < 10, go to step 1
     e. If tool_calls >= 10, stop and use current answer
   - If no tool_calls (text response):
     a. This is the final answer
     b. Extract source reference from answer
     c. Format JSON output
     d. Exit
```

### System Prompt Strategy

The system prompt guides the LLM to choose the right tool based on question type:

1. **Wiki/documentation questions** → `list_files` + `read_file`
2. **System fact questions** → `read_file` (source code) or `query_api` (live behavior)
3. **Data queries** → `query_api`
4. **Bug diagnosis** → `query_api` (reproduce error) + `read_file` (find buggy code)

The prompt explicitly instructs the LLM to mention file paths in answers for proper source extraction.

## Usage

```bash
# Run with a question
uv run agent.py "How many items are in the database?"

# Expected output (JSON to stdout)
{
  "answer": "There are 44 items in the database.",
  "source": "",
  "tool_calls": [
    {
      "tool": "query_api",
      "args": {"method": "GET", "path": "/items/"},
      "result": "{\"status_code\": 200, \"body\": [...]}"
    }
  ]
}
```

## Output Format

**stdout**: Single line of valid JSON

```json
{
  "answer": "<LLM response text>",
  "source": "wiki/filename.md#section-anchor or backend/path/file.py",
  "tool_calls": [
    {
      "tool": "tool_name",
      "args": {"param": "value"},
      "result": "tool output"
    }
  ]
}
```

**stderr**: Debug and error messages (not parsed by autochecker)

## Environment Variables

| Variable | Purpose | Source | Default |
|----------|---------|--------|---------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` | - |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` | - |
| `LLM_MODEL` | Model name | `.env.agent.secret` | `qwen3-coder-plus` |
| `LMS_API_KEY` | Backend API key for query_api | `.env.docker.secret` or env | - |
| `AGENT_API_BASE_URL` | Base URL for query_api | Environment | `http://localhost:42002` |

**Important**: The autochecker injects its own values. Never hardcode these.

## Error Handling

| Error Type | Behavior |
|------------|----------|
| Missing `.env.agent.secret` | Error message to stderr, exit code 1 |
| Missing environment variables | Error message with hints, exit code 1 |
| HTTP error from LLM API | Status code and response logged, exit code 1 |
| Network error | Error message to stderr, exit code 1 |
| File not found | Error in tool result, loop continues |
| Path traversal attempt | Security error in tool result |
| API error | JSON with status_code and error in tool result |
| Max tool calls (10) | Stop loop, use current answer |

## Benchmark Results

**Final Score: 10/10 PASSED**

The agent passes all 10 local benchmark questions:

| # | Question Type | Tools Used | Status |
|---|--------------|------------|--------|
| 1 | Wiki: Branch protection | read_file | ✓ |
| 2 | Wiki: SSH connection | read_file | ✓ |
| 3 | Source: Framework | read_file | ✓ |
| 4 | Source: Router modules | list_files | ✓ |
| 5 | Data: Item count | query_api | ✓ |
| 6 | System: Status code | query_api (use_auth=false) | ✓ |
| 7 | Bug: Division by zero | query_api + read_file | ✓ |
| 8 | Bug: TypeError | query_api + read_file | ✓ |
| 9 | Reasoning: Request lifecycle | read_file | ✓ |
| 10 | Reasoning: ETL idempotency | read_file | ✓ |

### Iteration History

| Iteration | Score | Failure | Fix |
|-----------|-------|---------|-----|
| 1 | 5/10 | Status code without auth | Added `use_auth` parameter to `query_api` |
| 2 | 6/10 | Missing source field | Updated `_extract_source` to handle source code files |
| 3 | 6/10 | Max tool calls | Improved system prompt to emphasize file paths |
| 4 | 10/10 | All passed | - |

### Lessons Learned

1. **Tool parameters matter**: The `use_auth` parameter was essential for testing unauthenticated API access. Without it, the agent couldn't answer questions about 401/403 status codes.

2. **Source extraction**: The `_extract_source` function needed to handle both wiki files (`.md`) and source code files (`.py`). The regex patterns now match `wiki/*.md`, `backend/**/*.py`, `docker-compose.yml`, and `Dockerfile`.

3. **System prompt tuning**: Explicitly telling the LLM to mention file paths in answers (e.g., "The bug is in backend/app/routers/analytics.py...") dramatically improved source detection. The LLM needs clear guidance on what format to use.

4. **Max tool calls**: The agentic loop can hit the 10-call limit if the LLM doesn't efficiently use tools. Clear tool descriptions and system prompts help the LLM make better decisions faster.

5. **Environment variable separation**: Keeping `LMS_API_KEY` (backend) separate from `LLM_API_KEY` (LLM provider) is crucial. The autochecker injects different values for each.

## Files

| File | Purpose |
|------|---------|
| `agent.py` | Main CLI agent implementation with 3 tools and agentic loop |
| `.env.agent.secret` | LLM credentials (gitignored) |
| `.env.docker.secret` | Backend API credentials (gitignored) |
| `plans/task-3.md` | Implementation plan with benchmark results |
| `tests/test_agent.py` | Regression tests (6 tests total) |
| `AGENT.md` | This documentation |
| `run_eval.py` | Local benchmark runner |

## Extension Points

- **Additional tools**: Can add more tools (e.g., `search_code`, `query_database`)
- **Better source extraction**: Can improve anchor detection from section headers
- **Caching**: Can cache file reads and API responses to reduce calls
- **Retry logic**: Can add retry/backoff for transient API errors
- **Streaming**: Can support streaming responses for long answers
