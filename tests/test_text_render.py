# peripage-python - python library for peripage thermal printers
# Copyright (C) 2020-2023  bitrate16 (pegasko)

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from peripage.text_render import render_text, _wrap_line, _load_font


def test_render_text_returns_image_of_requested_width():
    img = render_text('hello world', width_px=384, font_size=20)
    assert img.size[0] == 384
    assert img.size[1] > 0


def test_render_text_empty_string_does_not_crash():
    img = render_text('', width_px=384, font_size=20)
    assert img.size[0] == 384
    assert img.size[1] > 0


def test_wrap_line_fits_within_width():
    font = _load_font(None, 20)
    text = 'the quick brown fox jumps over the lazy dog ' * 3
    lines = _wrap_line(text, font, max_width_px=300)

    for line in lines:
        assert int(font.getlength(line)) <= 300, f'line exceeded width: {line!r}'


def test_wrap_line_hard_breaks_unbreakable_word():
    font = _load_font(None, 20)
    word = 'x' * 200  # definitely wider than 100px at font size 20
    lines = _wrap_line(word, font, max_width_px=100)

    assert len(lines) > 1
    for line in lines:
        assert int(font.getlength(line)) <= 100
    assert ''.join(lines) == word


def test_render_text_preserves_explicit_newlines_as_paragraphs():
    # Two short paragraphs shouldn't get merged into one wrapped block -
    # rendering with an explicit newline should be taller than without one,
    # since a blank/empty second paragraph still consumes a line.
    img_one_line = render_text('short', width_px=384, font_size=20)
    img_two_lines = render_text('short\nshort', width_px=384, font_size=20)
    assert img_two_lines.size[1] > img_one_line.size[1]


def test_render_text_align_center_differs_from_left():
    # Rendering the same short text with different alignment should
    # produce different pixel content (text shifted horizontally).
    left_img = render_text('hi', width_px=384, font_size=32, align='left')
    center_img = render_text('hi', width_px=384, font_size=32, align='center')
    assert left_img.tobytes() != center_img.tobytes()


if __name__ == '__main__':
    tests = [v for k, v in list(globals().items()) if k.startswith('test_')]
    failed = 0
    for t in tests:
        try:
            t()
            print(f'PASS {t.__name__}')
        except Exception as e:
            failed += 1
            print(f'FAIL {t.__name__}: {e}')
    print(f'\n{len(tests) - failed}/{len(tests)} passed')
    sys.exit(1 if failed else 0)
