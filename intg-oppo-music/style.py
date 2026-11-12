"""Font size and colour of a sensor value on the remote."""

import html
import re

_COLOR_RE = re.compile(r"^(#[0-9a-fA-F]{3,8}|[a-zA-Z]{3,30})$")


def style_value(value: str, font_size: int = 0, color: str = "") -> str:
    """Wrap a sensor value in the HTML the remote's text widget renders.

    The remote shows sensor values in a large font (36 px). Its Qt text widget renders simple
    HTML: <font size='N'> scales the text (1 = 70 %, 2 = 80 %, 3 = 100 %...) and color='...'
    sets its colour. Without a style, or for an empty value, the value is returned as is.
    """
    attrs = []
    if 1 <= (font_size or 0) <= 7:
        attrs.append(f"size='{font_size}'")
    if color and _COLOR_RE.match(color):
        attrs.append(f"color='{color}'")
    if not attrs or not value:
        return value
    return f"<font {' '.join(attrs)}>{html.escape(value, quote=False)}</font>"
