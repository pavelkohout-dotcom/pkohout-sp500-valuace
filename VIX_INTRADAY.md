# Intradenní VIX

`investicni_pristrojova_deska.html` vychází z existující šestipřístrojové desky (lokální verze z 23. 10. 2026). Ostatní ukazatele a vzhled zachovává. HTML lze otevřít přímo v prohlížeči nebo vložit místo dosavadního HTML na webu.

- Primární zdroj: Yahoo Finance, spot index **^VIX**, nikoli VIX futures ani ETF. Používá cenu `regularMarketPrice` a její `regularMarketTime` z chart endpointu. Endpoint není garantované veřejné API a může vracet chyby nebo omezovat požadavky.
- Yahoo uvádí pro Cboe Indices zpoždění **15 minut**: https://help.yahoo.com/kb/finance/article-exchanges-data-delays-sln2310.html
- Server: běžící GitHub Actions sběrač kontroluje VIX a S&P 500 každých **30 minut**. Podrobnosti nového rozvrhu a omezení jsou v `INTRADAY_REFRESH.md`. Plánování GitHubu je best effort; zpoždění přenosu a běhu se přičítá ke zpoždění zdroje. Není to realtime feed.
- Prohlížeč: kontrola JSON každých **60 sekund**, při otevření, ruční obnově a návratu na kartu. Stáří se přepočítává každých **15 sekund**. Skrytá karta neprovádí pravidelné kontroly.
- Čas **ET** pochází z kotace a respektuje zimní/letní čas. `checked_at` je oddělený čas serverové kontroly; nikdy nenahrazuje `quote_time`.
- Stáří nad **60 minut** během seance: viditelné označení ZASTARALÁ KOTACE. Mimo seanci se poslední závěrečná kotace označí Trh uzavřen; chybějící závěr zůstává zastaralý. Kalendář NYSE zahrnuje svátky a zkrácené seance 2026–2028.
- Fallback: poslední platná intradenní kotace v serverovém JSON / paměti / localStorage; denní FRED VIXCLS při absenci kotace nebo pokud má novější datum pozorování. Při shodném dni má přednost intradenní záznam s přesným časem. FRED je vždy označen jako denní fallback, nikdy jako intradenní údaj.
- `data/vixcls.json` a původní denní aktualizace zůstávají zachované. Nový soubor je `data/vix_intraday.json`. Žádný nový API klíč není potřeba.
- Neplatné, záporné, nulové, budoucí nebo chybně identifikované kotace jsou odmítnuty. Starší odpověď nesmí přepsat novější pozorování. Při úplném výpadku se zachová původní čas; bez dostupné historie se zobrazí nedostupnost.

## Ověření

```
python -m unittest discover -s tests -p 'test_vix*.py'
node tests/test_vix_ui.cjs
```

Python testy pokrývají validaci ceny/symbolu/času, newyorské datum, výpadek obou zdrojových hostů, poškozenou cache, zachování kotace při výpadku/regresi a novější čas při stejné ceně. Test celé aplikační části HTML používá simulované síťové odpovědi a DOM: ověřuje změnu ceny, přechod do stale, odmítnutí starší odpovědi, localStorage, denní fallback, zdroj v dialogu, časovače a úplnou nedostupnost. Nejde o vizuální test skutečného prohlížeče.
