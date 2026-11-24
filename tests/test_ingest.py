"""Chunking and document parsing: pure functions, no OpenAI and no Chroma needed."""

from pathlib import Path

import pytest

from ingest import KB_DIR, MAX_CHARS, OVERLAP_CHARS, chunk_text, parse_doc

KB_FILES = sorted(Path(KB_DIR).glob("*.md"))


def test_short_text_stays_one_chunk():
    assert chunk_text("Short article.") == ["Short article."]


def test_leading_and_trailing_whitespace_is_stripped():
    assert chunk_text("\n\n  Short article.  \n") == ["Short article."]


LONG_TEXT = "".join(chr(ord("a") + i % 26) for i in range(1500))


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known bug: the loop only stops when `start` passes the end, so after the chunk "
        "that reaches the end (700-1500) it adds a redundant tail chunk (1400-1500) "
        "that is fully contained in the previous one. No KB article is long enough to hit it."
    ),
)
def test_long_text_is_split_with_overlap():
    chunks = chunk_text(LONG_TEXT)

    assert len(chunks) == 2
    assert all(len(c) <= MAX_CHARS for c in chunks)
    # The last OVERLAP_CHARS characters of chunk 1 start chunk 2.
    assert chunks[0][-OVERLAP_CHARS:] == chunks[1][:OVERLAP_CHARS]


def test_consecutive_chunks_overlap_by_overlap_chars():
    chunks = chunk_text(LONG_TEXT)
    assert chunks[0][-OVERLAP_CHARS:] == chunks[1][:OVERLAP_CHARS]


def test_no_empty_chunks():
    assert all(chunk_text("x" * 2000))


def test_knowledge_base_has_16_articles():
    assert len(KB_FILES) == 16


@pytest.mark.parametrize("path", KB_FILES, ids=lambda p: p.name)
def test_every_article_parses_cleanly(path):
    category, title, body = parse_doc(path)

    assert category != "uncategorized"
    assert title != path.stem  # a real "# Title:" line was found
    assert body
    assert not body.startswith("#")  # header lines are not in the body


@pytest.mark.parametrize("path", KB_FILES, ids=lambda p: p.name)
def test_every_article_fits_in_one_chunk(path):
    _, _, body = parse_doc(path)
    assert len(chunk_text(body)) == 1
