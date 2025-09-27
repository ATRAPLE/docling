from __future__ import annotations

import argparse
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from src.ai_pipeline import AIResult, collect_markdown_files, run_ai_pipeline
from src.chunking import ChunkPlan, build_chunk_plan, save_chunk_plan
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
        "--chunking",
        choices=["auto", "force", "off"],
        help="Modo de chunking do Markdown antes de enviar à IA.",
    )
    parser.add_argument(
        "--chunk-target",
        type=int,
        help="Alvo de tokens por chunk (antes da sobreposição).",
    )
    parser.add_argument(
        "--chunk-max",
        type=int,
        help="Limite duro de tokens por chunk.",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        help="Tokens sobrepostos entre chunks sequenciais.",
    )
    parser.add_argument(
        "--chunk-price-input",
        type=float,
        help="Custo estimado por 1k tokens de entrada para cálculo de orçamento.",
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

    if args.chunking:
        settings.chunking_mode = args.chunking
    if args.chunk_target is not None:
        settings.chunk_target_tokens = max(1, args.chunk_target)
    if args.chunk_max is not None:
        settings.chunk_max_tokens = max(args.chunk_max, settings.chunk_target_tokens)
    if args.chunk_overlap is not None:
        settings.chunk_overlap_tokens = max(0, args.chunk_overlap)
    if args.chunk_price_input is not None:
        settings.chunk_pricing_input_per_1k = max(0.0, args.chunk_price_input)

    if args.system_prompt_file and args.system_prompt_file.exists():
        settings.system_prompt = args.system_prompt_file.read_text(encoding="utf-8")
    elif args.system_prompt:
        settings.system_prompt = args.system_prompt

    if args.user_prompt_file and args.user_prompt_file.exists():
        settings.user_prompt_template = args.user_prompt_file.read_text(encoding="utf-8")
        settings.user_prompt_parts = []

    if args.skip_existing_ai:
        settings.skip_existing_ai_outputs = True

    settings.chunking_mode = settings.chunking_mode.lower()
    if settings.chunking_mode not in {"auto", "force", "off"}:
        logger = logging.getLogger(__name__)
        logger.warning("Invalid chunking mode %s; falling back to auto", settings.chunking_mode)
        settings.chunking_mode = "auto"

    if settings.chunk_max_tokens < settings.chunk_target_tokens:
        settings.chunk_max_tokens = settings.chunk_target_tokens

    if settings.chunk_overlap_tokens < 0:
        settings.chunk_overlap_tokens = 0


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
    chunk_plans: List[ChunkPlan] | None,
) -> None:
    if not (markdown_files or conversion_results or ai_results or chunk_plans):
        return

    logger.info("\n===== Diagnóstico de Processamento =====")

    token_counter = TokenCount(model_name=settings.token_counter_model)
    conversion_index: Dict[Path, ConversionResult] = {res.markdown_file: res for res in conversion_results}
    plan_index: Dict[Path, ChunkPlan] = {plan.document: plan for plan in (chunk_plans or [])}
    ai_by_doc: Dict[Path, Dict[str, List[AIResult]]] = defaultdict(lambda: defaultdict(list))
    for result in ai_results:
        key = result.chunk_id or "document"
        ai_by_doc[result.markdown_file][key].append(result)

    prompt_entries = settings.get_user_prompt_entries(None)
    multi_prompt_mode = len(prompt_entries) > 1 or any(
        entry.get("display") not in {"default", "inline-override"} for entry in prompt_entries
    )

    all_docs = (
        set(markdown_files)
        | set(conversion_index.keys())
        | set(ai_by_doc.keys())
        | set(plan_index.keys())
    )
    if not all_docs:
        return

    for md_path in sorted(all_docs, key=lambda p: p.name.lower()):
        logger.info("\nDocumento: %s", md_path.name)
        step = 1

        conversion = conversion_index.get(md_path)
        if conversion:
            logger.info("%s. Tempo Docling: %.2fs", step, conversion.duration_seconds)
            step += 1
            logger.info(
                "%s. Markdown pós-Docling: %s tokens | %s palavras",
                step,
                conversion.token_count,
                conversion.word_count,
            )
            step += 1
        else:
            if md_path.exists():
                text = md_path.read_text(encoding="utf-8")
                tokens = token_counter.num_tokens_from_string(text)
                words = len(text.split())
                logger.info("%s. Tempo Docling: não executado nesta execução (Markdown reutilizado)", step)
                step += 1
                logger.info(
                    "%s. Markdown pós-Docling: %s tokens | %s palavras",
                    step,
                    tokens,
                    words,
                )
                step += 1
            else:
                logger.info("%s. Tempo Docling: não executado (Markdown ausente)", step)
                step += 1
                logger.info("%s. Markdown pós-Docling: arquivo não encontrado", step)
                step += 1

        plan = plan_index.get(md_path)
        chunk_store = ai_by_doc.get(md_path, {})

        if plan:
            logger.info(
                "%s. Chunking: %s chunk(s) | modo=%s | motivo=%s",
                step,
                len(plan.chunks),
                plan.applied_mode,
                plan.reason,
            )
            step += 1

            for chunk in plan.chunks:
                chunk_suffix = "" if len(plan.chunks) == 1 else f"_{chunk.chunk_id}"
                base_filename = f"{md_path.stem}{chunk_suffix}_ai"
                logger.info(
                    "   - %s (%s/%s): %s tokens | %s palavras | linhas %s-%s",
                    chunk.chunk_id,
                    chunk.index,
                    len(plan.chunks),
                    chunk.token_count,
                    chunk.word_count,
                    chunk.start_line,
                    chunk.end_line,
                )

                chunk_results = {
                    res.prompt_label: res
                    for res in chunk_store.get(chunk.chunk_id, [])
                    if res.prompt_label
                }

                for idx, entry in enumerate(prompt_entries, start=1):
                    label = str(entry.get("label", f"part{idx}"))
                    display = entry.get("display", label)
                    prefix = f"     · Prompt {display} ({label}):"
                    result = chunk_results.get(label)

                    if result and result.duration_seconds is not None:
                        logger.info(
                            "%s %.2fs | saída %s",
                            prefix,
                            result.duration_seconds,
                            result.output_file.name,
                        )
                        continue

                    if multi_prompt_mode:
                        output_path = settings.ai_output_dir / f"{base_filename}_{label}.md"
                    else:
                        output_path = settings.ai_output_dir / f"{base_filename}.md"

                    if output_path.exists():
                        logger.info("%s já existente (%s)", prefix, output_path.name)
                    else:
                        logger.info("%s não executado", prefix)

                merged_key = f"{chunk.chunk_id}-merged"
                merged_result = chunk_results.get(merged_key)
                chunk_merge_path = settings.ai_output_dir / f"{base_filename}.md"

                if merged_result and merged_result.token_count is not None:
                    logger.info(
                        "     · Chunk combinado: %s tokens | %s palavras (%s)",
                        merged_result.token_count,
                        merged_result.word_count,
                        merged_result.output_file.name,
                    )
                elif chunk_merge_path.exists():
                    text = chunk_merge_path.read_text(encoding="utf-8")
                    tokens = token_counter.num_tokens_from_string(text)
                    words = len(text.split())
                    logger.info(
                        "     · Chunk combinado: %s tokens | %s palavras (pré-existente)",
                        tokens,
                        words,
                    )
                else:
                    logger.info("     · Chunk combinado: não gerado")

        global_results = {
            res.prompt_label: res
            for res in chunk_store.get("global", [])
            if res.prompt_label
        }
        global_merge_path = settings.ai_output_dir / f"{md_path.stem}_ai.md"

        merged_global = global_results.get("merged")
        if merged_global and merged_global.token_count is not None:
            logger.info(
                "%s. Markdown concatenado: %s tokens | %s palavras (%s)",
                step,
                merged_global.token_count,
                merged_global.word_count,
                merged_global.output_file.name,
            )
        elif global_merge_path.exists():
            text = global_merge_path.read_text(encoding="utf-8")
            tokens = token_counter.num_tokens_from_string(text)
            words = len(text.split())
            logger.info(
                "%s. Markdown concatenado: %s tokens | %s palavras (pré-existente)",
                step,
                tokens,
                words,
            )
        else:
            logger.info("%s. Markdown concatenado: não gerado", step)

def collect_pdf_listing(pdf_dir: Path) -> List[Path]:
    return sorted(path for path in pdf_dir.glob("*.pdf") if path.is_file())


def execute_ai_stage(
    settings: Settings,
    markdown_files: List[Path],
    *,
    dry_run: bool,
) -> tuple[List[AIResult], List[ChunkPlan]]:
    if not markdown_files:
        logger.warning("No Markdown files available for AI processing.")
        return [], []

    settings.ensure_directories(include_ai=True)
    prompt_entries = settings.get_user_prompt_entries(None)
    tokenizer = TokenCount(model_name=settings.token_counter_model)

    chunk_plans: List[ChunkPlan] = []
    for md_file in markdown_files:
        try:
            markdown_text = md_file.read_text(encoding="utf-8")
        except OSError as exc:
            logger.error("Failed to read %s: %s", md_file, exc)
            continue

        plan = build_chunk_plan(
            document=md_file,
            markdown_text=markdown_text,
            settings=settings,
            tokenizer=tokenizer,
            prompt_entries=prompt_entries,
        )
        chunk_plans.append(plan)
        save_chunk_plan(plan, settings=settings, parts=max(1, len(prompt_entries)))

    if dry_run:
        logger.info(
            "[dry-run] Preparado envio de %s documento(s) para o modelo %s",
            len(chunk_plans),
            settings.openai_model,
        )
        if prompt_entries:
            logger.info("[dry-run] Usando %s prompt(s) de usuário:", len(prompt_entries))
            for entry in prompt_entries:
                label = entry.get("label", "part")
                display = entry.get("display", label)
                source = entry.get("path") or "inline"
                logger.info("   - %s (%s) from %s", label, display, source)

        for plan in chunk_plans:
            logger.info(
                " - %s ⇒ %s chunk(s) | modo=%s | motivo=%s",
                plan.document.name,
                len(plan.chunks),
                plan.applied_mode,
                plan.reason,
            )
            estimated_tokens = plan.estimated_input_tokens(parts=max(1, len(prompt_entries)))
            estimated_cost = plan.estimated_cost(parts=max(1, len(prompt_entries)))
            if estimated_cost is not None:
                logger.info(
                    "     · Consumo estimado: %s tokens de entrada (~US$ %.4f)",
                    estimated_tokens,
                    estimated_cost,
                )
            else:
                logger.info(
                    "     · Consumo estimado: %s tokens de entrada",
                    estimated_tokens,
                )
            for chunk in plan.chunks:
                logger.info(
                    "     · %s: %s tokens | %s palavras | linhas %s-%s",
                    chunk.chunk_id,
                    chunk.token_count,
                    chunk.word_count,
                    chunk.start_line,
                    chunk.end_line,
                )
        return [], chunk_plans

    try:
        ai_results = run_ai_pipeline(
            settings,
            chunk_plans,
            prompt_entries=prompt_entries,
            overwrite=not settings.skip_existing_ai_outputs,
        )
    except RuntimeError as exc:
        logger.error("AI stage aborted: %s", exc)
        return [], chunk_plans

    if not ai_results:
        logger.info("AI stage completed with no new outputs.")
    else:
        for result in ai_results:
            logger.info("AI output saved to %s", result.output_file)

    return ai_results, chunk_plans


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
    chunk_plans: List[ChunkPlan] = []

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

        ai_results, chunk_plans = execute_ai_stage(
            settings,
            markdown_files,
            dry_run=args.dry_run,
        )

    summarize_processing(
        settings,
        markdown_files,
        conversion_results,
        ai_results,
        chunk_plans,
    )


if __name__ == "__main__":
    main()