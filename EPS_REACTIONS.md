# EPS beat a první cenová reakce

V detailu EPS Beat Rate je nový čítač a seznam **EPS beat → pokles ceny**. Původní ciferník FactSet se nemění. Doplňkový vzorek používá Yahoo Finance a vlastní výpočet; jejich EPS konsenzus nemusí být totožný s FactSet.

- Beat = skutečné EPS > konsenzuální odhad (funguje i pro záporné EPS); shoda není beat.
- Pokles = první běžný závěr po oznámení / předchozí běžný závěr − 1 < 0. Při oznámení během seance se používá její závěr proti předchozímu závěru. Nejde o kauzální atribuci ani abnormální výnos vůči indexu.
- Seance určuje kalendář XNYS, včetně víkendů, svátků, letního času a zkrácených seancí. Vyhodnocení nastane nejdříve 30 minut po konci seance. Používají se přesná data obou seancí, nikoli nejbližší dostupné ceny. Dividendové výnosy se nepřičítají; split v intervalu znamená nevyhodnocený případ.
- Čas zveřejnění musí být dodaný Yahoo (`TAS`); datum s neuvedeným časem (`TNS`) se neodhaduje. Sporné duplicitní záznamy se vyřadí z vyhodnocení. Oznámení bez EPS nebo odhadu nejsou v základním vzorku.
- Sezona je definována oknem zveřejňování: pro FactSet 2026-Q3 jde o 1. října až 31. prosince 2026, nejvýše do dne sběru. Jde o oznámení v tomto období, nikoli striktní shodu fiskálních čtvrtletí všech společností. Po změně čtvrtletí FactSet se okno posune; HTML odmítne zobrazit čítač jiné sezony.
- Výběr firem: aktuální seznam S&P 500 z veřejného repozitáře datasets/s-and-p-500-companies. Datum výběru a zdroj jsou v JSON. Není to historické složení indexu k datu každého oznámení. Stejný CIK a den znamenají jednu firmu (více akciových tříd se nezapočítává dvakrát).
- Yahoo kalendář se stránkuje až do konce; opakovaná stránka nebo neúspěšný sběr zastaví publikaci. Ceny se načítají jen pro beaty s dostupným časem. Chybějící ceny se vykazují v samostatném počtu a seznamu, nikdy jako nulová reakce.
- `data/earnings_reactions.json` obsahuje všechny nalezené beaty s daty a stavy; čítače se v prohlížeči kontrolují proti řádkům. Přehled je vždy označen **dostupný vzorek**, nikoli celé S&P 500.
- Server kontroluje data v 23:35 UTC Po–Pá a 07:35 UTC Út–So. GitHub Actions nemá garantovaný přesný čas spuštění. Prohlížeč načte data při otevření detailu a nejvýše každých 15 minut při otevřeném detailu; ruční Obnovit vynutí kontrolu. HTML obsahuje počáteční ověřený snapshot pro offline použití. Při chybě zůstane poslední přehled s upozorněním; po třech dnech je označen jako starší.
- Yahoo rozhraní není garantované veřejné API. Při výpadku kalendáře nebo úplné absenci měřitelných cen se starý serverový soubor nepřepíše. Jednotlivé výpadky cen sníží pokrytí a jsou viditelné. Závislosti mají vlastní soubor, ostatní aktualizační úlohy se nemění.

Ověření: 10 testů Pythonu (BMO, AMC, DST, svátek, zkrácená seance, období, cenový výpočet, split, CIK/deduplikace, záporné EPS, čekající/neurčené reakce); testy celé aplikační části HTML (čítače, seznam, přepínání dialogu, neplatné řádky, jiná sezona, výpadek); původní regresní testy VIX.

```
pip install -r requirements-earnings-reactions.txt
python -m unittest discover -s tests -p 'test_earnings_reactions.py'
node tests/test_earnings_ui.cjs
node tests/test_vix_ui.cjs
python update_earnings_reactions.py
```
