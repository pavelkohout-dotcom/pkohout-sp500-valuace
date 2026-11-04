# Oprava průběžné aktualizace (4. listopadu 2026)

Původní plán GitHub Actions byl nastaven na pět minut, ale skutečné běhy měly dlouhé mezery. VIX JSON se po 00:34 UTC neobnovil a obsahoval závěr předchozího dne. Samotné minutové načítání tohoto JSON v prohlížeči nemohlo situaci napravit. Valuační JSON byl rovněž starší a deska jej navíc automaticky nenačítala.

## Nové chování

- Workflow `update-vix-intraday.yml` spustí omezený běžící sběrač pro VIX a S&P 500. Ten načítá a publikuje oba indexy každých 300 sekund. Jedna úloha běží nejvýše 330 minut, během pracovních dní mezi 12:00 a 22:35 UTC. Každou hodinu v :07 je naplánován další start; souběžné běhy jsou serializované. Mimo okno se provede jedna kontrola a proces skončí.
- GitHub stále negarantuje čas zahájení úlohy. Zpoždění začátku, výpadek runneru nebo zdroje mohou aktualizace přerušit; UI proto nadále posuzuje skutečný čas kotace. Běžící sběrač odstraní závislost každého jednotlivého pětiminutového odběru na samostatném cron spuštění.
- `data/vix_intraday.json` obsahuje VIX, `data/sp500_intraday.json` průběžný S&P 500. Každý má vlastní čas kotace a čas kontroly. Kontrola nikdy neposune čas starého pozorování. Neplatné nebo starší kotace nepřepíšou novější.
- Oba ciferníky se v otevřené viditelné kartě obnovují každých 60 sekund, po ruční obnově i po návratu na kartu. Skrytá karta neprovádí periodické odběry.
- Equity Valuation používá aktuální měnový základ z `mzm_ratio.json` a průběžný S&P 500: `(S&P 500 / foreign_adjusted_mzm / 0.15 − 1) × 100`. Měsíční měnová data se neinterpolují. U valuace je vidět čas ceny a v dialogu datum měnového základu.
- Při stejném datu pozorování má pro VIX přednost intradenní záznam s přesným časem před denním FRED; při chybě zůstává poslední platný záznam. Starší datum nemůže přepsat novější.
- U obou kotací se po 30 minutách objeví označení zastaralých dat. VIX zůstává zdrojem zpožděný přibližně 15 minut; minutová obnova neznamená realtime přenos.

Ověření: testy obou indexových parserů, opakování sběru, časového okna, výběru VIX při shodném dni, živého přepočtu valuace, odmítnutí starší ceny, výpadku, stale stavu a automatické obnovy. Zachovány regresní testy VIX a EPS panelu.
