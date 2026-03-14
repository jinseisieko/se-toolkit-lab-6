#!/usr/bin/env python3
"""
Agent CLI - Calls an LLM and returns a structured JSON answer.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "tool_calls": []}
"""

import json
import sys
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


class LLMClient:
    """Client for OpenAI-compatible LLM APIs."""

    def __init__(self, settings: Settings):
        self.api_key = settings.llm_api_key
        self.api_base = settings.llm_api_base.rstrip("/")
        self.model = settings.llm_model

    def chat_completion(self, messages: list[dict[str, str]]) -> str:
        """
        Send a chat completion request to the LLM API.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.

        Returns:
            The assistant's response content as a string.

        Raises:
            httpx.HTTPStatusError: If the API returns an error status.
            httpx.RequestError: If the request fails.
        """
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
        }

        print(f"Sending request to {url}", file=sys.stderr)
        print(f"Model: {self.model}", file=sys.stderr)

        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        print(f"LLM response received ({len(content)} chars)", file=sys.stderr)
        return content


class Agent:
    """Agent that answers questions using an LLM."""

    def __init__(self, settings: Settings):
        self.client = LLMClient(settings)
        # System prompt for Task 1 - minimal, will be expanded in later tasks
        self.system_prompt = (
            "You are a helpful assistant. Answer questions concisely and accurately."
        )

    def ask(self, question: str) -> dict[str, Any]:
        """
        Ask a question and get a structured answer.

        Args:
            question: The user's question.

        Returns:
            Dict with 'answer' (str) and 'tool_calls' (list) keys.
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": question},
        ]

        print("Sending question to LLM...", file=sys.stderr)
        answer = self.client.chat_completion(messages)
        print("Got answer from LLM", file=sys.stderr)

        return {
            "answer": answer,
            "tool_calls": [],  # Empty for Task 1 - tools added in Task 2
        }


def main() -> int:
    """
    Main entry point for the CLI.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    # Check command-line arguments
    if len(sys.argv) != 2:
        print(
            'Usage: uv run agent.py "<question>"',
            file=sys.stderr,
        )
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
