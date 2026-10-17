"""High-level protocol for the Niimbot B1 printer.

The print sequence follows niimbluelib's ``B1PrintTask``
(https://github.com/MultiMote/niimbluelib), which is known to work with the
current B1 firmware. The older sequence used by some other clients (e.g.
``niimprint``) ends the job too early and produces blank labels on this printer.
"""

import logging
import struct
import time

from PIL import Image, ImageOps

from .protocol import LABEL_TYPES, PRINTHEAD_PX, packet
from .transports import SerialTransport

log = logging.getLogger(__name__)


class B1Printer:
    """A Niimbot B1 printer connection.

    ``B1Printer()`` connects over USB and auto-detects the port. Pass
    ``port="..."`` to select a specific USB port, or pass ``transport=`` to use
    a different transport (for example ``BleTransport()``).
    """

    def __init__(self, port: str | None = None, transport=None):
        self._transport = transport or SerialTransport(port)
        self._buf = bytearray()

    def close(self):
        self._transport.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # --- low level ---

    def _send(self, cmd: int, data: bytes = b"\x01"):
        pkt = packet(cmd, data)
        log.debug("send %s", pkt.hex(":"))
        self._transport.write(pkt)

    def _read_packets(self):
        self._buf.extend(self._transport.read())
        packets = []
        while True:
            start = self._buf.find(b"\x55\x55")
            if start < 0:
                del self._buf[:-1]  # keep a possible first 0x55 of the header
                break
            del self._buf[:start]
            if len(self._buf) < 4 or len(self._buf) < self._buf[3] + 7:
                break
            n = self._buf[3] + 7
            raw = bytes(self._buf[:n])
            del self._buf[:n]
            log.debug("recv %s", raw.hex(":"))
            packets.append((raw[2], raw[4 : 4 + raw[3]]))
        return packets

    def _request(self, cmd: int, data: bytes = b"\x01", resp: int | None = None, timeout: float = 2.0) -> bytes:
        resp = cmd + 1 if resp is None else resp
        self._send(cmd, data)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for code, payload in self._read_packets():
                if code == resp:
                    return payload
                if code == 0xDB:
                    raise RuntimeError(f"printer error for cmd {cmd:#04x}: {payload.hex()}")
        raise TimeoutError(f"no response {resp:#04x} for cmd {cmd:#04x}")

    # --- info ---

    def heartbeat(self) -> dict:
        d = self._request(0xDC, resp=0xDD)
        # 13-byte variant on B1
        return {"cover_closed": d[9] == 0, "battery": d[10], "paper_ok": d[11] == 0, "rfid_ok": d[12] == 1}

    def rfid_info(self) -> dict | None:
        """Read the RFID tag of the inserted label roll; ``None`` if no tag."""
        d = self._request(0x1A, resp=0x1B)
        if len(d) == 1:
            return None
        pos = 8
        uuid = d[:pos].hex()
        strings = []
        for _ in range(2):  # barcode, serial number (length-prefixed)
            n = d[pos]
            strings.append(d[pos + 1 : pos + 1 + n].decode())
            pos += 1 + n
        total, used, label_type = struct.unpack(">HHB", d[pos : pos + 5])
        pos += 5
        info = {
            "uuid": uuid,
            "barcode": strings[0],
            "serial": strings[1],
            "total": total,
            "used": used,
            "label_type": LABEL_TYPES.get(label_type, label_type),
        }
        if len(d) >= pos + 2:
            info["capacity"] = struct.unpack(">H", d[pos : pos + 2])[0]
            pos += 2
        if len(d) >= pos + 8:
            info["uuid2"] = d[pos : pos + 8].hex()
        return info

    def calibrate(self, label_type: int = 1) -> bool:
        """Label positioning calibration (0x8E): store label type and measure label pitch.

        Feeds ~15 cm of paper and works without an RFID tag. Supported types:
        1 gap, 2 black mark, 5 transparent. Refused while the cover is open,
        paper is out, or a job is running.
        """
        return self._request(0x8E, bytes((label_type,)), resp=0x8F, timeout=20)[0] == 1

    def align(self, label_type: int = 1):
        """Feed to the next label gap by printing a blank page.

        On stock firmware, without an RFID tag the printer does not seek the gap
        when the cover is closed, so the first print lands across two labels.
        Gap seeking after a print works, so one blank page fixes the position.
        Wastes one label; call once after closing the cover. (The patched
        firmware in this repo fixes this automatically, so ``align()`` is only
        needed on stock firmware.)
        """
        self.print_image(Image.new("1", (PRINTHEAD_PX, 8), 1), density=1, label_type=label_type)

    def print_status(self) -> dict:
        d = self._request(0xA3, resp=0xB3)
        page, print_progress, feed_progress = struct.unpack(">HBB", d[:4])
        return {"page": page, "print_progress": print_progress, "feed_progress": feed_progress}

    # --- printing ---

    @staticmethod
    def _row_packets(img: Image.Image):
        bw = ImageOps.invert(img.convert("L")).convert("1")  # 1 = black dot
        width_bytes = (bw.width + 7) // 8
        raw = bw.tobytes()  # rows packed MSB-first, padded to whole bytes
        chunk = PRINTHEAD_PX // 8 // 3
        for y in range(bw.height):
            row = raw[y * width_bytes : (y + 1) * width_bytes]
            if not any(row):
                yield 0x84, struct.pack(">HB", y, 1)  # empty row
                continue
            counts = [0, 0, 0]
            for i, b in enumerate(row):
                counts[min(i // chunk, 2)] += b.bit_count()
            yield 0x85, struct.pack(">H3BB", y, *counts, 1) + row

    def print_image(self, img: Image.Image, density: int = 5, copies: int = 1, label_type: int = 1):
        """Print a PIL image.

        ``density`` is 1 (lightest) to 5 (darkest). ``label_type`` matches
        ``LABEL_TYPES``: 1 gap, 2 black mark, 3 continuous, 5 transparent.
        The image is printed as-is (width = across the head); it is not rotated.
        """
        if img.width > PRINTHEAD_PX:
            raise ValueError(f"image width {img.width} > {PRINTHEAD_PX}px")

        self._request(0x21, bytes((density,)), resp=0x31)
        self._request(0x23, bytes((label_type,)), resp=0x33)
        # printStart7b: total pages, 4x zero, page color (0 = single color)
        self._request(0x01, struct.pack(">H5B", copies, 0, 0, 0, 0, 0))
        self._request(0x03)  # page start
        # setPageSize6b: rows, cols, copies
        self._request(0x13, struct.pack(">HHH", img.height, img.width, copies))
        for cmd, data in self._row_packets(img):
            self._send(cmd, data)
        self._request(0xE3, timeout=10)  # page end

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            status = self.print_status()
            log.debug("status %s", status)
            if status["page"] >= copies:
                break
            time.sleep(0.3)
        else:
            raise TimeoutError("print did not finish")

        self._request(0xF3)  # print end
