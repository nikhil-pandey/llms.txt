from typing import Protocol

from ..core.models import CodeLocation, Package


class ContentFetcher(Protocol):
    """Protocol for content fetchers"""

    async def fetch(self, package: Package) -> CodeLocation:
        """Fetch content from source"""
        ...

    async def cleanup(self) -> None:
        """Clean up any temporary resources"""
        ...
