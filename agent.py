#!/usr/bin/env python3
"""
Agent CLI - Documentation agent with tool calling capabilities.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "source": "...", "tool_calls": [...]}
"""

import json
import sys
from pathlib import Path
from typing import Any

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """LLM configuration loaded from .env.agent.secret."""

    model_config = SettingsConfigDict(
        env_file=".env.agent.secret",
        env_file_encoding="utf-8",
    )

    llm_api_key: str
    llm_api_base: str
    llm_model: str = "qwen3-coder-plus"


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
]

# System prompt for the documentation agent
SYSTEM_PROMPT = """You are a documentation agent that answers questions about a software engineering project by reading the project's wiki.

You have access to two tools:
- list_files: List files and directories in a given path
- read_file: Read the contents of a specific file

To answer a question:
1. First use list_files to discover relevant files in the wiki/ directory
2. Then use read_file to read specific files that may contain the answer
3. Look for section headers (lines starting with # or ##) to identify relevant sections
4. When you find the answer, include the source as: wiki/filename.md#section-anchor
   - Section anchors are lowercase with hyphens instead of spaces (e.g., "resolving-merge-conflicts")
5. Once you have enough information, provide your final answer with the source

Always include the source reference in your answer. The source should be in the format: wiki/filename.md#section-anchor

If you cannot find the answer in the wiki, say so honestly.
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

    # Load settings
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
