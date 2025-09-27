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
├── md_output_ia/            # Respostas da IA
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
- `--pdf-dir`, `--md-dir`, `--ai-dir`: sobrescrevem as pastas padrão (`md_output_ia` é o diretório base da IA)
- `--ai-model`: define outro modelo OpenAI (padrão `o4-mini-2025-04-16`)
- `--skip-existing-ai`: preserva respostas já geradas (por padrão o pipeline sobrescreve)
- `--system-prompt-file`, `--user-prompt-file`: definem prompts a partir de arquivos texto
- `--log-level DEBUG`: habilita logs detalhados

## Configurações e prompts

`src/config.py` centraliza as opções de runtime:

- **Diretórios**: sobrescreva via env vars (`PDF_INPUT_DIR`, `MD_OUTPUT_DIR`, `AI_OUTPUT_DIR`) ou via CLI
- **Chaves**: `OPENAI_API_KEY` continua válido; alternativamente a aplicação lê `openai_api_key.txt` (configurável via `OPENAI_API_KEY_FILE`) ou as variáveis em `.env`
- **Modelo de tokenização**: padrão `gpt-3.5-turbo` (`TOKEN_COUNTER_MODEL`)
- **Modelo da OpenAI**: padrão `o4-mini-2025-04-16` (`OPENAI_MODEL`)
- **Prompts**: edite `prompts/system_prompt.txt` e `prompts/user_prompt.md` para alterar o comportamento padrão. Também é possível usar env vars (`AI_SYSTEM_PROMPT`, `AI_USER_PROMPT_TEMPLATE`) ou apontar arquivos com `--system-prompt-file` / `--user-prompt-file`.
- **Prompts**: o sistema carrega automaticamente `prompts/system_prompt.txt` e até **quatro** arquivos `prompts/user_prompt_partN.md` (N=1..4). Cada parte gera uma chamada independente para a OpenAI, permitindo dividir saídas extensas. Se nenhum arquivo `user_prompt_partN.md` existir, o pipeline usa `prompts/user_prompt.md` como fallback.

> 💡 **Como funciona a divisão em partes**
>
> - `user_prompt_part1.md` ➜ Metadados, datas-chave, valores e pedidos principais.
> - `user_prompt_part2.md` ➜ Tipos penais, dados sensíveis, lacunas e observações.
> - `user_prompt_part3.md` ➜ Linha do tempo e resumo analítico.
> - `user_prompt_part4.md` ➜ Principais eventos detalhados e trechos-fonte.
>
> Cada arquivo mantém os placeholders `{document_name}` e `{markdown_content}` para injetar o conteúdo convertido. Você pode editar, remover ou adicionar arquivos partindo desse padrão. Se preferir um único prompt, basta excluir/renomear os arquivos em `prompts/user_prompt_part*.md` e manter apenas `user_prompt.md`.

As respostas são salvas em `md_output_ia/{documento}_ai_partX.md` (uma para cada parte), **e** o pipeline monta um arquivo consolidado `md_output_ia/{documento}_ai.md` com a concatenação das partes na ordem numérica. Quando há somente um template, apenas o arquivo consolidado é gerado, mantendo compatibilidade com a versão anterior.

### Diagnóstico pós-processamento

Ao término de cada execução (inclusive quando apenas a etapa de IA é rodada), o CLI imprime um bloco **“Diagnóstico de Processamento”** com as seguintes métricas por documento:

1. **Tempo de Docling**: duração da conversão PDF ➜ Markdown.
2. **Tamanho do Markdown**: número de tokens (pelo modelo configurado em `TOKEN_COUNTER_MODEL`) e contagem de palavras.
   3–6. **Tempos dos prompts**: duração individual das respostas da IA para `part1` a `part4` (ou mensagem indicando que o arquivo foi reaproveitado).
3. **Markdown concatenado**: tokens e palavras do arquivo final combinado.

Os tempos são mostrados em segundos com duas casas decimais. Se algum estágio for pulado (por exemplo, Markdown reaproveitado), o diagnóstico sinaliza o motivo.

## Resultados

`docling_test.py` registra a contagem de tokens por documento para estimar custos na OpenAI. As respostas geradas são salvas em `md_output_ia/{documento}_ai.md`.

## Publicação no GitHub

```powershell
git add .
git commit -m "chore: initial import"
git push -u origin main
```

`.venv/`, `__pycache__/` e `md_output_ia/` já estão no `.gitignore`.

## Troubleshooting

- **Avisos de symlink do Hugging Face**: suprimidos automaticamente (`HF_HUB_DISABLE_SYMLINKS_WARNING=1`).
- **Erros de SSL ao baixar modelos**: direcione o Requests para o bundle do certifi:
  ```powershell
  $env:REQUESTS_CA_BUNDLE = (python -m certifi)
  ```
- **PDFs grandes**: a primeira execução pode demorar enquanto o docling baixa modelos; execuções subsequentes usam cache em `%USERPROFILE%\.cache\huggingface`.
- **Sem API key**: a etapa de IA aborta com mensagem. Configure `OPENAI_API_KEY` e rode novamente.
- **Erro 400 invalid value 'text'**: garanta que o projeto esteja atualizado (`git pull && pip install -r requirements.txt`). A chamada usa o tipo `input_text`, compatível com a API Responses atual.

## Próximos passos sugeridos

- Fragmentar conteúdos grandes em blocos menores para respeitar limites de contexto do modelo
- Persistir as respostas também em JSON para parsing programático
- Criar testes automatizados (ex.: PDF de exemplo ➜ Markdown esperado)
- Adicionar agendamento ou uma interface web leve para disparar o pipeline sob demanda
