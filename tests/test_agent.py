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


def test_documentation_agent_reads_file():
    """
    Test that the documentation agent uses read_file tool and includes source.

    Question: "How do you resolve a merge conflict?"
    Expected:
    - read_file in tool_calls
    - wiki/git.md or wiki/git-workflow.md or wiki/git-vscode.md in source
    """
    project_root = Path(__file__).parent.parent

    question = "How do you resolve a merge conflict?"

    result = subprocess.run(
        ["uv", "run", "agent.py", question],
        capture_output=True,
        text=True,
        cwd=project_root,
        timeout=120,
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

    # Check required fields
    assert "answer" in output, "Missing 'answer' field in output"
    assert "source" in output, "Missing 'source' field in output"
    assert "tool_calls" in output, "Missing 'tool_calls' field in output"

    # Check that read_file was used
    tool_names = [tc.get("tool") for tc in output["tool_calls"]]
    assert "read_file" in tool_names, "Expected read_file to be called"

    # Check that source contains wiki reference
    source = output["source"]
    assert "wiki/" in source or any(
        "wiki/" in tc.get("result", "") for tc in output["tool_calls"]
    ), "Expected wiki reference in source or tool results"


def test_documentation_agent_lists_files():
    """
    Test that the documentation agent uses list_files tool.

    Question: "What files are in the wiki directory?"
    Expected: list_files in tool_calls
    """
    project_root = Path(__file__).parent.parent

    question = "What files are in the wiki directory?"

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

    # Check required fields
    assert "answer" in output, "Missing 'answer' field in output"
    assert "tool_calls" in output, "Missing 'tool_calls' field in output"

    # Check that list_files was used
    tool_names = [tc.get("tool") for tc in output["tool_calls"]]
    assert "list_files" in tool_names, "Expected list_files to be called"

    # Check that the tool result contains wiki files
    for tc in output["tool_calls"]:
        if tc.get("tool") == "list_files":
            result_text = tc.get("result", "")
            path = tc.get("args", {}).get("path", "")
            assert "wiki" in path, "Expected list_files to be called with wiki path"
            # Check that result contains some expected files
            assert ".md" in result_text, "Expected markdown files in result"


def test_system_agent_reads_source_code():
    """
    Test that the system agent uses read_file for framework questions.

    Question: "What framework does the backend use?"
    Expected: read_file in tool_calls
    """
    project_root = Path(__file__).parent.parent

    question = "What Python web framework does this project's backend use?"

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

    # Check required fields
    assert "answer" in output, "Missing 'answer' field in output"

    # Check that read_file was used
    tool_names = [tc.get("tool") for tc in output["tool_calls"]]
    assert "read_file" in tool_names, "Expected read_file to be called"


def test_system_agent_queries_api():
    """
    Test that the system agent uses query_api for data questions.

    Question: "How many items are in the database?"
    Expected: query_api in tool_calls
    """
    project_root = Path(__file__).parent.parent

    question = "How many items are currently stored in the database?"

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

    # Check required fields
    assert "answer" in output, "Missing 'answer' field in output"

    # Check that query_api was used
    tool_names = [tc.get("tool") for tc in output["tool_calls"]]
    assert "query_api" in tool_names, "Expected query_api to be called"

    # Check that the answer contains a number
    import re

    answer = output.get("answer", "")
    numbers = re.findall(r"\d+", answer)
    assert len(numbers) > 0, "Expected a number in the answer"
    # The number should be greater than 0 (there are items in the database)
    assert any(int(n) > 0 for n in numbers), "Expected a positive number in the answer"
