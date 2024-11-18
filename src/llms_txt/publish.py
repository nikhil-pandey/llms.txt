import argparse
from pathlib import Path
from typing import List
from .config.logging import setup_logging
import logging

setup_logging()
logger = logging.getLogger(__name__)


def combine_docs(data_dir: Path, output_dir: Path) -> None:
    """
    Process documentation files and create a static site.

    Args:
        data_dir: Directory containing the model documentation
        output_dir: Directory where the static site will be generated
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create index.html with basic styling
    index_content = """
    <html>
    <head>
        <title>LLM Friendly Documentation</title>
        <style>
            body { 
                font-family: system-ui, -apple-system, sans-serif;
                max-width: 800px;
                margin: 0 auto;
                padding: 2rem;
                line-height: 1.5;
            }
            h1 { color: #2563eb; }
            a { 
                color: #3b82f6;
                text-decoration: none;
            }
            a:hover { text-decoration: underline; }
            li { margin: 0.5rem 0; }
        </style>
    </head>
    <body>
        <h1>LLMs Documentation</h1>
        <ul>
    """

    index_file = output_dir / "index.html"
    index_file.write_text(index_content)

    # Process each model directory
    processed_models: List[str] = []
    for model_dir in data_dir.glob("*/"):
        logger.info(f"Processing model directory: {model_dir}")
        if not model_dir.is_dir():
            logger.info(f"Not a directory: {model_dir}")
            continue

        model_name = model_dir.name
        doc_files = []

        # Find all markdown and text files
        for ext in ["md", "txt", "rst"]:
            logger.info(f"Searching for {ext} files in {model_dir}")
            doc_files.extend(model_dir.glob(f"data/**/*.{ext}"))

        if doc_files:
            # Create model directory
            logger.info(f"Found {len(doc_files)} documentation files for {model_name}")
            model_output = output_dir / model_name
            model_output.mkdir(exist_ok=True)

            # Combine documentation files
            combined_content = []
            for doc_file in sorted(doc_files):
                try:
                    content = doc_file.read_text()
                    combined_content.append(doc_file.name)
                    combined_content.append(content)
                except Exception as e:
                    logger.error(f"Error reading {doc_file}: {e}")

            if combined_content:
                # Write combined content
                output_file = model_output / "llms.txt"
                output_file.write_text("\n\n---\n\n".join(combined_content))
                processed_models.append(model_name)
        else:
            logger.info(f"No documentation files found for {model_name}")

    # Update index with processed models
    logger.info(f"Processed {len(processed_models)} models: {processed_models}")
    with index_file.open("a") as f:
        for model in sorted(processed_models):
            f.write(f'            <li><a href="{model}/llms.txt">{model}</a></li>\n')
        f.write(
            """
        </ul>
    </body>
    </html>
    """
        )


def main() -> None:
    """Entry point for the publish command."""
    parser = argparse.ArgumentParser(description="Process and publish documentation as a static site")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default="data",
        help="Directory containing the documentation",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default="site",
        help="Directory where the static site will be generated",
    )

    args = parser.parse_args()
    combine_docs(args.data_dir, args.output_dir)


if __name__ == "__main__":
    main()
