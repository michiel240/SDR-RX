# Externe Windows-decoderbibliotheken, bronnen en licenties

Deze software gebruikt onafhankelijke externe projecten. Hun namen, uitvoerbare bestanden en licenties zijn **geen eigen code** van SDR Studio RX by M@rcello. Geen claim op herlicentiëring van derde-partijsoftware.

| Component | Officieel project / broncode | Release gebruikt door Windows-downloader |
|---|---|---|
| DSD-neo — DMR/P25/NXDN/M17/YSF | https://github.com/arancormonk/dsd-neo | v2.11.4 |
| AIS-catcher — AIS | https://github.com/jvde-github/AIS-catcher | v0.70 |
| rtl_433 — ISM-sensoren | https://github.com/merbanan/rtl_433 | 25.12 |
| Dire Wolf — APRS/AX.25 | https://github.com/wb2osz/direwolf | 1.8.1 |
| multimon-ng — POCSAG/FLEX | https://github.com/EliasOenal/multimon-ng | 1.6.1 |
| Airspy Host Tools — `libairspy.dll` en afhankelijkheden | https://github.com/airspy/airspyone_host | v1.0.10 (optioneel, geen officiële hash beschikbaar) |

Elke gedownloade decoder-release wordt **ongewijzigd uitgepakt in een eigen submap**, inclusief eventuele upstreamlicentiebestanden en DLL's. Dit voorkomt dat de ene decoder een DLL van een andere overschrijft. De uitgepakte portable distributie kan licentievereisten en broncodebeschikbaarstelling met zich meebrengen als je de binaries verder verspreidt. Raadpleeg voor elk project zijn `LICENSE`, `COPYING`, broncode en releasevoorwaarden. De projectlicentie `LICENSE-SDR-RX.txt` dekt **alleen de eigen SDR RX-broncode**.

Andere niet-bundelbare gespecialiseerde software: dump1090 (https://github.com/flightaware/dump1090), acarsdec (https://github.com/f00b4r0/acarsdec), redsea (https://github.com/windytan/redsea), WSJT-X (https://wsjt.sourceforge.io/), fldigi (https://github.com/w1hkj/fldigi), SSTV tools. Deze vereisen eigen installatie, compatibiliteitscontrole of hardware- en audioconfiguratie.

Voor **WinUSB / Zadig**: alleen bewust en voor het juiste RTL2832U-interface installeren; `libairspy.dll` is niet hetzelfde als de Windows USB-kerneldriver. Het installeren van de driver wordt om veiligheidsredenen niet geautomatiseerd.
