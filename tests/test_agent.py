"""
Regression tests for agent.py.

Tests verify that the agent CLI:
1. Runs successfully with a question argument
2. Outputs valid JSON to stdout
3. Contains required 'answer' and 'tool_calls' fields
"""

import json
import subprocess
import sys
from pathlib import Path


def test_agent_returns_valid_json():
    """
    Test that agent.py returns valid JSON with required fields.

    This test:
    1. Runs agent.py as a subprocess with a test question
    2. Parses the stdout as JSON
    3. Asserts 'answer' field exists and is a non-empty string
    4. Asserts 'tool_calls' field exists and is a list
    """
    # Get the project root directory (parent of tests/)
    project_root = Path(__file__).parent.parent
    agent_path = project_root / "agent.py"

    # Test question
    question = "What is the capital of France?"

    # Run agent.py as subprocess using uv run
    result = subprocess.run(
        ["uv", "run", "agent.py", question],
        capture_output=True,
        text=True,
        cwd=project_root,
        timeout=60,
    )

    # Check exit code
    assert result.returncode == 0, f"Agent failed with: {result.stderr}"

    # Parse stdout as JSON
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(
            f"Agent output is not valid JSON: {result.stdout}\nError: {e}"
        ) from e

    # Check 'answer' field exists and is non-empty string
    assert "answer" in output, "Missing 'answer' field in output"
    assert isinstance(output["answer"], str), "'answer' must be a string"
    assert len(output["answer"].strip()) > 0, "'answer' must not be empty"

    # Check 'tool_calls' field exists and is a list
    assert "tool_calls" in output, "Missing 'tool_calls' field in output"
    assert isinstance(output["tool_calls"], list), "'tool_calls' must be a list"


def test_agent_missing_argument():
    """
    Test that agent.py returns non-zero exit code when no argument is provided.
    """
    project_root = Path(__file__).parent.parent

    result = subprocess.run(
        ["uv", "run", "agent.py"],
        capture_output=True,
        text=True,
        cwd=project_root,
        timeout=10,
    )

    # Should fail with usage message
    assert result.returncode != 0, "Agent should fail without arguments"
    assert "Usage" in result.stderr, "Should show usage message"
