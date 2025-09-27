# Docling Intelligence Pipeline

Structured workflow that converts PDFs to Markdown with [docling](https://github.com/DS4SD/docling), counts tokens, and optionally feeds the Markdown into the OpenAI API for downstream intelligence tasks (resumos, insights, planos de ação etc.).

## Arquitetura em alto nível

```
.
├── docling_test.py          # CLI orquestrador (converter PDFs, chamar OpenAI ou ambos)
├── src/
│   ├── __init__.py
│   ├── config.py            # Configurações centrais (pastas, prompts, modelos, chunking)
│   ├── conversion.py        # Utilitários de conversão PDF ➜ Markdown
│   ├── chunking.py          # Planejamento e particionamento do Markdown em chunks
│   └── ai_pipeline.py       # Processamento Markdown ➜ OpenAI (multi-prompt + chunks)
├── pdf_input/               # Coloque aqui os PDFs de origem
├── md_output/               # Markdown gerado
├── md_output_ia/            # Respostas da IA
├── docs/                    # Estratégia e mapas de chunking gerados pelo pipeline
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

## Chunking do Markdown

Para respeitar limites de contexto dos modelos, o pipeline avalia automaticamente a necessidade de **quebrar o Markdown em chunks** antes de chamar a OpenAI:

- **Modo** (`--chunking` ou env `AI_CHUNKING_MODE`):
  - `auto` (padrão) ➜ aplica chunking apenas se o documento extrapolar o orçamento de contexto estimado
  - `force` ➜ sempre fatia o Markdown
  - `off` ➜ envia o arquivo inteiro independente do tamanho
- **Tamanho** (`--chunk-target`, `--chunk-max`) ➜ define alvo e teto de tokens por chunk; o pipeline usa títulos e parágrafos para cortar de forma natural e aplica split extra se necessário.
- **Sobreposição** (`--chunk-overlap`) ➜ repete os últimos N tokens do chunk anterior no início do próximo para manter continuidade.
- **Estimativa de custo** (`--chunk-price-input`) ➜ informa o valor por 1k tokens de entrada para estimar custo em dry-run e salvar no plano.

Cada execução gera um **plano de chunking** (`chunk_metadata/{documento}_chunks.json`) e um **mapa em Markdown** (`chunk_metadata/{documento}_chunk_map.md`) com as seções, tokens e intervalos de linhas. Em `--dry-run`, o CLI exibe a quantidade de chunk(s), tokens previstos por requisição e custo estimado.

Quando chunking está ativo, os arquivos de saída seguem o padrão:

- `md_output_ia/{documento}_chunkNN_ai_partX.md` ➜ resposta da parte X para o chunk NN
- `md_output_ia/{documento}_chunkNN_ai.md` ➜ fusão das partes daquele chunk
- `md_output_ia/{documento}_ai.md` ➜ fusão global (todos os chunks, na ordem original)

Se o documento couber em um único chunk, o pipeline mantém os nomes compatíveis com a versão anterior (`{documento}_ai_partX.md` e `{documento}_ai.md`).

### Diagnóstico pós-processamento

Ao término de cada execução (inclusive quando apenas a etapa de IA é rodada), o CLI imprime um bloco **“Diagnóstico de Processamento”** com as seguintes métricas por documento:

1. **Tempo de Docling** e **tamanho do Markdown** após a conversão.
2. **Resumo de chunking** (quando aplicável): total de chunks, modo utilizado e motivação (ex.: “documento excede limite disponível”). Cada chunk mostra tokens, palavras, linhas cobertas, tempo/caminho das respostas por prompt e o tamanho do arquivo combinado daquele pedaço.
3. **Markdown concatenado global**: tokens e palavras do arquivo final (`{documento}_ai.md`), indicando se foi reutilizado de execução anterior.

Os tempos são mostrados em segundos com duas casas decimais. Se algum estágio for pulado (por exemplo, Markdown reaproveitado), o diagnóstico sinaliza o motivo.

## Resultados

`docling_test.py` registra a contagem de tokens por documento para estimar custos na OpenAI. As respostas geradas ficam em `md_output_ia/`, onde cada chunk recebe nome próprio (`{documento}_chunkNN_ai_partX.md` ➜ `{documento}_chunkNN_ai.md`) e o arquivo `md_output_ia/{documento}_ai.md` concentra o texto consolidado.

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
