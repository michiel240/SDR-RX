"""Exact, USB-independent frequency step definitions and tuning calculations."""
from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re


@dataclass(frozen=True)
class TuningStep:
    label: str
    step_hz: Fraction


TUNING_STEPS = (
    TuningStep('100 Hz', Fraction(100)),
    TuningStep('500 Hz', Fraction(500)),
    TuningStep('1 kHz', Fraction(1_000)),
    TuningStep('2.5 kHz', Fraction(2_500)),
    TuningStep('5 kHz', Fraction(5_000)),
    TuningStep('6.25 kHz', Fraction(6_250)),
    TuningStep('8.33 kHz', Fraction(25_000, 3)),
    TuningStep('10 kHz', Fraction(10_000)),
    TuningStep('12.5 kHz', Fraction(12_500)),
    TuningStep('25 kHz', Fraction(25_000)),
    TuningStep('100 kHz', Fraction(100_000)),
)
DEFAULT_STEP = '12.5 kHz'
_STEP_MAP = {step.label: step.step_hz for step in TUNING_STEPS}


def tuning_step_hz(label: str) -> Fraction:
    return _STEP_MAP[label]


def tuned_frequency_hz(anchor_hz: int, step_label: str, count: int) -> int:
    """Anchor-based stepping; no cumulative 8.33 kHz rounding drift.

    Rounds half a Hertz away from zero symmetrically. UI resolution is 1 Hz.
    """
    delta = tuning_step_hz(step_label) * int(count)
    absolute = abs(delta)
    whole = (2 * absolute.numerator + absolute.denominator) // (2 * absolute.denominator)
    return int(anchor_hz) + (whole if delta >= 0 else -whole)


def format_frequency_mhz(frequency_hz: int) -> str:
    """Render a receiver frequency as MHz with exactly 6 decimals (1 Hz)."""
    hz = int(frequency_hz)
    if hz < 0:
        raise ValueError('Frequency cannot be negative')
    mhz, remainder = divmod(hz, 1_000_000)
    return f'{mhz}.{remainder:06d}'


def parse_frequency_mhz(text: str, minimum_hz: int, maximum_hz: int) -> int | None:
    """Parse MHz from a typed value, accepting either comma or dot decimals.

    Reject invalid, blank, out-of-range and sub-Hz entries rather than
    silently rounding them to an unrelated frequency.
    """
    value = str(text).strip().replace(',', '.')
    if not re.fullmatch(r'\d{1,4}(?:\.\d{1,6})?', value):
        return None
    try:
        hz = int((Decimal(value) * Decimal('1000000'))
                 .to_integral_value(rounding=ROUND_HALF_UP))
    except (InvalidOperation, OverflowError):
        return None
    return hz if minimum_hz <= hz <= maximum_hz else None
