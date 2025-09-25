from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

from openai import OpenAI

from .config import Settings

logger = logging.getLogger(__name__)


@dataclass
class AIResult:
    markdown_file: Path
    output_file: Path
    response_text: str


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
    user_prompt_template = user_prompt_template or settings.user_prompt_template

    settings.ai_output_dir.mkdir(parents=True, exist_ok=True)

    client = OpenAI(api_key=settings.openai_api_key)
    results: List[AIResult] = []

    for md_path in markdown_files:
        if not md_path.exists():
            logger.warning("Markdown file not found: %s", md_path)
            continue

        output_path = settings.ai_output_dir / f"{md_path.stem}_ai.md"
        if output_path.exists() and not overwrite and settings.skip_existing_ai_outputs:
            logger.info("Skipping %s because output already exists", md_path)
            continue

        markdown_text = md_path.read_text(encoding="utf-8")
        user_prompt = _build_prompt(
            user_prompt_template,
            document_name=md_path.stem,
            markdown_content=markdown_text,
        )

        logger.info("Requesting completion for %s", md_path.name)
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
            logger.exception("OpenAI request failed for %s: %s", md_path, exc)
            continue

        output_text = response.output_text  # type: ignore[attr-defined]
        output_path.write_text(output_text, encoding="utf-8")
        logger.info("Saved AI response to %s", output_path)

        results.append(
            AIResult(
                markdown_file=md_path,
                output_file=output_path,
                response_text=output_text,
            )
        )

    return results


def collect_markdown_files(md_dir: Path) -> List[Path]:
    """Gather Markdown files sorted by name."""

    return sorted(path for path in md_dir.glob("*.md") if path.is_file())
