# Estratégia Proposta para Chunking de Markdown

> Status: implementado no pipeline principal (set/2025). Este documento continua descrevendo o racional e aponta evoluções futuras.

## Objetivos e Restrições

- **Manter cobertura completa dos prompts**: cada pedaço (chunk) do Markdown precisa passar por todas as partes de prompt já definidas (part1…partN) para preservar o comportamento atual.
- **Evitar perda de informação**: a junção dos resultados não pode descartar conteúdo. Precisamos garantir ordenação cronológica e metadados que permitam reconstruir o texto original.
- **Avaliação pré-execução**: antes de chamar a IA, deve ser possível estimar tokens, número de requisições e custo.
- **Compatibilidade com o pipeline atual**: o plano deve encaixar com `convert_pdfs_to_markdown`, `run_ai_pipeline` e a etapa de diagnóstico sem quebrar a experiência existente.

## 1. Análise de Orçamento de Contexto

1. Calcular o tamanho do Markdown com `TokenCount` (já disponível) logo após a conversão ou ao carregar o arquivo.
2. Calcular o custo de prompt por parte: `tokens(system_prompt + user_prompt_parte + chunk)`.
3. Estimar o limite do modelo via tabela (ex.: `o4-mini-2025-04-16 ≈ 200k tokens`). Permitir override via `.env`.
4. Se o Markdown + prompts couberem no limite com folga (ex.: 80% do contexto), enviar inteiro. Caso contrário, ativar chunking.
5. Gerar um relatório `dry-run` com a estimativa (número de chunks, tokens por requisição, custo aproximado baseado em pricing configurável).

## 2. Estratégia de Chunking

1. **Pré-processamento estrutural**:
   - Parsear o Markdown em blocos com base em títulos (`#`, `##`, etc.).
   - Manter parágrafos e listas como unidades mínimas para evitar quebra no meio de frases.
2. **Construção de chunks**:
   - Definir um alvo de tokens por chunk (ex.: 10k) com tolerância ±15%.
   - Agregar seções sequenciais até atingir o alvo; evitar passar muito do limite.
   - Caso uma seção isolada ultrapasse o alvo, subdividir por parágrafos ou subseções.
   - Inserir **sobreposição opcional** (ex.: repetir últimos 200 tokens no próximo chunk) para preservar contexto.
3. **Metadados de chunk**:
   - Atribuir identificadores (`chunk_01`, `chunk_02`…), registrar intervalo de linhas e títulos cobertos.
   - Criar um índice (`chunks.json`) com informações: tokens, palavras, seções, dependências.
4. **Fallback**: se parsing estrutural falhar, usar split por parágrafo em janela deslizante baseada em tokens.

## 3. Disparo dos Prompts por Chunk

1. Para cada chunk, gerar o texto final de prompt substituindo `{markdown_content}` pelo conteúdo do chunk.
2. Executar todas as partes (`part1…partN`) para cada chunk, preservando os nomes de arquivos com padrões como `documento_chunkXX_ai_partY.md`.
3. Passar metadados no início do prompt (ex.: "Este é o chunk 2/5 contendo as seções X, Y").
4. Reutilizar mecanismos existentes de skip (`AI_SKIP_EXISTING`) com granularidade por chunk.
5. Registrar tempos, tokens e custos por chunk e por parte no diagnóstico.

## 4. Organização e Unificação das Saídas

1. **Outputs primários**: arquivos por chunk/parte (ex.: `processo_chunk02_ai_part3.md`).
2. **Mesclagem por chunk**: concatenar as partes (`part1…partN`) de cada chunk se necessário, gerando `processo_chunk02_ai.md`.
3. **Mesclagem global**: concatenar todos os chunks na ordem original, garantindo:
   - Delimitadores explícitos entre chunks (`<!-- chunk_02 start/end -->`).
   - Índice remissivo opcional com links para cada chunk.
4. **Verificação de integridade**: comparar token count do Markdown original com a soma dos chunks para assegurar cobertura total.
5. **Relatório final**: atualizar `Diagnóstico de Processamento` com o quadro geral (n chunks, tokens de entrada/saída, tempo total, requisições).

## 5. Avaliação e Ferramentas de Apoio

- **Comando dry-run chunking**: listar tamanho estimado dos chunks sem chamar IA.
- **Visualização rápida**: gerar `docs/chunk_map.md` com tabela de seções x chunk.
- **Limite manual**: permitir ajuste de tamanho alvo via env (`AI_CHUNK_TARGET_TOKENS`).
- **Monitoramento**: adicionar logs por chunk e part na mesma formatação já existente.

## 6. Considerações e Pontos de Atenção

- **Coerência entre chunks**: algumas seções (Linha do Tempo, Principais Eventos) exigem visão do documento completo. Podemos reservar um chunk final "resumo global" com o Markdown inteiro caso o contexto permita, ou usar um passo adicional de agregação com prompts especiais.
- **Referências cruzadas**: manter marcações de origem (ex.: "Fonte: chunk03 §2") para rastrear trechos.
- **Paralelismo**: executar chunks em paralelo com limites configuráveis para respeitar rate limits.
- **Reprocessamento**: se o Markdown mudar, invalidar chunks afetados; usar hash do conteúdo para detectar mudanças parciais.
- **Custos**: chunking aumenta o número de requisições; medir ROI comparando custo extra vs. impossibilidade de rodar sem chunking.

## 7. Próximos Passos Sugeridos

1. Avaliar paralelismo controlado dos chunks respeitando limites de rate limit da API.
2. Experimentar heurísticas alternativas de sobreposição (ex.: por sentença) para reduzir redundância sem perder contexto.
3. Incorporar métricas de custo real (a partir do billing) para comparar com a estimativa.
4. Investigar prompts agregadores opcionais para gerar sumários globais adicionais após o merge.
5. Criar testes unitários cobrindo casos extremos (seção única gigante, markdown sem títulos, etc.) para o módulo `chunking.py`.

> Esta estratégia permanece como guia de referência para manter o chunking saudável e evolutivo à medida que novos modelos e requisitos surgirem.
