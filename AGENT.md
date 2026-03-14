# Agent Architecture (Task 2)

## Overview

This agent is a documentation assistant that answers questions about the project by reading the project's wiki. It uses an **agentic loop** with tool calling to iteratively gather information before providing an answer.

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
                        └──────────────┘
```

## Components

### 1. Settings (`Settings` class)

Loads configuration from `.env.agent.secret` using `pydantic-settings`:

- `LLM_API_KEY` — API key for authentication
- `LLM_API_BASE` — Base URL of the LLM API
- `LLM_MODEL` — Model name to use

### 2. Tools

#### `read_file(path: str) -> str`

Reads the contents of a file from the project repository.

**Parameters:**

- `path`: Relative path from project root (e.g., `wiki/git-workflow.md`)

**Returns:** File contents as string, or error message if file doesn't exist.

**Security:**

- Validates path to prevent directory traversal attacks
- Uses `Path.resolve()` to ensure path is within project root

#### `list_files(path: str) -> str`

Lists files and directories at a given path.

**Parameters:**

- `path`: Relative directory path from project root (e.g., `wiki`)

**Returns:** Newline-separated list of entries.

**Security:**

- Same path validation as `read_file`
- Skips hidden files and common ignored directories

### 3. Tool Schema (OpenAI Function Calling)

Tools are defined as function schemas in the OpenAI-compatible format:

```python
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file...",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "..."}
                },
                "required": ["path"]
            }
        }
    },
    # ... list_files schema
]
```

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
- Extracts source references from answers

### 6. CLI Entry Point (`main()` function)

- Parses command-line argument (the question)
- Loads settings from `.env.agent.secret`
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
     a. Execute each tool (read_file or list_files)
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

### Message History

The agent maintains a conversation history that grows with each iteration:

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question},
    # After each LLM response with tool_calls:
    {"role": "assistant", "tool_calls": [...]},
    # After each tool execution:
    {"role": "tool", "tool_call_id": "...", "content": "..."},
    # Repeat until LLM returns text answer
]
```

### System Prompt Strategy

The system prompt instructs the LLM to:

1. Use `list_files` to discover relevant wiki files
2. Use `read_file` to read specific files for answers
3. Look for section headers to identify relevant sections
4. Include source references in the format: `wiki/filename.md#section-anchor`
5. Stop calling tools once enough information is gathered

## Usage

```bash
# Run with a question
uv run agent.py "How do you resolve a merge conflict?"

# Expected output (JSON to stdout)
{
  "answer": "To resolve a merge conflict...",
  "source": "wiki/git.md#merge-conflict",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "api.md\ngit.md\n..."
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git.md"},
      "result": "# Git\n\n..."
    }
  ]
}
```

## Output Format

**stdout**: Single line of valid JSON

```json
{
  "answer": "<LLM response text>",
  "source": "wiki/filename.md#section-anchor",
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

## Error Handling

| Error Type | Behavior |
|------------|----------|
| Missing `.env.agent.secret` | Error message to stderr, exit code 1 |
| Missing environment variables | Error message with hints, exit code 1 |
| HTTP error from API | Status code and response logged, exit code 1 |
| Network error | Error message to stderr, exit code 1 |
| File not found | Error in tool result, loop continues |
| Path traversal attempt | Security error in tool result |
| Max tool calls (10) | Stop loop, use current answer |

## Path Security

To prevent directory traversal attacks:

```python
def validate_path(path: str) -> Path:
    project_root = Path(__file__).parent
    full_path = (project_root / path).resolve()
    
    # Ensure the resolved path is within project root
    if not str(full_path).startswith(str(project_root)):
        raise ValueError(f"Path traversal detected: {path}")
    
    return full_path
```

## Files

| File | Purpose |
|------|---------|
| `agent.py` | Main CLI agent implementation with tools and agentic loop |
| `.env.agent.secret` | LLM credentials (gitignored) |
| `plans/task-2.md` | Implementation plan |
| `tests/test_agent.py` | Regression tests (4 tests) |
| `AGENT.md` | This documentation |

## Extension Points (Task 3)

- **Additional tools**: Can add more tools (e.g., `search_code`, `query_api`)
- **Better source extraction**: Can improve anchor detection from section headers
- **Caching**: Can cache file reads to reduce API calls
- **Retry logic**: Can add retry/backoff for API errors
