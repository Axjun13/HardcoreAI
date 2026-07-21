"""USB VID:PID -> candidate board id lookup.

Two confidence tiers, because these boards fall into two very different
categories of USB identification:

  - GENUINE_VID_PID: Arduino's own USB VID (0x2341) with a PID assigned to
    one specific official board. High confidence — if this exact PID shows
    up, it *is* that board (or a 100%-compatible clone deliberately using
    the same descriptor).
  - BRIDGE_CHIP_VID_PID: third-party USB-serial bridge chips (CH340,
    CP210x, FTDI) used by countless different boards and clones across
    every vendor. Seeing one of these tells you almost nothing about which
    specific board is attached — it only narrows down "this is some
    serial-bootloader board", so it's kept low-confidence and maps to
    several plausible candidates rather than one.

Not exhaustive — extend as real hardware turns up unrecognized ids rather
than trying to enumerate every USB-serial chip in existence up front.
"""

# (vid, pid) -> (board_id, confidence, reason)
GENUINE_VID_PID: dict[tuple[str, str], tuple[str, float, str]] = {
    ("2341", "0043"): ("uno", 0.9, "Arduino Uno Rev3 (ATmega16U2 USB-serial) VID:PID"),
    ("2341", "0001"): ("uno", 0.85, "Arduino Uno (older ATmega8U2 USB-serial) VID:PID"),
    ("2341", "0042"): ("megaatmega2560", 0.9, "Arduino Mega 2560 VID:PID"),
    ("2341", "0036"): ("leonardo", 0.9, "Arduino Leonardo (bootloader mode) VID:PID"),
    ("2341", "8036"): ("leonardo", 0.9, "Arduino Leonardo (native USB CDC) VID:PID"),
    ("2341", "0037"): ("micro", 0.9, "Arduino Micro (bootloader mode) VID:PID"),
    ("2341", "8037"): ("micro", 0.9, "Arduino Micro (native USB CDC) VID:PID"),
    ("2341", "804f"): ("zeroUSB", 0.85, "Arduino Zero (native USB, programming port) VID:PID"),
    ("2341", "8057"): ("mkrwifi1010", 0.85, "Arduino MKR WiFi 1010 VID:PID"),
    ("2341", "804e"): ("mkrzero", 0.85, "Arduino MKR Zero VID:PID"),
}

# (vid, pid) -> [(board_id, confidence)], reason filled in by caller.
# Every entry here is a widely-reused bridge chip, hence multiple/low-confidence
# candidates and a shared explanatory reason.
BRIDGE_CHIP_VID_PID: dict[tuple[str, str], list[tuple[str, float]]] = {
    ("1a86", "7523"): [  # CH340 — the most common clone/dev-board bridge chip
        ("uno", 0.3), ("nanoatmega328", 0.3), ("esp32dev", 0.3), ("nodemcuv2", 0.3), ("d1_mini", 0.3),
    ],
    ("10c4", "ea60"): [  # CP2102/CP2104 — common on ESP32 dev boards
        ("esp32dev", 0.45), ("esp32-s3-devkitc-1", 0.3), ("nodemcuv2", 0.25),
    ],
    ("0403", "6001"): [  # FTDI FT232R — used by both genuine FT232R-based Uno
        # clones and Nanos. There's no reliable VID:PID-level signal that
        # separates them (confirmed against real hardware both ways) — tied
        # confidence is the honest answer, not a guess dressed up as one.
        # Don't re-weight this pair again without a signal stronger than
        # "which board a user happened to have" — that's not generalizable.
        ("nanoatmega328", 0.3), ("uno", 0.3),
    ],
    ("303a", "1001"): [  # Espressif's own native-USB descriptor (ESP32-S3/C3 with native USB)
        ("esp32-s3-devkitc-1", 0.45), ("esp32-c3-devkitm-1", 0.4),
    ],
}


def parse_hwid(hwid: str) -> tuple[str, str] | None:
    """Extract (vid, pid) lowercase hex strings from a pyserial/PlatformIO
    hwid string like 'USB VID:PID=1A86:7523 SER=... LOCATION=...'. Returns
    None if the string doesn't contain a VID:PID pair (e.g. non-USB ports)."""
    import re
    m = re.search(r"VID:PID=([0-9A-Fa-f]{4}):([0-9A-Fa-f]{4})", hwid or "")
    if not m:
        return None
    return m.group(1).lower(), m.group(2).lower()