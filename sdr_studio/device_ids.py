"""Qt-safe SDR device IDs.

Airspy exposes unsigned 64-bit serial numbers; Qt/PySide6 converts Python
integers in QVariant through signed 64-bit and raises OverflowError for
numbers >= 2**63. Store identifiers as decimal *strings* in QComboBox data,
then turn them back into Python integers before opening the radio. This avoids
both signed overflow and floating-point precision loss.
"""
from __future__ import annotations

UINT64_MAX = (1 << 64) - 1


def encode_device_id(value: int | None) -> str | None:
    """Serialize a device identifier to Qt-safe QVariant text."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("Device-ID mag geen boolean zijn")
    number = int(value)
    if not 0 <= number <= UINT64_MAX:
        raise ValueError("Device-ID buiten unsigned 64-bit bereik")
    return str(number)


def decode_device_id(value: str | int | None) -> int | None:
    """Deserialize QComboBox.currentData() to an exact unsigned int."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("Device-ID mag geen boolean zijn")
    if isinstance(value, str) and (not value or not value.isascii() or not value.isdecimal()):
        raise ValueError("Device-ID is geen geldig decimaal serienummer")
    if not isinstance(value, (str, int)):
        raise TypeError("Device-ID moet tekst, integer of None zijn")
    number = int(value)
    if not 0 <= number <= UINT64_MAX:
        raise ValueError("Device-ID buiten unsigned 64-bit bereik")
    return number
