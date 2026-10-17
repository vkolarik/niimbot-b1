"""Command-line interface for the Niimbot B1 printer.

Examples::

    python -m niimbot_b1                      # printer status + RFID roll info
    python -m niimbot_b1 label.png -d 5       # print a label image (gap labels)
    python -m niimbot_b1 receipt.png -t 3     # continuous thermal paper
    python -m niimbot_b1 label.png --ble      # print over Bluetooth LE
"""

import argparse
import logging

from PIL import Image

from . import __version__
from .printer import B1Printer
from .transports import BleTransport


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="niimbot-b1", description="Niimbot B1 label printer client")
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("image", nargs="?", help="image to print; omit to only show printer/RFID info")
    ap.add_argument("-p", "--port", help="USB serial port (default: autodetect)")
    ap.add_argument("--ble", nargs="?", const="", metavar="ADDRESS", help="use Bluetooth LE (optionally a device address/UUID)")
    ap.add_argument("-d", "--density", type=int, default=5, help="1 (light) .. 5 (dark)")
    ap.add_argument("-n", "--copies", type=int, default=1)
    ap.add_argument("-t", "--label-type", type=int, default=1, help="1 gap, 2 black mark, 3 continuous, 5 transparent")
    ap.add_argument("--align", action="store_true", help="feed to next gap first (after cover close without tag, stock FW)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    transport = BleTransport(args.ble or None) if args.ble is not None else None
    with B1Printer(args.port, transport=transport) as p:
        log.info("heartbeat %s", p.heartbeat())
        log.info("rfid %s", p.rfid_info())
        if args.align:
            p.align(args.label_type)
            log.info("aligned")
        if args.image:
            p.print_image(Image.open(args.image), density=args.density, copies=args.copies, label_type=args.label_type)
            log.info("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
