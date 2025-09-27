from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Sequence

from token_count import TokenCount

from .config import Settings

logger = logging.getLogger(__name__)

_heading_re = re.compile(r"^(#{1,6})\s+(.*)")
_sentence_split_re = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Þ0-9])")


@dataclass(slots=True)
class ContentBlock:
    """Atomic markdown content block that fits within the chunk limit."""

    text: str
    start_line: int
    end_line: int
    heading_path: Sequence[str]
    tokens: int
    words: int


@dataclass(slots=True)
class MarkdownChunk:
    document: Path
    chunk_id: str
    index: int
    text: str
    token_count: int
    word_count: int
    start_line: int
    end_line: int
    headings: List[str]
    block_count: int
    overlap_from_previous_tokens: int = 0


@dataclass(slots=True)
class ChunkPlan:
    document: Path
    applied_mode: str
    reason: str
    original_tokens: int
    original_words: int
    system_prompt_tokens: int
    max_user_prompt_tokens: int
    context_limit: int | None
    chunk_target_tokens: int
    chunk_max_tokens: int
    chunk_overlap_tokens: int
    pricing_input_per_1k: float
    chunks: List[MarkdownChunk] = field(default_factory=list)

    def estimated_input_tokens(self, *, parts: int) -> int:
        base = (self.system_prompt_tokens + self.max_user_prompt_tokens)
        return sum(base + chunk.token_count for chunk in self.chunks) * parts

    def estimated_cost(self, *, parts: int) -> float | None:
        if self.pricing_input_per_1k <= 0:
            return None
        total_tokens = self.estimated_input_tokens(parts=parts)
        return round((total_tokens / 1000.0) * self.pricing_input_per_1k, 4)

    def to_dict(self, *, parts: int) -> dict[str, object]:
        return {
            "document": str(self.document),
            "applied_mode": self.applied_mode,
            "reason": self.reason,
            "original_tokens": self.original_tokens,
            "original_words": self.original_words,
            "system_prompt_tokens": self.system_prompt_tokens,
            "max_user_prompt_tokens": self.max_user_prompt_tokens,
            "context_limit": self.context_limit,
            "chunk_target_tokens": self.chunk_target_tokens,
            "chunk_max_tokens": self.chunk_max_tokens,
            "chunk_overlap_tokens": self.chunk_overlap_tokens,
            "pricing_input_per_1k": self.pricing_input_per_1k,
            "chunk_count": len(self.chunks),
            "estimated_input_tokens": self.estimated_input_tokens(parts=parts),
            "estimated_cost": self.estimated_cost(parts=parts),
            "chunks": [
                {
                    "chunk_id": chunk.chunk_id,
                    "index": chunk.index,
                    "token_count": chunk.token_count,
                    "word_count": chunk.word_count,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "headings": chunk.headings,
                    "block_count": chunk.block_count,
                    "overlap_from_previous_tokens": chunk.overlap_from_previous_tokens,
                }
                for chunk in self.chunks
            ],
        }


def build_chunk_plan(
    *,
    document: Path,
    markdown_text: str,
    settings: Settings,
    tokenizer: TokenCount,
    prompt_entries: Sequence[dict[str, object]],
) -> ChunkPlan:
    """Return the chunking plan for a markdown document."""

    total_tokens = tokenizer.num_tokens_from_string(markdown_text)
    total_words = len(markdown_text.split())

    system_tokens = tokenizer.num_tokens_from_string(settings.system_prompt)
    user_prompt_tokens = [
        tokenizer.num_tokens_from_string(str(entry.get("prompt", "")))
        for entry in prompt_entries
    ]
    max_user_tokens = max(user_prompt_tokens) if user_prompt_tokens else 0

    context_limit = settings.get_model_context_limit()
    applied_mode = settings.chunking_mode
    reason = ""

    def should_chunk() -> bool:
        nonlocal reason
        if applied_mode == "force":
            reason = "Modo force ativado"
            return True
        if applied_mode == "off":
            reason = "Chunking desativado"
            return False
        # auto
        if context_limit is None:
            reason = "Sem limite conhecido do modelo; conteúdo enviado inteiro"
            return False
        available_markdown_tokens = int(context_limit * settings.chunk_context_fraction) - (
            system_tokens + max_user_tokens
        )
        if available_markdown_tokens <= 0:
            reason = (
                "Limite de contexto insuficiente após prompts; chunking obrigatório"
            )
            return True
        if total_tokens <= available_markdown_tokens:
            reason = "Documento cabe inteiro no contexto"
            return False
        reason = (
            f"Markdown excede limite disponível ({total_tokens}>{available_markdown_tokens}); chunking ativado"
        )
        return True

    need_chunking = should_chunk()

    plan = ChunkPlan(
        document=document,
        applied_mode=applied_mode,
        reason=reason,
        original_tokens=total_tokens,
        original_words=total_words,
        system_prompt_tokens=system_tokens,
        max_user_prompt_tokens=max_user_tokens,
        context_limit=context_limit,
        chunk_target_tokens=settings.chunk_target_tokens,
        chunk_max_tokens=settings.chunk_max_tokens,
        chunk_overlap_tokens=settings.chunk_overlap_tokens,
        pricing_input_per_1k=settings.chunk_pricing_input_per_1k,
    )

    if not need_chunking:
        chunk_text = markdown_text.strip()
        tokens = tokenizer.num_tokens_from_string(chunk_text)
        words = len(chunk_text.split())
        plan.chunks.append(
            MarkdownChunk(
                document=document,
                chunk_id="chunk_01",
                index=1,
                text=wrap_chunk_text(
                    chunk_id="chunk_01",
                    chunk_index=1,
                    total_chunks=1,
                    body_text=chunk_text,
                ),
                token_count=tokens,
                word_count=words,
                start_line=1,
                end_line=markdown_text.count("\n") + 1,
                headings=["<documento inteiro>"],
                block_count=1,
            )
        )
        if not plan.reason:
            plan.reason = "Chunking não necessário"
        return plan

    blocks = list(_generate_blocks(markdown_text, tokenizer))
    if not blocks:
        logger.warning("Documento %s sem blocos; chunk único será usado", document)
        return plan

    expanded_blocks = list(_enforce_block_limits(blocks, settings.chunk_max_tokens, tokenizer))
    chunks = _build_chunks_from_blocks(
        expanded_blocks,
        plan,
        tokenizer,
    )

    plan.chunks.extend(chunks)
    return plan


def _generate_blocks(markdown_text: str, tokenizer: TokenCount) -> Iterable[ContentBlock]:
    lines = markdown_text.splitlines()
    sections: List[dict[str, object]] = []
    current = {
        "level": 1,
        "title": "Documento",
        "start_line": 1,
        "lines": [],
    }
    for idx, line in enumerate(lines, start=1):
        match = _heading_re.match(line)
        if match:
            if current["lines"]:
                current["end_line"] = idx - 1
                sections.append(current)
            level = len(match.group(1))
            title = match.group(2).strip() or f"Seção sem título ({idx})"
            current = {
                "level": level,
                "title": title,
                "start_line": idx,
                "lines": [(idx, line)],
            }
        else:
            current.setdefault("lines", []).append((idx, line))
    if current["lines"]:
        current["end_line"] = len(lines)
        sections.append(current)

    if not sections:
        paragraphs = _split_paragraphs(lines_with_numbers=[(idx, line) for idx, line in enumerate(lines, start=1)])
        for para in paragraphs:
            text = para["text"].strip()
            if not text:
                continue
            tokens = tokenizer.num_tokens_from_string(text)
            words = len(text.split())
            yield ContentBlock(
                text=text,
                start_line=para["start_line"],
                end_line=para["end_line"],
                heading_path=("Documento",),
                tokens=tokens,
                words=words,
            )
        return

    heading_stack: List[tuple[int, str]] = []
    for section in sections:
        level = section["level"]
        title = section["title"]
        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()
        heading_stack.append((level, title))
        heading_path = tuple(item[1] for item in heading_stack)
        paragraphs = _split_paragraphs(section["lines"])
        for para in paragraphs:
            text = para["text"].strip()
            if not text:
                continue
            tokens = tokenizer.num_tokens_from_string(text)
            words = len(text.split())
            yield ContentBlock(
                text=text,
                start_line=para["start_line"],
                end_line=para["end_line"],
                heading_path=heading_path,
                tokens=tokens,
                words=words,
            )


def _split_paragraphs(lines_with_numbers: Sequence[tuple[int, str]]) -> List[dict[str, object]]:
    paragraphs: List[dict[str, object]] = []
    buffer: List[str] = []
    start_line = lines_with_numbers[0][0] if lines_with_numbers else 1
    current_start = start_line

    def flush(end_line: int) -> None:
        nonlocal buffer, current_start
        if not buffer:
            return
        text = "\n".join(buffer).strip()
        paragraphs.append({
            "text": text,
            "start_line": current_start,
            "end_line": end_line,
        })
        buffer = []

    last_line = start_line
    for line_number, text in lines_with_numbers:
        if not text.strip():
            flush(line_number - 1)
            current_start = line_number + 1
            last_line = line_number
            continue
        if not buffer:
            current_start = line_number
        buffer.append(text)
        last_line = line_number
    flush(last_line)
    return paragraphs


def _enforce_block_limits(
    blocks: Iterable[ContentBlock],
    chunk_max_tokens: int,
    tokenizer: TokenCount,
) -> Iterable[ContentBlock]:
    for block in blocks:
        if block.tokens <= chunk_max_tokens:
            yield block
            continue

        segments = _split_text_to_token_limit(block.text, chunk_max_tokens, tokenizer)
        for idx, segment in enumerate(segments, start=1):
            text = segment.strip()
            if not text:
                continue
            tokens = tokenizer.num_tokens_from_string(text)
            words = len(text.split())
            yield ContentBlock(
                text=text,
                start_line=block.start_line,
                end_line=block.end_line,
                heading_path=block.heading_path,
                tokens=tokens,
                words=words,
            )
            if idx == 1:
                logger.debug(
                    "Dividindo bloco grande (%s tokens) em %s segmentos",
                    block.tokens,
                    len(segments),
                )


def _split_text_to_token_limit(text: str, max_tokens: int, tokenizer: TokenCount) -> List[str]:
    sentences = _sentence_split_re.split(text)
    if not sentences or tokenizer.num_tokens_from_string(text) <= max_tokens:
        return [text]

    segments: List[str] = []
    buffer: List[str] = []
    buffer_tokens = 0
    for sentence in sentences:
        sentence_tokens = tokenizer.num_tokens_from_string(sentence)
        if sentence_tokens > max_tokens:
            words = sentence.split()
            step = max(1, math.ceil(len(words) / math.ceil(sentence_tokens / max_tokens)))
            for idx in range(0, len(words), step):
                slice_words = words[idx: idx + step]
                slice_text = " ".join(slice_words)
                segments.append(slice_text)
            continue
        if buffer_tokens + sentence_tokens > max_tokens and buffer:
            segments.append(" ".join(buffer))
            buffer = [sentence]
            buffer_tokens = sentence_tokens
        else:
            buffer.append(sentence)
            buffer_tokens += sentence_tokens
    if buffer:
        segments.append(" ".join(buffer))
    return segments or [text]


def _build_chunks_from_blocks(
    blocks: Sequence[ContentBlock],
    plan: ChunkPlan,
    tokenizer: TokenCount,
) -> List[MarkdownChunk]:
    chunks: List[MarkdownChunk] = []
    current_blocks: List[ContentBlock] = []
    current_tokens = 0
    chunk_index = 0

    for idx, block in enumerate(blocks):
        next_block_exists = idx < len(blocks) - 1
        if current_blocks and current_tokens + block.tokens > plan.chunk_max_tokens:
            chunk_index += 1
            chunks.append(
                _finalize_chunk(
                    plan,
                    chunk_index,
                    current_blocks,
                    tokenizer,
                )
            )
            current_blocks = []
            current_tokens = 0

        current_blocks.append(block)
        current_tokens += block.tokens

        if current_tokens >= plan.chunk_target_tokens and next_block_exists:
            chunk_index += 1
            chunks.append(
                _finalize_chunk(
                    plan,
                    chunk_index,
                    current_blocks,
                    tokenizer,
                )
            )
            current_blocks = []
            current_tokens = 0

    if current_blocks:
        chunk_index += 1
        chunks.append(
            _finalize_chunk(
                plan,
                chunk_index,
                current_blocks,
                tokenizer,
            )
        )

    order_fix(chunks, plan, tokenizer)
    return chunks


def _finalize_chunk(
    plan: ChunkPlan,
    chunk_index: int,
    blocks: Sequence[ContentBlock],
    tokenizer: TokenCount,
) -> MarkdownChunk:
    total_chunks_placeholder = chunk_index  # updated later
    chunk_id = f"chunk_{chunk_index:02d}"

    headings = []
    for block in blocks:
        for heading in block.heading_path:
            if heading not in headings:
                headings.append(heading)

    body_parts: List[str] = []
    body_parts.extend(block.text.strip() for block in blocks if block.text.strip())
    body_text = "\n\n".join(body_parts).strip()

    start_line = min(block.start_line for block in blocks)
    end_line = max(block.end_line for block in blocks)

    wrapped_text = wrap_chunk_text(
        chunk_id=chunk_id,
        chunk_index=chunk_index,
        total_chunks=total_chunks_placeholder,
        body_text=body_text,
    )

    tokens = tokenizer.num_tokens_from_string(body_text)
    words = len(body_text.split())

    chunk = MarkdownChunk(
        document=plan.document,
        chunk_id=chunk_id,
        index=chunk_index,
        text=wrapped_text,
        token_count=tokens,
        word_count=words,
        start_line=start_line,
        end_line=end_line,
        headings=headings,
        block_count=len(blocks),
        overlap_from_previous_tokens=0,
    )

    return chunk


def order_fix(chunks: List[MarkdownChunk], plan: ChunkPlan, tokenizer: TokenCount) -> None:
    total = len(chunks)
    if total == 0:
        return

    for chunk in chunks:
        body = _strip_chunk_wrapping(chunk.text)
        chunk.text = wrap_chunk_text(
            chunk_id=chunk.chunk_id,
            chunk_index=chunk.index,
            total_chunks=total,
            body_text=body,
        )
        chunk.token_count = tokenizer.num_tokens_from_string(body)
        chunk.word_count = len(body.split())

    for idx, chunk in enumerate(chunks):
        if idx == len(chunks) - 1 or plan.chunk_overlap_tokens <= 0:
            continue
        overlap_source = chunk.text
        overlap_text = _extract_overlap_text(overlap_source, plan.chunk_overlap_tokens, tokenizer)
        next_chunk = chunks[idx + 1]
        if overlap_text:
            body = _strip_chunk_wrapping(next_chunk.text)
            combined = f"<!-- overlap-from-previous chunk={chunk.chunk_id} -->\n{overlap_text}\n\n{body}".strip()
            next_chunk.text = wrap_chunk_text(
                chunk_id=next_chunk.chunk_id,
                chunk_index=next_chunk.index,
                total_chunks=total,
                body_text=combined,
            )
            next_chunk.token_count = tokenizer.num_tokens_from_string(combined)
            next_chunk.word_count = len(combined.split())
            next_chunk.overlap_from_previous_tokens = min(
                plan.chunk_overlap_tokens,
                next_chunk.token_count,
            )


def wrap_chunk_text(*, chunk_id: str, chunk_index: int, total_chunks: int, body_text: str) -> str:
    return (
        f"<!-- {chunk_id} start ({chunk_index}/{total_chunks}) -->\n"
        f"{body_text}\n"
        f"\n<!-- {chunk_id} end ({chunk_index}/{total_chunks}) -->"
    ).strip() + "\n"


def _strip_chunk_wrapping(text: str) -> str:
    lines = text.splitlines()
    if len(lines) >= 2 and lines[0].startswith("<!-- ") and lines[-1].startswith("<!-- "):
        return "\n".join(lines[1:-1]).strip()
    return text.strip()


def _extract_overlap_text(text: str, desired_tokens: int, tokenizer: TokenCount) -> str:
    if desired_tokens <= 0:
        return ""
    body = _strip_chunk_wrapping(text)
    words = body.split()
    if not words:
        return ""
    count = min(len(words), desired_tokens)
    overlap_words = words[-count:]
    return " ".join(overlap_words)


def save_chunk_plan(plan: ChunkPlan, *, settings, parts: int) -> None:
    plan_path = settings.chunk_plan_json_path(plan.document)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan.to_dict(parts=parts), ensure_ascii=False, indent=2), encoding="utf-8")

    map_path = settings.chunk_map_markdown_path(plan.document)
    map_path.parent.mkdir(parents=True, exist_ok=True)
    map_path.write_text(render_chunk_map(plan), encoding="utf-8")


def render_chunk_map(plan: ChunkPlan) -> str:
    lines = [
        f"# Mapa de chunks para {plan.document.name}",
        "",
        f"- Modo aplicado: **{plan.applied_mode}**",
        f"- Motivo: {plan.reason}",
        f"- Chunks gerados: **{len(plan.chunks)}**",
        "",
        "| Chunk | Tokens | Palavras | Linhas | Seções |",
        "| ----- | ------ | -------- | ------ | ------ |",
    ]
    for chunk in plan.chunks:
        heading_preview = ", ".join(chunk.headings[:3])
        lines.append(
            f"| {chunk.chunk_id} | {chunk.token_count} | {chunk.word_count} | {chunk.start_line}-{chunk.end_line} | {heading_preview} |")
    lines.append("")
    return "\n".join(lines)