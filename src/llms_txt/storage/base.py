from typing import Protocol

from ..core.models import ProcessedDoc


class StorageProvider(Protocol):
    """Protocol for storage providers"""

    async def store(self, doc: ProcessedDoc) -> str:
        """Store processed documentation"""
        ...
