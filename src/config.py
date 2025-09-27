from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List

try:
    from dotenv import find_dotenv, load_dotenv  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    find_dotenv = load_dotenv = None

if load_dotenv:
    load_dotenv(find_dotenv())

BASE_DIR = Path(__file__).resolve().parents[1]
PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR", BASE_DIR / "prompts"))
DEFAULT_SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system_prompt.txt"
DEFAULT_USER_PROMPT_PATH = PROMPTS_DIR / "user_prompt.md"
DEFAULT_USER_PROMPT_PART_PATTERN = os.getenv("AI_USER_PROMPT_PART_PATTERN", "user_prompt_part*.md")
DEFAULT_USER_PROMPT_PART_DIR = Path(
    os.getenv("AI_USER_PROMPT_PART_DIR", str(PROMPTS_DIR))
)

DEFAULT_SYSTEM_PROMPT_FALLBACK = "Você é um(a) Analista Jurídico(a) especializado(a) em processos do Judiciário brasileiro.\nReceberá a seguir o CONTEÚDO INTEGRAL de um processo em Markdown."

DEFAULT_USER_PROMPT_FALLBACK = (
    "Você é um(a) Analista Jurídico(a) especializado(a) em processos do Judiciário brasileiro.\n"
    "Receberá a seguir o CONTEÚDO INTEGRAL de um processo em **Markdown**.\n\n"
    "### OBJETIVO\n\n"
    "Gerar um **novo arquivo em Markdown** com seções bem organizadas contendo:\n\n"
    "1. **Metadados do Processo**\n"
    "   - Número, tribunal, grau, comarca\n"
    "   - Classe, competência, órgão julgador, magistrados\n"
    "   - Situação e sigilo\n"
    "   - Assuntos\n"
    "   - Partes (autor, réu(s), MP) e representantes\n"
    "2. **Datas-chave**\n"
    "   - Autuação\n"
    "   - Fato principal\n"
    "   - Audiências\n"
    "   - Sentença\n"
    "   - Acórdão\n"
    "3. **Valores**\n"
    "   - Pedido inicial\n"
    "   - Condenação ou acordo\n"
    "   - Observações\n"
    "4. **Pedidos principais**\n"
    "5. **Tipos penais e leis mencionadas**\n"
    "   - Lei, artigo, descrição, contexto\n"
    "6. **Linha do Tempo**\n"
    "   - Eventos em ordem cronológica (data, evento, fonte)\n"
    "7. **Resumo (5000–10000 palavras)**\n"
    "   - Texto corrido em parágrafo(s), objetivo e extrativo\n"
    "8. **Trechos-fonte**\n"
    "   - Campo → citação literal → referência no documento\n"
    "9. **Lacunas ou Inconsistências**\n"
    "10. **Dados sensíveis detectados**\n"
    "11. **Principais Eventos**\n\n"
    "- **Tabela em Markdown** listando os principais eventos, com colunas:\n"
    "  - Data\n"
    "  - Tipo do evento\n"
    "  - Descrição curta\n"
    "  - Fonte\n"
    "- **Descrição detalhada** (mínimo 300 palavras cada) dos 20 eventos mais relevantes, abordando:\n"
    "  - Contexto jurídico e processual\n"
    "  - Impacto no andamento do processo\n"
    "  - Fundamentação legal (se aplicável)\n"
    "  - Relação com as partes\n"
    "  - Conexões com fatos anteriores/posteriores\n\n"
    "### REGRAS\n\n"
    "- Idioma da saída: **pt-BR**.\n"
    "- Estrutura final deve ser **Markdown válido** com títulos de nível 2 (`##`) para cada seção.\n"
    "- Não invente dados: se não encontrado, escreva `Não identificado`.\n"
    "- Preservar literalidade dos trechos-fonte.\n"
    "- Normalize leis/artigos citados em uma lista.\n"
    "- Linha do tempo deve ter lista de eventos com data + evento + fonte.\n"
    "- Resumo deve ter entre **8000 e 10000 palavras**.\n"
    "- Cada descrição dos 20 principais eventos deve ter **mínimo de 500 palavras**.\n"
    "- Seja extensivo e completo\n"
    "- Use apenas este arquivo como base, e sua habilidade de \"reasoning\" para extração e resumo. Não utilize dados externos.\n\n"
    "### EXEMPLO DE FORMATO (resumido)\n\n"
    "```markdown\n"
    "# Resumo Estruturado do Processo\n\n"
    "## Metadados do Processo\n\n"
    "- Número: XXXXX\n"
    "- Tribunal: TJSC\n"
    "- Grau: 1º grau\n"
    "- Comarca: Itajaí\n"
    "  ...\n\n"
    "## Linha do Tempo\n\n"
    "- 18/05/2023 – Fato narrado – Dos Fatos\n"
    "- 01/02/2024 – Autuação – Capa\n"
    "- 12/06/2024 – Audiência – Evento 004\n\n"
    "## Principais Eventos\n\n"
    "### Tabela dos Principais Eventos\n\n"
    "| Data       | Tipo do Evento | Descrição curta              | Fonte      |\n"
    "| ---------- | -------------- | ---------------------------- | ---------- |\n"
    "| 18/05/2023 | Fato           | Ocorrência principal narrada | Dos Fatos  |\n"
    "| 01/02/2024 | Autuação       | Início formal do processo    | Capa       |\n"
    "| 12/06/2024 | Audiência      | Audiência de instrução       | Evento 004 |\n"
    "| ...        | ...            | ...                          | ...        |\n\n"
    "### Descrição Detalhada dos 20 Principais Eventos\n\n"
    "#### Evento 1 – [Título do Evento]\n\n"
    "[Descrição com no mínimo 500 palavras]\n\n"
    "#### Evento 2 – [Título do Evento]\n\n"
    "[Descrição com no mínimo 500 palavras]\n\n"
    "...\n"
    "```\n\n"
    "### CONTEÚDO ORIGINAL ({document_name})\n\n"
    "```markdown\n"
    "{markdown_content}\n"
    "```"
)


def _read_prompt(path: Path, fallback: str) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return fallback


DEFAULT_SYSTEM_PROMPT = _read_prompt(DEFAULT_SYSTEM_PROMPT_PATH, DEFAULT_SYSTEM_PROMPT_FALLBACK)
DEFAULT_USER_PROMPT_TEMPLATE = _read_prompt(DEFAULT_USER_PROMPT_PATH, DEFAULT_USER_PROMPT_FALLBACK)


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
    ai_output_dir: Path = field(default_factory=lambda: Path(os.getenv("AI_OUTPUT_DIR", "md_output_ia")))

    openai_api_key: str | None = field(default_factory=_load_openai_api_key)
    openai_model: str = os.getenv("OPENAI_MODEL", "o4-mini-2025-04-16")
    token_counter_model: str = os.getenv("TOKEN_COUNTER_MODEL", "gpt-3.5-turbo")

    system_prompt: str = os.getenv("AI_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)
    user_prompt_template: str = os.getenv("AI_USER_PROMPT_TEMPLATE", DEFAULT_USER_PROMPT_TEMPLATE)
    user_prompt_parts_dir: Path = field(
        default_factory=lambda: Path(os.getenv("AI_USER_PROMPT_PART_DIR", str(PROMPTS_DIR)))
    )
    user_prompt_parts_pattern: str = os.getenv("AI_USER_PROMPT_PART_PATTERN", "user_prompt_part*.md")
    user_prompt_parts: List[Path] = field(default_factory=list)

    skip_existing_ai_outputs: bool = os.getenv("AI_SKIP_EXISTING", "0") not in {"0", "false", "False"}

    def __post_init__(self) -> None:
        if not isinstance(self.user_prompt_parts_dir, Path):
            self.user_prompt_parts_dir = Path(self.user_prompt_parts_dir)

        if not self.user_prompt_parts:
            self.user_prompt_parts = [
                path
                for path in sorted(self.user_prompt_parts_dir.glob(self.user_prompt_parts_pattern))
                if path.is_file()
            ]

        if os.getenv("AI_USER_PROMPT_TEMPLATE") is not None:
            self.user_prompt_parts = []

    def ensure_directories(self, *, include_ai: bool = True) -> None:
        """Create required directories if they do not exist."""

        for path in self._iter_directories(include_ai=include_ai):
            path.mkdir(parents=True, exist_ok=True)

    def _iter_directories(self, *, include_ai: bool = True) -> Iterable[Path]:
        yield self.pdf_input_dir
        yield self.md_output_dir
        if include_ai:
            yield self.ai_output_dir

    def get_user_prompt_entries(self, override: str | None = None) -> List[dict[str, object]]:
        """Return a list of user prompt definitions to execute."""

        if override is not None:
            return [
                {
                    "label": "part1",
                    "display": "inline-override",
                    "prompt": override,
                    "path": None,
                }
            ]

        entries: List[dict[str, object]] = []
        if self.user_prompt_parts:
            for idx, path in enumerate(self.user_prompt_parts, start=1):
                try:
                    prompt_text = path.read_text(encoding="utf-8")
                except OSError as exc:
                    logging.getLogger(__name__).error(
                        "Failed to read user prompt part %s: %s", path, exc
                    )
                    continue
                entries.append(
                    {
                        "label": f"part{idx}",
                        "display": path.stem,
                        "prompt": prompt_text,
                        "path": path,
                    }
                )

        if entries:
            return entries

        return [
            {
                "label": "part1",
                "display": "default",
                "prompt": self.user_prompt_template,
                "path": None,
            }
        ]
