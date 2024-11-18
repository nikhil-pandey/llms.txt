import json
import logging
from pathlib import Path

import aiofiles

from ..core.exceptions import StorageError
from ..core.models import ProcessedDoc

logger = logging.getLogger(__name__)


class PathEncoder(json.JSONEncoder):
    """Custom JSON encoder that converts Path objects to strings"""

    def default(self, obj):
        if isinstance(obj, Path):
            return str(obj)
        return super().default(obj)


class FileSystemStorage:
    """File system storage for processed documentation"""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def store(self, doc: ProcessedDoc) -> str:
        try:
            # Create package directory
            # Add multiple versions later. Skip for now.
            package_dir = self.base_path / f"{doc.package.name}-latest"
            package_dir.mkdir(parents=True, exist_ok=True)

            # Store metadata including repo info, package info, and processing info
            metadata = {
                "package": doc.package.model_dump(),
                "location": doc.location.model_dump(),
                "processed_at": doc.processed_at.isoformat(),
                "errors": doc.errors,
            }

            # Store metadata file at package directory level
            async with aiofiles.open(
                package_dir / "metadata.json", "w", encoding="utf-8"
            ) as f:
                await f.write(json.dumps(metadata, indent=2, cls=PathEncoder))

            # Create data directory for content files
            data_dir = package_dir / "data"
            data_dir.mkdir(exist_ok=True)

            # Store each processed directory's content
            for directory in doc.directories:
                # Create sanitized filename from relative path
                dir_name = str(directory.relative_path)
                if dir_name == ".":
                    dir_name = "root"

                # Store directory metadata
                async with aiofiles.open(
                    package_dir / f"{dir_name.replace('/', '_')}_metadata.json",
                    "w",
                    encoding="utf-8",
                ) as f:
                    dir_data = directory.model_dump()
                    await f.write(json.dumps(dir_data, indent=2, cls=PathEncoder))

                # Store content files in data directory
                for file_name, content in directory.content.items():
                    content_file = f"{dir_name}/{file_name}"
                    (data_dir / content_file).parent.mkdir(parents=True, exist_ok=True)
                    async with aiofiles.open(
                        data_dir / content_file, "w", encoding="utf-8"
                    ) as f:
                        await f.write(content)

            return str(package_dir)

        except Exception as e:
            raise StorageError(f"Failed to store document: {str(e)}") from e
