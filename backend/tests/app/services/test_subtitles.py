import pytest
from pathlib import Path
from backend.app.services.subtitles import has_subtitle_lines, _wrap, _sanitize, build_ass, _ass_time

def test_has_subtitle_lines():
    assert has_subtitle_lines([{"text": "hello"}]) is True
    assert has_subtitle_lines([{"text": "   "}]) is False
    assert has_subtitle_lines([{"text": ""}]) is False
    assert has_subtitle_lines([{"start": 1.0}]) is False
    assert has_subtitle_lines([{"text": ""}, {"text": "world"}]) is True

def test_wrap():
    # max width is 38
    short_text = "Hello world"
    assert _wrap(short_text) == short_text

    long_text = "This is a very long text that should definitely be wrapped into multiple lines because it exceeds the maximum characters per line."
    wrapped = _wrap(long_text)
    assert "\\N" in wrapped
    assert len(wrapped.split("\\N")) <= 2

def test_sanitize():
    assert _sanitize("Hello\nWorld") == "Hello World"
    assert _sanitize("{Hello}") == "(Hello)"
    assert _sanitize("  test  ") == "test"
    assert _sanitize("{Hello}\nWorld") == "(Hello) World"

def test_ass_time():
    assert _ass_time(0.0) == "0:00:00.00"
    assert _ass_time(1.5) == "0:00:01.50"
    assert _ass_time(61.5) == "0:01:01.50"
    assert _ass_time(3661.5) == "1:01:01.50"
    assert _ass_time(-5.0) == "0:00:00.00"

def test_build_ass(tmp_path):
    dst = tmp_path / "test.ass"
    segments = [
        {"start": 0.0, "end": 2.0, "text": "Hello"},
        {"start": 2.0, "end": 4.0, "text": "World"}
    ]

    result = build_ass(segments, 1920, 1080, dst)
    assert result == dst
    assert dst.exists()

    content = dst.read_text(encoding="utf-8")
    assert "[Script Info]" in content
    assert "PlayResX: 1920" in content
    assert "PlayResY: 1080" in content
    assert "Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,Hello" in content
    assert "Dialogue: 0,0:00:02.00,0:00:04.00,Default,,0,0,0,,World" in content

def test_build_ass_empty(tmp_path):
    dst = tmp_path / "empty.ass"
    result = build_ass([], 1920, 1080, dst)
    assert result is None
    assert not dst.exists()

def test_build_ass_lone_word(tmp_path):
    dst = tmp_path / "lone.ass"
    segments = [{"start": 1.0, "end": 1.0, "text": "Wait"}]
    result = build_ass(segments, 1920, 1080, dst)
    assert result == dst
    content = dst.read_text(encoding="utf-8")
    # end should be start + 1.2
    assert "Dialogue: 0,0:00:01.00,0:00:02.20,Default,,0,0,0,,Wait" in content

def test_build_ass_whitespace_only(tmp_path):
    dst = tmp_path / "whitespace.ass"
    segments = [{"start": 0.0, "end": 1.0, "text": "   "}]
    result = build_ass(segments, 1920, 1080, dst)
    assert result is None
    assert not dst.exists()
