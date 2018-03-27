These texts are stored for archival purposes. They have been removed from the website in order to save people from
translating stuff that is already in the manual.


# Welke grote veranderingen zijn er geweest?

December 2017

Lijsten met recente updates toegevoegd.

1500 urls toegevoegd.

November 2017

Grafieken van kwetsbaarheden toegevoegd.

Scores vervangen door absolute faal voor meer duidelijkheid.

Beter opvolgen van redirects (feedback).

6 november: livegang nieuwe versie faalkaart.

Oktober 2017

Scan op het ontbreken van TLS toegevoegd.

Scores tussen 0 (geen vermelding), 200 en 1000.

Scan op HTTP Headers toegevoegd, waaronder HSTS.

Scores tussen 0 en 200.

Enkele duizenden domeinen toegevoegd.

Januari 2017

Scanners hebben enkele maanden op pauze gestaan.

Juni 2016

Nieuwe TLS kwetsbaarheid: veel rood.

Maart 2016

Introductie faalkaart, 1800 domeinen.

Scores tussen 0 tot en met 1000.




# Wat is de historie van Faalkaart?

**28 augustus 2017**: Er wordt op een nieuwe manier beoordeeld. Per beveiligingsfout worden punten uitgedeeld. Heeft een organisatie geen punten, dan hebben we geen fouten kunnen vinden: perfect! Er is nu dus ook een top win!

In deze update is de kaartsoftware bijgewerkt: er wordt nu gebruik gemaakt van open streetmaps, beter kaartmateriaal, het django python framework, dynamische javascripts en betere caching. De site laadt niet alleen sneller, hij is beter te onderhouden. Alle ontwikkeling van de faalkaart gebeurd inmiddels open source. Patches zijn welkom.

Al het werk levert ook wat nieuwe features op: deze site wordt automatisch ververst als je de site open laat staan, het is mogelijk om door de tijd heen te scrollen en er is nu een top 50 van meest falende organisaties. In plaats van afzonderlijke sites te kijken, wordt er nu per organisatie beoordeeld. Tenslotte hebben we alle sites die niet meteen TLS spreken aangemerkt als een "gemiddelde" fout: in de vorige versie van de kaart werd hier nog geen oordeel over gegeven. Het ontbreken van TLS is net zo erg als slechte TLS.

**15 februari 2017**: Inmiddels wordt er weer [volop gewerkt](https://github.com/failmap) aan faalkaart. De kaart is bijgewerkt naar nieuwe, goed onderhoudbare, technieken. Inmiddels is er een [stichting opgericht](https://internetcleanup.foundation) om de ontwikkeling van de kaart te stimuleren. Binnenkort wordt er gewerkt aan het beter scannen van e.e.a: er gaat meer en sneller gescand worden.

**7 augustus 2016**: Faalkaart heeft de steun gekregen van het SIDN fonds, we zullen het komende jaar de kaart uitbreiden en op veel meer controleren. We gaan de kaartrot oplossen en zorgen dat het makkelijk wordt om zelf de kaart te kunnen draaien (onafhankelijk). Ook is de chaching van de site ingevoerd, dus het voelt weer snel(ler) aan.

**9 juni 2016**: Door een nieuwe kwetsbaarheid zijn er 100+ domeinen in het rood beland, van 2% naar 9% kwetsbaar dus. Het aantal matige domeinen blijft gelukkig afnemen. Hoe lang zal het duren tot alles gepatched is? Wie patcht het laatst?

**Extra update**: Faalkaart heeft een projectbijdrage gevraagd aan het SIDN fonds om er voor te zorgen dat dit middel breder en makkelijker kan worden ingezet. We gaan hierdoor vele honderdduizenden kwetsbaarheden aan de kaak te stellen en blijven motiveren om ze te verhelpen. De techneuten, hackers en nerds achter faalkaart staan te trappelen om het internet robuuster te maken. Half Juni weten we meer. Spannend!

**Extra update 2**: We zien dat door de grote hoeveelheid data we caching moeten gaan toepassen en verder moeten optimaliseren. De bedoeling is om de kaart zo actueel mogelijk weer te geven. Tot dit opgelost is zal het iets langer duren voordat de kaart geladen is.

**8 april 2016**: Het aantal domeinen met een onvoldoende is gezakt naar 2%, was ooit 8%. Er zijn zojuist 1200 domeinen toegevoegd. Er is een team aan het ontstaan dat de faalkaart verder gaat uitbreiden en onderhouden. Vele handen maken licht werk. Dank aan gemeenten voor het insturen van subdomeinen. Dit is altijd welkom!

**25 maart 2016**: De kaart wordt automatisch ververst. Onder de uitleg staat een overzicht met domeinen die onvoldoende scoren.

**18 maart 2016**: De kaart wordt zeer binnenkort automatisch bijgewerkt. Nieuw zijn statistieken met historie. De domeinenlijst is verbeterd en er is tekst toegevoegd over de totstandkoming van het cijfer. Binnenkort ook open source.

**16 maart 2016**: De eerste serie van 1800 domeinen is geladen, dit wordt nog aangevuld en zal binnenkort opnieuw worden gecontroleerd. De testdatum is nu zichtbaar. De eerste verbeteringen schijnen een half uur na presentatie al te zijn doorgevoerd. Dat is stoer!