from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from openai import OpenAI
from token_count import TokenCount

from .config import Settings
from .chunking import ChunkPlan

logger = logging.getLogger(__name__)


@dataclass
class AIResult:
    markdown_file: Path
    output_file: Path
    response_text: str
    prompt_label: Optional[str] = None
    duration_seconds: Optional[float] = None
    token_count: Optional[int] = None
    word_count: Optional[int] = None
    chunk_id: Optional[str] = None


def _build_prompt(template: str, *, document_name: str, markdown_content: str) -> str:
    return template.format(document_name=document_name, markdown_content=markdown_content)


def run_ai_pipeline(
    settings: Settings,
    chunk_plans: Sequence[ChunkPlan],
    *,
    system_prompt: str | None = None,
    prompt_entries: Sequence[dict[str, object]] | None = None,
    user_prompt_template: str | None = None,
    overwrite: bool = False,
) -> List[AIResult]:
    """Execute the AI stage given precomputed chunk plans."""

    if not chunk_plans:
        logger.warning("No chunk plans provided for AI processing.")
        return []

    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Export it as an environment variable "
            "or provide it before running the AI stage."
        )

    system_prompt = system_prompt or settings.system_prompt
    if prompt_entries is None:
        prompt_entries = settings.get_user_prompt_entries(user_prompt_template)

    if not prompt_entries:
        logger.error("No user prompt templates available; aborting AI stage.")
        return []

    settings.ai_output_dir.mkdir(parents=True, exist_ok=True)

    client = OpenAI(api_key=settings.openai_api_key)
    token_counter = TokenCount(model_name=settings.token_counter_model)
    results: List[AIResult] = []
    multi_prompt_mode = len(prompt_entries) > 1 or any(
        entry.get("display") not in {"default", "inline-override"} for entry in prompt_entries
    )
    for plan in chunk_plans:
        doc_path = plan.document
        if not doc_path.exists():
            logger.warning("Markdown file not found: %s", doc_path)
            continue

        if not plan.chunks:
            logger.warning("Chunk plan for %s has no chunks; skipping.", doc_path)
            continue

        total_chunks = len(plan.chunks)
        logger.info(
            "Processing %s com %s chunk(s) usando modelo %s",
            doc_path.name,
            total_chunks,
            settings.openai_model,
        )

        chunk_merge_paths: List[Path] = []

        for chunk in plan.chunks:
            chunk_suffix = "" if total_chunks == 1 else f"_{chunk.chunk_id}"
            base_filename = f"{doc_path.stem}{chunk_suffix}_ai"

            heading_summary = ", ".join(chunk.headings[:4]) or "sem títulos"
            chunk_header = (
                f"Chunk {chunk.index}/{total_chunks} do documento {doc_path.name}. "
                f"Linhas {chunk.start_line}-{chunk.end_line}. Seções: {heading_summary}."
            )
            chunk_markdown_content = f"{chunk_header}\n\n{chunk.text}".strip()

            part_outputs: List[tuple[dict[str, object], Path]] = []
            pending_entries: List[tuple[dict[str, object], Path]] = []

            for entry in prompt_entries:
                label = str(entry.get("label", "part1"))
                if multi_prompt_mode:
                    output_filename = f"{base_filename}_{label}.md"
                else:
                    output_filename = f"{base_filename}.md"

                output_path = settings.ai_output_dir / output_filename
                part_outputs.append((entry, output_path))

                if output_path.exists() and not overwrite:
                    logger.info(
                        "Skipping %s (%s - %s) because output already exists",
                        doc_path.name,
                        chunk.chunk_id,
                        entry.get("display", label),
                    )
                else:
                    pending_entries.append((entry, output_path))

            part_results: List[AIResult] = []

            for entry, output_path in pending_entries:
                label = str(entry.get("label", "part1"))
                logger.info(
                    "Requesting completion for %s (%s - %s)",
                    doc_path.name,
                    chunk.chunk_id,
                    entry.get("display", label),
                )

                user_prompt = _build_prompt(
                    str(entry.get("prompt", settings.user_prompt_template)),
                    document_name=f"{doc_path.stem} ({chunk.chunk_id})",
                    markdown_content=chunk_markdown_content,
                )

                start_time = time.perf_counter()
                try:
                    response = client.responses.create(
                        model=settings.openai_model,
                        input=[
                            {
                                "role": "system",
                                "content": [
                                    {"type": "input_text", "text": system_prompt},
                                ],
                            },
                            {
                                "role": "user",
                                "content": [
                                    {"type": "input_text", "text": user_prompt},
                                ],
                            },
                        ],
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "OpenAI request failed for %s (%s - %s): %s",
                        doc_path.name,
                        chunk.chunk_id,
                        entry.get("display", label),
                        exc,
                    )
                    continue

                output_text = response.output_text  # type: ignore[attr-defined]
                output_path.write_text(output_text, encoding="utf-8")
                duration = time.perf_counter() - start_time
                tokens = token_counter.num_tokens_from_string(output_text)
                words = len(output_text.split())
                logger.info("Saved AI response to %s", output_path)

                result = AIResult(
                    markdown_file=doc_path,
                    output_file=output_path,
                    response_text=output_text,
                    prompt_label=label,
                    duration_seconds=duration,
                    token_count=tokens,
                    word_count=words,
                    chunk_id=chunk.chunk_id,
                )
                results.append(result)
                part_results.append(result)

            # Merge prompts for this chunk
            chunk_merge_path = settings.ai_output_dir / f"{base_filename}.md"
            merged_text_sources: List[str] = []
            for _, output_path in part_outputs:
                if output_path.exists():
                    merged_text_sources.append(output_path.read_text(encoding="utf-8").strip())

            merged_text = "\n\n".join(text for text in merged_text_sources if text)
            chunk_merge_path.write_text((merged_text + "\n") if merged_text else "", encoding="utf-8")
            logger.info("Saved chunk merged output to %s", chunk_merge_path)

            merged_tokens = token_counter.num_tokens_from_string(merged_text)
            merged_words = len(merged_text.split()) if merged_text else 0

            results.append(
                AIResult(
                    markdown_file=doc_path,
                    output_file=chunk_merge_path,
                    response_text=merged_text,
                    prompt_label=f"{chunk.chunk_id}-merged",
                    duration_seconds=None,
                    token_count=merged_tokens,
                    word_count=merged_words,
                    chunk_id=chunk.chunk_id,
                )
            )

            chunk_merge_paths.append(chunk_merge_path)

        # merge all chunks into a single document-level file
        if chunk_merge_paths:
            global_merge_path = settings.ai_output_dir / f"{doc_path.stem}_ai.md"
            global_chunks: List[str] = []
            for chunk in plan.chunks:
                chunk_suffix = "" if total_chunks == 1 else f"_{chunk.chunk_id}"
                candidate_path = settings.ai_output_dir / f"{doc_path.stem}{chunk_suffix}_ai.md"
                if candidate_path.exists():
                    text = candidate_path.read_text(encoding="utf-8").strip()
                    if text:
                        global_chunks.append(text)

            global_merged_text = "\n\n".join(global_chunks)
            global_merge_path.write_text((global_merged_text + "\n") if global_merged_text else "", encoding="utf-8")
            logger.info("Saved global merged output to %s", global_merge_path)

            global_tokens = token_counter.num_tokens_from_string(global_merged_text)
            global_words = len(global_merged_text.split()) if global_merged_text else 0

            results.append(
                AIResult(
                    markdown_file=doc_path,
                    output_file=global_merge_path,
                    response_text=global_merged_text,
                    prompt_label="merged",
                    duration_seconds=None,
                    token_count=global_tokens,
                    word_count=global_words,
                    chunk_id="global",
                )
            )

    return results


def collect_markdown_files(md_dir: Path) -> List[Path]:
    """Gather Markdown files sorted by name."""

    return sorted(path for path in md_dir.glob("*.md") if path.is_file())
