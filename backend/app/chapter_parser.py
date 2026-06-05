from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

ErrorCode = Literal["INVALID_INPUT", "INVALID_CHAPTER_COUNT"]

MAX_HEADING_LENGTH = 80

CHINESE_NUMBER_PATTERN = r"\d+|[零〇一二两三四五六七八九十百千万]+"
MARKDOWN_HEADING_PATTERN = re.compile(r"^#{1,6}\s+")
CHINESE_HEADING_PATTERN = re.compile(
    rf"^第\s*(?:{CHINESE_NUMBER_PATTERN})\s*[章节回话]\s*.*$",
)
ENGLISH_HEADING_PATTERN = re.compile(
    r"^chapter\s+\d+\b(?:\s*[:：.\-]\s*\S.*|\s+\S.*)?$",
    re.IGNORECASE,
)
NUMBERED_HEADING_PATTERN = re.compile(r"^\d+\s*[.．、]\s*\S.*$")


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


@dataclass(frozen=True)
class _ChapterHeading:
    start: int
    end: int
    title: str


def _extract_heading_title(line: str) -> str | None:
    candidate = line.strip()

    if not candidate:
        return None

    candidate = MARKDOWN_HEADING_PATTERN.sub("", candidate, count=1).strip()

    if not candidate or len(candidate) > MAX_HEADING_LENGTH:
        return None

    if CHINESE_HEADING_PATTERN.fullmatch(candidate):
        return " ".join(candidate.split())

    if ENGLISH_HEADING_PATTERN.fullmatch(candidate):
        return " ".join(candidate.split())

    if NUMBERED_HEADING_PATTERN.fullmatch(candidate):
        return " ".join(candidate.split())

    return None


def _find_chapter_headings(text: str) -> list[_ChapterHeading]:
    headings: list[_ChapterHeading] = []
    offset = 0

    for line in text.splitlines(keepends=True):
        title = _extract_heading_title(line.rstrip("\r\n"))

        if title is not None:
            headings.append(_ChapterHeading(start=offset, end=offset + len(line), title=title))

        offset += len(line)

    return headings


def parse_novel_chapters(text: str, min_chapters: int = 3) -> list[Chapter]:
    if not text.strip():
        raise ChapterParseError("INVALID_INPUT", "小说文本不能为空。")

    headings = _find_chapter_headings(text)

    if not headings:
        raise ChapterParseError("INVALID_INPUT", "未识别到章节标题。")

    chapters: list[Chapter] = []

    for position, heading in enumerate(headings):
        content_start = heading.end
        content_end = headings[position + 1].start if position + 1 < len(headings) else len(text)
        chapter_content = text[content_start:content_end].strip()

        if not chapter_content:
            raise ChapterParseError("INVALID_INPUT", f"章节“{heading.title}”正文不能为空。")

        chapters.append(
            Chapter(
                index=position + 1,
                title=heading.title,
                content=chapter_content,
            )
        )

    if len(chapters) < min_chapters:
        raise ChapterParseError(
            "INVALID_CHAPTER_COUNT",
            f"小说章节数量不能少于 {min_chapters} 章。",
        )

    return chapters
