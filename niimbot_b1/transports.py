"""Transport layer: USB serial and Bluetooth LE.

Both transports expose the same tiny interface (``write``, ``read``, ``close``)
so ``B1Printer`` does not care which one it is using.
"""

import logging
import threading
import time

log = logging.getLogger(__name__)


def find_port() -> str:
    """Return the first B1 USB serial port.

    macOS exposes the printer as ``/dev/cu.usbmodemB1_<serial>``; Linux uses
    ``/dev/ttyACM*``.
    """
    import glob

    ports = sorted(glob.glob("/dev/cu.usbmodemB1_*")) or sorted(glob.glob("/dev/ttyACM*"))
    if not ports:
        raise RuntimeError("B1 printer not found on USB (use --port or --ble)")
    return ports[0]


class SerialTransport:
    """USB serial transport (115200 baud)."""

    def __init__(self, port: str | None = None, timeout: float = 0.5):
        import serial

        port = port or find_port()
        self._serial = serial.Serial(port=port, baudrate=115200, timeout=timeout)

    def write(self, data: bytes):
        self._serial.write(data)

    def read(self) -> bytes:
        return self._serial.read(self._serial.in_waiting or 1)

    def close(self):
        self._serial.close()


class BleTransport:
    """Bluetooth LE via bleak, driven from a background asyncio loop.

    The printer exposes one characteristic with ``notify`` and
    ``write-without-response`` (service ``e7810a71-73ae-499d-8c15-faa9aef0c3f2``);
    packets are the same as over USB.
    """

    SERVICE = "e7810a71-73ae-499d-8c15-faa9aef0c3f2"
    PACKET_INTERVAL = 0.01  # niimbluelib default

    def __init__(self, address: str | None = None, name_prefix: str = "B1", timeout: float = 10.0):
        import asyncio

        self._asyncio = asyncio
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._rx = bytearray()
        self._rx_event = threading.Event()
        self._lock = threading.Lock()
        self._run(self._connect(address, name_prefix, timeout), timeout + 10)

    def _run(self, coro, timeout: float = 10.0):
        return self._asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    async def _connect(self, address, name_prefix, timeout):
        from bleak import BleakClient, BleakScanner

        if address:
            device = await BleakScanner.find_device_by_address(address, timeout=timeout)
        else:
            device = await BleakScanner.find_device_by_filter(
                lambda d, adv: bool(d.name and d.name.startswith(name_prefix))
                or self.SERVICE in (adv.service_uuids or []),
                timeout=timeout,
            )
        if device is None:
            raise RuntimeError("B1 printer not found over BLE (is it on and not connected elsewhere?)")
        log.debug("ble device %s %s", device.address, device.name)
        self._client = BleakClient(device)
        await self._client.connect()
        self._char = next(
            c
            for s in self._client.services
            for c in s.characteristics
            if "notify" in c.properties and "write-without-response" in c.properties
        )
        log.debug("ble characteristic %s", self._char.uuid)
        await self._client.start_notify(self._char, self._on_notify)

    def _on_notify(self, _char, data: bytearray):
        with self._lock:
            self._rx.extend(data)
        self._rx_event.set()

    def write(self, data: bytes):
        time.sleep(self.PACKET_INTERVAL)
        self._run(self._client.write_gatt_char(self._char, data, response=False))

    def read(self) -> bytes:
        self._rx_event.wait(0.05)
        with self._lock:
            data, self._rx = bytes(self._rx), bytearray()
            self._rx_event.clear()
        return data

    def close(self):
        try:
            self._run(self._client.disconnect())
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
