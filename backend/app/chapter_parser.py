from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

ErrorCode = Literal["INVALID_INPUT", "INVALID_CHAPTER_COUNT"]

CHAPTER_HEADING_PATTERN = re.compile(
    r"^\s*(第\s*(?:\d+|[零〇一二两三四五六七八九十百千万]+)\s*章[^\r\n]*)\s*$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class Chapter:
    index: int
    title: str
    content: str


class ChapterParseError(ValueError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def parse_novel_chapters(text: str, min_chapters: int = 3) -> list[Chapter]:
    if not text.strip():
        raise ChapterParseError("INVALID_INPUT", "小说文本不能为空。")

    headings = list(CHAPTER_HEADING_PATTERN.finditer(text))

    if not headings:
        raise ChapterParseError("INVALID_INPUT", "未识别到章节标题。")

    chapters: list[Chapter] = []

    for position, heading in enumerate(headings):
        content_start = heading.end()
        content_end = headings[position + 1].start() if position + 1 < len(headings) else len(text)
        chapter_content = text[content_start:content_end].strip()
        chapter_title = " ".join(heading.group(1).split())

        if not chapter_content:
            raise ChapterParseError("INVALID_INPUT", f"章节“{chapter_title}”正文不能为空。")

        chapters.append(
            Chapter(
                index=position + 1,
                title=chapter_title,
                content=chapter_content,
            )
        )

    if len(chapters) < min_chapters:
        raise ChapterParseError(
            "INVALID_CHAPTER_COUNT",
            f"小说章节数量不能少于 {min_chapters} 章。",
        )

    return chapters
