# macOS

## Installatie van het programma

1. dubbelklik op het package Hubspot-WeFact.pkg
2. open het Shortcuts programma van macOS
3. importeer de hubspot-wefact shortcut vanuit ~/Applications door File->Import te starten
4. voeg de shortcut toe

## Uitvoeren van een synchronisatie van facturen tussen Hubspot en WeFact

1. voer de shortcut hubspot-wefact uit

# Windows

## Installatie van het programma

1. kopieer start.cmd en hubspot-wefact.exe naar een locatie van keuze, bijvoorbeeld C:\Program Files\hubspot-wefact (laatste directory even aanmaken)
2. kopieer hubspot-wefact.db naar C:\Users\<gebruikersnaam>\AppData\Roaming (deze locatie zou al moeten bestaan)

## Uitvoeren van een synchronisatie van facturen tussen Hubspot en WeFact

1. dubbelklik op start.cmd

Dit zal een schermpje tonen met logging dat aan het einde vanzelf weer sluit.

# Belangrijk

Het bestand start.cmd/start.sh waarmee het programma uitgevoerd wordt, bevat ook de geheimen om te kunnen verbinden met Hubspot en WeFact.
LET DUS GOED OP AAN WIE JE DIT BESTAND UITGEEFT!

Mocht er twijfel zijn over de beveiliging, dan kunnen en moeten we de sleutels vervangen in Hubspot en WeFact zodat eventueel gelekte gegevens niet misbruikt kunnen worden.
