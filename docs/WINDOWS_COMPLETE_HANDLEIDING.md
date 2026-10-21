# SDR Studio RX by M@rcello — Windows complete portable build

Basis: **v0.8.2 + decoderfase 1 en fase 2 + Windows-testfix**, met decoderzoekfunctie voor losse mappen en een downloader voor officiële Windows-releasebestanden.

## Wat is dit pakket?

Het ZIP-bestand met broncode **bevat geen vooraf gecompileerde Windows-EXE, drivers of decoder-EXE's**. Deze Windows-binaries konden in de ontwikkelomgeving niet worden opgehaald of op Windows worden getest. De **complete Windows-EXE wordt op je eigen Windows-pc of op GitHub Actions** samengesteld.

Na een succesvolle build bevat `dist/SDR-Studio-RX/`:

- `SDR-Studio-RX.exe` en alle door PyInstaller meegeleverde Python-, NumPy-, SciPy- en Qt-bestanden (alles moet bij elkaar blijven).
- `decoders/bin/` met **DSD-neo**, **AIS-catcher**, **rtl_433**, **Dire Wolf** en **multimon-ng**, elk in een eigen submap en met bijbehorende upstreambestanden, indien alle officiële downloads slagen.
- `drivers/` met eventuele lokale x64 Airspy Host Tools DLL's (lokale bouw) en ondersteunende bestanden. Windows zelf vereist nog de juiste USB-driverbinding/WinUSB; het programma installeert of verandert dit niet automatisch.
- `docs/` met gebruiksaanwijzing en verwijzingen naar derde-partijlicenties.
- `CONTROLEER_WINDOWS_PAKKET.bat` om te kijken welke EXE's en DLL's aanwezig zijn.

**Externe tools die niet automatisch worden meegeleverd:** onder andere `dump1090`, `dump978`, `redsea` (RDS), `acarsdec`, `WSJT-X`, `fldigi`, SSTV-ontvangers, DAB-, TETRA-, TETRAPOL- en VDL2-decoders. Hiervoor zijn niet overal gecontroleerde x64 ZIP-releases met bekende SHA256 en een werkende ingebouwde koppeling beschikbaar. In het menu aanwezige modes betekenen niet dat ieder protocol zelfstandig werkt.

## Windows EXE lokaal maken — aanbevolen voor Airspy R2

1. Pak de **hele broncode-ZIP** uit in een **nieuwe map** op de Windows 64-bit pc.
2. Sluit andere programma's die RTL-SDR of Airspy gebruiken.
3. Start **`MAAK_COMPLETE_WINDOWS_VERSIE.bat`**. Dit script:
   - maakt zo nodig een Python `.venv` (Python 3.11 t/m 3.14 x64 vereist);
   - installeert afhankelijkheden en PyInstaller;
   - downloadt vijf officiële decoderrelease-ZIP's en controleert de door GitHub gepubliceerde SHA-256-digests;
   - probeert de officiële Airspy x64 Host Tools DLL's te plaatsen (de officiële Airspy Host Tools ZIP gebruikt `airspy.dll` (niet `libairspy.dll`), en deze oudere Airspy-release heeft géén officiële SHA-256 in zijn GitHub-releasemetadata; je kunt ook je bestaande werkende x64 DLL's gebruiken);
   - draait de softwaretests;
   - bouwt de EXE en kopieert alle beschikbare drivers en decoderbestanden naar één portable map.
4. Kijk of de laatste regels **Bouwstatus: 0** melden.
5. Open `dist\SDR-Studio-RX\CONTROLEER_WINDOWS_PAKKET.bat`.
6. Start `dist\SDR-Studio-RX\SDR-Studio-RX.exe` en test achtereenvolgens **Demo**, **RTL-SDR**, **Airspy R2** en **Decoders**.
7. Voor transport: klik met rechts op de **hele map** `dist\SDR-Studio-RX` en comprimeer tot een ZIP-bestand. Verplaats niet alleen de EXE!

**Download niet gelukt?** Dan toont de installer een fout en geeft de lokale bouwer **Bouwstatus 1**; er wordt niet beweerd dat de bundel compleet is. Voer het script opnieuw uit als de verbinding werkt. Als je al werkende Airspy-DLL's hebt, kopieer die naar `drivers` vóór het bouwen, in plaats van automatische installatie.


## Kleinere portable EXE maken (SLIM)

Wil je de Windows-distributie verkleinen zonder decoders of drivers te wissen,
start dan **`MAAK_KLEINE_WINDOWS_VERSIE.bat`** in plaats van de volledige bouwer.
Het script gebruikt een **nieuwe `.venv-slim`** met alleen
`PySide6_Essentials` in plaats van alle PySide6 Addons/WebEngine/PDF-onderdelen.
PyInstaller sluit bovendien onnodige testmodules, OpenGL-voorbeeldmodi en
WebEngine-onderdelen uit. Alle bestaande **DSD-neo, AIS-catcher, rtl_433,
Dire Wolf, multimon-ng, Airspy- en RTL-SDR-bestanden** worden meegenomen.

De uitvoer is `dist/SDR-Studio-RX-SLIM/SDR-Studio-RX-SLIM.exe`. De bouwer
start die nieuwe EXE zelf met een **offscreen GUI/plot/DSP/audio-smoketest**,
zodat een ontbrekende Qt- of PortAudio-bibliotheek een duidelijke bouwfout
geeft. Dit vervangt geen echte RTL-SDR-, Airspy- of decoder-test.

Het bestand **`dist/GROOTTE_VERGELIJKING.txt`** toont het gemeten verschil
met je vorige distributie. Bewaar die vorige distributie totdat de SLIM-versie
ook op jouw echte ontvangers werkt. Voor andere pc's kopieer je alleen de
**volledige** nieuwe `dist/SDR-Studio-RX-SLIM`-map, niet de broncode,
`.venv`, `.venv-slim` of `build`-map. Een ZIP verkleint de overdracht, maar
niet de benodigde uitgepakte runtime-bestanden.

GitHub Actions kan dezelfde SLIM-bouwer draaien via
**Build Windows SLIM (EXE + Decoders)**.

## GitHub — EXE laten bouwen zonder lokale installatie

1. Zet de broncode en `.github/workflows/build-windows-complete.yml` in je repository `Masko68/SDR-RX`.
2. Open `https://github.com/Masko68/SDR-RX/actions`.
3. Kies **Build Windows Complete (EXE + Decoders)** → **Run workflow** → branch `main`.
4. Open na de succesvolle workflow de run. Onder **Artifacts** staat **SDR-Studio-RX-Windows-Compleet**.
5. Download het artifact, pak de daarin aanwezige **`SDR-Studio-RX-v0.8.2-Decoderfix-Windows-Portable.zip`** uit, en start de EXE in de map `SDR-Studio-RX`.

**Let op:** de GitHub Actions-run bevat vanwege de ontbrekende controlehash voor de oudere Airspy-Host-Tools-release **niet automatisch de Airspy-DLL's**. Voeg je vertrouwde lokale x64 DLL's toe in de `drivers`-map van de complete portable distributie als Airspy anders niet gevonden wordt. Windows' USB/WinUSB-configuratie wordt nooit in de distributie meegeleverd.

## Wat werkt en wat is nog niet geverifieerd?

- De softwaretests controleren programmeerlogica; ze testen **geen** live digitale RF-decoding.
- DSD-neo ontvangt PCM-discriminatoraudio; DMR/P25/NXDN-herkenning moet blijken uit echte frames van de externe decoder.
- POCSAG/FLEX gebruikt een experimentele 22.050 Hz-audiobrug; ACARS kan een eigen tuner openen.
- AIS, dump1090 en rtl_433 gebruiken verschillende IQ-formaten; alleen decoders die daadwerkelijk aanwezig zijn, kunnen gestart worden.
- RDS (redsea), FT8, RTTY, SSTV en overige gespecialiseerde modi hebben een eigen externe applicatie/audiokoppeling nodig.
- **EXE-start en hardwareontvangst moeten nog op jouw Windows-pc worden getest.** Bewaar je vorige werkende SDR-RX-map.

## Troubleshooting

- **Zwart venster sluit**: de BAT blijft na afloop open; stuur de laatste regels.
- **Decoder niet gevonden**: gebruik `CONTROLEER_WINDOWS_PAKKET.bat` en controleer `decoders/bin/<decoder>/`.
- **Airspy niet gevonden**: controleer officiële `airspy.dll` (of `libairspy.dll`) en `libusb-1.0.dll` in `drivers`; ook moet het USB-apparaat de juiste Windows-driver hebben. Bewaar je oude werkende DLL-set.
- **Geen RTL-SDR**: de Windows USB-driver voor RTL2832U interface 0 moet correct geïnstalleerd zijn; sluit overige SDR-software.
- **GitHub Actions rood**: open de mislukte stap. Fouten bij downloads of ontbrekende ZIP-lijsten zijn niet hetzelfde als een Python-codefout.

## Licenties en veiligheid

Decoders en Airspy-Host-Tools worden alleen gedownload vanaf hun **officiële GitHub-release-URL's**. De vijf decoder-ZIP's hebben vastgepinde hashes. Download de bestanden zelf als je dat liever hebt. Zie `DERDEN_LICENTIES_EN_DOWNLOADS.md` voor auteurs/verwijzingen en controleer licentievoorwaarden voordat je een publieke distributie maakt. **Er wordt geen USB-driver ongemerkt geïnstalleerd.**
