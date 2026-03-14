# Agent Architecture (Task 1)

## Overview

This agent is a CLI tool that takes a natural language question and returns a structured JSON answer using an LLM. It forms the foundation for the agentic system that will be extended with tools in Tasks 2–3.

## LLM Provider

**Provider**: Qwen Code API

**Why Qwen Code?**
- 1000 free requests per day
- Works from Russia without VPN
- No credit card required
- OpenAI-compatible API format

**Deployment**: The Qwen Code API is deployed on the VM at `http://10.93.25.13:42005/v1` using the `qwen-code-oai-proxy` service.

**Model**: `qwen3-coder-plus` — a strong coding model suitable for software engineering tasks.

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
                        │   "tool_     │
                        │   calls":[]} │
                        └──────────────┘
```

## Components

### 1. Settings (`Settings` class)

Loads configuration from `.env.agent.secret` using `pydantic-settings`:

- `LLM_API_KEY` — API key for authentication
- `LLM_API_BASE` — Base URL of the LLM API
- `LLM_MODEL` — Model name to use

### 2. LLM Client (`LLMClient` class)

Handles HTTP communication with the LLM API:

- Uses `httpx` for HTTP requests
- Sends requests to `{LLM_API_BASE}/chat/completions`
- Uses OpenAI-compatible request/response format
- 60-second timeout for requests

### 3. Agent (`Agent` class)

Orchestrates the question-answer flow:

- Holds a system prompt (minimal for Task 1)
- Calls `LLMClient.chat_completion()` with user question
- Returns structured response: `{"answer": str, "tool_calls": []}`

### 4. CLI Entry Point (`main()` function)

- Parses command-line argument (the question)
- Loads settings from `.env.agent.secret`
- Handles errors gracefully with informative messages to stderr
- Outputs valid JSON to stdout
- Returns exit code 0 on success, non-zero on failure

## Usage

```bash
# Run with a question
uv run agent.py "What does REST stand for?"

# Expected output (JSON to stdout)
{"answer": "Representational State Transfer.", "tool_calls": []}
```

## Error Handling

| Error Type | Behavior |
|------------|----------|
| Missing `.env.agent.secret` | Error message to stderr, exit code 1 |
| Missing environment variables | Error message with hints, exit code 1 |
| HTTP error from API | Status code and response logged, exit code 1 |
| Network error | Error message to stderr, exit code 1 |
| Wrong number of arguments | Usage hint to stderr, exit code 1 |

## Output Format

**stdout**: Single line of valid JSON
```json
{"answer": "<LLM response text>", "tool_calls": []}
```

**stderr**: Debug and error messages (not parsed by autochecker)

## Files

| File | Purpose |
|------|---------|
| `agent.py` | Main CLI agent implementation |
| `.env.agent.secret` | LLM credentials (gitignored) |
| `plans/task-1.md` | Implementation plan |
| `tests/test_agent.py` | Regression tests |

## Extension Points (Tasks 2–3)

- **System prompt**: Will be expanded with domain knowledge
- **Tool calls**: Will be populated in Task 2 when tools are added
- **Agentic loop**: Will be implemented in Task 3 for multi-step reasoning
