import logging
import re
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import AsyncIterator, Dict, Optional

import aiofiles
from docutils.core import publish_string

from ..core.exceptions import ProcessingError
from ..core.models import CodeLocation, DocFormat, ProcessedDirectory
from .base import BaseProcessor

logger = logging.getLogger(__name__)


class SphinxProcessor(BaseProcessor):
    """Processor for Sphinx documentation"""

    def __init__(self):
        super().__init__()
        self.format = DocFormat.SPHINX
        self.exclude_patterns = {
            "node_modules",
            "venv",
            ".git",
            ".pytest_cache",
            "__pycache__",
            "build",
            "dist",
            ".tox",
            ".venv",
            ".env",
            "_build",
            "_static",
            "_templates",
        }

    async def detect(self, location: CodeLocation) -> AsyncIterator[Path]:
        """Find directories containing Sphinx documentation"""
        for conf_file in location.path.rglob("conf.py"):
            # Skip excluded directories
            if any(p in conf_file.parts for p in self.exclude_patterns):
                continue
            yield conf_file.parent

    async def process(
        self, location: CodeLocation, directory: Path
    ) -> ProcessedDirectory:
        """Process Sphinx documentation directory"""
        try:
            # Read basic configuration without requiring Sphinx
            config = await self._read_basic_config(directory)

            # Convert RST to Markdown
            content = await self._convert_directory_to_markdown(directory)

            return ProcessedDirectory(
                relative_path=directory.relative_to(location.path),
                format=self.format,
                content=content,
                metadata={
                    "sphinx_config": config,
                    "master_doc": config.get("master_doc", "index"),
                    "project": config.get("project"),
                    "version": config.get("version"),
                },
            )

        except Exception as e:
            raise ProcessingError(
                f"Failed to process Sphinx directory {directory}: {str(e)}"
            )

    async def _read_basic_config(self, directory: Path) -> Dict:
        """Read basic configuration without requiring Sphinx installation"""
        config: Dict = {
            "project": "unknown",
            "version": "0.1",
            "release": "0.1",
            "master_doc": "index",
        }

        config_file = directory / "conf.py"
        if not config_file.exists():
            return config

        try:
            # Read conf.py as text and extract basic variables
            async with aiofiles.open(config_file, "r", encoding="utf-8") as f:
                content = await f.read()

            # Extract basic variables using regex
            for var in ["project", "version", "release", "master_doc"]:
                match = re.search(rf'{var}\s*=\s*[\'"]([^\'"]+)[\'"]', content)
                if match:
                    config[var] = match.group(1)

            # Extract extensions list
            extensions_match = re.search(
                r"extensions\s*=\s*\[(.*?)\]", content, re.DOTALL
            )
            if extensions_match:
                # Clean and parse extensions list
                extensions_str = extensions_match.group(1)
                extensions = [
                    ext.strip(" '\"")
                    for ext in extensions_str.split(",")
                    if ext.strip(" '\"")
                ]
                config["extensions"] = extensions

        except Exception as e:
            logger.warning(f"Failed to read conf.py: {e}")

        return config

    async def _convert_directory_to_markdown(self, directory: Path) -> Dict[str, str]:
        """Convert all RST files in directory to Markdown"""
        content = {}

        # First, gather all RST files
        rst_files = []
        for rst_file in directory.rglob("*.rst"):
            if any(p in rst_file.parts for p in self.exclude_patterns):
                continue
            rst_files.append(rst_file)

        # Process each RST file
        for rst_file in rst_files:
            try:
                md_content = await self._convert_rst_to_markdown(rst_file)
                if md_content:
                    rel_path = rst_file.relative_to(directory)
                    md_path = rel_path.with_suffix(".md")
                    content[str(md_path)] = md_content

            except Exception as e:
                logger.warning(f"Failed to convert RST file {rst_file}: {e}")

        return content

    async def _convert_rst_to_markdown(self, rst_file: Path) -> Optional[str]:
        """Convert a single RST file to Markdown"""
        try:
            # Read RST content
            async with aiofiles.open(rst_file, "r", encoding="utf-8") as f:
                rst_content = await f.read()

            # Pre-process RST content
            rst_content = await self._preprocess_rst(rst_content, rst_file)

            # Try pandoc first
            try:
                md_content = await self._convert_with_pandoc(rst_content)
            except Exception as e:
                logger.debug(
                    f"Pandoc conversion failed, falling back to basic conversion: {e}"
                )
                md_content = await self._convert_with_basic(rst_content)

            # Post-process the markdown content
            if md_content:
                md_content = await self._postprocess_markdown(md_content)

            return md_content

        except Exception as e:
            logger.warning(f"Failed to convert {rst_file}: {e}")
            return None

    async def _convert_with_pandoc(self, content: str) -> Optional[str]:
        """Convert RST to Markdown using pandoc if available"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".rst", encoding="utf-8"
        ) as temp_rst:
            temp_rst.write(content)
            temp_rst.flush()

            try:
                result = subprocess.run(
                    [
                        "pandoc",
                        "--from=rst",
                        "--to=gfm",
                        "--wrap=none",
                        temp_rst.name,
                    ],  # GitHub-Flavored Markdown
                    capture_output=True,
                    text=True,
                    check=True,
                )
                return result.stdout
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                raise Exception(f"Pandoc conversion failed: {e}")

    async def _convert_with_basic(self, content: str) -> str:
        """Basic RST to Markdown conversion using docutils"""
        try:
            # Convert to HTML first
            html = publish_string(
                source=content,
                writer_name="html5",
                settings_overrides={"report_level": "quiet", "warning_stream": None},
            ).decode("utf-8")

            # Convert HTML to Markdown using basic rules
            md_content = self._html_to_markdown(html)
            return md_content

        except Exception as e:
            # If all else fails, return the original content with a warning
            logger.warning(f"Basic conversion failed: {e}")
            return f"```rst\n{content}\n```"

    def _html_to_markdown(self, html: str) -> str:
        """Convert HTML to Markdown using basic rules"""
        # This is a very basic implementation
        # Replace with a proper HTML to Markdown converter if needed
        content = html

        # Remove HTML document structure
        content = re.sub(r"<!DOCTYPE.*?>", "", content, flags=re.DOTALL)
        content = re.sub(r"<html.*?>.*?<body>", "", content, flags=re.DOTALL)
        content = re.sub(r"</body>.*?</html>", "", content, flags=re.DOTALL)

        # Convert basic elements
        content = re.sub(r"<h1>(.*?)</h1>", r"# \1", content)
        content = re.sub(r"<h2>(.*?)</h2>", r"## \1", content)
        content = re.sub(r"<h3>(.*?)</h3>", r"### \1", content)
        content = re.sub(r"<p>(.*?)</p>", r"\1\n", content)
        content = re.sub(r"<code>(.*?)</code>", r"`\1`", content)
        content = re.sub(r"<pre>(.*?)</pre>", r"```\n\1\n```", content)
        content = re.sub(r"<em>(.*?)</em>", r"*\1*", content)
        content = re.sub(r"<strong>(.*?)</strong>", r"**\1**", content)

        # Clean up
        content = re.sub(r"\n\s*\n", "\n\n", content)
        content = content.strip()

        return content

    async def _preprocess_rst(self, content: str, source_file: Path) -> str:
        """Pre-process RST content before conversion"""
        # Handle includes
        content = await self._process_includes(content, source_file)

        # Handle directives
        content = self._process_directives(content)

        # Handle roles
        content = self._process_roles(content)

        return content

    async def _process_includes(self, content: str, source_file: Path) -> str:
        """Process RST include directives"""
        include_pattern = r".. include:: ([^\n]+)"

        async def replace_include(match):
            include_path = match.group(1).strip()
            try:
                full_path = (source_file.parent / include_path).resolve()
                async with aiofiles.open(full_path, "r", encoding="utf-8") as f:
                    return await f.read()
            except Exception as e:
                logger.warning(f"Failed to process include {include_path}: {e}")
                return f"<!-- Failed to include {include_path} -->"

        # Process all includes
        while re.search(include_pattern, content):
            for match in re.finditer(include_pattern, content):
                replacement = await replace_include(match)
                content = content.replace(match.group(0), replacement)

        return content

    def _process_directives(self, content: str) -> str:
        """Process RST directives"""
        # Convert code-block directives
        content = re.sub(
            r".. code-block:: ([^\n]+)\n\s*\n((?:\s+[^\n]*\n)+)",
            lambda m: f"```{m.group(1)}\n{textwrap.dedent(m.group(2))}```\n",
            content,
        )

        # Convert admonitions (note, warning, etc.)
        for directive in ["note", "warning", "important", "tip", "caution"]:
            content = re.sub(
                f".. {directive}::\n\s*\n((?:\s+[^\n]*\n)+)",
                lambda m: f"> **{directive.title()}**\n> \n{textwrap.dedent(m.group(1))}",
                content,
            )

        return content

    def _process_roles(self, content: str) -> str:
        """Process RST roles"""
        # Convert :ref: roles
        content = re.sub(
            r":ref:`([^`]+)`",
            lambda m: f'[{m.group(1)}](#{m.group(1).lower().replace(" ", "-")})',
            content,
        )

        # Convert :doc: roles
        content = re.sub(
            r":doc:`([^`]+)`", lambda m: f"[{m.group(1)}]({m.group(1)}.md)", content
        )

        # Convert other common roles
        for role in ["class", "func", "meth", "attr", "exc", "data", "const"]:
            content = re.sub(f":{role}:`([^`]+)`", lambda m: f"`{m.group(1)}`", content)

        return content

    async def _postprocess_markdown(self, content: str) -> str:
        """Post-process converted markdown content"""
        # Fix code blocks
        content = re.sub(r"``` {([^}]+)}", r"```\1", content)

        # Fix internal links
        content = re.sub(r"\[([^\]]+)\]\(([^)]+)\.rst\)", r"[\1](\2.md)", content)

        # Fix image paths
        content = re.sub(
            r"!\[([^\]]*)\]\(([^)]+)\)",
            lambda m: self._fix_image_path(m.group(1), m.group(2)),
            content,
        )

        # Clean up extra whitespace
        content = re.sub(r"\n\s*\n\s*\n", "\n\n", content)

        return content.strip()

    def _fix_image_path(self, alt_text: str, path: str) -> str:
        """Fix image paths in markdown"""
        # Remove _static/ prefix if present
        path = re.sub(r"^_static/", "", path)
        return f"![{alt_text}]({path})"
