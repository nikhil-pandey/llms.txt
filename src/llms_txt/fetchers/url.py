import logging
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import aiofiles
import aiohttp

from ..core.exceptions import FetchError
from ..core.models import CodeLocation, Package

logger = logging.getLogger(__name__)


class URLFetcher:
    """Fetches content from URLs"""

    def __init__(self):
        self._temp_dirs: list[Path] = []
        self.supported_extensions = {
            ".md": "markdown",
            ".txt": "text",
            ".rst": "restructuredtext",
            ".adoc": "asciidoc",
        }

    async def fetch(self, package: Package) -> CodeLocation:
        """Fetch content from URL and return its location"""
        if not package.documentation_url:
            raise FetchError(
                f"No documentation URL provided for package {package.name}"
            )

        url = package.documentation_url
        try:
            # Create temp directory
            temp_dir = Path(tempfile.mkdtemp())
            self._temp_dirs.append(temp_dir)

            # Determine URL type and handle accordingly
            if await self._is_direct_file(url):
                return await self._fetch_direct_file(url, temp_dir)
            else:
                return await self._handle_website(url, temp_dir)

        except Exception as e:
            await self.cleanup()
            raise FetchError(f"Failed to fetch URL {url}: {str(e)}") from e

    async def cleanup(self) -> None:
        """Remove all temporary directories"""
        for temp_dir in self._temp_dirs:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
        self._temp_dirs.clear()

    async def _is_direct_file(self, url: str) -> bool:
        """Check if URL points to a direct file"""
        parsed = urlparse(url)
        return any(
            parsed.path.lower().endswith(ext) for ext in self.supported_extensions
        )

    async def _fetch_direct_file(self, url: str, temp_dir: Path) -> CodeLocation:
        """Fetch a direct file from URL"""
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()

                # Determine filename from URL or Content-Disposition header
                filename = self._get_filename_from_url(url, response)
                file_path = temp_dir / filename

                # Download file
                async with aiofiles.open(file_path, "wb") as f:
                    await f.write(await response.read())

                logger.info(f"Downloaded file to {file_path}")

                return CodeLocation(
                    path=temp_dir,
                    source_url=url,
                    metadata={
                        "type": "direct_file",
                        "original_filename": filename,
                        "content_type": response.headers.get("Content-Type"),
                    },
                )

    async def _handle_website(self, url: str, temp_dir: Path) -> CodeLocation:
        """Handle website URL (placeholder for now)"""
        logger.warning(f"Website crawling not implemented yet for {url}")
        return CodeLocation(
            path=temp_dir,
            source_url=url,
            metadata={"type": "website", "status": "not_implemented"},
        )

    def _get_filename_from_url(self, url: str, response: aiohttp.ClientResponse) -> str:
        """Extract filename from URL or Content-Disposition header"""
        # Try Content-Disposition header first
        if "Content-Disposition" in response.headers:
            content_disposition = response.headers["Content-Disposition"]
            if "filename=" in content_disposition:
                return content_disposition.split("filename=")[1].strip("\"'")

        # Fall back to URL path
        path = urlparse(url).path
        filename = Path(path).name

        # If no extension, try to determine from Content-Type
        if not Path(filename).suffix:
            content_type = response.headers.get("Content-Type", "")
            if "markdown" in content_type.lower():
                filename += ".md"
            elif "text/plain" in content_type.lower():
                filename += ".txt"

        return filename or "document.md"
