import logging
from pathlib import Path
from typing import AsyncIterator

import aiofiles

from ..core.models import CodeLocation, DocFormat, ProcessedDirectory
from .base import BaseProcessor

logger = logging.getLogger(__name__)


class MarkdownProcessor(BaseProcessor):
    """Processor for standalone Markdown and text files in root directory"""

    def __init__(self):
        super().__init__()
        self.format = DocFormat.PLAIN
        self.markdown_extensions = {".md", ".markdown", ".mdown", ".mkdn"}
        self.text_extensions = {".txt", ".text"}
        self.ignored_files = {
            "requirements.txt",
            "requirements-dev.txt",
        }

    async def detect(self, location: CodeLocation) -> AsyncIterator[Path]:
        """Find markdown or text files in root directory"""
        root_dir = location.path

        for ext in self.markdown_extensions | self.text_extensions:
            for file_path in root_dir.glob(f"*{ext}"):
                if file_path.name in self.ignored_files:
                    continue
                yield root_dir

    async def process(self, location: CodeLocation, directory: Path) -> ProcessedDirectory:
        """Process markdown and text files in root directory"""
        content = {}
        file_count = 0

        # Process markdown files
        for ext in self.markdown_extensions | self.text_extensions:
            for file_path in directory.glob(f"*{ext}"):
                if file_path.name in self.ignored_files:
                    continue
                try:
                    async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                        file_content = await f.read()

                    # Store relative path as key
                    rel_path = file_path.relative_to(directory)
                    content[str(rel_path)] = file_content
                    file_count += 1

                except Exception as e:
                    logger.error(f"Error processing file {file_path}: {e}")

        if not content:
            logger.warning(f"No content found in directory: {directory}")

        return ProcessedDirectory(
            relative_path=directory.relative_to(location.path),
            format=self.format,
            content=content,
            metadata={"file_count": file_count, "file_types": list(self.markdown_extensions | self.text_extensions)},
        )
