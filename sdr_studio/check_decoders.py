"""Non-invasive diagnostic for optional decoder programs; does not execute any binary."""
from __future__ import annotations
import shutil
from pathlib import Path
from .decoder_catalog import DECODERS
from .decoder_locations import locate_decoder, decoder_directory


def main():
    root = decoder_directory()
    print('SDR Studio RX by M@rcello v0.8.2 -- EXTERNE DECODERS / FASE 2')
    print('Zoeken in', root, 'en in PATH. Programma\'s worden NIET gestart.\n')
    names = list(dict.fromkeys(d.executable for d in DECODERS if d.executable))
    for name in names:
        local = locate_decoder(name)
        path = local or shutil.which(name)
        status = 'GEVONDEN' if path else 'ONTBREEKT'
        print(f'{status:10s} {name:18s} {path or "zie README.md"}')
    print('\nKOPPELSTATUS PER MODE')
    for decoder in DECODERS:
        status = ('Live IQ/audio' if decoder.stream else
                  'Eigen USB-ontvanger' if decoder.approach == 'external-rtl' else
                  'Externe audiokabel' if decoder.approach == 'audio/iq' else
                  'Nog geen koppeling')
        print(f'{decoder.label[:35]:35s} {status}')
    print('\nGEVONDEN betekent alleen bestand aanwezig, niet dat IQ/spraakdecodering gelukt is.')

if __name__ == '__main__':
    main()
