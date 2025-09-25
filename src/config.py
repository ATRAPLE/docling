from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

try:
    from dotenv import find_dotenv, load_dotenv  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    find_dotenv = load_dotenv = None

if load_dotenv:
    load_dotenv(find_dotenv())

DEFAULT_SYSTEM_PROMPT = (
    "You are an assistant that reads industrial automation documents "
    "and produces concise, well-structured analyses."
)
DEFAULT_USER_PROMPT_TEMPLATE = (
    "You will receive the full Markdown content of a document named '{document_name}'.\n"
    "Provide: \n"
    "1. A short executive summary in Portuguese.\n"
    "2. Bullet points with the most important insights.\n"
    "3. Up to five suggested next steps or open questions.\n"
    "Do not invent information that is not supported by the text.\n\n"
    "Document Markdown:\n{markdown_content}"
)


def _load_openai_api_key() -> str | None:
    """Resolve the OpenAI API key from env vars or a local file."""

    env_key = os.getenv("OPENAI_API_KEY")
    if env_key:
        return env_key

    file_path = Path(os.getenv("OPENAI_API_KEY_FILE", "openai_api_key.txt"))
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        return None

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            _, value = stripped.split("=", 1)
            return value.strip().strip('"').strip("'") or None
        return stripped.strip('"').strip("'") or None

    return None


@dataclass
class Settings:
    """Runtime configuration for the docling + AI pipeline."""

    pdf_input_dir: Path = field(default_factory=lambda: Path(os.getenv("PDF_INPUT_DIR", "pdf_input")))
    md_output_dir: Path = field(default_factory=lambda: Path(os.getenv("MD_OUTPUT_DIR", "md_output")))
    ai_output_dir: Path = field(default_factory=lambda: Path(os.getenv("AI_OUTPUT_DIR", "ai_output")))

    openai_api_key: str | None = field(default_factory=_load_openai_api_key)
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    token_counter_model: str = os.getenv("TOKEN_COUNTER_MODEL", "gpt-3.5-turbo")

    system_prompt: str = os.getenv("AI_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)
    user_prompt_template: str = os.getenv("AI_USER_PROMPT_TEMPLATE", DEFAULT_USER_PROMPT_TEMPLATE)

    skip_existing_ai_outputs: bool = os.getenv("AI_SKIP_EXISTING", "1") not in {"0", "false", "False"}

    def ensure_directories(self, *, include_ai: bool = True) -> None:
        """Create required directories if they do not exist."""

        for path in self._iter_directories(include_ai=include_ai):
            path.mkdir(parents=True, exist_ok=True)

    def _iter_directories(self, *, include_ai: bool = True) -> Iterable[Path]:
        yield self.pdf_input_dir
        yield self.md_output_dir
        if include_ai:
            yield self.ai_output_dir
