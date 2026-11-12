"""Sensor value style (font size and colour on the remote)."""

from style import style_value


def test_no_style_keeps_value() -> None:
    assert style_value("DSD 5.1") == "DSD 5.1"
    assert style_value("", 2, "#4da6ff") == ""


def test_size_and_colour() -> None:
    assert style_value("DSD 5.1", 2, "#4da6ff") == "<font size='2' color='#4da6ff'>DSD 5.1</font>"
    assert style_value("PCM 24/96", 1) == "<font size='1'>PCM 24/96</font>"


def test_bad_colour_ignored_and_text_escaped() -> None:
    assert style_value("A<B", 2, "x' onload='") == "<font size='2'>A&lt;B</font>"
