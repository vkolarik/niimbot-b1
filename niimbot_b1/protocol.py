"""Shared protocol constants and helpers for the Niimbot B1 printer."""

# Print head is 384 px wide = 48 mm at 203 dpi (8 px/mm).
PRINTHEAD_PX = 384

# Values accepted by the 0x23 "set label type" command.
LABEL_TYPES = {
    0: "invalid",
    1: "with_gaps",
    2: "black",
    3: "continuous",
    4: "perforated",
    5: "transparent",
    6: "pvc_tag",
    10: "black_mark_gap",
    11: "heat_shrink_tube",
}


def packet(cmd: int, data: bytes) -> bytes:
    """Wrap a command and payload into a Niimbot serial packet.

    Frame: ``55 55 <cmd> <len> <payload...> <checksum> aa aa`` where the
    checksum is ``cmd ^ len ^ data[0] ^ data[1] ^ ...``.
    """
    checksum = cmd ^ len(data)
    for b in data:
        checksum ^= b
    return b"\x55\x55" + bytes((cmd, len(data))) + data + bytes((checksum,)) + b"\xaa\xaa"
