# SDR Studio RX by M@rcello — decoder-overzicht / fase 2

Dit is **een broncode-update** voor `Masko68/SDR-RX`. Er worden geen betaalde,
proprietaire of third-party decoders meegeleverd en er is geen automatische
installatie van externe programma's. Een aanwezig `*.exe` is **geen bewijs**
van ontvangst of van correcte decodering.

## Welke decoder werkt op welke manier?

| Protocol / mode | Extern programma | Verbinding met SDR Studio RX | Status |
|---|---|---|---|
| DMR, P25 I/II, NXDN, YSF, D-STAR, M17, dPMR, ProVoice, X2 | DSD-neo | NFM PCM16LE 48 kHz via stdin; binaire spraak via stdout | Experimentele live brug; echte synchronisatie nog te testen |
| APRS / AX.25 | Dire Wolf | NFM PCM16LE 48 kHz via stdin | Live brug aanwezig, RF-validatie nodig |
| POCSAG 512/1200/2400 | multimon-ng | **Nieuw**: NFM PCM16LE 22.050 Hz via stdin | Live brug; decode in Windows nog te testen |
| FLEX / FLEX_NEXT | multimon-ng | **Nieuw**: NFM PCM16LE 22.050 Hz via stdin | Live brug; decode in Windows nog te testen |
| 433/868/915-MHz sensoren | rtl_433 | CU8 IQ, 250 kS/s via stdin | Live IQ-brug; apparaat/protocol-afhankelijke sample rate |
| AIS | AIS-catcher | CF32 IQ, 288 kS/s via stdin, tuner 162 MHz | Live IQ-brug, RF-validatie nodig |
| ADS-B 1090 | dump1090 | CU8 IQ, 2 MSPS via stdin | Live IQ-brug, RF-validatie nodig |
| **ACARS VHF** | acarsdec | **Nieuw**: decoder opent zelf RTL-SDR `-r` of Airspy `-s` | Extern proces, eigen USB-tuner; geschikte Windows-build nodig |
| **VDL Mode 2** | dumpvdl2 | Nog geen werkende stdin-brug | Externe IQ-configuratie vereist |
| UAT ADS-B 978 | dump978 | Nog geen werkende stdin-brug | Externe IQ-configuratie vereist |
| RDS-PS / radiotekst | redsea | WFM-multiplex; koppeling in **ontvangstscherm**, niet in deze decoderlijst | Externe redsea vereist |
| FT8, FT4, JT65, WSPR | WSJT-X | USB-ontvangst en zelf geconfigureerde audio-loopback/virtuele audiokabel | Externe audio, geen automatische route |
| RTTY, PSK31, Olivia, MFSK | fldigi | USB/LSB of CW-audio via virtuele audiokabel | Externe audio, geen automatische route |
| SSTV | MMSSTV of vergelijkbaar | Audio via loopback of kabel | Externe audio; geen ingebouwde beelddecoder |
| NOAA APT | Externe NOAA-APT-software | Audiokabel / WAV-export buiten decoderbrug | Alleen handmatig |
| Radiosondes | radiosonde_auto_rx | Zelfstandige ontvanger/configuratie | Geen gedeelde IQ-brug |
| DAB / DAB+ | Eigen DAB-decoder | Eigen IQ-bron nodig | Nog niet geïntegreerd |
| TETRA / TETRAPOL | Geschikte protocolruntime | Eigen IQ-bron/gespecialiseerde keten | Nog niet geïntegreerd; geen decryptie |

## Fase 2 toegevoegd

- Twee live `multimon-ng` profielen voor POCSAG en FLEX.
- Correcte sample-rateconversie van de interne 48 kHz-discriminator naar **22.050 Hz**
  voor deze profielen (PCM16LE, stdin). Alle decoders blijven één USB-bron
  tegelijk gebruiken.
- POCSAG/FLEX-logregels worden als events getoond in de gedecodeerde-berichtenlijst.
- `acarsdec` krijgt voor RTL-SDR en Airspy een apparaatgebonden startvoorbeeld
  met frequentie in MHz. Dit programma bestuurt **zijn eigen ontvanger**; de
  hoofdontvanger stopt daarom eerst. Pas zo nodig apparaatindex `0` aan.
- ACARS JSON met relevante velden wordt in de gebeurtenissentabel weergegeven;
  willekeurige consoleberichten tellen niet mee als gedecodeerd bericht.
- Handmatige externe audioprogramma's laten de gewone SDR-ontvangst doorlopen.
  Voor WSJT-X, fldigi en SSTV moet je het Windows-audiopad **zelf** instellen,
  bijvoorbeeld met een virtuele audiokabel. De GUI kan nog niet zelfstandig
  een virtuele audiokabel configureren.
- De decoder-tab toont het verbindingstype en een knop om de bijbehorende
  project-/downloadpagina te openen; downloads blijven handmatig.
- DSD-neo-profielen verwijzen nu naar de juiste DSD-neo-releasepagina.

## Wat test je op jouw Windows-pc?

1. Controleer eerst de gewone RTL-SDR- en Airspy-ontvangst.
2. Plaats een betrouwbare Windows-versie van de benodigde decoder, met alle
   bijbehorende DLL's, in `decoders/bin/` **in de projectmap**. Voor de portable
   EXE gebruik je `dist/SDR-Studio-RX/decoders/bin/`.
3. Start `TEST_DECODERS_WINDOWS.bat` in de **broncodeprojectmap**. Dit voert
   softwaretests uit en toont welke binaries gevonden zijn.
4. Voor POCSAG/FLEX: selecteer een van de `multimon-ng`-profielen, stem af op
   een lokaal toegestane zender en klik op *Decoder starten*. De gewone
   ontvanger stopt; dezelfde SDR levert NFM-audio via de decoderbrug.
5. Voor ACARS: selecteer *ACARS · vliegtuigberichten*, kies hardware,
   controleer of de argumenten `-r 0` of `-s 0` kloppen, en start de externe
   decoder. Gebruik een compatibele acarsdec-build met het juiste backend.
6. Voor FT8/RTTY/SSTV: laat gewone USB/audio-ontvangst spelen terwijl
   WSJT-X/fldigi/MMSSTV open is. Richt een virtuele audiokabel/loopback in.
7. De executable voor een portable build ligt in `dist/SDR-Studio-RX/`;
   neem de **hele map** mee (ook dependencies en `decoders/bin/`).

Deze tests zijn grotendeels synthetisch. Belangrijk: veel modes kunnen alleen
ontvangen wanneer de externe decoder aanwezig is én geschikte signaalkwaliteit,
sample-rate, demodulatorinstellingen en/of Windows-audiorouting zijn getest.
Er is geen ingebouwde decoder voor elk hierboven genoemd protocol.

## Volgende technische werkzaamheden

- Digitale FSK-discriminator met instelbare kanaalbandbreedte zonder
  voice-filter voor POCSAG, DMR en NXDN (huidige NFM-audioketen is experimenteel).
- Protocolspecifieke semantische parser voor RAN/NAC/Talkgroup/Color Code,
  met validatie op echte decoderlogbestanden.
- UI voor de keuze van Windows audio-apparaat of loopback, onder andere voor
  WSJT-X en fldigi.
- Echte hardwarevalidatie en automatische regressietests met RF-opnames.

**Gebruik de ontvanger en decoder alleen voor legaal toegestane uitzendingen.**
