from abc import ABC, abstractmethod
from pathlib import Path
from typing import AsyncIterator

from ..core.models import CodeLocation, DocFormat, ProcessedDirectory


class BaseProcessor(ABC):
    """Base class for documentation processors"""

    def __init__(self):
        self.format: DocFormat = DocFormat.OTHER

    @abstractmethod
    async def detect(self, location: CodeLocation) -> AsyncIterator[Path]:
        """Detect directories containing documentation for this processor"""
        pass

    @abstractmethod
    async def process(
        self, location: CodeLocation, directory: Path
    ) -> ProcessedDirectory:
        """Process a detected directory"""
        pass
