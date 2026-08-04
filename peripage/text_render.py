# peripage-python - python library for peripage thermal printers
# Copyright (C) 2020-2023  bitrate16 (pegasko)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
Renders text to a `PIL.Image` for printers with no onboard font (e.g. the
P21 and other BLE "cat printer"-style devices - see the module docstring
in `peripage/protocol.py`'s `Printer.printText()` for why this is
necessary at all). Ships with a bundled copy of DejaVu Sans Mono
(Bitstream Vera license, freely redistributable - see `fonts/LICENSE.txt`)
so text rendering looks consistent across platforms without depending on
whatever fonts happen to be installed on the user's OS.
"""

import os
import typing

import PIL.Image
import PIL.ImageDraw
import PIL.ImageFont

_BUNDLED_FONT_PATH = os.path.join(os.path.dirname(__file__), 'fonts', 'DejaVuSansMono.ttf')


def _load_font(font_path: typing.Optional[str], font_size: int) -> PIL.ImageFont.FreeTypeFont:
    path = font_path or _BUNDLED_FONT_PATH
    try:
        return PIL.ImageFont.truetype(path, font_size)
    except Exception as e:
        raise RuntimeError(
            f'Failed to load font {path!r} at size {font_size}: {e}. '
            f'Pass a valid font_path, or omit it to use the bundled DejaVu Sans Mono.'
        )


def _wrap_line(line: str, font: PIL.ImageFont.FreeTypeFont, max_width_px: int) -> typing.List[str]:
    """
    Word-wrap a single line (no embedded newlines) to fit `max_width_px`.
    Words longer than the available width on their own are hard-broken
    character by character, so nothing silently overflows the printer's
    dot width.
    """

    if not line:
        return ['']

    def text_width(s: str) -> int:
        # textlength is the modern, correct API; bbox-based fallback for
        # older Pillow.
        try:
            return int(font.getlength(s))
        except AttributeError:
            bbox = font.getbbox(s)
            return bbox[2] - bbox[0]

    words = line.split(' ')
    wrapped: typing.List[str] = []
    current = ''

    for word in words:
        candidate = word if not current else current + ' ' + word

        if text_width(candidate) <= max_width_px:
            current = candidate
            continue

        # candidate doesn't fit - flush what we have, then place `word`
        if current:
            wrapped.append(current)
            current = ''

        if text_width(word) <= max_width_px:
            current = word
            continue

        # the word itself is wider than the line - hard-break it
        chunk = ''
        for ch in word:
            if text_width(chunk + ch) <= max_width_px:
                chunk += ch
            else:
                if chunk:
                    wrapped.append(chunk)
                chunk = ch
        current = chunk

    if current:
        wrapped.append(current)

    return wrapped or ['']


def render_text(
    text: str,
    width_px: int,
    font_size: int = 32,
    font_path: typing.Optional[str] = None,
    align: str = 'left',
    line_spacing: int = 6,
    padding: int = 4,
) -> PIL.Image.Image:
    """
    Render `text` to a white-background/black-text image, word-wrapped to
    fit `width_px`. Explicit newlines in `text` are preserved as paragraph
    breaks; each resulting line is independently word-wrapped.

    Arguments:
    * `text` - the text to render. Unicode is fine (subject to what the
      font can render) - unlike raw ASCII passthrough, this path doesn't
      require filtering to ASCII-only.
    * `width_px` - target width in pixels. Pass `Printer.getRowWidth()` to
      match your printer's dot width exactly.
    * `font_size` - font size in points.
    * `font_path` - path to a `.ttf`/`.otf` font. Defaults to the bundled
      DejaVu Sans Mono if omitted.
    * `align` - `'left'`, `'center'`, or `'right'`.
    * `line_spacing` - extra pixels between lines, on top of the font's
      natural line height.
    * `padding` - blank pixels on all four sides.

    Returns a `PIL.Image` sized `(width_px, <computed height>)`, suitable
    for passing straight to `Printer.printImage()`.
    """

    if align not in ('left', 'center', 'right'):
        raise ValueError(f"align must be 'left', 'center', or 'right', got {align!r}")

    font = _load_font(font_path, font_size)
    usable_width = max(1, width_px - 2 * padding)

    lines: typing.List[str] = []
    for paragraph in text.split('\n'):
        lines.extend(_wrap_line(paragraph, font, usable_width))

    ascent, descent = font.getmetrics()
    line_height = ascent + descent + line_spacing

    height_px = max(1, 2 * padding + line_height * len(lines))
    img = PIL.Image.new('L', (width_px, height_px), color=255)
    draw = PIL.ImageDraw.Draw(img)

    y = padding
    for line in lines:
        line_width = int(font.getlength(line)) if line else 0

        if align == 'left':
            x = padding
        elif align == 'center':
            x = padding + (usable_width - line_width) // 2
        else:
            x = padding + (usable_width - line_width)

        draw.text((x, y), line, font=font, fill=0)
        y += line_height

    return img
