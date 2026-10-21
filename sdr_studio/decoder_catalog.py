"""Optional third-party decoder profiles for SDR Studio RX.

The catalog describes integrations, not claims of embedded decoding. Stream
profiles have a verified *interface design* but still require a locally
installed executable and real-radio tests. Binaries are never shipped.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Decoder:
    label: str
    protocols: str
    approach: str  # stream, external-rtl, audio/iq, configure
    executable: str = ''
    input_hint: str = ''
    stream: str = ''  # cu8, cf32, audio16; blank => manual/external process
    preset_hz: int = 0
    link: str = ''
    voice_flag: str = ''
    voice_channels: int = 1


DECODERS = (
    Decoder('rtl_433 · ISM sensoren', '433/868/915 MHz draadloze sensoren', 'stream', 'rtl_433',
            'Echte IQ-stream via stdin; rtl_433 moet op je PC geïnstalleerd zijn. Deze profile gebruikt 250 kS/s CU8.',
            'cu8', 433_920_000, 'https://github.com/merbanan/rtl_433'),
    Decoder('AIS-catcher · schepen', 'AIS 161.975 / 162.025 MHz', 'stream', 'AIS-catcher',
            'Dual-channel AIS: externe AIS-catcher leest CF32 IQ. Zet de tuner op 162.000 MHz.',
            'cf32', 162_000_000, 'https://github.com/jvde-github/AIS-catcher'),
    Decoder('dump1090 · ADS-B vliegtuigen', 'ADS-B Mode S 1090 MHz', 'stream', 'dump1090',
            'Externe dump1090 leest een 2 MSPS CU8 IQ-stream. Alleen ongecodeerde luchtvaartberichten.',
            'cu8', 1_090_000_000, 'https://github.com/flightaware/dump1090'),
    Decoder('Dire Wolf · APRS / AX.25', 'APRS Bell 202 1200-baud AFSK', 'stream', 'direwolf',
            'NFM-audio gaat als 48 kHz PCM16 via stdin naar Dire Wolf. Monitor op een lokale APRS-frequentie.',
            'audio16', 144_800_000, 'https://github.com/wb2osz/direwolf'),
    Decoder('dump978 · UAT vliegtuigen', 'UAT 978 MHz', 'configure', 'dump978',
            'Vereist een compatibele dump978-build en een passende 978 MHz IQ-ingang. Nog geen automatische IQ-koppeling.',
            preset_hz=978_000_000, link='https://github.com/flightaware/dump978'),
    Decoder('DSD-neo · Digital Auto', 'DMR, P25 I/II, NXDN, D-STAR, YSF, dPMR, ProVoice, M17, X2',
            'stream', 'dsd-neo',
            'Experimenteel: 48 kHz NFM PCM naar DSD-neo, 8 kHz decoderstem naar luidspreker; compatibele Windows-runtime vereist.',
            'voice16', link='https://github.com/arancormonk/dsd-neo/releases', voice_flag='-fa', voice_channels=2),
    Decoder('DSD-neo · DMR', 'DMR TDMA TS1/TS2', 'stream', 'dsd-neo',
            'Experimentele DMR-audiobrug en dual-slot voice-output via DSD-neo.', 'voice16',
            link='https://github.com/arancormonk/dsd-neo/releases', voice_flag='-fs', voice_channels=2),
    Decoder('DSD-neo · P25 fase I', 'P25 fase I', 'stream', 'dsd-neo',
            'Experimentele P25 I 48 kHz PCM-invoer.', 'voice16',
            link='https://github.com/arancormonk/dsd-neo/releases', voice_flag='-f1'),
    Decoder('DSD-neo · P25 fase II', 'P25 fase II', 'stream', 'dsd-neo',
            'Experimentele P25 II 48 kHz PCM-invoer.', 'voice16',
            link='https://github.com/arancormonk/dsd-neo/releases', voice_flag='-f2', voice_channels=2),
    Decoder('DSD-neo · NXDN 48', 'NXDN 4800 baud', 'stream', 'dsd-neo',
            'Experimentele NXDN4800 PCM-invoer.', 'voice16',
            link='https://github.com/arancormonk/dsd-neo/releases', voice_flag='-fi'),
    Decoder('DSD-neo · NXDN 96', 'NXDN 9600 baud', 'stream', 'dsd-neo',
            'Experimentele NXDN9600 PCM-invoer.', 'voice16',
            link='https://github.com/arancormonk/dsd-neo/releases', voice_flag='-fn'),
    Decoder('DSD-neo · D-STAR', 'D-STAR', 'stream', 'dsd-neo',
            'Experimentele D-STAR PCM-invoer.', 'voice16',
            link='https://github.com/arancormonk/dsd-neo/releases', voice_flag='-fd'),
    Decoder('DSD-neo · YSF', 'Yaesu System Fusion', 'stream', 'dsd-neo',
            'Experimentele YSF PCM-invoer.', 'voice16',
            link='https://github.com/arancormonk/dsd-neo/releases', voice_flag='-fy'),
    Decoder('DSD-neo · dPMR', 'dPMR', 'stream', 'dsd-neo',
            'Experimentele dPMR PCM-invoer.', 'voice16',
            link='https://github.com/arancormonk/dsd-neo/releases', voice_flag='-fm'),
    Decoder('DSD-neo · ProVoice', 'ProVoice', 'stream', 'dsd-neo',
            'Experimentele ProVoice PCM-invoer.', 'voice16',
            link='https://github.com/arancormonk/dsd-neo/releases', voice_flag='-fp'),
    Decoder('DSD-neo · M17', 'M17', 'stream', 'dsd-neo',
            'Experimentele M17 PCM-invoer.', 'voice16',
            link='https://github.com/arancormonk/dsd-neo/releases', voice_flag='-fz'),
    Decoder('DSD-neo · X2-TDMA', 'X2-TDMA', 'stream', 'dsd-neo',
            'Experimentele X2 PCM-invoer.', 'voice16',
            link='https://github.com/arancormonk/dsd-neo/releases', voice_flag='-fx', voice_channels=2),
    Decoder('DSD-FME · digitale spraak', 'DMR, P25, NXDN, YSF, M17 (buildafhankelijk)', 'configure', 'dsd-fme',
            'Voornamelijk Linux-georiënteerd; op Windows installatie en audio-routing handmatig nodig.',
            link='https://github.com/lwvmobile/dsd-fme'),
    Decoder('TETRA · datamonitor', 'TETRA downlink, signaling, SDS (alleen toegestaan verkeer)', 'configure', '',
            'TETRA vereist een eigen gespecialiseerde decoder/runtime, hier nog niet aangesloten.'),
    Decoder('TETRAPOL · analyse', 'TETRAPOL experimentaal', 'configure', '',
            'Gespecialiseerde TETRAPOL-runtime en IQ-format nodig. Geen decryptie.'),
    Decoder('DAB / DAB+', 'Band III digitale radio', 'configure', '',
            'Externe DAB-decoder met 2.048 MSPS IQ-ingang en audioweergave vereist.'),
    Decoder('Radiosondes RS41 / DFM / M10', 'Meteorologische radiosondes', 'configure', 'radiosonde_auto_rx',
            'Eigen radiosonde-keten nodig, bijvoorbeeld radiosonde_auto_rx of specifieke rs41mod/dfm decoders.',
            link='https://github.com/projecthorus/radiosonde_auto_rx'),
    Decoder('SSTV · afbeeldingen', 'Robot, Martin, Scottie SSTV', 'audio/iq', '',
            'Vereist bijvoorbeeld MMSSTV of een ander programma met een audio-ingang.',
            link='https://hamsoft.ca/pages/mmsstv.php'),
    Decoder('FT8 / FT4 · WSJT-X', 'FT8, FT4, JT65', 'audio/iq', 'wsjtx',
            'Tijdgesynchroniseerde audio-ingang en correcte klok nodig; gebruik WSJT-X.',
            link='https://wsjt.sourceforge.io/'),
    Decoder('RTTY / PSK31 · fldigi', 'RTTY, PSK31, Olivia, MFSK', 'audio/iq', 'fldigi',
            'Vereist afstemming van audiobrug en fldigi-instellingen.',
            link='https://github.com/w1hkj/fldigi'),
    Decoder('multimon-ng · POCSAG', 'POCSAG 512/1200/2400', 'stream', 'multimon-ng',
            'NFM-discriminator via stdin als 22050 Hz PCM16LE; externe multimon-ng-build vereist. Alleen toegestane berichten.',
            'audio16', link='https://github.com/EliasOenal/multimon-ng'),
    Decoder('multimon-ng · FLEX', 'FLEX / FLEX_NEXT', 'stream', 'multimon-ng',
            'NFM-discriminator via stdin als 22050 Hz PCM16LE; FLEX-ondersteuning moet in de Windows-build zitten.',
            'audio16', link='https://github.com/EliasOenal/multimon-ng'),
    Decoder('ACARS · vliegtuigberichten', 'ACARS VHF 131 MHz AM', 'external-rtl', 'acarsdec',
            'Acarsdec opent ZELF een vrijgegeven RTL-SDR (-r) of Airspy (-s); juiste Windows-build/hardwareondersteuning vereist. App-ontvanger wordt gestopt.',
            preset_hz=131_525_000, link='https://github.com/TLeconte/acarsdec'),
    Decoder('VDL Mode 2 · vliegtuigdata', 'VDL2 ACARS-datalink', 'configure', 'dumpvdl2',
            'Alleen extern: dumpvdl2 heeft een eigen IQ/audio-ingang nodig, nog geen stdin-bridge.',
            link='https://github.com/szpajder/dumpvdl2'),
    Decoder('WSPR · zwakke signalen', 'WSPR HF', 'audio/iq', 'wsjtx',
            'Gebruik WSJT-X met USB-audio (virtuele kabel/loopback) en nauwkeurige klok; geen directe audiobrug.',
            link='https://wsjt.sourceforge.io/'),
    Decoder('NOAA APT · weerbeelden', 'NOAA APT VHF weerfax', 'audio/iq', '',
            'WFM/NFM-audio naar een externe APT-beelddecoder/virtuele audiokabel; geen ingebouwde APT-decoder.'),
    Decoder('Eigen decoder / handmatig', 'Extern proces (handmatig)', 'configure', '',
            'Selecteer zelf programma, argumenten en compatibele ingang.'),
)


def stream_command(decoder: Decoder, frequency: int, device: str) -> tuple[str, list[str], int]:
    """Executable, argv, output IQ sample rate for our controlled stdin bridge.

    The sample rate is actual decoder stdin rate, not the USB sample rate.
    """
    if decoder.executable == 'rtl_433' and decoder.stream == 'cu8':
        return 'rtl_433', ['-r', '-', '-s', '250000', '-f', str(frequency), '-F', 'json'], 250_000
    if decoder.executable == 'AIS-catcher' and decoder.stream == 'cf32':
        # AIS-catcher -r CF32 . reads complex float32 samples from standard input.
        return 'AIS-catcher', ['-r', 'CF32', '.', '-s', '288000', '-o', '5'], 288_000
    if decoder.executable == 'dump1090' and decoder.stream == 'cu8':
        return 'dump1090', ['--ifile', '-', '--raw'], 2_000_000
    if decoder.executable == 'direwolf' and decoder.stream == 'audio16':
        return 'direwolf', ['-r', '48000', '-n', '1', '-b', '16', '-B', '1200', '-t', '0', '-q', 'dx', '-'], 48_000
    if decoder.executable == 'multimon-ng' and decoder.stream == 'audio16':
        if 'POCSAG' in decoder.label:
            return 'multimon-ng', ['-t', 'raw', '-a', 'POCSAG512', '-a', 'POCSAG1200',
                                   '-a', 'POCSAG2400', '-'], 22_050
        if 'FLEX' in decoder.label:
            return 'multimon-ng', ['-t', 'raw', '-a', 'FLEX', '-a', 'FLEX_NEXT', '-'], 22_050
    if decoder.executable == 'dsd-neo' and decoder.stream == 'voice16' and decoder.voice_flag:
        return 'dsd-neo', [decoder.voice_flag, '-i', '-', '-s', '48000', '-o', '-'], 48_000
    raise ValueError('Geen geïntegreerde IQ/audio-stdin mode voor ' + decoder.label)


def decoder_template(decoder: Decoder, freq: int, device: str) -> tuple[str, str]:
    """Friendly defaults for manual mode. For digital streaming use stream_command."""
    if decoder.stream:
        executable, args, _ = stream_command(decoder, freq, device)
        return executable, ' '.join(args)
    if decoder.executable == 'acarsdec' and decoder.approach == 'external-rtl':
        mhz = f'{freq / 1_000_000:.3f}'
        if device == 'RTL-SDR':
            return 'acarsdec', f'-o 4 -r 0 {mhz}'
        if device == 'Airspy R2':
            return 'acarsdec', f'-o 4 -s 0 {mhz}'
        return 'acarsdec', ''
    return decoder.executable, ''


def decoder_description(decoder: Decoder, device: str) -> str:
    text = f'Modes: {decoder.protocols}. {decoder.input_hint}'
    if decoder.stream:
        text += ' IQ/audio-koppeling vanuit SDR Studio RX aanwezig (externe decoder vereist).'
    elif decoder.approach == 'external-rtl':
        text += ' Eigen SDR-aansturing door decoder; SDR Studio RX geeft de USB-ontvanger eerst vrij. Pas apparaatindex 0 zo nodig aan.'
    elif decoder.approach == 'audio/iq':
        text += ' Externe audioverbinding of eigen ontvanger vereist; geen automatische audio-overdracht.'
    else:
        text += ' Alleen handmatige externe integratie, geen live IQ-koppeling.'
    if device == 'Airspy R2' and decoder.stream:
        text += ' Airspy R2 voert IQ intern terug naar de decoder; er wordt geen tweede USB-sessie geopend.'
    return text
