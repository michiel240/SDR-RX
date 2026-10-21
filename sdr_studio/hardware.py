"""Hardware enumeration: never silently report an installed DLL as a connected radio."""
from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceInfo:
    backend: str
    label: str
    identifier: int | None


def discover(kind: str):
    """Return devices and diagnostic string. No capture stream is started."""
    if kind == 'Demo (geen hardware)':
        return [DeviceInfo(kind, 'Gesimuleerde IQ-bron', None)], 'Demo beschikbaar.'
    if kind == 'RTL-SDR':
        try:
            # pyrtlsdr exposes enumeration through its ctypes librtlsdr binding,
            # NOT through RtlSdr.get_device_count/get_device_name.
            from rtlsdr.librtlsdr import librtlsdr
            count = int(librtlsdr.rtlsdr_get_device_count())
            found = []
            for i in range(count):
                try:
                    name = librtlsdr.rtlsdr_get_device_name(i)
                    if isinstance(name, bytes):
                        name = name.decode('utf-8', 'replace')
                except Exception:
                    name = 'RTL2832U'
                found.append(DeviceInfo(kind, f'RTL-SDR #{i} — {name}', i))
            return found, (f'{count} RTL-SDR gevonden' if count else
                           'Geen RTL-SDR gevonden (0 apparaten). Controleer USB-aansluiting, WinUSB voor RTL2832U interface 0 en andere SDR-programma’s.')
        except (ImportError, OSError, AttributeError) as exc:
            return [], f'RTL-SDR DLL/binding ontbreekt of werkt niet: {exc}'
        except Exception as exc:
            return [], f'RTL-SDR detectie mislukt: {type(exc).__name__}: {exc}'
    if kind == 'Airspy R2':
        try:
            from .airspy_native import enumerate_airspy
            serials, message = enumerate_airspy()
            return [DeviceInfo(kind, f'Airspy R2 serienummer {s:016X}', s) for s in serials], message
        except Exception as exc:
            return [], f'Airspy driver ontbreekt of werkt niet: {exc}'
    raise ValueError(kind)
