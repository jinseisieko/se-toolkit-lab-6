#!/usr/bin/env python3
"""
Agent CLI - System agent with tool calling capabilities.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "source": "...", "tool_calls": [...]}
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env.agent.secret",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM configuration (from .env.agent.secret)
    llm_api_key: str
    llm_api_base: str
    llm_model: str = "qwen3-coder-plus"

    # Backend API configuration (from environment or .env.docker.secret)
    lms_api_key: str = ""
    agent_api_base_url: str = "http://localhost:42002"


# Maximum number of tool calls per question
MAX_TOOL_CALLS = 10

# Tool definitions for OpenAI-compatible function calling
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
                        "description": "Relative path from project root (e.g., 'wiki/git-workflow.md')",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories at a given path in the project repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from project root (e.g., 'wiki')",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_api",
            "description": "Query the backend API. Use for data queries (item count, scores) or to check system behavior (status codes, errors). Returns JSON with status_code and body.",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "description": "HTTP method (GET, POST, etc.)",
                    },
                    "path": {
                        "type": "string",
                        "description": "API endpoint path (e.g., '/items/', '/analytics/completion-rate')",
                    },
                    "body": {
                        "type": "string",
                        "description": "JSON request body (optional, for POST/PUT requests)",
                    },
                    "use_auth": {
                        "type": "boolean",
                        "description": "Whether to send authentication header (default: true). Set to false to test unauthenticated access.",
                    },
                },
                "required": ["method", "path"],
            },
        },
    },
]

# System prompt for the system agent
SYSTEM_PROMPT = """You are a documentation and system agent that answers questions about a software engineering project.

You have access to three tools:
- list_files: List files and directories in a given path
- read_file: Read the contents of a specific file
- query_api: Query the backend API (use for data queries or to check system behavior)

To answer a question:

1. For wiki/documentation questions (e.g., "How do I...", "What steps..."):
   - Use list_files to discover relevant wiki files
   - Use read_file to read specific files
   - In your answer, mention the file path like "According to wiki/git.md..."

2. For system fact questions (e.g., "What framework...", "What port...", "What status code..."):
   - Use read_file to check source code or config files (backend/, docker-compose.yml, .env files)
   - Or use query_api to check actual system behavior
   - In your answer, mention the file path like "In backend/app/main.py..."

3. For data queries (e.g., "How many items...", "What is the score..."):
   - Use query_api to query the backend
   - Common endpoints: /items/, /analytics/...

4. For bug diagnosis (e.g., "What error...", "What is the bug..."):
   - FIRST use query_api to reproduce the error
   - THEN use read_file to find the buggy code in the source
   - In your answer, explicitly mention the file path like "The bug is in backend/app/routers/analytics.py..."
   - Explain the root cause and the specific buggy line

Always mention the file path in your answer when you read a file.
For API queries, mention the endpoint used.
If you cannot find the answer, say so honestly.
"""


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent


def validate_path(path: str) -> Path:
    """
    Validate and resolve a path, ensuring it's within the project root.

    Args:
        path: Relative path from project root.

    Returns:
        Resolved absolute Path.

    Raises:
        ValueError: If path traversal is detected.
    """
    project_root = get_project_root()
    full_path = (project_root / path).resolve()

    # Ensure the resolved path is within project root
    if not str(full_path).startswith(str(project_root)):
        raise ValueError(f"Path traversal detected: {path}")

    return full_path


def read_file(path: str) -> str:
    """
    Read the contents of a file.

    Args:
        path: Relative path from project root.

    Returns:
        File contents as string, or error message.
    """
    try:
        full_path = validate_path(path)

        if not full_path.exists():
            return f"Error: File not found: {path}"

        if not full_path.is_file():
            return f"Error: Not a file: {path}"

        return full_path.read_text()

    except ValueError as e:
        return f"Security error: {e}"
    except Exception as e:
        return f"Error reading file: {e}"


def list_files(path: str) -> str:
    """
    List files and directories at a given path.

    Args:
        path: Relative directory path from project root.

    Returns:
        Newline-separated list of entries, or error message.
    """
    try:
        full_path = validate_path(path)

        if not full_path.exists():
            return f"Error: Path not found: {path}"

        if not full_path.is_dir():
            return f"Error: Not a directory: {path}"

        entries = []
        for entry in sorted(full_path.iterdir()):
            # Skip hidden files and common ignored directories
            if entry.name.startswith(".") and entry.name not in [".qwen", ".vscode"]:
                continue
            if entry.name in ["__pycache__", ".venv", ".pytest_cache", ".ruff_cache"]:
                continue

            suffix = "/" if entry.is_dir() else ""
            entries.append(f"{entry.name}{suffix}")

        return "\n".join(entries)

    except ValueError as e:
        return f"Security error: {e}"
    except Exception as e:
        return f"Error listing files: {e}"


def query_api(
    method: str, path: str, body: str | None = None, use_auth: bool = True
) -> str:
    """
    Query the backend API.

    Args:
        method: HTTP method (GET, POST, etc.).
        path: API endpoint path (e.g., '/items/').
        body: Optional JSON request body for POST/PUT requests.
        use_auth: Whether to send authentication header (default: True).

    Returns:
        JSON string with status_code and body, or error message.
    """
    try:
        # Get configuration from environment
        base_url = os.environ.get("AGENT_API_BASE_URL", "http://localhost:42002")
        lms_api_key = os.environ.get("LMS_API_KEY", "")

        url = f"{base_url}{path}"
        headers = {
            "Content-Type": "application/json",
        }

        # Only add auth header if use_auth is True
        if use_auth and lms_api_key:
            headers["Authorization"] = f"Bearer {lms_api_key}"

        print(f"Querying API: {method} {url} (auth={use_auth})", file=sys.stderr)

        with httpx.Client(timeout=30.0) as client:
            if method.upper() == "GET":
                response = client.get(url, headers=headers)
            elif method.upper() == "POST":
                response = client.post(url, headers=headers, data=body or "{}")
            elif method.upper() == "PUT":
                response = client.put(url, headers=headers, data=body or "{}")
            elif method.upper() == "DELETE":
                response = client.delete(url, headers=headers)
            else:
                return f"Error: Unsupported method: {method}"

        result = {
            "status_code": response.status_code,
            "body": response.text,
        }

        # Try to parse body as JSON for prettier output
        try:
            result["body"] = response.json()
        except json.JSONDecodeError, ValueError:
            pass

        print(f"API response: {response.status_code}", file=sys.stderr)
        return json.dumps(result)

    except httpx.HTTPStatusError as e:
        return json.dumps(
            {
                "status_code": e.response.status_code,
                "body": e.response.text,
                "error": str(e),
            }
        )
    except httpx.RequestError as e:
        return json.dumps(
            {
                "status_code": 0,
                "body": "",
                "error": f"Request failed: {e}",
            }
        )
    except Exception as e:
        return json.dumps(
            {
                "status_code": 0,
                "body": "",
                "error": f"Error: {e}",
            }
        )


def execute_tool(tool_name: str, args: dict[str, Any]) -> str:
    """
    Execute a tool and return the result.

    Args:
        tool_name: Name of the tool to execute.
        args: Tool arguments.

    Returns:
        Tool result as string.
    """
    print(f"Executing tool: {tool_name} with args: {args}", file=sys.stderr)

    if tool_name == "read_file":
        return read_file(args.get("path", ""))
    elif tool_name == "list_files":
        return list_files(args.get("path", ""))
    elif tool_name == "query_api":
        return query_api(
            args.get("method", "GET"),
            args.get("path", ""),
            args.get("body"),
            args.get("use_auth", True),
        )
    else:
        return f"Error: Unknown tool: {tool_name}"


class LLMClient:
    """Client for OpenAI-compatible LLM APIs with tool calling support."""

    def __init__(self, settings: Settings):
        self.api_key = settings.llm_api_key
        self.api_base = settings.llm_api_base.rstrip("/")
        self.model = settings.llm_model

    def chat_completion(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """
        Send a chat completion request with optional tool calling.

        Args:
            messages: List of message dicts.
            tools: Optional list of tool definitions.

        Returns:
            Dict with 'content' and 'tool_calls' keys.
        """
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }

        if tools:
            payload["tools"] = tools

        print(f"Sending request to {url}", file=sys.stderr)
        print(f"Model: {self.model}", file=sys.stderr)

        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()

        data = response.json()
        choice = data["choices"][0]["message"]

        result = {
            "content": choice.get("content", ""),
            "tool_calls": [],
        }

        # Parse tool calls if present
        if "tool_calls" in choice and choice["tool_calls"]:
            for tc in choice["tool_calls"]:
                if tc.get("type") == "function":
                    func = tc.get("function", {})
                    try:
                        args = json.loads(func.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        args = {}

                    result["tool_calls"].append(
                        {
                            "id": tc.get("id", ""),
                            "name": func.get("name", ""),
                            "arguments": args,
                        }
                    )

        print(
            f"LLM response: {len(result['content'])} chars, {len(result['tool_calls'])} tool calls",
            file=sys.stderr,
        )
        return result


class Agent:
    """Agent with tool calling capabilities for answering documentation questions."""

    def __init__(self, settings: Settings):
        self.client = LLMClient(settings)
        self.tool_call_count = 0

    def ask(self, question: str) -> dict[str, Any]:
        """
        Ask a question using the agentic loop.

        Args:
            question: The user's question.

        Returns:
            Dict with 'answer', 'source', and 'tool_calls' keys.
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]

        all_tool_calls: list[dict[str, Any]] = []

        # Agentic loop
        while self.tool_call_count < MAX_TOOL_CALLS:
            print(
                f"\n--- Agentic loop iteration {self.tool_call_count + 1} ---",
                file=sys.stderr,
            )

            # Get LLM response
            response = self.client.chat_completion(messages, tools=TOOLS)

            # If no tool calls, we have the final answer
            if not response["tool_calls"]:
                print("No tool calls, extracting final answer", file=sys.stderr)
                answer = response["content"].strip()

                # Try to extract source from the answer
                source = self._extract_source(answer)

                return {
                    "answer": answer,
                    "source": source,
                    "tool_calls": all_tool_calls,
                }

            # Process tool calls
            for tool_call in response["tool_calls"]:
                print(f"Processing tool call: {tool_call['name']}", file=sys.stderr)

                # Execute the tool
                result = execute_tool(tool_call["name"], tool_call["arguments"])

                # Record the tool call
                tool_call_record = {
                    "tool": tool_call["name"],
                    "args": tool_call["arguments"],
                    "result": result,
                }
                all_tool_calls.append(tool_call_record)
                self.tool_call_count += 1

                # Add assistant message with tool calls
                messages.append(
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": tool_call["id"],
                                "type": "function",
                                "function": {
                                    "name": tool_call["name"],
                                    "arguments": json.dumps(tool_call["arguments"]),
                                },
                            }
                        ],
                    }
                )

                # Add tool result
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result,
                    }
                )

                print(f"Tool result: {result[:100]}...", file=sys.stderr)

            # Continue loop to get next LLM response

        # Max tool calls reached
        print("Max tool calls reached", file=sys.stderr)
        return {
            "answer": "I reached the maximum number of tool calls (10) before finding a complete answer.",
            "source": "",
            "tool_calls": all_tool_calls,
        }

    def _extract_source(self, answer: str) -> str:
        """
        Extract source reference from the answer.

        Looks for patterns like:
        - wiki/filename.md#section
        - wiki/filename.md
        - backend/path/file.py
        - path/to/file.py

        Args:
            answer: The answer text.

        Returns:
            Source reference or empty string.
        """
        import re

        # Look for wiki/filename.md#anchor pattern
        match = re.search(r"wiki/[\w-]+\.md(?:#[\w-]+)?", answer)
        if match:
            return match.group()

        # Look for wiki/filename.md pattern
        match = re.search(r"wiki/[\w-]+\.md", answer)
        if match:
            return match.group()

        # Look for backend/path/file.py pattern (source code)
        match = re.search(r"backend/[\w/.-]+\.py", answer)
        if match:
            return match.group()

        # Look for any path/file.py pattern
        match = re.search(r"[\w]+/[\w/.-]+\.py", answer)
        if match:
            return match.group()

        # Look for docker-compose.yml or Dockerfile
        match = re.search(r"(?:docker-compose\.yml|Dockerfile)", answer, re.IGNORECASE)
        if match:
            return match.group()

        return ""


def main() -> int:
    """
    Main entry point for the CLI.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    # Check command-line arguments
    if len(sys.argv) != 2:
        print('Usage: uv run agent.py "<question>"', file=sys.stderr)
        return 1

    question = sys.argv[1]

    # Load LLM settings from .env.agent.secret
    try:
        settings = Settings()
        print("Settings loaded from .env.agent.secret", file=sys.stderr)
    except Exception as e:
        print(f"Error loading settings: {e}", file=sys.stderr)
        print(
            "Make sure .env.agent.secret exists with LLM_API_KEY, LLM_API_BASE, LLM_MODEL",
            file=sys.stderr,
        )
        return 1

    # Load LMS_API_KEY from .env.docker.secret if not already in environment
    # This allows the autochecker to inject its own value
    if not os.environ.get("LMS_API_KEY"):
        env_docker_path = Path(".env.docker.secret")
        if env_docker_path.exists():
            for line in env_docker_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("LMS_API_KEY="):
                    _, _, value = line.partition("=")
                    os.environ["LMS_API_KEY"] = value.strip().strip('"').strip("'")
                    print("LMS_API_KEY loaded from .env.docker.secret", file=sys.stderr)
                    break

    # Set AGENT_API_BASE_URL from settings if not in environment
    if not os.environ.get("AGENT_API_BASE_URL"):
        os.environ["AGENT_API_BASE_URL"] = settings.agent_api_base_url

    # Create agent and get answer
    try:
        agent = Agent(settings)
        result = agent.ask(question)
    except httpx.HTTPStatusError as e:
        print(f"HTTP error from LLM API: {e.response.status_code}", file=sys.stderr)
        print(f"Response: {e.response.text}", file=sys.stderr)
        return 1
    except httpx.RequestError as e:
        print(f"Request failed: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1

    # Output JSON to stdout
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
