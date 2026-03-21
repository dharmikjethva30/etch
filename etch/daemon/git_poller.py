"""Git poller for monitoring commits."""

import threading
import time
from pathlib import Path
from typing import Optional

from git import Repo, GitCommandError

from etch.memory.store import Store


class GitPoller:
    """Polls git repository for new commits."""

    def __init__(self, repo_path: Path, store: Store, project_id: str):
        """Initialize git poller.

        Args:
            repo_path: Path to git repository
            store: Store instance for recording commits
            project_id: Project identifier
        """
        self.repo_path = Path(repo_path)
        self.store = store
        self.project_id = project_id
        self.repo = Repo(str(self.repo_path))
        self._last_commit_hash: Optional[str] = None
        self._stop_event = threading.Event()

    def poll(self) -> int:
        """Poll for new commits since last known.

        Returns:
            Number of new commits found
        """
        try:
            # Get starting point
            if self._last_commit_hash is None:
                # First poll - check DB for last known
                self._last_commit_hash = self.store.get_latest_commit_hash(self.project_id)

            new_commits = 0

            # Walk all commits
            for commit in self.repo.iter_commits():
                commit_hash = commit.hexsha

                # If we've reached the last known commit, stop
                if commit_hash == self._last_commit_hash:
                    break

                # Process this commit
                files_changed = []
                lines_added = 0
                lines_removed = 0

                try:
                    if commit.parents:
                        diff_index = commit.parents[0].diff(commit)
                        for item in diff_index:
                            if item.b_path:
                                files_changed.append(item.b_path)
                    else:
                        # Initial commit
                        for item in commit.tree.traverse():
                            if item.type == "blob":
                                files_changed.append(item.path)

                    stats = commit.stats.total
                    lines_added = stats.get("insertions", 0)
                    lines_removed = stats.get("deletions", 0)
                except Exception:
                    pass

                diff_summary = f"{len(files_changed)} files, +{lines_added}/-{lines_removed}"

                self.store.add_git_commit(
                    commit_hash=commit_hash,
                    ts=int(commit.committed_date),
                    message=commit.message.split("\n")[0],
                    author=commit.author.name if commit.author else "unknown",
                    diff_summary=diff_summary,
                    files_changed=files_changed,
                    project_id=self.project_id,
                )

                new_commits += 1

                # Update last known (after storing first new commit)
                if self._last_commit_hash is None:
                    self._last_commit_hash = commit_hash

            # Update last known to most recent
            try:
                head_commit = self.repo.head.commit
                self._last_commit_hash = head_commit.hexsha
            except Exception:
                pass

            return new_commits

        except GitCommandError:
            return 0
        except Exception:
            return 0

    def run(self, interval: int = 60) -> None:
        """Run poller loop until stopped.

        Args:
            interval: Poll interval in seconds
        """
        while not self._stop_event.is_set():
            try:
                self.poll()
            except Exception:
                pass
            self._stop_event.wait(interval)

    def stop(self) -> None:
        """Stop poller loop."""
        self._stop_event.set()
