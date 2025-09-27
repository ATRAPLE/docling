from __future__ import annotations

import argparse
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from src.ai_pipeline import AIResult, collect_markdown_files, run_ai_pipeline
from src.config import Settings
from src.conversion import ConversionResult, convert_pdfs_to_markdown
from token_count import TokenCount

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
        "--skip-existing-ai",
        action="store_true",
        help="Preserve respostas da IA já existentes (padrão é sobrescrever).",
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
        settings.user_prompt_parts = []

    if args.skip_existing_ai:
        settings.skip_existing_ai_outputs = True


def execute_conversion(settings: Settings, *, dry_run: bool) -> List[ConversionResult]:
    if dry_run:
        pdf_files = collect_pdf_listing(settings.pdf_input_dir)
        if not pdf_files:
            logger.info("[dry-run] No PDF files found in %s", settings.pdf_input_dir)
            return []

        to_convert: List[Path] = []
        for pdf in pdf_files:
            md_path = settings.md_output_dir / f"{pdf.stem}.md"
            if md_path.exists():
                logger.info("[dry-run] Skipping %s; Markdown already exists at %s", pdf.name, md_path)
            else:
                to_convert.append(pdf)

        if not to_convert:
            logger.info(
                "[dry-run] All Markdown outputs already exist in %s; docling conversion would be skipped.",
                settings.md_output_dir,
            )
            return []

        logger.info("[dry-run] Would convert %s PDF(s):", len(to_convert))
        for pdf in to_convert:
            logger.info(" - %s", pdf)
        return []

    return convert_pdfs_to_markdown(settings)


def summarize_processing(
    settings: Settings,
    markdown_files: List[Path],
    conversion_results: List[ConversionResult],
    ai_results: List[AIResult],
) -> None:
    if not (markdown_files or conversion_results or ai_results):
        return

    logger.info("\n===== Diagnóstico de Processamento =====")

    token_counter = TokenCount(model_name=settings.token_counter_model)
    conversion_index: Dict[Path, ConversionResult] = {res.markdown_file: res for res in conversion_results}
    ai_by_doc: Dict[Path, List[AIResult]] = defaultdict(list)
    for result in ai_results:
        ai_by_doc[result.markdown_file].append(result)

    all_docs = set(markdown_files) | set(conversion_index.keys()) | set(ai_by_doc.keys())
    if not all_docs:
        return

    for md_path in sorted(all_docs, key=lambda p: p.name.lower()):
        logger.info("\nDocumento: %s", md_path.name)

        conversion = conversion_index.get(md_path)
        if conversion:
            logger.info("1. Tempo Docling: %.2fs", conversion.duration_seconds)
            logger.info(
                "2. Markdown pós-Docling: %s tokens | %s palavras",
                conversion.token_count,
                conversion.word_count,
            )
        else:
            if md_path.exists():
                text = md_path.read_text(encoding="utf-8")
                tokens = token_counter.num_tokens_from_string(text)
                words = len(text.split())
                logger.info("1. Tempo Docling: não executado nesta execução (Markdown reutilizado)")
                logger.info(
                    "2. Markdown pós-Docling: %s tokens | %s palavras",
                    tokens,
                    words,
                )
            else:
                logger.info("1. Tempo Docling: não executado (Markdown ausente)")
                logger.info("2. Markdown pós-Docling: arquivo não encontrado")

        ai_entries = ai_by_doc.get(md_path, [])
        ai_map = {entry.prompt_label: entry for entry in ai_entries if entry.prompt_label}

        for idx in range(1, 5):
            label = f"part{idx}"
            prefix = f"{idx + 2}. Tempo IA prompt {idx}:"
            result = ai_map.get(label)
            if result and result.duration_seconds is not None:
                logger.info("%s %.2fs", prefix, result.duration_seconds)
            else:
                output_path = settings.ai_output_dir / f"{md_path.stem}_ai_{label}.md"
                if output_path.exists():
                    logger.info("%s não medido nesta execução (arquivo existente)", prefix)
                else:
                    logger.info("%s não executado", prefix)

        merged = ai_map.get("merged") or next(
            (entry for entry in ai_entries if entry.prompt_label == "merged"),
            None,
        )
        merged_path = settings.ai_output_dir / f"{md_path.stem}_ai.md"
        if merged and merged.token_count is not None:
            logger.info(
                "7. Markdown concatenado: %s tokens | %s palavras",
                merged.token_count,
                merged.word_count,
            )
        elif merged_path.exists():
            text = merged_path.read_text(encoding="utf-8")
            tokens = token_counter.num_tokens_from_string(text)
            words = len(text.split())
            logger.info(
                "7. Markdown concatenado: %s tokens | %s palavras (pré-existente)",
                tokens,
                words,
            )
        else:
            logger.info("7. Markdown concatenado: não gerado")


def collect_pdf_listing(pdf_dir: Path) -> List[Path]:
    return sorted(path for path in pdf_dir.glob("*.pdf") if path.is_file())


def execute_ai_stage(
    settings: Settings,
    markdown_files: List[Path],
    *,
    dry_run: bool,
) -> List:
    if not markdown_files:
        logger.warning("No Markdown files available for AI processing.")
        return []

    prompt_entries = settings.get_user_prompt_entries(None)

    if dry_run:
        logger.info(
            "[dry-run] Would send %s Markdown file(s) to model %s",
            len(markdown_files),
            settings.openai_model,
        )
        if prompt_entries:
            logger.info("[dry-run] Using %s user prompt(s):", len(prompt_entries))
            for entry in prompt_entries:
                label = entry.get("label", "part")
                display = entry.get("display", label)
                source = entry.get("path") or "inline"
                logger.info("   - %s (%s) from %s", label, display, source)
        for md_file in markdown_files:
            logger.info(" - %s", md_file)
        return []

    try:
        ai_results = run_ai_pipeline(
            settings,
            markdown_files,
            overwrite=not settings.skip_existing_ai_outputs,
        )
    except RuntimeError as exc:
        logger.error("AI stage aborted: %s", exc)
        return []

    if not ai_results:
        logger.info("AI stage completed with no new outputs.")
    else:
        for result in ai_results:
            if result.prompt_label == "merged":
                logger.info("AI merged output saved to %s", result.output_file)
            else:
                logger.info("AI output saved to %s", result.output_file)

    return ai_results


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )

    settings = Settings()
    apply_overrides(settings, args)

    markdown_files: List[Path] = []
    conversion_results: List[ConversionResult] = []
    ai_results: List[AIResult] = []

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

        ai_results = execute_ai_stage(
            settings,
            markdown_files,
            dry_run=args.dry_run,
        )

    summarize_processing(
        settings,
        markdown_files,
        conversion_results,
        ai_results,
    )


if __name__ == "__main__":
    main()