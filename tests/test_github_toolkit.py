"""
tests/test_github_toolkit.py

Unit tests for github_tools/github_toolkit.py.
All GitHub API calls are mocked — no network required.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

# Helpers


def _make_repo(
    full_name="owner/repo", description="A test repo", default_branch="main"
):
    repo = MagicMock()
    repo.full_name = full_name
    repo.description = description
    repo.default_branch = default_branch
    return repo


def _make_content(path="README.md", content_b64=None, size=42, type_="file"):
    import base64

    obj = MagicMock()
    obj.path = path
    obj.size = size
    obj.type = type_
    obj.content = content_b64 or base64.b64encode(b"Hello, world!").decode()
    obj.sha = "abc123"
    return obj


# list_repos


class TestListRepos:
    def test_returns_repo_names(self):
        from github_tools.github_toolkit import list_repos

        mock_repo = _make_repo("owner/alpha", "First repo")
        with patch("github_tools.github_toolkit._get_client") as mock_client:
            g = MagicMock()
            user = MagicMock()
            user.get_repos.return_value = [mock_repo]
            g.get_user.return_value = user
            mock_client.return_value = g

            result = list_repos.invoke({"visibility": "all"})

        assert "owner/alpha" in result
        assert "First repo" in result

    def test_empty_returns_message(self):
        from github_tools.github_toolkit import list_repos

        with patch("github_tools.github_toolkit._get_client") as mock_client:
            g = MagicMock()
            user = MagicMock()
            user.get_repos.return_value = []
            g.get_user.return_value = user
            mock_client.return_value = g

            result = list_repos.invoke({"visibility": "all"})

        assert result == "No repositories found."

    def test_repo_without_description(self):
        from github_tools.github_toolkit import list_repos

        repo = _make_repo(description=None)
        with patch("github_tools.github_toolkit._get_client") as mock_client:
            g = MagicMock()
            user = MagicMock()
            user.get_repos.return_value = [repo]
            g.get_user.return_value = user
            mock_client.return_value = g

            result = list_repos.invoke({"visibility": "all"})

        assert "owner/repo" in result
        assert " — None" not in result


# read_github_file


class TestReadGithubFile:
    def test_reads_file_content(self):
        import base64
        from github_tools.github_toolkit import read_github_file

        encoded = base64.b64encode(b"print('hello')").decode()
        content = _make_content("src/main.py", content_b64=encoded)

        with patch("github_tools.github_toolkit._get_client") as mock_client:
            g = MagicMock()
            repo = MagicMock()
            repo.get_contents.return_value = content
            g.get_repo.return_value = repo
            mock_client.return_value = g

            result = read_github_file.invoke(
                {"repo": "owner/repo", "path": "src/main.py", "branch": "main"}
            )

        assert "print('hello')" in result

    def test_returns_error_for_directory(self):
        from github_tools.github_toolkit import read_github_file

        with patch("github_tools.github_toolkit._get_client") as mock_client:
            g = MagicMock()
            repo = MagicMock()
            # get_contents returns a list → it's a directory
            repo.get_contents.return_value = [_make_content(), _make_content()]
            g.get_repo.return_value = repo
            mock_client.return_value = g

            result = read_github_file.invoke(
                {"repo": "owner/repo", "path": "src", "branch": "main"}
            )

        assert "Error" in result
        assert "directory" in result

    def test_github_exception_handled(self):
        from github import GithubException
        from github_tools.github_toolkit import read_github_file

        with patch("github_tools.github_toolkit._get_client") as mock_client:
            g = MagicMock()
            repo = MagicMock()
            repo.get_contents.side_effect = GithubException(
                404, {"message": "Not Found"}, None
            )
            g.get_repo.return_value = repo
            mock_client.return_value = g

            result = read_github_file.invoke(
                {"repo": "owner/repo", "path": "missing.py", "branch": "main"}
            )

        assert "Error" in result or "Not Found" in result


# write_github_file


class TestWriteGithubFile:
    def test_creates_new_file(self):
        from github_tools.github_toolkit import write_github_file

        with patch("github_tools.github_toolkit._get_client") as mock_client:
            g = MagicMock()
            repo = MagicMock()
            from github import GithubException

            repo.get_contents.side_effect = GithubException(404, {}, None)
            commit_result = {"commit": MagicMock(sha="deadbeef")}
            repo.create_file.return_value = commit_result
            g.get_repo.return_value = repo
            mock_client.return_value = g

            result = write_github_file.invoke(
                {
                    "repo": "owner/repo",
                    "path": "new_file.py",
                    "content": "x = 1",
                    "commit_message": "Add new_file.py",
                    "branch": "main",
                }
            )

        assert (
            "deadbeef" in result
            or "created" in result.lower()
            or "new_file.py" in result
        )

    def test_updates_existing_file(self):
        from github_tools.github_toolkit import write_github_file

        with patch("github_tools.github_toolkit._get_client") as mock_client:
            g = MagicMock()
            repo = MagicMock()
            existing = _make_content("existing.py")
            repo.get_contents.return_value = existing
            commit_result = {"commit": MagicMock(sha="cafebabe")}
            repo.update_file.return_value = commit_result
            g.get_repo.return_value = repo
            mock_client.return_value = g

            result = write_github_file.invoke(
                {
                    "repo": "owner/repo",
                    "path": "existing.py",
                    "content": "x = 2",
                    "commit_message": "Update existing.py",
                    "branch": "main",
                }
            )

        assert (
            "cafebabe" in result
            or "updated" in result.lower()
            or "existing.py" in result
        )


# get_file_tree


class TestGetFileTree:
    def test_lists_files_and_dirs(self):
        from github_tools.github_toolkit import get_file_tree

        file_item = MagicMock()
        file_item.type = "file"
        file_item.path = "README.md"
        dir_item = MagicMock()
        dir_item.type = "dir"
        dir_item.path = "src"

        with patch("github_tools.github_toolkit._get_client") as mock_client:
            g = MagicMock()
            repo = MagicMock()
            repo.get_contents.return_value = [file_item, dir_item]
            g.get_repo.return_value = repo
            mock_client.return_value = g

            result = get_file_tree.invoke(
                {"repo": "owner/repo", "path": "", "branch": "main"}
            )

        assert "README.md" in result
        assert "src" in result

    def test_empty_directory(self):
        from github_tools.github_toolkit import get_file_tree

        with patch("github_tools.github_toolkit._get_client") as mock_client:
            g = MagicMock()
            repo = MagicMock()
            repo.get_contents.return_value = []
            g.get_repo.return_value = repo
            mock_client.return_value = g

            result = get_file_tree.invoke(
                {"repo": "owner/repo", "path": "empty/", "branch": "main"}
            )

        assert "Empty" in result or result == ""


# create_branch


class TestCreateBranch:
    def test_creates_branch_from_main(self):
        from github_tools.github_toolkit import create_branch

        with patch("github_tools.github_toolkit._get_client") as mock_client:
            g = MagicMock()
            repo = MagicMock()
            source_ref = MagicMock()
            source_ref.object.sha = "sha123"
            repo.get_git_ref.return_value = source_ref
            g.get_repo.return_value = repo
            mock_client.return_value = g

            result = create_branch.invoke(
                {
                    "repo": "owner/repo",
                    "branch_name": "feature/new",
                    "from_branch": "main",
                }
            )

        repo.create_git_ref.assert_called_once()
        assert "feature/new" in result or "created" in result.lower()

    def test_handles_existing_branch(self):
        from github import GithubException
        from github_tools.github_toolkit import create_branch

        with patch("github_tools.github_toolkit._get_client") as mock_client:
            g = MagicMock()
            repo = MagicMock()
            source_ref = MagicMock()
            source_ref.object.sha = "sha123"
            repo.get_git_ref.return_value = source_ref
            repo.create_git_ref.side_effect = GithubException(
                422, {"message": "Reference already exists"}, None
            )
            g.get_repo.return_value = repo
            mock_client.return_value = g

            result = create_branch.invoke(
                {
                    "repo": "owner/repo",
                    "branch_name": "feature/existing",
                    "from_branch": "main",
                }
            )

        assert "Error" in result or "already exists" in result.lower()


# create_issue


class TestCreateIssue:
    def test_creates_issue(self):
        from github_tools.github_toolkit import create_issue

        with patch("github_tools.github_toolkit._get_client") as mock_client:
            g = MagicMock()
            repo = MagicMock()
            issue = MagicMock()
            issue.number = 42
            issue.html_url = "https://github.com/owner/repo/issues/42"
            repo.create_issue.return_value = issue
            g.get_repo.return_value = repo
            mock_client.return_value = g

            result = create_issue.invoke(
                {
                    "repo": "owner/repo",
                    "title": "Bug: something broken",
                    "body": "Details here",
                }
            )

        assert "42" in result
        assert "github.com" in result


# create_pull_request


class TestCreatePullRequest:
    def test_creates_pr(self):
        from github_tools.github_toolkit import create_pull_request

        with patch("github_tools.github_toolkit._get_client") as mock_client:
            g = MagicMock()
            repo = MagicMock()
            pr = MagicMock()
            pr.number = 7
            pr.html_url = "https://github.com/owner/repo/pull/7"
            repo.create_pull.return_value = pr
            g.get_repo.return_value = repo
            mock_client.return_value = g

            result = create_pull_request.invoke(
                {
                    "repo": "owner/repo",
                    "title": "Feature: add login",
                    "body": "Adds login page",
                    "head": "feature/login",
                    "base": "main",
                }
            )

        assert "7" in result
        assert "github.com" in result


# _get_client


class TestGetClient:
    def test_raises_without_token(self, monkeypatch):
        import importlib

        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        from github_tools import github_toolkit

        importlib.reload(github_toolkit)

        with pytest.raises(ValueError, match="GITHUB_TOKEN"):
            github_toolkit._get_client()

    def test_returns_client_with_token(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken")
        from github_tools.github_toolkit import _get_client

        with patch("github_tools.github_toolkit.Github") as MockGithub:
            MockGithub.return_value = MagicMock()
            client = _get_client()
        MockGithub.assert_called_once_with("ghp_testtoken")
