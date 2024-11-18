from abc import ABC, abstractmethod
from pathlib import Path
from typing import AsyncIterator
import logging
import subprocess

from ..core.models import CodeLocation, DocFormat, ProcessedDirectory

logger = logging.getLogger(__name__)


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

    @staticmethod
    def convert_rst_to_markdown(content: str, file_path: Path) -> str:
        """Convert RST content to Markdown using pandoc"""
        try:
            process = subprocess.run(
                [
                    "pandoc",
                    "--from=rst",
                    "--to=markdown",
                    "--wrap=none",
                    "-",  # Read from stdin
                ],
                input=content.encode(),
                capture_output=True,
                check=True,
            )

            converted = process.stdout.decode()
            logger.info(f"Converted RST file to markdown: {file_path}")
            return converted

        except FileNotFoundError:
            logger.warning("pandoc not found. Please install pandoc on your system")
        except subprocess.CalledProcessError as e:
            logger.warning(
                f"Pandoc conversion failed for {file_path}: {e.stderr.decode()}"
            )
        except Exception as e:
            logger.warning(f"Failed to convert RST file {file_path}: {e}")

        return content  # Return original content if conversion fails
