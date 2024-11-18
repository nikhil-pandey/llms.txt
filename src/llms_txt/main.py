import argparse
import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional
from urllib.parse import urlparse

from .config.logging import setup_logging
from .core.enums import RegistryType, SourceType
from .core.exceptions import LlmsTxtError
from .core.models import CodeLocation, LlmsTxtConfig, Package, ProcessedDoc
from .discovery.pypi import PyPIProvider
from .fetchers.base import ContentFetcher
from .fetchers.github import GitHubFetcher
from .fetchers.url import URLFetcher
from .processors.base import BaseProcessor
from .processors.markdown import MarkdownProcessor
from .processors.mkdocs import MkDocsProcessor
from .processors.sphinx import SphinxProcessor
from .storage.fs import FileSystemStorage

setup_logging()
logger = logging.getLogger(__name__)


class PackageSpec(NamedTuple):
    """Package specification with registry type and version"""

    name: str
    registry: RegistryType
    version: Optional[str] = None
    url: Optional[str] = None


def parse_package_spec(
    spec: str, registry_type: Optional[RegistryType] = None
) -> PackageSpec:
    """Parse package specification string into PackageSpec"""
    # Handle direct URLs
    if spec.startswith(("http://", "https://")):
        # Check if URL ends with supported extensions
        path = urlparse(spec).path.lower()
        if path.endswith((".md", ".rst", ".txt")):
            return PackageSpec(
                name=Path(path).name, 
                registry=RegistryType.HTTP, 
                url=spec
            )
    
    # Handle local files
    if Path(spec).exists():
        return PackageSpec(
            name=Path(spec).name,
            registry=RegistryType.LOCAL,
            url=str(Path(spec).absolute()),
        )

    # Handle package specs with version
    # Support formats: package==version, package@version, package:version
    version_match = re.match(r"^([^=@:]+)(==|@|:)(.+)$", spec)
    if version_match:
        name, _, version = version_match.groups()
        return PackageSpec(
            name=name, registry=registry_type or RegistryType.PYPI, version=version
        )

    # Simple package name
    return PackageSpec(name=spec, registry=registry_type or RegistryType.PYPI)


class LlmTxtHarvester:
    """Main Documentation Harvester"""

    def __init__(self, output_dir: Path):
        # Initialize providers for different registries
        self.registry_providers = {
            RegistryType.PYPI: PyPIProvider(),
            # Add other registry providers here
            # RegistryType.NPM: NPMProvider(),
            # RegistryType.CARGO: CargoProvider(),
            # RegistryType.NUGET: NuGetProvider(),
        }

        self.fetchers: Dict[RegistryType, ContentFetcher] = {
            SourceType.GITHUB: GitHubFetcher(),
            SourceType.HTTP: URLFetcher(),
        }
        self.storage = FileSystemStorage(output_dir)
        self.processors: List[BaseProcessor] = [
            MarkdownProcessor(),
            MkDocsProcessor(),
            SphinxProcessor(),
        ]

    async def harvest_packages(self, specs: List[PackageSpec]) -> None:
        """Harvest documentation for multiple packages"""
        for spec in specs:
            try:
                await self.harvest_package(spec)
            except Exception as e:
                logger.error(
                    f"Failed to harvest package {spec.name}: {e}", exc_info=True
                )

    async def harvest_package(self, spec: PackageSpec) -> None:
        """Harvest documentation for a package"""
        try:
            logger.info(f"Harvesting package: {spec.name}")
            if spec.url:
                logger.info(f"Direct URL: {spec.url}")
                # Create a simple package object for direct URLs
                package = Package(
                    name=spec.name,
                    version="latest",
                    registry=spec.registry,
                    documentation_url=spec.url,
                )

                # Use URL fetcher
                fetcher = self.fetchers[SourceType.HTTP]
            else:
                logger.info(f"Registry: {spec.registry}")
                # Get package info from registry
                provider = self.registry_providers.get(spec.registry)
                if not provider:
                    raise LlmsTxtError(f"Unsupported registry type: {spec.registry}")

                package = await provider.get_package_info(spec.name, spec.version)

                # Use GitHub fetcher for repository-based packages
                fetcher = self.fetchers[SourceType.GITHUB]

            logger.info(f"Processing package: {package.name} {package.version}")

            # Fetch content
            location: CodeLocation = await fetcher.fetch(package)
            logger.info(f"Fetched content to: {location.path}")

            # Process with all processors
            processed_dirs = []
            errors = []
            processed_paths = set()

            # Try each processor
            for processor in self.processors:
                logger.info(f"Processing with {processor.__class__.__name__}")
                try:
                    async for directory in processor.detect(location):
                        logger.info(
                            f"Detected {directory} for {processor.__class__.__name__}"
                        )
                        rel_path = directory.relative_to(location.path)
                        if rel_path in processed_paths:
                            continue

                        try:
                            result = await processor.process(location, directory)
                            processed_dirs.append(result)
                            # Dont count MarkdownProcessor towards processed paths
                            if (
                                processor.__class__.__name__
                                != MarkdownProcessor.__name__
                            ):
                                processed_paths.add(rel_path)
                            logger.info(
                                f"Processed {rel_path} with {processor.__class__.__name__}"
                            )
                        except Exception as e:
                            errors.append(f"Failed to process {rel_path}: {str(e)}")
                            logger.error(f"Processing error: {e}", exc_info=True)

                except Exception as e:
                    errors.append(
                        f"Processor {processor.__class__.__name__} failed: {str(e)}"
                    )
                    logger.error(f"Processor error: {e}", exc_info=True)

            # Create and store final document
            if processed_dirs:
                doc = ProcessedDoc(
                    package=package,
                    location=location,
                    directories=processed_dirs,
                    processed_at=datetime.now(),
                    errors=errors,
                )
                await self.storage.store(doc)
                logger.info(f"Stored documentation for {package.name}")
            else:
                logger.warning(f"No documentation found for {package.name}")

        except Exception as e:
            logger.error(f"Failed to harvest package {spec.name}: {e}", exc_info=True)
            raise

        finally:
            if fetcher:
                await fetcher.cleanup()


def parse_args():
    parser = argparse.ArgumentParser(description="Documentation Harvester CLI")

    # Add config file option
    parser.add_argument("--config", "-c", type=Path, help="TOML configuration file")
    parser.add_argument(
        "--output-dir", "-o", type=Path, help="Output directory", default=Path("data")
    )

    # Keep existing arguments for direct CLI use
    source_group = parser.add_argument_group("source")
    source_group.add_argument(
        "--pypi", nargs="+", help="PyPI packages (e.g., package==version)"
    )
    source_group.add_argument("--npm", nargs="+", help="NPM packages")
    source_group.add_argument("--cargo", nargs="+", help="Cargo packages")
    source_group.add_argument("--nuget", nargs="+", help="NuGet packages")
    source_group.add_argument(
        "--url", nargs="+", help="Direct URLs to documentation files"
    )
    source_group.add_argument("--file", nargs="+", help="Local documentation files")

    return parser.parse_args()


async def process_config(config: LlmsTxtConfig) -> None:
    """Process all packages specified in the configuration"""
    specs = []

    # Collect all package specs from config
    if config.pypi:
        specs.extend(
            parse_package_spec(spec, RegistryType.PYPI) for spec in config.pypi
        )
    if config.npm:
        specs.extend(parse_package_spec(spec, RegistryType.NPM) for spec in config.npm)
    if config.cargo:
        specs.extend(
            parse_package_spec(spec, RegistryType.CARGO) for spec in config.cargo
        )
    if config.nuget:
        specs.extend(
            parse_package_spec(spec, RegistryType.NUGET) for spec in config.nuget
        )
    if config.urls:
        specs.extend(
            PackageSpec(name=Path(url).name, registry=RegistryType.OTHER, url=url)
            for url in config.urls
        )
    if config.files:
        specs.extend(
            PackageSpec(
                name=Path(f).name,
                registry=RegistryType.LOCAL,
                url=str(Path(f).absolute()),
            )
            for f in config.files
        )
    if not specs:
        raise LlmsTxtError("No packages specified. Use --help for usage information.")

    # Create harvester with configured output directory
    harvester = LlmTxtHarvester(output_dir=Path(config.output_dir))
    await harvester.harvest_packages(specs)


def main():
    args = parse_args()

    # Collect package specs
    specs = []

    if args.config:
        # Load and process config file
        try:
            config = LlmsTxtConfig.from_toml(args.config)
            asyncio.run(process_config(config))
        except Exception as e:
            logger.error(f"Failed to process config file: {e}", exc_info=True)
            return
    else:
        if args.pypi:
            specs.extend(
                parse_package_spec(spec, RegistryType.PYPI) for spec in args.pypi
            )
        if args.npm:
            specs.extend(
                parse_package_spec(spec, RegistryType.NPM) for spec in args.npm
            )
        if args.cargo:
            specs.extend(
                parse_package_spec(spec, RegistryType.CARGO) for spec in args.cargo
            )
        if args.nuget:
            specs.extend(
                parse_package_spec(spec, RegistryType.NUGET) for spec in args.nuget
            )
        if args.url:
            specs.extend(
                PackageSpec(name=Path(url).name, registry=RegistryType.OTHER, url=url)
                for url in args.url
            )
        if args.file:
            specs.extend(
                PackageSpec(
                    name=Path(f).name,
                    registry=RegistryType.LOCAL,
                    url=str(Path(f).absolute()),
                )
                for f in args.file
            )
        if not specs:
            print("No packages specified. Use --help for usage information.")
            return

        harvester = LlmTxtHarvester(output_dir=args.output_dir)
        asyncio.run(harvester.harvest_packages(specs))


if __name__ == "__main__":
    main()
