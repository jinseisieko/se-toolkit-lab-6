# Task 1 Plan: Call an LLM from Code

## LLM Provider Choice

**Provider**: Qwen Code API (deployed on VM)

**Reasoning**:
- Already set up during lab setup
- 1000 free requests per day
- Works from Russia without VPN
- No credit card required
- OpenAI-compatible API

**Configuration**:
- `LLM_API_BASE`: `http://10.93.25.13:42005/v1`
- `LLM_MODEL`: `qwen3-coder-plus`
- `LLM_API_KEY`: Read from `.env.agent.secret`

## Architecture

### Components

1. **Environment Configuration** (`Settings` class)
   - Uses `pydantic-settings` to load from `.env.agent.secret`
   - Fields: `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL`

2. **LLM Client** (`LLMClient` class)
   - Uses `httpx` for HTTP requests
   - Method: `chat_completion(messages: list) -> str`
   - Handles OpenAI-compatible API format

3. **Agent** (`Agent` class)
   - Composes settings and client
   - Method: `ask(question: str) -> dict`
   - Returns structured response: `{"answer": str, "tool_calls": list}`

4. **CLI Entry Point**
   - Parses command-line argument (question)
   - Calls agent
   - Outputs JSON to stdout
   - Debug logs to stderr

### Data Flow

```
Command line → agent.py "Question"
                    ↓
            Parse argument
                    ↓
            Agent.ask(question)
                    ↓
            LLMClient.chat_completion(messages)
                    ↓
            HTTP POST to LLM_API_BASE/chat/completions
                    ↓
            Parse response
                    ↓
            Format JSON: {"answer": "...", "tool_calls": []}
                    ↓
            Print to stdout
```

## Error Handling

- **Missing environment variables**: Exit with error message to stderr, code 1
- **HTTP errors**: Catch and report to stderr, exit code 1
- **JSON parsing errors**: Catch and report to stderr, exit code 1
- **Timeout**: Set 60-second timeout on HTTP request

## Testing Strategy

**Test file**: `tests/test_agent.py`

**Test case**: `test_agent_returns_valid_json`
- Run `agent.py` as subprocess with a test question
- Parse stdout as JSON
- Assert `answer` field exists and is non-empty string
- Assert `tool_calls` field exists and is a list

## Files to Create

1. `plans/task-1.md` - This plan
2. `agent.py` - Main CLI agent
3. `AGENT.md` - Documentation (update existing)
4. `tests/test_agent.py` - Regression test

## Dependencies

All required dependencies are already in `pyproject.toml`:
- `httpx` - HTTP client
- `pydantic-settings` - Environment configuration
- `pytest` - Testing
