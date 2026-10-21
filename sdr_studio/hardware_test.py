"""Bounded IQ smoke-test with clear pass/fail; run with only ONE app using USB SDR."""
from __future__ import annotations
import argparse
import sys
import time
import numpy as np

from .devices import make_source
from .hardware import discover


def capture_test(kind, frequency=100_000_000, seconds=2.5, device_id=None):
    print(f'\n== {kind} ==', flush=True)
    devices, message = discover(kind)
    print('Detectie:', message)
    for dev in devices:
        print('  ', dev.label)
    if kind == 'RTL-SDR' and not devices:
        raise RuntimeError('Geen RTL-SDR gedetecteerd; start geen IQ-capture. ' + message)
    if kind == 'Airspy R2' and not devices and not message.startswith('Airspy-DLL gevonden, maar'):
        raise RuntimeError('Geen Airspy beschikbaar; start geen IQ-capture. ' + message)
    print('IQ capture starten op', frequency / 1e6, 'MHz...', flush=True)
    source = make_source(kind, frequency, 2_500_000 if kind == 'Airspy R2' else 2_048_000,
                         None, device_id)
    try:
        deadline = time.monotonic() + seconds
        samples, blocks, max_power, noise_power = 0, 0, 0.0, 0.0
        while time.monotonic() < deadline:
            iq = source.read(65536)
            if len(iq) == 0:
                continue
            samples += len(iq)
            blocks += 1
            max_power = max(max_power, float(np.max(np.abs(iq))))
            noise_power += float(np.mean(np.abs(iq)**2))
        if not samples:
            raise RuntimeError('Geen IQ-samples ontvangen; controleer USB en firmware')
        print(f'PASS — {samples:,} complex64 IQ-samples uit {blocks} blokken')
        print(f'Ingestelde sample-rate: {source.sample_rate / 1e6:.3f} MSPS')
        print(f'RMS (ongenormeerd): {(noise_power / blocks)**.5:.5f}; piek: {max_power:.5f}')
        print('Ontvangst-API functioneert. Een RF-signaal is hiermee nog NIET bewezen.')
        drops = getattr(source, 'dropped', None)
        if drops is not None:
            print('Airspy dropped samples / applicatieblokken:', drops)
        return True
    finally:
        source.close()


def main():
    parser = argparse.ArgumentParser(description='RTL-SDR / Airspy R2 ontvangsttest')
    parser.add_argument('device', choices=['rtl', 'airspy'])
    parser.add_argument('--freq', type=float, default=100.0, help='Frequentie in MHz (standaard 100)')
    parser.add_argument('--seconds', type=float, default=2.5)
    parser.add_argument('--index', type=int, default=None, help='RTL USB-device index of Airspy serienummer (decimaal)')
    args = parser.parse_args()
    if not 0.3 <= args.seconds <= 30:
        parser.error('seconds moet tussen 0.3 en 30 liggen')
    try:
        ok = capture_test('RTL-SDR' if args.device == 'rtl' else 'Airspy R2',
                  round(args.freq * 1e6), args.seconds, args.index)
        return 0 if ok else 1
    except Exception as exc:
        print(f'FOUT — {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
