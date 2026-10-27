"""Markdown reader: headings, list items and paragraphs from the markdown-it token stream."""

from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token

from autoflashcards.models import Block


def _plain_text(inline: Token) -> str:
    """Inline token as plain text: drops emphasis markers, keeps link text and code."""
    parts = []
    for child in inline.children or []:
        if child.type in ("text", "code_inline"):
            parts.append(child.content)
        elif child.type in ("softbreak", "hardbreak"):
            parts.append(" ")
    return "".join(parts).strip()


def read_markdown(path: Path) -> list[Block]:
    tokens = MarkdownIt().parse(path.read_text(encoding="utf-8"))
    blocks: list[Block] = []
    headings: list[tuple[int, str]] = []  # (level, text) of the headings above
    list_depth = 0
    heading_level = 0

    for i, token in enumerate(tokens):
        if token.type in ("bullet_list_open", "ordered_list_open"):
            list_depth += 1
        elif token.type in ("bullet_list_close", "ordered_list_close"):
            list_depth -= 1
        elif token.type == "heading_open":
            heading_level = int(token.tag[1])
        elif token.type == "inline":
            text = _plain_text(token)
            if not text:
                continue
            parent = tokens[i - 1].type
            if parent == "heading_open":
                headings = [h for h in headings if h[0] < heading_level]
                blocks.append(Block("heading", text, path.name, tuple(h for _, h in headings)))
                headings.append((heading_level, text))
            elif parent == "paragraph_open":
                kind = "bullet" if list_depth else "paragraph"
                blocks.append(Block(kind, text, path.name, tuple(h for _, h in headings)))
    return blocks
