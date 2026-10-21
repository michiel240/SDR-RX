# Bijdragen aan SDR Studio RX by M@rcello

Dit is een Windows SDR-ontvanger in Python met ondersteuning voor RTL-SDR en Airspy R2.

## Starten met ontwikkelen

1. Maak een branch voor je wijziging (`feature/korte-naam` of `fix/korte-naam`).
2. Installeer de testafhankelijkheden: `python -m pip install -r requirements-tests.txt`.
3. Voer uit: `python -m pytest -q`.
4. Dien een pull request in met een beschrijving van de wijziging, testresultaten en eventuele hardwaretests.

Voor de Windows GUI installeer je de volledige afhankelijkheden met `python -m pip install -r requirements.txt`. Start met `python -m sdr_studio`.

## Hardware en DSP

- Houd wijzigingen voor RTL-SDR en Airspy R2 gescheiden waar mogelijk.
- Houd bestaande analoge ontvangst werkend, ook als een externe decoder niet geïnstalleerd is.
- Voeg een synthetische IQ-test toe voor nieuwe DSP-functies.
- Geef duidelijk aan wat met echte hardware getest is en wat alleen met mocks getest is.
- Voeg geen persoonsgegevens, IQ-opnamen, wachtwoorden, DLL's of onvrij meegeleverde decoderbestanden toe aan commits.

## Versiebeheer

Gebruik versienummers en release-notities. Een nieuwe release wordt pas als **hardwaregetest** gemarkeerd nadat ontvangst én audio op een Windows-systeem zijn gecontroleerd.
