# Protocol notes (USB & Bluetooth LE)

The Niimbot B1 speaks the same protocol on both transports. Everything below
was observed on hardware **6.01** / firmware **6.19**.

## Framing

Every packet is wrapped as:

```
55 55 <cmd> <len> <payload...> <checksum> aa aa
```

where `<checksum>` is the XOR of `<cmd>`, `<len>`, and every payload byte.
Requests get a response packet whose command is `cmd + 1`; an error is reported
as a `0xDB` packet.

USB runs at **115200 baud**. The macOS port is `/dev/cu.usbmodemB1_<serial>`,
Linux uses `/dev/ttyACM*`.

Bluetooth LE uses service `e7810a71-73ae-499d-8c15-faa9aef0c3f2` with a single
characteristic that supports `notify` + `write-without-response`; the printer
advertises as `B1-<serial>`. See [`bluetooth.md`](bluetooth.md).

## Print sequence

The working sequence (from niimbluelib's `B1PrintTask`) is:

| Command | Payload | Purpose |
|---|---|---|
| `0x21` | `density` (1 B) | set print density 1–5 |
| `0x23` | `label_type` (1 B) | set label type (see below) |
| `0x01` | 7 B | print start: total pages (u16 BE), 4× zero, page color (0 = single) |
| `0x03` | — | page start |
| `0x13` | 6 B | page size: rows (u16), cols (u16), copies (u16) |
| `0x84` | row index (u16), `0x01` | empty row |
| `0x85` | row index (u16), 3× black-pixel counts, row bytes | non-empty row |
| `0xE3` | — | page end |
| `0xA3` → `0xB3` | — | poll print status until done |
| `0xF3` | — | print end |

The `0x85` row payload carries the row number, the number of black pixels in
each of the three 16-byte slices of the 48-byte row (packed as three bytes),
then the row bitmap (48 bytes, MSB-first, `1` = black dot).

The older sequence used by some clients (for example `niimprint`) sends a
different page-start sequence and finishes too early, so it prints **blank
labels** on this firmware. If you see blank output from another client, this is
why.

## Status / info commands

| Command | Response | Purpose |
|---|---|---|
| `0xDC` | `0xDD` | heartbeat: cover closed, battery, paper present, RFID present |
| `0x1A` | `0x1B` | RFID tag info (or a 1-byte "no tag" response) |
| `0x8E` | `0x8F` | label calibration (measure pitch / sensor) |
| `0xA3` | `0xB3` | print progress |

### RFID response (`0x1B`)

The B1 adds two extra fields compared to other models:

```
uuid (8 B)
barcode (length-prefixed string)
serial  (length-prefixed string)
total (u16 BE)
used  (u16 BE)
label_type (1 B)
capacity (u16 BE)     # B1 only
uuid2 (8 B)           # B1 only
```

`used` increments with every printed label and is stored on the tag, so it
survives opening the cover.

## Firmware / hardware version

`get_info(SOFTVERSION)` returns two bytes `major, minor`; `0x06 0x13` is
firmware **6.19**, hardware **6.01**. (Some clients decode these bytes as
decimal digits, wrongly reporting e.g. "15.55".)

## Label types

`0x23` accepts:

| Value | Meaning |
|---|---|
| 1 | labels with gaps (the common die-cut rolls) |
| 2 | black-mark labels |
| 3 | continuous thermal paper (no gaps) |
| 5 | transparent labels |
