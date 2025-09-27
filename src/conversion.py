from __future__ import annotations

import logging
import os
import time
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
    word_count: int
    duration_seconds: float


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

    to_convert: List[Path] = []
    for pdf_path in pdf_files:
        markdown_filename = pdf_path.stem + ".md"
        markdown_path = settings.md_output_dir / markdown_filename
        if markdown_path.exists():
            logger.info(
                "Skipping %s because Markdown already exists at %s",
                pdf_path.name,
                markdown_path,
            )
            continue
        to_convert.append(pdf_path)

    if not to_convert:
        logger.info(
            "All PDFs in %s already have Markdown outputs in %s; skipping docling conversion.",
            settings.pdf_input_dir,
            settings.md_output_dir,
        )
        return results

    logger.info("Converting %s PDF(s) from %s", len(to_convert), settings.pdf_input_dir)

    for pdf_path in to_convert:
        logger.info("Converting: %s", pdf_path)
        start_time = time.perf_counter()
        try:
            conversion = converter.convert(pdf_path)
            markdown_content = conversion.document.export_to_markdown()
            markdown_filename = pdf_path.stem + ".md"
            markdown_path = settings.md_output_dir / markdown_filename
            markdown_path.write_text(markdown_content, encoding="utf-8")

            tokens = token_counter.num_tokens_from_string(markdown_content)
            words = len(markdown_content.split())
            duration = time.perf_counter() - start_time
            logger.info(
                "Saved Markdown to %s (tokens=%s, words=%s, duration=%.2fs)",
                markdown_path,
                tokens,
                words,
                duration,
            )

            results.append(
                ConversionResult(
                    source_pdf=pdf_path,
                    markdown_file=markdown_path,
                    token_count=tokens,
                    word_count=words,
                    duration_seconds=duration,
                )
            )
        except Exception as exc:  # noqa: BLE001 - we log and continue
            logger.exception("Failed to convert %s: %s", pdf_path, exc)

    return results
