# Bluetooth LE printing

The B1 can be driven entirely over Bluetooth LE; the protocol is identical to
USB (see [`protocol.md`](protocol.md)).

## Connection details

* Service UUID: `e7810a71-73ae-499d-8c15-faa9aef0c3f2`
* Characteristic: the single characteristic with `notify` **and**
  `write-without-response` properties.
* The printer advertises as `B1-<serial>`.

The client discovers the device by name prefix (`B1`) or by the service UUID,
connects, subscribes to notifications, and writes packets with
`write-without-response`. A small inter-packet delay (10 ms) keeps the writes
reliable.

## macOS permissions

On macOS the terminal/process must have **Bluetooth** permission
(*System Settings → Privacy & Security → Bluetooth*). Without it the process
aborts with exit code 134.

## Using the client over BLE

```sh
pip install -e .[ble]

python -m niimbot_b1 --ble                 # status + RFID
python -m niimbot_b1 label.png -d 5 --ble  # print (a few seconds, incl. connect)
```

A specific device address/UUID can be passed to `--ble`:

```sh
python -m niimbot_b1 label.png --ble "AA:BB:CC:DD:EE:FF"
```

Python API:

```python
from niimbot_b1 import B1Printer, BleTransport

with B1Printer(transport=BleTransport()) as p:
    p.print_image(img, density=5)
```

## Notes

* Only one connection at a time — close the phone app (or other clients)
  before connecting.
* Printing over BLE is slower than USB because of the per-packet delay.
