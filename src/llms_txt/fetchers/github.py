import logging
import shutil
import tempfile
from pathlib import Path

from git import Repo
from git.exc import GitCommandError

from ..core.exceptions import FetchError
from ..core.models import CodeLocation, Package

logger = logging.getLogger(__name__)


class GitHubFetcher:
    """Fetches repositories from GitHub"""

    def __init__(self):
        self._temp_dirs: list[Path] = []

    async def fetch(self, package: Package) -> CodeLocation:
        """Clone repository and return its location"""
        if not package.repository_url or "github.com" not in package.repository_url:
            raise FetchError(f"Invalid GitHub repository URL: {package.repository_url}")

        temp_dir = Path(tempfile.mkdtemp())
        self._temp_dirs.append(temp_dir)

        try:
            clone_url = self._get_clone_url(package.repository_url)
            repo = await self._clone_repository(clone_url, temp_dir)

            return CodeLocation(
                path=temp_dir,
                source_url=package.repository_url,
                metadata={
                    "type": "github",
                    "default_branch": repo.active_branch.name,
                    "commit_hash": repo.head.commit.hexsha,
                },
            )

        except Exception as e:
            await self.cleanup()
            raise FetchError(f"Failed to fetch repository: {str(e)}") from e

    async def cleanup(self) -> None:
        """Remove all temporary directories"""
        for temp_dir in self._temp_dirs:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
        self._temp_dirs.clear()

    def _get_clone_url(self, repo_url: str) -> str:
        """Convert GitHub URL to clone URL"""
        return repo_url.rstrip("/") + ".git"

    async def _clone_repository(self, url: str, path: Path) -> Repo:
        """Clone repository and detect default branch"""
        try:
            # Initialize temporary repo to get default branch
            temp_repo = Repo.init(path)
            temp_repo.create_remote("origin", url)

            # Fetch remote info
            refs = temp_repo.git.ls_remote("--heads", "origin").split("\n")
            if not refs:
                raise FetchError("No branches found in repository")

            # Detect default branch
            default_branch = self._detect_default_branch(refs)
            logger.info(f"Using default branch: {default_branch}")

            # Remove temporary repo
            shutil.rmtree(path)

            # Clone repository with detected branch
            return Repo.clone_from(
                url=url, to_path=path, depth=1, branch=default_branch
            )

        except GitCommandError as e:
            raise FetchError(f"Git operation failed: {str(e)}")

    def _detect_default_branch(self, refs: list[str]) -> str:
        """Detect default branch from git refs"""
        for ref in refs:
            if not ref:
                continue
            _, ref_name = ref.split("\t")
            ref_name = ref_name.replace("refs/heads/", "")
            if ref_name in ["main", "master"]:
                return ref_name

        # If no common default branch found, use first one
        _, ref_name = refs[0].split("\t")
        return ref_name.replace("refs/heads/", "")
