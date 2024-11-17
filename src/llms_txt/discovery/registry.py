from typing import Optional, Protocol

from ..core.models import Package


class RegistryProvider(Protocol):
    """Protocol for package registry providers"""

    async def get_package_info(self, name: str, version: Optional[str] = None) -> Package:
        """Retrieve package information"""
        ...
