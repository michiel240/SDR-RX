# SDR Studio RX by M@rcello

> **Broncode voor verdere ontwikkeling op GitHub.** Basis: v0.8.2 Beta (selectieve groepsscanner). Softwaretests: 140 geslaagd; volledige Windows- en hardwaretests blijven nodig.

**Platforms:** Windows 64-bit, RTL-SDR en Airspy R2. **Python:** 3.11–3.14 (64-bit).

## Snel beginnen

```powershell
python -m pip install -r requirements.txt
python -m sdr_studio
```

Op Windows kun je ook `START_HIER_v0.8.2.bat` gebruiken; die maakt een eigen `.venv` en installeert afhankelijkheden. Voor Airspy R2 zijn de officiële, apart te installeren Windows-DLL's nodig; zie de oorspronkelijke handleiding hieronder. Digitale decoders worden niet meegeleverd.

### Ontwikkelen en testen

```powershell
python -m pip install -r requirements-tests.txt
python -m pytest -q
```

Zie [GitHub installeren en publiceren](docs/GITHUB_START.md) en [bijdragen](CONTRIBUTING.md). Via GitHub Actions worden de tests bij iedere push en pull request automatisch uitgevoerd.

## Huidige status en beperkingen

- De nieuwste bronversie is **v0.8.2 Beta**. Gebruikerstests van eerdere versies bevestigden RTL-SDR- en Airspy-ontvangst, maar v0.8.2 is niet op alle hardwareconfiguraties bevestigd.
- DIGITAL AUTO verzamelt RF-kandidaten. Protocolbevestiging vereist een geschikte digitale decoder; externe runtimes en decoders zitten niet in dit pakket.
- Sommige decoderprofielen zijn voorbereid, maar niet volledig functioneel geïntegreerd.
- Eén fysieke SDR betekent dat scannen opeenvolgend gebeurt. Dubbele VFO-audio werkt alleen voor frequenties binnen de actuele IQ-capture.

---



Deze versie is gebaseerd op **v0.8.1 Beta** en behoudt de bestaande RTL-SDR-, Airspy-, DSP- en DIGITAL AUTO-code. Bewaar je vorige werkende versie in een aparte map.

## Groepsscanner: bijvoorbeeld 10 van 20 frequenties scannen

1. Open **Geheugens** en maak een groep zoals **Beek** met de knop **+ Groep**.
2. Bewaar je frequenties in die groep met **+ Kanaal**, of verplaats bestaande kanalen via **Bewerk**.
3. Open het tabblad **Scan** en kies bij **Scanmodus** de optie **Geheugenkanalen**.
4. Kies bij **Scangroep** de groep **Beek** (de groepskeuze is gekoppeld aan het tabblad Geheugens).
5. Klik op **Kies scankanalen**. Je ziet alle 20 opgeslagen kanalen met een vinkje naast elk kanaal.
6. Vink de 10 kanalen aan die je wilt scannen. Of zet **Aantal** op `10` en klik **Kies eerste N** om de eerste 10 op frequentievolgorde aan te vinken.
7. Klik **Selectie opslaan**. De Scan-tab toont `Groep Beek: 10 van 20 kanalen geselecteerd`.
8. Start de ontvanger en vink **Scan geheugenkanalen (SQL-gestuurd)** aan.

Andere keuze-opties: **Alles**, **Geen** en handmatig aanvinken. Je kunt later eenvoudig 5, 12 of 18 kanalen kiezen. Niet-aangevinkte frequenties worden **niet verwijderd**: ze blijven afstembaar en bewerkbaar onder Geheugens, waar `SCAN UIT` naast de naam verschijnt. In het kanaalbewerkvenster staat ook **Meenemen in groepsscan**.

**Belangrijk:** De selectie wordt opgeslagen met elk kanaal in `%USERPROFILE%\SDRStudio-RX\memories.json` via het nieuwe veld `scan_enabled`. Bestaande geheugenkanalen zonder dat veld staan standaard **aan** voor scannen, zodat oude instellingen bruikbaar blijven. De geselecteerde lijst wordt ververst wanneer je tijdens een actieve scan de selectie wijzigt. Een scan zonder geselecteerde kanalen wordt niet gestart.

Voor een frequentiebereikscan verandert niets. De scanner gebruikt nog steeds **één fysieke SDR** en loopt kanalen één voor één af met instelbare dwell-, holdtijd en squelch. Selectief scannen maakt geen tweede ontvangerkanaal aan. DIGITAL AUTO gebruikt dezelfde scan-instellingen bij **Scan + monitor**.

## Installatie op Windows

1. Pak dit pakket uit in een **nieuwe map**.
2. Kopieer voor Airspy R2 de werkende x64-DLL-bestanden van je eerdere `drivers`-map naar deze `drivers`-map. RTL-SDR-gebruikers kunnen hun bestaande WinUSB-driver behouden.
3. Dubbelklik op **`START_HIER_v0.8.2.bat`**. De starter maakt of hergebruikt een `.venv` en installeert waar nodig de pakketten uit `requirements.txt`.
4. Test eerst gewoon luisteren op 2,4/2,5 MSPS, daarna de scanner met een kleine groep. Bewaar **v0.8.1** als terugvalversie.

## Teststatus en beperkingen

**140 automatische softwaretests geslaagd** op Linux, inclusief 9 nieuwe tests voor selectieve groepsscans, oude geheugenrecords, scannerrotatie en behoud bij hernoemen/verwijderen van groepen. De Qt-interface is syntactisch gecontroleerd, maar de nieuwe Windows-knoppen zijn **niet fysiek op Windows getest**. Ook fysieke RTL-SDR- en Airspy-ontvangst moeten bij jou bevestigd worden.

Er wordt geen decoderprogramma meegeleverd. Voor digitale modes zijn externe decoders nog steeds apart nodig. Decoderondersteuning blijft experimenteel zoals in v0.8.1.

---

## Historische handleiding v0.8.1 en ouder

# SDR Studio RX by M@rcello — v0.8 Beta: DIGITAL AUTO

**Windows 64-bit · RTL-SDR en Airspy R2 · Python 3.11 t/m 3.14 (x64)**

Deze versie bouwt voort op **v0.7 Beta**. Behoud je werkende vorige versie in een andere map. De basisontvangercode (`devices.py`, `airspy_native.py`, `worker.py`, `dsp.py`, `audio.py`) is ongewijzigd.

## Wat is toegevoegd in v0.8?

- **Passieve DIGITAL AUTO-monitor**: zoekt maximaal acht sterke RF-pieken in de lopende FFT en toont een kandidaat pas na **minstens twee waarnemingen**. Dit zijn **geen automatisch herkende protocollen**.
- **Instelbare gevoeligheid** (12–35 dB boven mediane FFT-ruisvloer). Het algoritme onderdrukt de middenfrequentie-DC-piek en randbins; het geeft frequentie, grove bandbreedte en signaalniveau-indicatie. De FFT-piekbreedte is geen gegarandeerde RF-kanaalbreedte.
- **Kandidatenlijst**: selecteer en klik op **Afstemmen**, of dubbelklik op een regel. Gevonden frequenties zijn maximaal 150 regels zichtbaar. Een herhaalde kandidaat wordt niet vaker dan ongeveer elke 25 seconden gelogd.
- **Scan + monitor**: gebruikt de bestaande geheugen- of frequentiebereikscanner (tab **Scan**). Er wordt **geen tweede USB-ontvangersessie** geopend. De knop stelt een minimale dwell van 2500 ms in; de scanner stopt/blijft hangen volgens de bestaande squelchinstellingen; dit is geen gespecialiseerde protocolscanner.
- **Controleren met DSD-neo**: selecteer een kandidaat en klik op deze knop. De gewone ontvanger wordt gestopt, waarna de **externe** decoder in AUTO-modus op de gekozen frequentie kan worden gestart. Het proces kan alleen starten als je een compatibele DSD-neo voor Windows hebt geïnstalleerd.
- **Decodergebeurtenissen** blijven in een aparte tabel; DMR/P25/NXDN-identificatie verschijnt uitsluitend wanneer de externe decoder specifieke synchronisatie/frame/spraakmeldingen produceert. De RF-lijst toont *Onbekend · RF* en geen fictieve protocollen. RF-kandidaten kunnen als CSV worden geëxporteerd.

### Installeren

1. Pak het complete ZIP-pakket uit in een **nieuwe map**.
2. Kopieer je werkende Windows x64 `libairspy.dll` en de bijbehorende DLL's naar `drivers` als je de Airspy R2 gebruikt. De RTL-SDR-USB-driver hoeft niet opnieuw geïnstalleerd te worden als de vorige versie al werkte.
3. Dubbelklik op **`START_HIER_v0.8.bat`**. De starter gebruikt een geschikte 64-bit Python 3.11–3.14 en installeert waar nodig Python-bibliotheken in `.venv`.
4. Kies eerst **Demo (geen hardware)**, open **Decoders**, vink **AUTO monitor inschakelen** aan en bevestig dat de RF-kandidaten verschijnen. Daarna test je de RTL-SDR of Airspy R2, bij voorkeur op 2,4/2,5 MSPS.
5. Voor echte digitale spraak: download en installeer apart een compatibele Windows-build van [DSD-neo](https://github.com/arancormonk/dsd-neo/releases). Zet de uitvoerbare bestanden inclusief eventuele vereiste DLL's in `decoders/bin` of selecteer zelf de .exe in het Decoders-tabblad. Controleer met `CHECK_DECODERS.bat` of het programma gevonden wordt.
6. Selecteer een actieve, **onversleutelde** digitale uitzending en gebruik *Controleren met DSD-neo*. Niet elke RF-piek is digitaal; ook goede ontvangst garandeert geen decodeerbare frames.

### Grenzen van deze beta

- FFT-energie alleen herkent **geen DMR, P25 of NXDN**. Geldige decoderuitvoer is noodzakelijk. De module kan ook analoge zenders, interferentie en andere RF-bronnen als kandidaten registreren.
- DSD-neo wordt **niet meegeleverd**; de externe CLI kan veranderen tussen releases. Controleer zelf compatibiliteit en licentievoorwaarden.
- **Niet volledig handsfree:** een kandidaat moet worden geselecteerd voordat de externe decoder wordt gestart. Automatisch wisselen tussen protocollen bij één constante IQ-stroom is een vervolgstap.
- De eerdere dual-VFO stereo, RDS-koppeling, AM/NFM/WFM/USB/LSB/CW en alle analoge instellingen blijven beschikbaar, maar de nieuwe DIGITAL AUTO-interface is **nog niet getest met echte USB-ontvangers op Windows**.
- Leg signalen alleen vast en beluister/decoderen ze waar dat wettelijk is toegestaan. Versleutelde communicatie wordt niet ontsleuteld.

## Testen

Uitvoeren vanuit de programmamap met een geschikte Python-omgeving:

```bat
.venv\Scripts\python.exe -m pytest -q
```

Voor de tests moet `pytest` zo nodig apart worden geïnstalleerd. De tests controleren voornamelijk DSP, gegevensverwerking en programmeerlogica; ze vervangen geen Windows-/hardwaretest.

---

## Historische handleiding v0.7 en ouder

# SDR Studio RX by M@rcello — v0.7 beta: Dual RX / RDS / RF-indicaties

**Windows 64-bit · RTL-SDR · Airspy R2 · Python 3.11–3.14**

Dit is een **experimentele update** bovenop de v0.6-code. Bewaar jouw geteste, werkende versie afzonderlijk.

## Drie nieuwe uitbreidingen

1. **Dubbele stereo-ontvangst**: activeer `Dual RX · A links / B rechts` in het VFO-paneel. Zet VFO A en B op twee dichtbij gelegen NFM/AM/SSB-kanalen en klik Ontvangen. Er worden twee onafhankelijke demodulatoren gevoed met **één** SDR IQ-stream; VFO A klinkt links, VFO B rechts, elk met eigen squelch. De filters moeten beide binnen het gezamenlijke IF-venster passen (meestal ongeveer ±100 kHz). Twee ver verwijderde frequenties en twee gelijktijdige WFM-kanalen zijn **niet** gegarandeerd/ondersteund. Stel de sample-rate op 2,5 MSPS om CPU-overbelasting te beperken. Tijdens dual RX worden retuning en scanner geblokkeerd. Gebruik een stereo-hoofdtelefoon om het verschil te horen.
2. **Automatische RF-signaalindicatie en decoderberichten**: het Decoders-tabblad toont een signaalindicatie uit het spectrum. Dat **identificeert geen digitaal protocol**. Alleen concrete meldingen van een aangesloten externe decoder gelden als protocolindicaties; DMR, P25, NXDN enzovoort vereisen nog compatibele externe decoderprogramma's en live verificatie. Geen volledig automatische digitale protocoldetectie.
3. **FM-RDS**: selecteer WFM in enkele-VFO-modus en gebruik de optionele externe decoder [`redsea`](https://github.com/windytan/redsea). Plaats een compatibele **Windows 64-bit** `redsea.exe` op de pc en selecteer die in het SDR-tabblad. Schakel RDS aan; ontvangen PI, PS (zendernaam) en Radiotext worden getoond wanneer de uitzending ze bevat. De redsea-binary wordt **niet meegeleverd**. RDS gebruikt de 57-kHz-informatie uit de gedemoduleerde FM-multiplex (niet het gewone luidsprekergeluid). Zonder redsea of met onvoldoende ontvangst blijft het RDS-veld leeg.

## Installatie

1. Pak de ZIP uit in een **nieuwe map**. Start `START_HIER_v0.7.bat` in de programmamap.
2. Kopieer de **werkende x64 Airspy-DLL's** uit de huidige SDR Studio RX `drivers`-map naar deze nieuwe map `drivers`. De RTL-SDR-driver blijft zoals hij al is geïnstalleerd.
3. Test eerst enkel VFO met WFM/NFM en audio; vervolgens een paar **dichtbij gelegen NFM-kanalen** met Dual RX op 2,5 MSPS. Gebruik pas daarna 10 MSPS en houd wachtrij-drops in de gaten.
4. Installeer eventueel een passende redsea.exe apart voor RDS en controleer WFM-ontvangst op een sterke lokale FM-zender.

**Teststatus:** 118 automatische softwaretests (zonder echte USB-ontvangers) geslaagd op Linux, inclusief gesimuleerde IQ-signalen, stereo-mixer en RDS-communicatie met een testproces. De Windows-GUI, de echte RF-stereo-ontvangst en redsea-gedecodeerde RDS-signalen zijn hier **niet** fysiek getest. Bestaande decoderprofielen maken de externe executables niet automatisch beschikbaar.

---

## Bestaande v0.6-functies


**Windows 64-bit · RTL-SDR · Airspy R2 · Python 3.11–3.14 (64 bit)**

Dit is een **testversie**, gebouwd bovenop de door jou geteste **v0.5.1**. Bewaar v0.5.1 in een aparte map. De ontvangermodules (`devices.py`, `airspy_native.py`) en de bestaande audiodriver (`audio.py`) zijn ongewijzigd. De nieuwe interface en echte USB-ontvangst konden hier niet op Windows worden getest. De softwaretests en synthetische IQ-tests zijn wel uitgevoerd.

## Installeren

1. Pak de volledige ZIP uit in een **nieuwe** map, bijvoorbeeld `C:\SDR-Studio-RX-v06`.
2. Kopieer **jouw werkende** Airspy x64-DLL's vanuit de map `drivers` van v0.5.1 naar de nieuwe `drivers`-map. Neem geen 32-bit DLL's.
3. Start **`START_HIER_v0.6.bat`**; wacht de eerste installatie af. De starter maakt een lokale `.venv` aan en controleert de Python-bibliotheken.
4. Test eerst `Demo (geen hardware)`, dan RTL-SDR of Airspy R2 op 2,5 MSPS, in AM/NFM/WFM met alle nieuwe audiofilters op nul/uit.
5. Verhoog daarna alleen als je CPU het aankan naar Airspy 10 MSPS. **Wachtrij-drops > 0** betekenen dat de software IQ-blokken achterloopt, ook als **USB-drops = 0**.

## Nieuwe functies in v0.6

| Functie | Bediening | Status / beperking |
| --- | --- | --- |
| **Passband shift (PBT)** | VFO-paneel: `PBT shift`; sleep de turquoise filterzone over het RF-spectrum | DSP-mixer verschuift het kanaalfilter maximaal ±100 kHz ten opzichte van de SDR-middenfrequentie. VFO A en B bewaren afzonderlijke shift. Bij een te grote verschuiving buiten het SDR-span ontvang je geen bruikbaar signaal. |
| **Variabele BW** | `BW / filter` en filtergrenzen | Bestond al. Filterbandbreedte is onafhankelijk van afstem-STEP. |
| **Driebands EQ** | SDR-tab → EQ laag/midden/hoog in dB | Nieuwe driebands IIR-equalizer met ±12 dB. Met alle drie op 0 dB is het audio ongewijzigd. |
| **AGC / notch / noise reduction** | SDR-tab → Audiofilters | Bestond al, nu gecombineerd met EQ. Spectrale ruisonderdrukking blijft experimenteel en kan artefacten geven. |
| **RF-signaal / piekwaarde** | Bovenaan bij RF-meter | dBFS en piekwaarde met ongeveer 2 seconden hold. |
| **S-meter / dBm** | SDR-tab → RF meter kalibratie | Staat standaard **uit**. Pas na het invoeren van een bekende kalibratiereferentie verschijnt een **schatting**; geen meetinstrument. S9=-73 dBm is slechts een HF-conventie, niet automatisch geldig voor VHF/UHF. |
| **Waterfall** | Boven waterfall: snelheid 1×/2×/4×, Thema/Grijs/Viridis, Laag/Hoog dBFS | Nieuwe weergave-instellingen. Waterfall en spectrum behouden de spectrumzoom. |
| **FFT-resolutie** | Boven spectrum: FFT 2048/4096/8192/16384 | Verhoog resolutie voor smalle signalen; verlaag voor minder CPU-belasting. |
| **Geheugengroepen** | Geheugens-tab → Groep; bij bewaren groep en F1–F8 kiezen | Bestaande geheugens zonder groep komen onder Algemeen. Sneltoetsen zijn uniek; 0 betekent geen sneltoets. |
| **Scanner per groep** | Geheugens: selecteer een groep; Scan: geheugenmodus | Scant alleen de gekozen groep. Frequentiebereik, dwell en hold blijven werken. |
| **IQ-opname** | SDR-tab → IQ-opname starten/stoppen | Asynchrone CF32LE-bestanden, maximaal **2 GiB**; metadata in gelijknamig JSON-bestand. Start bij voorkeur op 2,5 MSPS; log vermeldt eventuele ontbrekende IQ-samples. Nieuwe afstemming of scanner beëindigt opname, om foutieve metadata te voorkomen. |
| **IQ replay** | Stop gewone ontvangst → SDR-tab → IQ-bestand afspelen | Speelt **de eigen CF32LE + JSON** opnieuw af in de analoge demodulator. Niet opnieuw opnemen, hardware openen of scannen tijdens replay. Stop of einde bestand sluit netjes af. Externe digitale decoders krijgen de replay-data nog niet rechtstreeks. |

### Hoeveel schijfruimte verbruikt IQ?

Ongecomprimeerde **complex float32** bevat 8 bytes per IQ-sample. Op 2,5 MSPS is dat ongeveer **20 MB/s**; op 10 MSPS ongeveer **80 MB/s**. De opname stopt automatisch bij 2 GiB of bij een schijffout. Het gaat om **ruwe** IQ-data zonder audiocompressie. Opnames vind je onder `%USERPROFILE%\SDRStudio-RX\iq_recordings`.

Het `.cf32`-bestand en het `.json`-bestand horen bij elkaar. Bewaar die samen om opnieuw af te spelen. De JSON bevat onder meer `center_hz`, `sample_rate`, `samples`, `dropped_samples` en `complete`. Bij een overflow kunnen ontbrekende samples niet achteraf worden gerepareerd.

## Functies uit v0.5.1 die blijven werken

- RTL-SDR en Airspy R2 ontvangen (dezelfde hardwarebackends), met AM, NFM, WFM, USB, LSB en CW.
- VFO A/B met afzonderlijke frequentie, mode, SQL en BW, **omschakelen** op één SDR.
- Spectrumklik, muiswielzoom, STEP-invoer, doorlaatfilter en actuele waterfall.
- Frequentiebereikscanner, squelch-gestuurde geheugen-scanner, WAV-audio-opname.
- Lichte en donkere weergave, decoder-tabblad met berichtenlog en export.
- Externe koppelingen voor rtl_433, AIS-catcher, dump1090 en Dire Wolf. DSD-neo digitale spraak blijft **experimenteel**. Externe decoderbinaries worden niet meegeleverd; `CHECK_DECODERS.bat` toont wat aanwezig is.

## Nog niet klaar — volgende ontwikkelfasen

1. **Twee VFO's tegelijk naar stereo-audio**: VFO A links, VFO B rechts. Hiervoor zijn twee gelijktijdige IF-kanalen, afzonderlijke squelch/audioqueues en een stereo-audiobuffer nodig. Dit werkt alleen wanneer de frequenties binnen dezelfde IQ-samplingband liggen, of met twee SDR's. v0.6 biedt nog steeds **A/B-switching**, geen gelijktijdige ontvangst.
2. **WFM RDS**: echte 57-kHz subcarrierdemodulatie, bitsynchronisatie, groepsdecode voor PI/PS/RadioText en uitgebreide tests. Er is **nog geen RDS-decoder** in deze ZIP.
3. **Automatische digitale protocoldetectie** en extra decoderpanelen: vereist bewezen DMR/P25/TETRA/DAB+ runtimes en real-life tests. De aanwezigheid van een decoderprofiel is geen bewijs van werkende demodulatie.
4. **Offline digitale IQ-decodering** vanuit CF32-replay; momenteel alleen analoge replay.
5. **Optionele prestatiemonitor** voor GUI/FFT/DSP-belasting en automatische kwaliteitsinstellingen bij Airspy 10 MSPS.

## Betrouwbaarheid en licenties

- Dit is een RX-only SDR-app; volg de toepasselijke regels voor radio-ontvangst en privacy.
- Bestaande GNU/GitHub decoderprojecten blijven aparte programma's met hun eigen licenties. Geen binaries van derden zijn in dit pakket opgenomen.
- Softwaretests werken met synthese, nepdrivers en testbestanden. De gemodificeerde GUI is **nog niet** getest met jouw RTL-SDR/Airspy R2. Gebruik v0.5.1 als veilige terugvalversie.
- Voor ontwikkelaars: installeer desgewenst `pytest` en draai `python -m pytest -q` in de uitgepakte map.


## Nieuw in v0.8.1 beta: geheugenkanalen organiseren in groepen

Open **Geheugens**. Klik op **+ Groep** en voer bijvoorbeeld **Beek** in.
Selecteer daarna de groep **Beek**. Met **+ Kanaal** kun je handmatig
frequenties toevoegen; met **Bewerk** kun je ook bestaande kanalen aan
Beek toewijzen. Kies groep **Alle groepen** om alles tegelijk te tonen.

- **+ Groep** maakt ook lege groepen aan; die blijven na een herstart bestaan.
- **Hernoem** wijzigt de groepsnaam van alle aangesloten geheugenkanalen.
- **Wis groep** vraagt bevestiging en verplaatst frequenties veilig naar **Algemeen**;
  de kanalen worden niet verwijderd.
- Een kanaal krijgt frequentie in MHz, naam, mode, groep, optioneel commentaar,
  favoriet en F1–F8 (0 = geen sneltoets).
- Selecteer een groep in **Geheugens**, ga naar **Scan**, kies
  **Geheugenkanalen** en start de scanner; uitsluitend de kanalen uit die groep
  worden dan gescand. Een lege groep kan niet gescand worden.
- **Beek** is een groepsnaam, geen vooraf geladen lijst met frequenties;
  voeg alleen de frequenties toe die je zelf wilt bewaren.

De bestaande `%USERPROFILE%\SDRStudio-RX\memories.json` blijft in gebruik.
De nieuwe groepscatalogus wordt afzonderlijk opgeslagen onder
`%USERPROFILE%\SDRStudio-RX\groups.json`. Er worden geen bestaande
kanalen overschreven bij alleen het aanmaken van een groep. Maak voor de zekerheid
vooraf een kopie van je `memories.json`.

Installeer v0.8.1 in een **nieuwe map**; gebruik `START_HIER_v0.8.1.bat`
en kopieer voor Airspy R2 indien nodig de werkende x64-DLL's naar `drivers`.
De nieuwe Windows-GUI moet nog op een echte Windows-ontvanger worden getest.
