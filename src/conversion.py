from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from docling.document_converter import DocumentConverter
from token_count import TokenCount

from .config import Settings

logger = logging.getLogger(__name__)

# Reduce noise from Hugging Face on Windows systems without symlink support.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


@dataclass
class ConversionResult:
    source_pdf: Path
    markdown_file: Path
    token_count: int


def iter_pdf_files(pdf_dir: Path) -> Iterable[Path]:
    """Yield PDF files sorted by name for deterministic processing order."""

    return sorted(path for path in pdf_dir.glob("*.pdf") if path.is_file())


def convert_pdfs_to_markdown(settings: Settings) -> List[ConversionResult]:
    """Convert each PDF in ``settings.pdf_input_dir`` to Markdown."""

    settings.ensure_directories(include_ai=False)

    converter = DocumentConverter()
    token_counter = TokenCount(model_name=settings.token_counter_model)
    results: List[ConversionResult] = []

    pdf_files = list(iter_pdf_files(settings.pdf_input_dir))
    if not pdf_files:
        logger.warning("No PDF files found in %s", settings.pdf_input_dir)
        return results

    logger.info("Converting %s PDF(s) from %s", len(pdf_files), settings.pdf_input_dir)

    for pdf_path in pdf_files:
        logger.info("Converting: %s", pdf_path)
        try:
            conversion = converter.convert(pdf_path)
            markdown_content = conversion.document.export_to_markdown()
            markdown_filename = pdf_path.stem + ".md"
            markdown_path = settings.md_output_dir / markdown_filename
            markdown_path.write_text(markdown_content, encoding="utf-8")

            tokens = token_counter.num_tokens_from_string(markdown_content)
            logger.info("Saved Markdown to %s (tokens=%s)", markdown_path, tokens)

            results.append(
                ConversionResult(
                    source_pdf=pdf_path,
                    markdown_file=markdown_path,
                    token_count=tokens,
                )
            )
        except Exception as exc:  # noqa: BLE001 - we log and continue
            logger.exception("Failed to convert %s: %s", pdf_path, exc)

    return results
