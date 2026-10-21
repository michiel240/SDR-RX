# SDR Studio RX by M@rcello — Decoderfase 1 (DSD-neo)

Deze **broncode-update** is gemaakt voor de openbare GitHub-repository
`Masko68/SDR-RX`. Het is **geen kant-en-klare EXE**. De vorige werkende
Windows-installatie blijft bruikbaar; upload alleen de bestanden uit deze
update naar je repository en bouw daarna opnieuw op je pc.

## Wat is verbeterd?

- **Belangrijke fout opgelost:** het `voice16`-profiel voor DSD-neo kreeg
  geen FM-demodulator. De IQ-naar-PCM-conversie kon daardoor meteen crashen.
  Deze bridge levert nu echte 16-bits mono PCM-discriminatordata bij 48 kHz.
- **DMR/P25 stereo bewaard:** waar het decoderprofiel twee 8-kHz
  audiokanalen levert, houdt de speler links en rechts gescheiden bij het
  omzetten naar 48 kHz (geen onbedoelde mono-mix meer).
- **Voorzichtiger protocolindicatie:** expliciete meldingen als `DMR no sync`
  en `NXDN sync lost` worden niet langer als protocolbevestiging genoteerd.
  Een RF-piek zonder decoderlog blijft een onbekend RF-signaal.
- **Windows-test robuuster:** de eerder gemaakte reparatie voor de
  ontvangerthread-test zit ook in deze update. Dit voorkomt dat een trage
  eerste FFT op een Windows-pc direct tot een testfout leidt.

## Eerst op GitHub bijwerken (via website)

1. Pak `SDR-RX-Decoder-Fase-1-GitHub-Update.zip` uit.
2. Open https://github.com/Masko68/SDR-RX en ga naar de hoofdmap van `main`.
3. Klik **Add file → Upload files**.
4. Upload de inhoud van de uitgepakte update, dus `sdr_studio/`, `tests/`,
   `docs/` en `TEST_DECODERS_WINDOWS.bat`. Laat GitHub de bestaande bestanden
   met dezelfde paden vervangen.
5. Klik **Commit changes** en controleer **Actions → SDR Studio RX Tests**.

Alle andere bestanden in de repository blijven behouden.

## Op je Windows-pc testen

1. Download via **Code → Download ZIP** de bijgewerkte repository en pak uit.
2. Start zo nodig `START_HIER_v0.8.2.bat` om de Python-omgeving aan te maken.
3. Dubbelklik op `TEST_DECODERS_WINDOWS.bat`. Dit voert de decodertests uit,
   toont waar optionele decoderprogramma's zijn gevonden en **blijft open**.
4. Gebruik `BOUW_EXE_WINDOWS.bat` om opnieuw een portable Windows-map te
   maken. De volledige map `dist/SDR-Studio-RX/` moet bij elkaar blijven.

## DSD-neo installeren

Download een voor Windows geschikte, betrouwbare build van
https://github.com/arancormonk/dsd-neo/releases en pak die volledig uit.
Kopieer het programma **met vereiste bijbehorende DLL-bestanden** naar
`decoders/bin/` in je **werkende projectmap**. Bij de gebouwde portable EXE
is dat `dist/SDR-Studio-RX/decoders/bin/`. Of selecteer in de SDR Studio
RX-interface zelf het pad naar `dsd-neo.exe`.

Open SDR Studio RX → **Decoders** → **DSD-neo · Digital Auto**. Kies de
juiste RTL-SDR of Airspy R2. Test eerst de gewone SDR-ontvangst om te
controleren dat de USB-driver werkt. Start daarna DSD-neo bij een bekend,
sterk, onversleuteld digitaal signaal. De gewone ontvanger wordt tijdelijk
vrijgegeven zodat niet twee programma's hetzelfde apparaat proberen te
openen.

**Belangrijk:** de softwaretests gebruiken synthetische signalen en een
fake-spraakuitgang. Ze bewijzen *niet* dat het decoderen van DMR, P25 of NXDN
op echte hardware werkt. DSD-neo is een extern programma en wordt niet
meegeleverd. De huidige NFM-filterketen kan bepaalde digitale modi
beperken; dit is een onderwerp voor decoderfase 2 (ruwe discriminator,
handmatige kanaalbreedte en live decode-kwaliteitsmetingen).

## Daarna

Fase 2: kanaalbreedte/discriminator voor DMR en NXDN optimaliseren,
protocolsynchronisatie uit echte DSD-neo logs toetsen, tijdstempels en
Talkgroup/Radio ID tonen. Daarna volgen AIS/APRS/ADS-B en eventueel
ACARS/POCSAG, elk met eigen externe decoder en hardwaretests.
