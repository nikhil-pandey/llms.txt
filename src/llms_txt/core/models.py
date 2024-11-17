from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import tomli
from pydantic import BaseModel, Field

from .enums import DocFormat, RegistryType


class Package(BaseModel):
    """Package metadata from registry"""

    name: str
    version: str
    registry: RegistryType
    repository_url: Optional[str] = None
    documentation_url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CodeLocation(BaseModel):
    """Information about source code/documentation location"""

    path: Path
    source_url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProcessedDirectory(BaseModel):
    """Result of processing a directory in the repository"""

    relative_path: Path
    format: DocFormat
    content: Dict[str, str]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProcessedDoc(BaseModel):
    """Final processed documentation"""

    package: Package
    location: CodeLocation
    processed_at: datetime
    directories: List[ProcessedDirectory]
    errors: List[str] = Field(default_factory=list)


class LlmsTxtConfig(BaseModel):
    """Configuration model for documentation harvesting"""

    pypi: Optional[List[str]] = None
    npm: Optional[List[str]] = None
    cargo: Optional[List[str]] = None
    nuget: Optional[List[str]] = None
    urls: Optional[List[str]] = None
    files: Optional[List[str]] = None
    output_dir: Optional[str] = "docs_output"

    @classmethod
    def from_toml(cls, path: Path) -> "LlmsTxtConfig":
        """Load configuration from TOML file"""
        with open(path, "rb") as f:
            data = tomli.load(f)
        return cls.model_validate(data.get("llms-txt", {}))
