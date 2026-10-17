"""Print a label image file using the B1Printer API (USB by default).

Usage:
    python examples/print_image.py label.png            # gap labels (type 1)
    python examples/print_image.py receipt.png -t 3     # continuous paper
    python examples/print_image.py label.png --ble      # over Bluetooth LE
"""

import argparse

from PIL import Image

from niimbot_b1 import B1Printer, BleTransport


def main():
    ap = argparse.ArgumentParser(description="Print an image on a Niimbot B1")
    ap.add_argument("image")
    ap.add_argument("-d", "--density", type=int, default=5, help="1 (light) .. 5 (dark)")
    ap.add_argument("-n", "--copies", type=int, default=1)
    ap.add_argument("-t", "--label-type", type=int, default=1, help="1 gap, 2 black mark, 3 continuous, 5 transparent")
    ap.add_argument("--port", help="USB serial port (default: autodetect)")
    ap.add_argument("--ble", nargs="?", const="", metavar="ADDRESS", help="use Bluetooth LE")
    args = ap.parse_args()

    transport = BleTransport(args.ble or None) if args.ble is not None else None
    with B1Printer(args.port, transport=transport) as p:
        print("heartbeat:", p.heartbeat())
        print("rfid:", p.rfid_info())
        p.print_image(Image.open(args.image), density=args.density, copies=args.copies, label_type=args.label_type)
        print("printed", args.image)


if __name__ == "__main__":
    main()
