import logging
from typing import Optional

import httpx

from ..config.logging import setup_logging
from ..core.enums import RegistryType
from ..core.exceptions import DiscoveryError
from ..core.models import Package

setup_logging()
logger = logging.getLogger(__name__)


class PyPIProvider:
    """PyPI package registry provider"""

    def __init__(self):
        self.client = httpx.AsyncClient()
        self.base_url = "https://pypi.org/pypi"

    async def get_package_info(
        self, name: str, version: Optional[str] = None
    ) -> Package:
        """Get package information from PyPI"""
        url = f"{self.base_url}/{name}/json"
        if version:
            url = f"{self.base_url}/{name}/{version}/json"

        try:
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()

            info = data["info"]
            version = version or info["version"]

            # Extract repository URL from project URLs
            repo_url = None
            project_urls = info.get("project_urls", {})
            for key in project_urls.keys():
                url = project_urls[key]
                if "github.com" in url and "/sponsors/" not in url:
                    logger.info(f"Found GitHub repository URL: {url}")
                    split = url.split("/")
                    repo_url = "/".join(split[:5])
                    logger.info(f"Extracted GitHub repository URL: {repo_url}")
                    break

            return Package(
                name=name,
                version=version,
                registry=RegistryType.PYPI,
                repository_url=repo_url,
                documentation_url=info.get("project_urls", {}).get("Documentation"),
                metadata={
                    "description": info.get("description"),
                    "author": info.get("author"),
                    "license": info.get("license"),
                    "project_urls": info.get("project_urls", {}),
                    "requires_dist": info.get("requires_dist", []),
                },
            )

        except Exception as e:
            raise DiscoveryError(f"Failed to fetch package info for {name}: {str(e)}")

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
