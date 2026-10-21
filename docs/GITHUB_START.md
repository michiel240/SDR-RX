# SDR Studio RX op GitHub zetten

## Manier 1: GitHub Desktop (aanbevolen op Windows)

1. Pak `SDR-Studio-RX-by-Marcello-GitHub-v0.8.2.zip` uit op een vaste plek, bijvoorbeeld `C:\Projects\SDR-Studio-RX-by-Marcello`.
2. Installeer [GitHub Desktop](https://desktop.github.com/) en meld je aan bij je GitHub-account.
3. Kies **File > Add local repository > Choose...** en selecteer de uitgepakte projectmap.
4. Als GitHub Desktop aangeeft dat het nog geen Git repository is, kies **Create a repository here**.
5. Maak een commit met de tekst `Initial commit: SDR Studio RX v0.8.2` wanneer dat wordt gevraagd.
6. Klik **Publish repository**. Kies `SDR-Studio-RX-by-Marcello` als naam en selecteer **Private** (eerst alleen voor jou) of **Public** (voor iedereen).
7. Na publiceren zie je de bestanden op GitHub. Maak voor nieuwe functionaliteit een aparte branch en gebruik pull requests.

Je hoeft voor deze methode dus niet eerst zelf op github.com een lege repository aan te maken.

## Manier 2: git via PowerShell of CMD

Maak eerst op GitHub een **lege repository** aan. Open daarna PowerShell in de uitgepakte projectmap:

```powershell
git init
git branch -M main
git add .
git commit -m "Initial commit: SDR Studio RX v0.8.2"
git remote add origin https://github.com/JOUW-GEBRUIKERSNAAM/SDR-Studio-RX-by-Marcello.git
git push -u origin main
```

Vervang `JOUW-GEBRUIKERSNAAM` en meld je via de browser aan wanneer GitHub daarom vraagt. Gebruik bij een terminalprompt niet je gewone GitHub-wachtwoord; volg de veilige aanmeldstroom van Git Credential Manager of gebruik een passende token.

## Verder bouwen

- **Issues:** fouten en nieuwe functies registreren.
- **Branches:** nieuwe wijzigingen maken zonder de stabiele versie te overschrijven.
- **Pull requests:** code laten controleren en automatisch laten testen.
- **Releases:** downloadbare versies en testverslagen publiceren.
- **Actions:** draait softwaretests op Windows en Linux bij commits en pull requests.

## Wat hoort niet in de repository?

- `.venv`, logbestanden, instellingen, persoonlijke geheugenkanalen en opnames.
- `libairspy.dll`, `libusb-1.0.dll`, binaries van externe decoders en andere third-party DLL's.
- Privégegevens en geheime sleutels.

De repository heeft een MIT-licentie voor de hier geleverde eigen broncode. Externe decoders zoals DSD-neo, rtl_433 en AIS-catcher hebben hun eigen licenties en worden niet meegeleverd.
