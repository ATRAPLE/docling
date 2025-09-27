from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from openai import OpenAI
from token_count import TokenCount

from .config import Settings

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


def _build_prompt(template: str, *, document_name: str, markdown_content: str) -> str:
    return template.format(document_name=document_name, markdown_content=markdown_content)


def run_ai_pipeline(
    settings: Settings,
    markdown_files: Sequence[Path],
    *,
    system_prompt: str | None = None,
    user_prompt_template: str | None = None,
    overwrite: bool = False,
) -> List[AIResult]:
    """Send Markdown files to the configured OpenAI model and store responses."""

    if not markdown_files:
        logger.warning("No Markdown files provided for AI processing.")
        return []

    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Export it as an environment variable "
            "or provide it before running the AI stage."
        )

    system_prompt = system_prompt or settings.system_prompt
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

    for md_path in markdown_files:
        if not md_path.exists():
            logger.warning("Markdown file not found: %s", md_path)
            continue

        part_outputs = []
        for entry in prompt_entries:
            label = entry.get("label", "part1")
            if multi_prompt_mode:
                output_filename = f"{md_path.stem}_ai_{label}.md"
            else:
                output_filename = f"{md_path.stem}_ai.md"

            output_path = settings.ai_output_dir / output_filename
            part_outputs.append((entry, output_path))

        pending = []
        for entry, output_path in part_outputs:
            if output_path.exists() and not overwrite:
                logger.info(
                    "Skipping %s (%s) because output already exists",
                    md_path.name,
                    entry.get("display", entry.get("label", "part")),
                )
                continue
            pending.append((entry, output_path))

        if not pending:
            logger.info("No pending AI prompts for %s; moving on.", md_path.name)
            continue

        markdown_text = md_path.read_text(encoding="utf-8")
        part_results: List[AIResult] = []

        for entry, output_path in pending:
            user_prompt = _build_prompt(
                str(entry.get("prompt", settings.user_prompt_template)),
                document_name=md_path.stem,
                markdown_content=markdown_text,
            )

            label = entry.get("label", "part1")
            logger.info(
                "Requesting completion for %s (%s)",
                md_path.name,
                entry.get("display", label),
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
                    "OpenAI request failed for %s (%s): %s",
                    md_path.name,
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
                markdown_file=md_path,
                output_file=output_path,
                response_text=output_text,
                prompt_label=str(label),
                duration_seconds=duration,
                token_count=tokens,
                word_count=words,
            )
            results.append(result)
            part_results.append(result)

        if multi_prompt_mode and part_results:
            merged_path = settings.ai_output_dir / f"{md_path.stem}_ai.md"
            merged_text_chunks = [
                chunk.response_text.strip()
                for chunk in part_results
                if chunk.response_text.strip()
            ]
            merged_text = "\n\n".join(merged_text_chunks)
            if merged_text:
                merged_path.write_text(merged_text + "\n", encoding="utf-8")
            else:
                merged_path.write_text("", encoding="utf-8")
            logger.info("Saved merged AI response to %s", merged_path)

            merged_tokens = token_counter.num_tokens_from_string(merged_text)
            merged_words = len(merged_text.split()) if merged_text else 0

            results.append(
                AIResult(
                    markdown_file=md_path,
                    output_file=merged_path,
                    response_text=merged_text,
                    prompt_label="merged",
                    duration_seconds=None,
                    token_count=merged_tokens,
                    word_count=merged_words,
                )
            )

    return results


def collect_markdown_files(md_dir: Path) -> List[Path]:
    """Gather Markdown files sorted by name."""

    return sorted(path for path in md_dir.glob("*.md") if path.is_file())
