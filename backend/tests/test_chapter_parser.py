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
