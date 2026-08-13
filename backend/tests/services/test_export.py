import pytest
from app.services.export import safe_filename

def test_safe_filename_valid():
    assert safe_filename("My Awesome Video") == "My Awesome Video"
    assert safe_filename("File_name-123") == "File_name-123"

def test_safe_filename_invalid_chars():
    assert safe_filename("File<name>:/?*|\"\\") == "Filename"
    assert safe_filename("test\x00file") == "testfile"
    assert safe_filename("a\x1fb") == "ab"

def test_safe_filename_strip_spaces_dots():
    assert safe_filename("  Hello World  ") == "Hello World"
    assert safe_filename("..Hello World..") == "Hello World"
    assert safe_filename(" . Hello World . ") == "Hello World"

def test_safe_filename_collapse_spaces():
    assert safe_filename("Hello   World") == "Hello World"
    assert safe_filename("One    Two  Three") == "One Two Three"

def test_safe_filename_truncate_length():
    long_name = "a" * 150
    assert safe_filename(long_name) == "a" * 120

def test_safe_filename_fallback_empty():
    assert safe_filename("") == "part"
    assert safe_filename("   ") == "part"
    assert safe_filename("...") == "part"

def test_safe_filename_fallback_custom():
    assert safe_filename("", fallback="default") == "default"
    assert safe_filename("   ", fallback="my_fallback") == "my_fallback"

def test_safe_filename_all_invalid():
    assert safe_filename("<>:\"/\\|?*") == "part"
    assert safe_filename("<>:\"/\\|?*", fallback="custom") == "custom"
