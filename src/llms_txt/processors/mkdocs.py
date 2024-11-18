import logging
import re
from pathlib import Path
from typing import AsyncIterator, Dict

import yaml
from yaml.constructor import SafeConstructor

from ..core.exceptions import ProcessingError
from ..core.models import CodeLocation, DocFormat, ProcessedDirectory
from .base import BaseProcessor

logger = logging.getLogger(__name__)


class IgnorePythonObjectsConstructor(SafeConstructor):
    """Custom YAML constructor that ignores Python objects"""

    def construct_undefined(self, node):
        if node.tag.startswith("tag:yaml.org,2002:python/"):
            return None
        return super().construct_undefined(node)


class IgnorePythonObjectsLoader(yaml.SafeLoader):
    """Custom YAML loader that ignores Python objects"""

    pass


IgnorePythonObjectsLoader.add_constructor(
    None, IgnorePythonObjectsConstructor.construct_undefined
)


class MkDocsProcessor(BaseProcessor):
    """Processor for MkDocs documentation"""

    def __init__(self):
        super().__init__()
        self.format = DocFormat.MKDOCS

    async def detect(self, location: CodeLocation) -> AsyncIterator[Path]:
        """Find directories containing mkdocs.yml"""
        for config_file in location.path.rglob("mkdocs.yml"):
            yield config_file.parent

    async def process(
        self, location: CodeLocation, directory: Path
    ) -> ProcessedDirectory:
        """Process MkDocs documentation directory"""
        try:
            # Read MkDocs config
            config_path = directory / "mkdocs.yml"
            with open(config_path) as f:
                config = yaml.load(f, Loader=IgnorePythonObjectsLoader)

            # Get docs directory
            docs_dir = directory / (config.get("docs_dir", "docs"))
            if not docs_dir.exists():
                raise ProcessingError(f"Docs directory not found: {docs_dir}")

            # Process all markdown files
            content = {}

            # If nav is defined, process files in nav order
            if "nav" in config:
                content.update(self._process_nav_files(config["nav"], docs_dir))

            # Process any remaining markdown files not in nav
            for md_file in docs_dir.rglob("*.md"):
                rel_path = md_file.relative_to(docs_dir)
                if str(rel_path) not in content:
                    content[str(rel_path)] = self._read_markdown_file(md_file)

            return ProcessedDirectory(
                relative_path=directory.relative_to(location.path),
                format=self.format,
                content=content,
                metadata={
                    "mkdocs_config": config,
                    "site_name": config.get("site_name"),
                    "theme": config.get("theme", {}).get("name"),
                    "nav": config.get("nav"),
                },
            )

        except Exception as e:
            raise ProcessingError(
                f"Failed to process MkDocs directory {directory}: {str(e)}"
            )

    def _process_nav_files(self, nav: list, docs_dir: Path) -> Dict[str, str]:
        """Process navigation files and return a dict of file paths to content"""
        content = {}

        def process_nav_item(item):
            if isinstance(item, str):
                # Check for both MD and RST files
                if item.endswith((".md", ".rst")):
                    content[item] = self._read_markdown_file(docs_dir / item)
            elif isinstance(item, dict):
                for title, nav_content in item.items():
                    if isinstance(nav_content, str) and nav_content.endswith(
                        (".md", ".rst")
                    ):
                        content[nav_content] = self._read_markdown_file(
                            docs_dir / nav_content
                        )
                    elif isinstance(nav_content, list):
                        for child in nav_content:
                            process_nav_item(child)

        for item in nav:
            process_nav_item(item)

        return content

    def _read_markdown_file(self, file_path: Path) -> str:
        """Read and process a markdown or RST file"""
        try:
            if not file_path.exists():
                logger.warning(f"File not found: {file_path}")
                return ""

            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            # Process code inclusions
            content = self._process_code_inclusions(content, file_path)

            # Process relative links
            content = self._fix_relative_links(content, file_path)

            # Convert RST to Markdown if needed
            if file_path.suffix.lower() in {".rst", ".rest"}:
                content = self.convert_rst_to_markdown(content, file_path)

            return content

        except Exception as e:
            logger.warning(f"Failed to read {file_path}: {e}")
            return ""

    def _process_code_inclusions(self, content: str, current_file: Path) -> str:
        """Process code snippet inclusions in markdown content"""

        def replace_inclusion(match) -> str:
            # Split the match into file path and optional highlight info
            parts = match.group(1).split()
            file_ref = parts[0]

            # Extract highlight info if present
            highlight_info = None
            if len(parts) > 1:
                highlight_parts = [p for p in parts if p.startswith("hl[")]
                if highlight_parts:
                    highlight_info = highlight_parts[0]

            try:
                # First try to resolve the path relative to the docs root
                # by walking up the directory tree
                current_dir = current_file.parent
                target_path = None

                while current_dir.name:
                    try_path = current_dir / file_ref
                    if try_path.exists():
                        target_path = try_path
                        break
                    if (current_dir / "mkdocs.yml").exists():
                        # We've reached the docs root, stop searching
                        break
                    current_dir = current_dir.parent

                # If not found, try relative to the current file
                if not target_path:
                    target_path = (current_file.parent / file_ref).resolve()

                if not target_path.exists():
                    logger.warning(
                        f"Referenced file not found: {file_ref} (tried from {current_file})"
                    )
                    return f"```\n# File not found: {file_ref}\n```"

                with open(target_path, "r", encoding="utf-8") as f:
                    file_content = f.read()

                lang = target_path.suffix.lstrip(".")

                # Add highlight info as a comment if present
                if highlight_info:
                    return (
                        f"```{lang}\n# Highlight: {highlight_info}\n{file_content}\n```"
                    )
                else:
                    return f"```{lang}\n{file_content}\n```"

            except Exception as e:
                logger.warning(f"Failed to process code inclusion {file_ref}: {e}")
                return f"```\n# Error including file: {file_ref}\n# {str(e)}\n```"

        # Pattern for matching code inclusions
        patterns = [
            r"\{\*\s+([^}]+)\s*\*\}",  # {* file.py *}
            r"\{\!\s+([^}]+)\s*\!\}",  # {! file.py !}
            r"\{\=\s+([^}]+)\s*\=\}",  # {= file.py =}
        ]

        # Process each pattern
        for pattern in patterns:
            content = re.sub(pattern, replace_inclusion, content)

        return content

    def _fix_relative_links(self, content: str, file_path: Path) -> str:
        """Fix relative links in markdown content"""

        def replace_link(match):
            link_text = match.group(1)
            link_url = match.group(2)

            # Skip external links, anchors, and absolute paths
            if link_url.startswith(("http://", "https://", "#", "/")):
                return match.group(0)

            try:
                # Resolve the link path relative to the current file
                target_path = (file_path.parent / link_url).resolve()

                # Convert to a standardized relative path from docs root
                try:
                    new_url = target_path.relative_to(file_path.parent)
                    return f"[{link_text}]({new_url})"
                except ValueError:
                    # If we can't make it relative, leave it as is
                    return match.group(0)

            except Exception as e:
                logger.warning(f"Failed to process link {link_url}: {e}")
                return match.group(0)

        # Match markdown links: [text](url)
        pattern = r"\[([^\]]+)\]\(([^)]+)\)"
        content = re.sub(pattern, replace_link, content)

        # Match image links: ![alt](url)
        pattern = r"!\[([^\]]*)\]\(([^)]+)\)"
        content = re.sub(pattern, replace_link, content)

        return content
