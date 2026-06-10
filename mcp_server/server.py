"""
mcp_server/server.py

FastMCP server exposing custom tools to the agent.
Run this SEPARATELY from the main FastAPI app:
  python mcp_server/server.py

The agent connects to it via SSE at http://localhost:8001/sse
"""

import sys
import subprocess
import tempfile
import os
import httpx
from typing import Optional

from fastmcp import FastMCP

mcp = FastMCP("agent-tools", instructions="Tools for the ReAct GitHub agent")


# Code Tools
@mcp.tool()
def run_python(code: str, timeout: int = 15) -> str:
    """
    Execute Python code in an isolated subprocess and return stdout/stderr.
    Use this to test code, run calculations, or validate logic.

    Args:
        code: Python source code to execute
        timeout: Max execution time in seconds (default: 15)
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        fname = f.name

    try:
        result = subprocess.run(
            [sys.executable, fname],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = ""
        if result.stdout:
            output += f"STDOUT:\n{result.stdout}"
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"
        if result.returncode != 0:
            output += f"\nExit code: {result.returncode}"
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: execution timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"
    finally:
        os.unlink(fname)


@mcp.tool()
def format_python_code(code: str) -> str:
    """
    Format Python code using Black.
    Returns the formatted code, or an error message.

    Args:
        code: Python source code to format
    """
    try:
        import black

        formatted = black.format_str(code, mode=black.Mode())
        return formatted
    except ImportError:
        return "Error: black not installed. Run: pip install black"
    except Exception as e:
        return f"Format error: {e}"


@mcp.tool()
def lint_python_code(code: str) -> str:
    """
    Lint Python code using Pylint. Returns issues found.

    Args:
        code: Python source code to lint
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        fname = f.name

    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pylint",
                fname,
                "--output-format=text",
                "--disable=C0114,C0115,C0116",
            ],  # suppress docstring warnings
            capture_output=True,
            text=True,
        )
        output = result.stdout + result.stderr
        # Strip the tempfile path from output for cleanliness
        output = output.replace(fname, "<code>")
        return output.strip() or "No issues found ✅"
    except Exception as e:
        return f"Lint error: {e}"
    finally:
        os.unlink(fname)


# Web Tools
@mcp.tool()
def fetch_url(url: str, max_chars: int = 5000) -> str:
    """
    Fetch the content of a URL and return it as plain text.
    Strips HTML tags. Useful for reading documentation, README files, etc.

    Args:
        url: URL to fetch
        max_chars: Maximum characters to return (default: 5000)
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; agent-tools/1.0)"}
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")

            if "html" in content_type:
                from bs4 import BeautifulSoup

                soup = BeautifulSoup(response.text, "html.parser")
                # Remove script/style tags
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
            else:
                text = response.text

            # Trim
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n\n[... truncated at {max_chars} chars]"
            return text

    except httpx.HTTPStatusError as e:
        return f"HTTP error {e.response.status_code}: {url}"
    except Exception as e:
        return f"Error fetching URL: {e}"


@mcp.tool()
def web_search(query: str, num_results: int = 5) -> str:
    """
    Search the web using DuckDuckGo (no API key required) and return results.
    This is a tool for answering general questions, finding documentation, or getting recent info.
    Args:
        query: Search query
        num_results: Number of results to return (default: 5)
    """
    try:
        encoded = httpx.QueryParams(q=query, format="json", no_html=1, skip_disambig=1)
        url = f"https://api.duckduckgo.com/?{encoded}"
        with httpx.Client(timeout=10) as client:
            response = client.get(url)
            data = response.json()

        results = []

        # Instant answer
        if data.get("AbstractText"):
            results.append(f"**Summary**: {data['AbstractText']}")
            if data.get("AbstractURL"):
                results.append(f"Source: {data['AbstractURL']}")
            results.append("")

        # Related topics
        for topic in data.get("RelatedTopics", [])[:num_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(f"• {topic['Text']}")
                if topic.get("FirstURL"):
                    results.append(f"  {topic['FirstURL']}")

        return "\n".join(results) if results else "No results found."

    except Exception as e:
        return f"Search error: {e}"


# Utility Tools
@mcp.tool()
def read_local_file(path: str) -> str:
    """
    Read a local file from the filesystem. Useful for reading config files,
    logs, or other files on the server.

    Args:
        path: Absolute or relative file path
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if len(content) > 10_000:
            content = content[:10_000] + "\n\n[... file truncated at 10000 chars]"
        return content
    except FileNotFoundError:
        return f"Error: File not found: {path}"
    except Exception as e:
        return f"Error reading file: {e}"


@mcp.tool()
def write_local_file(path: str, content: str) -> str:
    """
    Write content to a local file. Creates parent directories if needed.

    Args:
        path: File path to write to
        content: Content to write
    """
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(content)
        return f"✅ Written to {path} ({len(content)} chars)"
    except Exception as e:
        return f"Error writing file: {e}"


@mcp.tool()
def summarize_text(text: str, max_length: int = 500) -> str:
    """
    Produce a brief extractive summary of long text by keeping the most
    informative sentences (first + last paragraphs + key sentences).

    Args:
        text: Text to summarise
        max_length: Target summary length in characters
    """
    if len(text) <= max_length:
        return text

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return text[:max_length] + "..."

    summary_parts = []
    budget = max_length

    # Always include the first paragraph
    if paragraphs:
        first = paragraphs[0][:budget]
        summary_parts.append(first)
        budget -= len(first)

    # Middle: include first sentence of each middle paragraph
    for para in paragraphs[1:-1]:
        if budget <= 50:
            break
        first_sentence = para.split(".")[0] + "."
        summary_parts.append(first_sentence[:budget])
        budget -= len(first_sentence)

    # Last paragraph if budget allows
    if budget > 100 and len(paragraphs) > 1:
        summary_parts.append(paragraphs[-1][:budget])

    return "\n\n".join(summary_parts)


@mcp.tool()
def parse_json(json_string: str) -> str:
    """
    Parse and pretty-print a JSON string. Returns formatted JSON or an error.

    Args:
        json_string: Raw JSON string to parse and format
    """
    import json

    try:
        parsed = json.loads(json_string)
        return json.dumps(parsed, indent=2, ensure_ascii=False)
    except json.JSONDecodeError as e:
        return f"JSON parse error at position {e.pos}: {e.msg}"


@mcp.tool()
def diff_strings(text_a: str, text_b: str) -> str:
    """
    Show a unified diff between two strings. Useful for comparing code versions.

    Args:
        text_a: Original text
        text_b: New text
    """
    import difflib

    diff = difflib.unified_diff(
        text_a.splitlines(keepends=True),
        text_b.splitlines(keepends=True),
        fromfile="original",
        tofile="modified",
    )
    result = "".join(diff)
    return result if result else "No differences found."


# Entry Point
if __name__ == "__main__":
    print("Starting FastMCP server on http://localhost:8001")
    mcp.run(transport="sse", host="0.0.0.0", port=8001)
