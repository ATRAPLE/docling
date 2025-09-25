from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import List

from src.ai_pipeline import collect_markdown_files, run_ai_pipeline
from src.config import Settings
from src.conversion import ConversionResult, convert_pdfs_to_markdown

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PDF → Markdown → OpenAI processing pipeline."
    )
    parser.add_argument(
        "--stage",
        choices=["convert", "ai", "full"],
        default="full",
        help="Which stage to execute. 'full' runs conversion followed by AI processing.",
    )
    parser.add_argument("--pdf-dir", type=Path, help="Override PDF input directory.")
    parser.add_argument("--md-dir", type=Path, help="Override Markdown output directory.")
    parser.add_argument("--ai-dir", type=Path, help="Override AI output directory.")
    parser.add_argument("--ai-model", help="OpenAI model to use for responses.")
    parser.add_argument(
        "--token-counter-model",
        help="Tokenizer model identifier used to estimate token counts.",
    )
    parser.add_argument(
        "--system-prompt",
        help="Inline system prompt. If combined with --system-prompt-file, the file wins.",
    )
    parser.add_argument(
        "--system-prompt-file",
        type=Path,
        help="Load system prompt text from file.",
    )
    parser.add_argument(
        "--user-prompt-file",
        type=Path,
        help="Load user prompt template from file. Template must include {document_name} and {markdown_content} placeholders.",
    )
    parser.add_argument(
        "--overwrite-ai",
        action="store_true",
        help="Overwrite existing AI output files instead of skipping them.",
    )
    parser.add_argument(
        "--force-ai",
        action="store_true",
        help="Disable the skip-existing behaviour configured via AI_SKIP_EXISTING.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the files that would be processed without calling external services.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR).",
    )
    return parser.parse_args()


def apply_overrides(settings: Settings, args: argparse.Namespace) -> None:
    if args.pdf_dir:
        settings.pdf_input_dir = args.pdf_dir
    if args.md_dir:
        settings.md_output_dir = args.md_dir
    if args.ai_dir:
        settings.ai_output_dir = args.ai_dir
    if args.ai_model:
        settings.openai_model = args.ai_model
    if args.token_counter_model:
        settings.token_counter_model = args.token_counter_model

    if args.system_prompt_file and args.system_prompt_file.exists():
        settings.system_prompt = args.system_prompt_file.read_text(encoding="utf-8")
    elif args.system_prompt:
        settings.system_prompt = args.system_prompt

    if args.user_prompt_file and args.user_prompt_file.exists():
        settings.user_prompt_template = args.user_prompt_file.read_text(encoding="utf-8")

    if args.force_ai:
        settings.skip_existing_ai_outputs = False


def execute_conversion(settings: Settings, *, dry_run: bool) -> List[ConversionResult]:
    if dry_run:
        pdf_files = collect_pdf_listing(settings.pdf_input_dir)
        if pdf_files:
            logger.info("[dry-run] Would convert %s PDF(s):", len(pdf_files))
            for pdf in pdf_files:
                logger.info(" - %s", pdf)
        else:
            logger.info("[dry-run] No PDF files found in %s", settings.pdf_input_dir)
        return []

    return convert_pdfs_to_markdown(settings)


def collect_pdf_listing(pdf_dir: Path) -> List[Path]:
    return sorted(path for path in pdf_dir.glob("*.pdf") if path.is_file())


def execute_ai_stage(
    settings: Settings,
    markdown_files: List[Path],
    *,
    overwrite: bool,
    dry_run: bool,
) -> None:
    if not markdown_files:
        logger.warning("No Markdown files available for AI processing.")
        return

    if dry_run:
        logger.info("[dry-run] Would send %s Markdown file(s) to model %s", len(markdown_files), settings.openai_model)
        for md_file in markdown_files:
            logger.info(" - %s", md_file)
        return

    try:
        ai_results = run_ai_pipeline(
            settings,
            markdown_files,
            overwrite=overwrite,
        )
    except RuntimeError as exc:
        logger.error("AI stage aborted: %s", exc)
        return

    if not ai_results:
        logger.info("AI stage completed with no new outputs.")
    else:
        for result in ai_results:
            logger.info("AI output saved to %s", result.output_file)


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )

    settings = Settings()
    apply_overrides(settings, args)

    markdown_files: List[Path] = []

    if args.stage in {"convert", "full"}:
        conversion_results = execute_conversion(settings, dry_run=args.dry_run)
        if conversion_results:
            markdown_files = [result.markdown_file for result in conversion_results]
        elif args.stage == "full":
            # If conversion produced nothing, fall back to existing Markdown files.
            markdown_files = collect_markdown_files(settings.md_output_dir)

    if args.stage in {"ai", "full"}:
        if args.stage == "ai":
            markdown_files = collect_markdown_files(settings.md_output_dir)

        execute_ai_stage(
            settings,
            markdown_files,
            overwrite=args.overwrite_ai,
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    main()