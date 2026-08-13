import pytest
from dataclasses import dataclass
import sys
import os

# Add backend directory to sys.path if not running pytest from there
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.viral import sentence_units, _Unit

@dataclass
class MockSegment:
    start: float
    end: float
    text: str | None = None

def test_sentence_units_empty_segments():
    assert sentence_units([]) == []

def test_sentence_units_empty_or_none_text():
    segments = [
        MockSegment(0.0, 1.0, ""),
        MockSegment(1.0, 2.0, "   "),
        MockSegment(2.0, 3.0, None),
    ]
    assert sentence_units(segments) == []

def test_sentence_units_single_sentence():
    segments = [
        MockSegment(0.0, 2.0, "This is a single sentence."),
    ]
    units = sentence_units(segments)
    assert len(units) == 1
    assert units[0] == _Unit(0.0, 2.0, "This is a single sentence.")

def test_sentence_units_multiple_sentences():
    # "Hello." (6) + "How are you!" (12) + "I am fine." (10) = 28
    segments = [
        MockSegment(0.0, 2.8, "Hello. How are you! I am fine."),
    ]
    units = sentence_units(segments)

    assert len(units) == 3

    assert units[0].text == "Hello."
    assert units[0].start == pytest.approx(0.0)
    assert units[0].end == pytest.approx(0.6)

    assert units[1].text == "How are you!"
    assert units[1].start == pytest.approx(0.6)
    assert units[1].end == pytest.approx(1.8)

    assert units[2].text == "I am fine."
    assert units[2].start == pytest.approx(1.8)
    assert units[2].end == pytest.approx(2.8)

def test_sentence_units_span_less_than_zero():
    segments = [
        MockSegment(2.0, 1.0, "Wait what. How did this happen."),
    ]
    units = sentence_units(segments)
    assert len(units) == 1
    assert units[0] == _Unit(2.0, 1.0, "Wait what. How did this happen.")

def test_sentence_units_span_zero():
    segments = [
        MockSegment(1.0, 1.0, "Zero span. Still processing."),
    ]
    units = sentence_units(segments)
    assert len(units) == 1
    assert units[0] == _Unit(1.0, 1.0, "Zero span. Still processing.")

def test_sentence_units_multiple_segments():
    segments = [
        MockSegment(0.0, 2.0, "First segment."),
        MockSegment(2.0, 4.0, "Second segment start. And end."),
    ]
    units = sentence_units(segments)
    assert len(units) == 3

    assert units[0] == _Unit(0.0, 2.0, "First segment.")

    assert units[1].text == "Second segment start."
    assert units[1].start == pytest.approx(2.0)
    assert units[1].end == pytest.approx(2.0 + (21/29) * 2.0)

    assert units[2].text == "And end."
    assert units[2].start == pytest.approx(2.0 + (21/29) * 2.0)
    assert units[2].end == pytest.approx(4.0)
