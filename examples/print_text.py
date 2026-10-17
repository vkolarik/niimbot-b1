"""Build a simple text label programmatically and print it on a Niimbot B1.

Shows the library API: make a 384x240 (50x30 mm) 1-bit image, then print it.
Works with any label type; pass ``-t``/``--ble`` the same way as print_image.py.

Usage:
    python examples/print_text.py "Hello" "World" -d 5
"""

import argparse

from PIL import Image, ImageDraw, ImageFont

from niimbot_b1 import B1Printer, BleTransport

W, H = 384, 240  # 50 x 30 mm at 203 dpi (8 px/mm)

# A few common font paths; falls back to Pillow's built-in bitmap font.
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def _load_font(size: int, bold: bool = True) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def make_label(lines: list[str], density_note: bool = True) -> Image.Image:
    img = Image.new("1", (W, H), 1)
    d = ImageDraw.Draw(img)
    d.rectangle([2, 2, W - 3, H - 3], outline=0, width=3)

    font = _load_font(44)
    small = _load_font(20, bold=False)

    total = sum(font.getbbox(t)[3] - font.getbbox(t)[1] for t in lines) + (len(lines) - 1) * 12
    y = (H - total) // 2
    for text in lines:
        box = font.getbbox(text)
        d.text(((W - (box[2] - box[0])) // 2, y), text, font=font, fill=0)
        y += (box[3] - box[1]) + 12

    if density_note:
        d.text((8, H - 24), "Niimbot B1", font=small, fill=0)
    return img


def main():
    ap = argparse.ArgumentParser(description="Print a text label on a Niimbot B1")
    ap.add_argument("lines", nargs="+", help="one or more lines of text")
    ap.add_argument("-d", "--density", type=int, default=5, help="1 (light) .. 5 (dark)")
    ap.add_argument("-t", "--label-type", type=int, default=1, help="1 gap, 2 black mark, 3 continuous, 5 transparent")
    ap.add_argument("--port", help="USB serial port (default: autodetect)")
    ap.add_argument("--ble", nargs="?", const="", metavar="ADDRESS", help="use Bluetooth LE")
    args = ap.parse_args()

    img = make_label(args.lines)
    transport = BleTransport(args.ble or None) if args.ble is not None else None
    with B1Printer(args.port, transport=transport) as p:
        p.print_image(img, density=args.density, label_type=args.label_type)
        print("printed", args.lines)


if __name__ == "__main__":
    main()
