from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    index: int
    start: int
    end: int
    text: str


def split_lossless(text: str, max_chars: int) -> list[TextChunk]:
    if max_chars <= 0:
        raise ValueError("max_chars deve ser positivo")

    chunks: list[TextChunk] = []
    start = 0
    while start < len(text):
        hard_end = min(len(text), start + max_chars)
        end = hard_end
        if hard_end < len(text):
            candidates = (
                text.rfind("\n\n", start, hard_end - 1),
                text.rfind(". ", start, hard_end - 1),
                text.rfind(" ", start, hard_end),
            )
            split_at = max(candidates[:2])
            if split_at <= start:
                split_at = candidates[2]
            if split_at > start:
                end = split_at + (2 if text[split_at:split_at + 2] in {"\n\n", ". "} else 1)
        chunks.append(TextChunk(len(chunks), start, end, text[start:end]))
        start = end
    return chunks


def join_lossless(chunks: list[TextChunk]) -> str:
    return "".join(chunk.text for chunk in chunks)
