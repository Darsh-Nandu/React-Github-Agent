"""
github_tools/github_toolkit.py

All GitHub operations exposed as LangChain @tool functions.
Uses PyGithub under the hood.

Tools exposed:
  - list_repos           → list user's repositories
  - read_github_file     → read a file from any repo/branch
  - write_github_file    → create or update a file with a commit
  - create_branch        → create a new branch
  - list_branches        → list branches in a repo
  - search_code          → search code across repos
  - list_issues          → list open/closed issues
  - create_issue         → open a new issue
  - add_issue_comment    → comment on an issue
  - close_issue          → close an issue
  - list_pull_requests   → list PRs
  - create_pull_request  → open a PR
  - get_pr_diff          → get the diff of a PR
  - list_commits         → list recent commits on a branch
  - get_file_tree        → list all files in a repo/directory
"""

import os
import base64
from typing import Optional

from github import Github, GithubException
from langchain.tools import tool


def _get_client() -> Github:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN not set in environment")
    return Github(token)


# Repository
@tool
def list_repos(visibility: str = "all") -> str:
    """
    List GitHub repositories for the authenticated user.
    Args:
        visibility: 'all', 'public', or 'private'
    Returns a formatted list of repo names with descriptions.
    """
    g = _get_client()
    user = g.get_user()
    repos = user.get_repos(visibility=visibility)
    lines = []
    for r in repos:
        desc = f" — {r.description}" if r.description else ""
        lines.append(f"• {r.full_name}{desc} [{r.default_branch}]")
    return "\n".join(lines) if lines else "No repositories found."


@tool
def get_file_tree(repo: str, path: str = "", branch: str = "main") -> str:
    """
    List all files and directories in a repo path.
    Args:
        repo: Full repo name, e.g. 'username/my-repo'
        path: Sub-directory path (empty string = root)
        branch: Branch name (default: main)
    """
    g = _get_client()
    try:
        repository = g.get_repo(repo)
        contents = repository.get_contents(path, ref=branch)
        if isinstance(contents, list):
            lines = []
            for item in contents:
                icon = "📁" if item.type == "dir" else "📄"
                lines.append(f"{icon} {item.path}")
            return "\n".join(lines) if lines else "Empty directory."
        else:
            return f"📄 {contents.path} ({contents.size} bytes)"
    except GithubException as e:
        return f"Error: {e.data.get('message', str(e))}"


# File operations
@tool
def read_github_file(repo: str, path: str, branch: str = "main") -> str:
    """
    Read the contents of a file from a GitHub repository.
    Args:
        repo: Full repo name, e.g. 'username/my-repo'
        path: File path within the repo, e.g. 'src/main.py'
        branch: Branch name (default: main)
    Returns the raw file content as a string.
    """
    g = _get_client()
    try:
        repository = g.get_repo(repo)
        file_obj = repository.get_contents(path, ref=branch)
        if isinstance(file_obj, list):
            return f"Error: '{path}' is a directory, not a file."
        content = base64.b64decode(file_obj.content).decode("utf-8", errors="replace")
        return f"```\n{content}\n```"
    except GithubException as e:
        return f"Error reading file: {e.data.get('message', str(e))}"


@tool
def write_github_file(
    repo: str,
    path: str,
    content: str,
    commit_message: str,
    branch: str = "main",
) -> str:
    """
    Create or update a file in a GitHub repository with a commit.
    If the file already exists it will be updated; otherwise created.
    Args:
        repo: Full repo name, e.g. 'username/my-repo'
        path: File path within the repo, e.g. 'src/hello.py'
        content: Full file content to write
        commit_message: Git commit message
        branch: Branch to commit to (default: main)
    Returns a success message with the commit SHA.
    """
    g = _get_client()
    try:
        repository = g.get_repo(repo)
        try:
            existing = repository.get_contents(path, ref=branch)
            # File exists — update it
            result = repository.update_file(
                path=path,
                message=commit_message,
                content=content,
                sha=existing.sha,
                branch=branch,
            )
            sha = result["commit"].sha[:7]
            return f"✅ Updated `{path}` on `{branch}` (commit {sha})"
        except GithubException:
            # File does not exist — create it
            result = repository.create_file(
                path=path,
                message=commit_message,
                content=content,
                branch=branch,
            )
            sha = result["commit"].sha[:7]
            return f"✅ Created `{path}` on `{branch}` (commit {sha})"
    except GithubException as e:
        return f"Error writing file: {e.data.get('message', str(e))}"


# Branches
@tool
def create_branch(repo: str, branch_name: str, from_branch: str = "main") -> str:
    """
    Create a new branch in a GitHub repository.
    Args:
        repo: Full repo name
        branch_name: Name for the new branch
        from_branch: Source branch to branch off from (default: main)
    """
    g = _get_client()
    try:
        repository = g.get_repo(repo)
        source = repository.get_branch(from_branch)
        repository.create_git_ref(
            ref=f"refs/heads/{branch_name}",
            sha=source.commit.sha,
        )
        return f"✅ Created branch `{branch_name}` from `{from_branch}`"
    except GithubException as e:
        return f"Error creating branch: {e.data.get('message', str(e))}"


@tool
def list_branches(repo: str) -> str:
    """
    List all branches in a GitHub repository.
    Args:
        repo: Full repo name, e.g. 'username/my-repo'
    """
    g = _get_client()
    try:
        repository = g.get_repo(repo)
        branches = [b.name for b in repository.get_branches()]
        return "\n".join(f"• {b}" for b in branches) or "No branches found."
    except GithubException as e:
        return f"Error: {e.data.get('message', str(e))}"


@tool
def list_commits(repo: str, branch: str = "main", limit: int = 10) -> str:
    """
    List recent commits on a branch.
    Args:
        repo: Full repo name
        branch: Branch name (default: main)
        limit: Number of commits to return (default: 10)
    """
    g = _get_client()
    try:
        repository = g.get_repo(repo)
        commits = list(repository.get_commits(sha=branch))[:limit]
        lines = []
        for c in commits:
            msg = c.commit.message.split("\n")[0][:72]
            sha = c.sha[:7]
            date = c.commit.author.date.strftime("%Y-%m-%d")
            lines.append(f"[{sha}] {date} — {msg}")
        return "\n".join(lines) or "No commits found."
    except GithubException as e:
        return f"Error: {e.data.get('message', str(e))}"


# Search
@tool
def search_code(query: str, repo: Optional[str] = None) -> str:
    """
    Search code across GitHub repositories.
    Args:
        query: Search query (supports GitHub code search syntax)
        repo: Optional — restrict search to a specific repo ('username/repo')
    Returns matching file paths and snippets.
    """
    g = _get_client()
    try:
        full_query = f"{query} repo:{repo}" if repo else query
        results = g.search_code(full_query)
        lines = []
        for item in list(results)[:10]:
            lines.append(f"📄 {item.repository.full_name}/{item.path}")
            if item.text_matches:
                snippet = item.text_matches[0].get("fragment", "")[:100]
                lines.append(f"   ...{snippet}...")
        return "\n".join(lines) if lines else "No results found."
    except GithubException as e:
        return f"Error searching: {e.data.get('message', str(e))}"


# Issues
@tool
def list_issues(repo: str, state: str = "open", limit: int = 20) -> str:
    """
    List issues in a GitHub repository.
    Args:
        repo: Full repo name
        state: 'open', 'closed', or 'all'
        limit: Max number of issues to return
    """
    g = _get_client()
    try:
        repository = g.get_repo(repo)
        issues = list(repository.get_issues(state=state))[:limit]
        lines = []
        for i in issues:
            labels = ", ".join(l.name for l in i.labels)
            label_str = f" [{labels}]" if labels else ""
            lines.append(f"#{i.number} {i.title}{label_str}")
        return "\n".join(lines) if lines else f"No {state} issues found."
    except GithubException as e:
        return f"Error: {e.data.get('message', str(e))}"


@tool
def create_issue(
    repo: str,
    title: str,
    body: str,
    labels: Optional[str] = None,
) -> str:
    """
    Create a new issue in a GitHub repository.
    Args:
        repo: Full repo name
        title: Issue title
        body: Issue body (supports Markdown)
        labels: Comma-separated label names (optional)
    """
    g = _get_client()
    try:
        repository = g.get_repo(repo)
        label_list = [l.strip() for l in labels.split(",")] if labels else []
        label_objs = [repository.get_label(l) for l in label_list] if label_list else []
        issue = repository.create_issue(
            title=title,
            body=body,
            labels=label_objs,
        )
        return f"✅ Created issue #{issue.number}: {issue.html_url}"
    except GithubException as e:
        return f"Error creating issue: {e.data.get('message', str(e))}"


@tool
def add_issue_comment(repo: str, issue_number: int, comment: str) -> str:
    """
    Add a comment to a GitHub issue.
    Args:
        repo: Full repo name
        issue_number: Issue number (integer)
        comment: Comment body (Markdown supported)
    """
    g = _get_client()
    try:
        repository = g.get_repo(repo)
        issue = repository.get_issue(issue_number)
        result = issue.create_comment(comment)
        return f"✅ Comment added: {result.html_url}"
    except GithubException as e:
        return f"Error commenting: {e.data.get('message', str(e))}"


@tool
def close_issue(repo: str, issue_number: int, comment: Optional[str] = None) -> str:
    """
    Close a GitHub issue, optionally with a closing comment.
    Args:
        repo: Full repo name
        issue_number: Issue number (integer)
        comment: Optional closing comment
    """
    g = _get_client()
    try:
        repository = g.get_repo(repo)
        issue = repository.get_issue(issue_number)
        if comment:
            issue.create_comment(comment)
        issue.edit(state="closed")
        return f"✅ Closed issue #{issue_number}"
    except GithubException as e:
        return f"Error closing issue: {e.data.get('message', str(e))}"


# Pull Requests
@tool
def list_pull_requests(repo: str, state: str = "open") -> str:
    """
    List pull requests in a GitHub repository.
    Args:
        repo: Full repo name
        state: 'open', 'closed', or 'all'
    """
    g = _get_client()
    try:
        repository = g.get_repo(repo)
        prs = list(repository.get_pulls(state=state))[:20]
        lines = []
        for pr in prs:
            lines.append(f"PR #{pr.number}: {pr.title} ({pr.head.ref} → {pr.base.ref})")
        return "\n".join(lines) if lines else f"No {state} PRs found."
    except GithubException as e:
        return f"Error: {e.data.get('message', str(e))}"


@tool
def create_pull_request(
    repo: str,
    title: str,
    body: str,
    head: str,
    base: str = "main",
) -> str:
    """
    Open a pull request on GitHub.
    Args:
        repo: Full repo name
        title: PR title
        body: PR description (Markdown supported)
        head: Source branch (the branch with your changes)
        base: Target branch to merge into (default: main)
    """
    g = _get_client()
    try:
        repository = g.get_repo(repo)
        pr = repository.create_pull(
            title=title,
            body=body,
            head=head,
            base=base,
        )
        return f"✅ Created PR #{pr.number}: {pr.html_url}"
    except GithubException as e:
        return f"Error creating PR: {e.data.get('message', str(e))}"


@tool
def get_pr_diff(repo: str, pr_number: int) -> str:
    """
    Get the diff (changed files and code) for a pull request.
    Args:
        repo: Full repo name
        pr_number: PR number (integer)
    """
    g = _get_client()
    try:
        repository = g.get_repo(repo)
        pr = repository.get_pull(pr_number)
        files = pr.get_files()
        lines = [f"PR #{pr_number}: {pr.title}\n"]
        for f in files:
            lines.append(f"--- {f.filename} (+{f.additions} -{f.deletions})")
            if f.patch:
                lines.append(f.patch[:500])
            lines.append("")
        return "\n".join(lines)
    except GithubException as e:
        return f"Error getting PR diff: {e.data.get('message', str(e))}"


# Tool List for Agent Binding


def get_github_tools():
    """Return all GitHub tools as a flat list for binding to the agent."""
    return [
        list_repos,
        get_file_tree,
        read_github_file,
        write_github_file,
        create_branch,
        list_branches,
        list_commits,
        search_code,
        list_issues,
        create_issue,
        add_issue_comment,
        close_issue,
        list_pull_requests,
        create_pull_request,
        get_pr_diff,
    ]
