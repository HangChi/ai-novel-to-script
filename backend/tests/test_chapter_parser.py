import pytest

from app.chapter_parser import ChapterParseError, parse_novel_chapters


def test_parse_three_standard_chapters() -> None:
    text = """
第 1 章 初遇
林澈推门而入。

第 2 章 暗线
苏晚发现信件。

第 3 章 选择
两人在雨夜分别。
"""

    chapters = parse_novel_chapters(text)

    assert len(chapters) == 3
    assert chapters[0].index == 1
    assert chapters[0].title == "第 1 章 初遇"
    assert chapters[0].content == "林澈推门而入。"


def test_parse_chinese_number_chapter_titles() -> None:
    text = """
第一章 初遇
林澈推门而入。

第二章 暗线
苏晚发现信件。

第三章 选择
两人在雨夜分别。
"""

    chapters = parse_novel_chapters(text)

    assert [chapter.title for chapter in chapters] == ["第一章 初遇", "第二章 暗线", "第三章 选择"]


def test_parse_zero_padded_chapter_titles() -> None:
    text = """
第001章 初遇
林澈推门而入。

第002章 暗线
苏晚发现信件。

第003章 选择
两人在雨夜分别。
"""

    chapters = parse_novel_chapters(text)

    assert [chapter.title for chapter in chapters] == ["第001章 初遇", "第002章 暗线", "第003章 选择"]


def test_parse_markdown_chapter_titles() -> None:
    text = """
# 第一章 初遇
林澈推门而入。

## 第 2 章 暗线
苏晚发现信件。

### 第003章 选择
两人在雨夜分别。
"""

    chapters = parse_novel_chapters(text)

    assert [chapter.title for chapter in chapters] == ["第一章 初遇", "第 2 章 暗线", "第003章 选择"]


def test_parse_other_chinese_chapter_units() -> None:
    text = """
第1回 初遇
林澈推门而入。

第2节 暗线
苏晚发现信件。

第3话 选择
两人在雨夜分别。
"""

    chapters = parse_novel_chapters(text)

    assert [chapter.title for chapter in chapters] == ["第1回 初遇", "第2节 暗线", "第3话 选择"]


def test_parse_english_chapter_titles() -> None:
    text = """
Chapter 1
Lin walks into the room.

CHAPTER 2: The Clue
Su finds the letter.

Chapter 3 - The Choice
They part in the rain.
"""

    chapters = parse_novel_chapters(text)

    assert [chapter.title for chapter in chapters] == ["Chapter 1", "CHAPTER 2: The Clue", "Chapter 3 - The Choice"]


def test_parse_numbered_chapter_titles() -> None:
    text = """
1. 初遇
林澈推门而入。

2、暗线
苏晚发现信件。

3. 选择
两人在雨夜分别。
"""

    chapters = parse_novel_chapters(text)

    assert [chapter.title for chapter in chapters] == ["1. 初遇", "2、暗线", "3. 选择"]


def test_does_not_parse_inline_chapter_words_as_headings() -> None:
    text = """
第一章 初遇
林澈读到手稿里写着第 1 章，却没有停下。

第二章 暗线
苏晚发现信件。

第三章 选择
两人在雨夜分别。
"""

    chapters = parse_novel_chapters(text)

    assert len(chapters) == 3
    assert chapters[0].content == "林澈读到手稿里写着第 1 章，却没有停下。"


def test_rejects_long_line_that_looks_like_chapter_heading() -> None:
    long_heading_like_line = "第 1 章 " + "这不是标题而是一段过长的正文" * 8
    text = f"""
{long_heading_like_line}
林澈推门而入。

第 2 章 暗线
苏晚发现信件。

第 3 章 选择
两人在雨夜分别。
"""

    with pytest.raises(ChapterParseError) as error:
        parse_novel_chapters(text)

    assert error.value.code == "INVALID_CHAPTER_COUNT"


def test_rejects_fewer_than_three_chapters() -> None:
    text = """
第一章 初遇
林澈推门而入。

第二章 暗线
苏晚发现信件。
"""

    with pytest.raises(ChapterParseError) as error:
        parse_novel_chapters(text)

    assert error.value.code == "INVALID_CHAPTER_COUNT"


def test_rejects_empty_input() -> None:
    with pytest.raises(ChapterParseError) as error:
        parse_novel_chapters("  \n  ")

    assert error.value.code == "INVALID_INPUT"


def test_rejects_text_without_chapter_titles() -> None:
    with pytest.raises(ChapterParseError) as error:
        parse_novel_chapters("林澈推门而入，雨水顺着衣角滴落。")

    assert error.value.code == "INVALID_INPUT"


def test_rejects_chapter_without_body() -> None:
    text = """
第一章 初遇

第二章 暗线
苏晚发现信件。

第三章 选择
两人在雨夜分别。
"""

    with pytest.raises(ChapterParseError) as error:
        parse_novel_chapters(text)

    assert error.value.code == "INVALID_INPUT"
