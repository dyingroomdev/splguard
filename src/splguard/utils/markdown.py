from __future__ import annotations

import re
from typing import Iterable

_ESCAPE_RE = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")
_URL_ESCAPE_RE = re.compile(r"([)\\])")


def escape_md(text: str) -> str:
    """Escape text for safe MarkdownV2 rendering."""
    if not text:
        return ""
    return _ESCAPE_RE.sub(r"\\\1", text)


def bold(text: str) -> str:
    return f"*{escape_md(text)}*"


def italic(text: str) -> str:
    return f"_{escape_md(text)}_"


def link(label: str, url: str) -> str:
    escaped_url = _URL_ESCAPE_RE.sub(r"\\\1", url)
    return f"[{escape_md(label)}]({escaped_url})"


def inline_code(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("`", "\\`")
    return f"`{escaped}`"


def join_lines(lines: Iterable[str | None]) -> str:
    return "\n".join("" if line is None else line for line in lines)
