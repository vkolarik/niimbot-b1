"""Minimal client for the Niimbot B1 label printer over USB serial or Bluetooth LE.

The printer speaks the same protocol on both transports; packets are framed as
``55 55 <cmd> <len> <payload...> <checksum> aa aa``. This package provides a
small ``B1Printer`` object that wraps that protocol for the things most people
need: reading printer/RFID status and printing images.

Quick start::

    from niimbot_b1 import B1Printer

    with B1Printer() as p:  # auto-detects the USB port
        print(p.heartbeat())
        print(p.rfid_info())
        p.print_image(pil_image, density=5)
"""

from .printer import B1Printer
from .protocol import LABEL_TYPES, PRINTHEAD_PX
from .transports import BleTransport, SerialTransport, find_port

__version__ = "0.1.0"

__all__ = [
    "B1Printer",
    "BleTransport",
    "LABEL_TYPES",
    "PRINTHEAD_PX",
    "SerialTransport",
    "find_port",
]
