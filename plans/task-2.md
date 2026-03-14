# Task 2 Plan: The Documentation Agent

## Overview

Extend the Task 1 agent with tools (`read_file`, `list_files`) and an agentic loop that allows the LLM to iteratively query the project wiki to answer questions.

## LLM Provider

**Provider**: Qwen Code API (same as Task 1)
- Already configured in `.env.agent.secret`
- Model: `qwen3-coder-plus` with strong tool calling capabilities

## Tool Definitions

### 1. `read_file`

**Purpose**: Read contents of a file from the project repository.

**Parameters**:
- `path` (string): Relative path from project root (e.g., `wiki/git-workflow.md`)

**Returns**: File contents as string, or error message if file doesn't exist.

**Security**:
- Must resolve path and ensure it's within project root
- Reject paths containing `../` traversal attempts
- Use `Path.resolve()` to get absolute path and verify it starts with project root

**Implementation**:
```python
def read_file(path: str) -> str:
    # Validate path security
    # Read file contents
    # Return contents or error
```

### 2. `list_files`

**Purpose**: List files and directories at a given path.

**Parameters**:
- `path` (string): Relative directory path from project root (e.g., `wiki`)

**Returns**: Newline-separated list of entries.

**Security**:
- Same path validation as `read_file`
- Only list directories, not files

**Implementation**:
```python
def list_files(path: str) -> str:
    # Validate path security
    # List directory contents
    # Return newline-separated list
```

## Tool Schema (OpenAI Function Calling)

Tools will be defined as function schemas in the OpenAI-compatible format:

```python
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file in the project repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root (e.g., 'wiki/git-workflow.md')"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories at a given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from project root (e.g., 'wiki')"
                    }
                },
                "required": ["path"]
            }
        }
    }
]
```

## Agentic Loop

### Flow

```
1. Send user question + system prompt + tool definitions to LLM
2. Parse LLM response:
   - If tool_calls present:
     a. Execute each tool
     b. Append tool results as 'tool' role messages
     c. If tool_calls < 10, go to step 1
     d. If tool_calls >= 10, stop and use current answer
   - If no tool_calls (text response):
     a. Extract answer and source from response
     b. Format JSON output
     c. Exit
```

### Message History

The agent will maintain a conversation history:

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question},
    # After each LLM response with tool_calls:
    # {"role": "assistant", "tool_calls": [...]}
    # After each tool execution:
    # {"role": "tool", "name": "read_file", "content": "..."}
]
```

### System Prompt Strategy

The system prompt will instruct the LLM to:
1. Use `list_files` to discover relevant wiki files
2. Use `read_file` to read specific files for answers
3. Include source references (file path + section anchor) in the answer
4. Stop calling tools once enough information is gathered

Example:
```
You are a documentation agent that answers questions about a software engineering project.

You have access to two tools:
- list_files: List files in a directory
- read_file: Read the contents of a file

To answer a question:
1. First use list_files to discover relevant files in the wiki/ directory
2. Then use read_file to read specific files that may contain the answer
3. When you find the answer, include the source as: wiki/filename.md#section-anchor
4. Once you have enough information, provide your final answer with the source

Always include the source reference in your answer.
```

## Output Format

```json
{
  "answer": "The answer text from the LLM.",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "git-workflow.md\n..."
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-workflow.md"},
      "result": "..."
    }
  ]
}
```

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

## Error Handling

| Error | Behavior |
|-------|----------|
| File not found | Return error message in tool result |
| Path traversal attempt | Return security error in tool result |
| LLM API error | Exit with error message to stderr |
| Max tool calls (10) | Stop loop, use current answer |

## Testing Strategy

**Test 1**: `test_documentation_agent_reads_file`
- Question: "How do you resolve a merge conflict?"
- Expected: `read_file` in tool_calls, `wiki/git-workflow.md` in source

**Test 2**: `test_documentation_agent_lists_files`
- Question: "What files are in the wiki directory?"
- Expected: `list_files` in tool_calls

## Files to Update/Create

1. `plans/task-2.md` - This plan
2. `agent.py` - Update with tools and agentic loop
3. `AGENT.md` - Update with tool documentation
4. `tests/test_agent.py` - Add 2 new test functions

## Dependencies

All required dependencies already in `pyproject.toml`:
- `httpx` - HTTP client (for LLM API)
- `pydantic-settings` - Configuration
