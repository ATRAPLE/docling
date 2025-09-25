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

BASE_DIR = Path(__file__).resolve().parents[1]
PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR", BASE_DIR / "prompts"))
DEFAULT_SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system_prompt.txt"
DEFAULT_USER_PROMPT_PATH = PROMPTS_DIR / "user_prompt.md"

DEFAULT_SYSTEM_PROMPT_FALLBACK = (
    "Você é um(a) Analista Jurídico(a) especializado(a) em processos do Judiciário brasileiro.\n"
    "Receberá a seguir o CONTEÚDO INTEGRAL de um processo em Markdown."
)

DEFAULT_USER_PROMPT_FALLBACK = (
    "### OBJETIVO\n"
    "Gerar um novo arquivo em Markdown com seções bem organizadas contendo:\n"
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
    "7. **Resumo (120–200 palavras)**\n"
    "   - Texto corrido em parágrafo(s), objetivo e extrativo\n"
    "8. **Trechos-fonte**\n"
    "   - Campo → citação literal → referência no documento\n"
    "9. **Lacunas ou Inconsistências**\n"
    "10. **Dados sensíveis detectados**\n\n"
    "### REGRAS\n"
    "- Idioma da saída: pt-BR.\n"
    "- Estrutura final deve ser Markdown válido com títulos de nível 2 (`##`) para cada seção.\n"
    "- Não invente dados: se não encontrado, escreva `Não identificado`.\n"
    "- Preservar literalidade dos trechos-fonte.\n"
    "- Normalize leis/artigos citados em uma lista.\n"
    "- Linha do tempo deve ter lista de eventos com data + evento + fonte.\n"
    "- Resumo deve ter entre 120–200 palavras.\n\n"
    "### EXEMPLO DE FORMATO (resumido)\n"
    "```markdown\n"
    "# Resumo Estruturado do Processo\n\n"
    "## Metadados do Processo\n"
    "- Número: XXXXX\n"
    "- Tribunal: TJSC\n"
    "- Grau: 1º grau\n"
    "- Comarca: Itajaí\n"
    "- Classe: Ação Penal\n"
    "- Competência: Criminal\n"
    "- Órgão Julgador: 3ª Vara Criminal\n"
    "- Magistrados: [Nome do juiz(a)]\n"
    "- Situação: Ativo\n"
    "- Sigilo: Público\n"
    "- Assuntos: Violação de domicílio\n"
    "- Partes:\n"
    "  - Autor: Ministério Público de SC\n"
    "  - Réu(s): Fulano da Silva\n"
    "  - MP: Promotoria X\n"
    "- Representantes: Dr. Advogado – OAB/SC 0000\n\n"
    "## Datas-chave\n"
    "- Autuação: 01/02/2024\n"
    "- Fato principal: 18/05/2023\n"
    "- Audiência: 12/06/2024\n"
    "- Sentença: Não identificado\n"
    "- Acórdão: Não identificado\n\n"
    "## Valores\n"
    "- Pedido inicial: Não identificado\n"
    "- Condenação/acordo: Não identificado\n"
    "- Observações: N/A\n\n"
    "## Pedidos principais\n"
    "- Condenação por violação de domicílio\n"
    "- Reparação de danos\n\n"
    "## Tipos penais e leis mencionadas\n"
    "- CP – Art. 150 – Violação de domicílio – citado nos “Fatos”\n"
    "- CP – Art. 163 – Dano – citado na denúncia\n\n"
    "## Linha do Tempo\n"
    "- 18/05/2023 – Fato narrado – Dos Fatos\n"
    "- 01/02/2024 – Autuação – Capa\n"
    "- 12/06/2024 – Audiência – Evento 004\n\n"
    "## Resumo (120–200 palavras)\n"
    "[Texto objetivo em 1–2 parágrafos...]\n\n"
    "## Trechos-fonte\n"
    "- Campo: Fato principal  \n"
    "  Citação: \"No dia 18 de maio de 2023, o acusado...\"  \n"
    "  Referência: Seção “Dos Fatos”, parágrafo 3\n\n"
    "## Lacunas ou Inconsistências\n"
    "- Não há sentença registrada\n"
    "- Valores não informados\n\n"
    "## Dados sensíveis detectados\n"
    "- CPF do réu\n"
    "- Endereço residencial\n"
    "```\n\n"
    "### CONTEÚDO ORIGINAL ({document_name})\n"
    "{markdown_content}"
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
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    token_counter_model: str = os.getenv("TOKEN_COUNTER_MODEL", "gpt-3.5-turbo")

    system_prompt: str = os.getenv("AI_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)
    user_prompt_template: str = os.getenv("AI_USER_PROMPT_TEMPLATE", DEFAULT_USER_PROMPT_TEMPLATE)

    skip_existing_ai_outputs: bool = os.getenv("AI_SKIP_EXISTING", "0") not in {"0", "false", "False"}

    def ensure_directories(self, *, include_ai: bool = True) -> None:
        """Create required directories if they do not exist."""

        for path in self._iter_directories(include_ai=include_ai):
            path.mkdir(parents=True, exist_ok=True)

    def _iter_directories(self, *, include_ai: bool = True) -> Iterable[Path]:
        yield self.pdf_input_dir
        yield self.md_output_dir
        if include_ai:
            yield self.ai_output_dir
