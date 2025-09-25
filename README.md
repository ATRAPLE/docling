# Docling Intelligence Pipeline

Structured workflow that converts PDFs to Markdown with [docling](https://github.com/DS4SD/docling), counts tokens, and optionally feeds the Markdown into the OpenAI API for downstream intelligence tasks (resumos, insights, planos de ação etc.).

## Arquitetura em alto nível

```
.
├── docling_test.py          # CLI orquestrador (converter PDFs, chamar OpenAI ou ambos)
├── src/
│   ├── __init__.py
│   ├── config.py            # Configurações centrais (pastas, prompts, modelos)
│   ├── conversion.py        # Utilitários de conversão PDF ➜ Markdown
│   └── ai_pipeline.py       # Processamento Markdown ➜ OpenAI
├── pdf_input/               # Coloque aqui os PDFs de origem
├── md_output/               # Markdown gerado
├── ai_output/               # Respostas da IA
├── requirements.txt         # Dependências Python
└── Rodar_ambiente.txt       # Passo a passo de configuração rápida
```

## Pré-requisitos

- Python 3.10+ (testado com Python 3.13)
- Git (se quiser versionar/publicar)
- Uma chave de API da OpenAI (apenas necessária para a etapa de IA)

## Configuração do ambiente (Windows PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Dependências principais:

- `docling`, `safetensors`, `requests`, `certifi` para parsing/OCR de PDFs
- `token_count` para estimar tokens do modelo GPT
- `openai` para conversar com a OpenAI Platform

## Executando o pipeline

Antes de rodar a etapa de IA, copie o modelo de chave e preencha com sua credencial:

```powershell
Copy-Item openai_api_key.txt.example openai_api_key.txt -ErrorAction SilentlyContinue
notepad openai_api_key.txt
```

O arquivo `openai_api_key.txt` está no `.gitignore` para evitar commits acidentais. Opcionalmente, você ainda pode definir a variável de ambiente `OPENAI_API_KEY` (ou apontar para outro arquivo com `OPENAI_API_KEY_FILE`). Se preferir um `.env`, crie um arquivo com `OPENAI_API_KEY=...`; a aplicação carrega automaticamente quando encontrar `python-dotenv` instalado.

Escolha a etapa desejada:

| Etapa             | Comando                                  | Descrição                                               |
| ----------------- | ---------------------------------------- | ------------------------------------------------------- |
| Converter         | `python docling_test.py --stage convert` | Converte PDFs em Markdown e registra contagem de tokens |
| IA                | `python docling_test.py --stage ai`      | Lê Markdown existente e envia para a OpenAI             |
| Completo (padrão) | `python docling_test.py`                 | Converte e processa com IA em uma única execução        |

### Flags úteis

- `--dry-run`: apenas lista os arquivos que seriam processados
- `--pdf-dir`, `--md-dir`, `--ai-dir`: sobrescrevem as pastas padrão
- `--ai-model`: define outro modelo OpenAI (padrão `gpt-4o-mini`)
- `--overwrite-ai`: regrava as respostas mesmo que já existam
- `--system-prompt-file`, `--user-prompt-file`: definem prompts a partir de arquivos texto
- `--log-level DEBUG`: habilita logs detalhados

## Configurações e prompts

`src/config.py` centraliza as opções de runtime:

- **Diretórios**: sobrescreva via env vars (`PDF_INPUT_DIR`, `MD_OUTPUT_DIR`, `AI_OUTPUT_DIR`) ou via CLI
- **Chaves**: `OPENAI_API_KEY` continua válido; alternativamente a aplicação lê `openai_api_key.txt` (configurável via `OPENAI_API_KEY_FILE`) ou as variáveis em `.env`
- **Modelo de tokenização**: padrão `gpt-3.5-turbo` (`TOKEN_COUNTER_MODEL`)
- **Modelo da OpenAI**: padrão `gpt-4o-mini` (`OPENAI_MODEL`)
- **Prompts**: ajuste `AI_SYSTEM_PROMPT` e `AI_USER_PROMPT_TEMPLATE` ou informe arquivos com `--system-prompt-file` / `--user-prompt-file`

O template de usuário padrão espera os placeholders `{document_name}` e `{markdown_content}`. Adapte conforme a tarefa (compliance, QA, plano de ação, etc.).

## Resultados

`docling_test.py` registra a contagem de tokens por documento para estimar custos na OpenAI.

## Publicação no GitHub

```powershell
git add .
git commit -m "chore: initial import"
git push -u origin main
```

`.venv/`, `__pycache__/` e `ai_output/` já estão no `.gitignore`.

## Troubleshooting

- **Avisos de symlink do Hugging Face**: suprimidos automaticamente (`HF_HUB_DISABLE_SYMLINKS_WARNING=1`).
- **Erros de SSL ao baixar modelos**: direcione o Requests para o bundle do certifi:
  ```powershell
  $env:REQUESTS_CA_BUNDLE = (python -m certifi)
  ```
- **PDFs grandes**: a primeira execução pode demorar enquanto o docling baixa modelos; execuções subsequentes usam cache em `%USERPROFILE%\.cache\huggingface`.
- **Sem API key**: a etapa de IA aborta com mensagem. Configure `OPENAI_API_KEY` e rode novamente.

## Próximos passos sugeridos

- Fragmentar conteúdos grandes em blocos menores para respeitar limites de contexto do modelo
- Persistir as respostas também em JSON para parsing programático
- Criar testes automatizados (ex.: PDF de exemplo ➜ Markdown esperado)
- Adicionar agendamento ou uma interface web leve para disparar o pipeline sob demanda
