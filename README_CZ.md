# Automatická valuace S&P 500 — návod pro Pavla

Tento balíček je připravený tak, aby po prvním nastavení fungoval bez vašeho počítače.

## Co se bude dít automaticky

Každý pracovní den ve 23:20 UTC GitHub:

1. stáhne poslední data z FRED,
2. převezme poslední dostupnou hodnotu S&P 500,
3. znovu spočítá Foreign-Adjusted MZM Proxy,
4. pokud FRED mezitím zveřejnil nový měsíční údaj, automaticky ho použije,
5. přepočítá valuační index,
6. uloží nový soubor `data/mzm_ratio.json`.

Nemusíte proto mít zvlášť „denní“ a „měsíční“ automatizaci.

---

# PRVNÍ NASTAVENÍ — klik za klikem

## A. Založení účtu GitHub

Pokud účet ještě nemáte:

1. otevřete https://github.com/
2. klikněte **Sign up**
3. vytvořte účet a přihlaste se.

## B. Vytvoření repozitáře

1. Na GitHubu klikněte vpravo nahoře na **+**
2. zvolte **New repository**
3. do **Repository name** napište přesně:

   `pkohout-sp500-valuace`

4. nastavte **Public**

   Důvod: Wix musí mít možnost načíst `mzm_ratio.json` bez přihlašování.

5. README ani jiné volby nemusíte zaškrtávat.
6. klikněte **Create repository**.

## C. Nahrání tohoto balíčku

Do repozitáře je potřeba dostat OBSAH této složky, nikoli ZIP jako jediný soubor.

Nejdůležitější je zachovat i skrytou složku:

`.github/workflows/update.yml`

Nejjednodušší postup přes web GitHubu:

1. v novém repozitáři klikněte **Add file → Upload files**
2. nahrajte:
   - `update_valuation.py`
   - `requirements.txt`
   - `data/mzm_ratio.json`
   - `wix_embed.html`
   - `README_CZ.md`
3. potvrďte **Commit changes**.

Složku `.github/workflows` je obvykle nejsnazší vytvořit přímo na GitHubu:

1. **Add file → Create new file**
2. do pole názvu napište přesně:

   `.github/workflows/update.yml`

3. otevřete z balíčku soubor `.github/workflows/update.yml`
4. jeho celý obsah vložte do GitHubu
5. klikněte **Commit changes**.

## D. Povolení GitHub Actions

1. v horním menu repozitáře otevřete **Actions**
2. pokud GitHub nabízí tlačítko **I understand my workflows, go ahead and enable them**, potvrďte ho
3. vlevo uvidíte workflow **Aktualizace valuace S&P 500**
4. otevřete ho
5. vpravo klikněte **Run workflow**
6. znovu **Run workflow**

První ruční spuštění je důležité: vytvoří skutečný `data/mzm_ratio.json`.

Po úspěchu bude běh označen zelenou fajfkou.

## E. Kontrola výsledku

V repozitáři otevřete:

`data/mzm_ratio.json`

Nahoře by mělo být:

`"status": "ok"`

a dále položky:

- `sp500_date`
- `sp500`
- `foreign_adjusted_mzm_date`
- `foreign_adjusted_mzm`
- `index`

---

# NAPOJENÍ NA WIX

Otevřete soubor:

`wix_embed.html`

Najděte tento řádek:

`https://raw.githubusercontent.com/USERNAME/pkohout-sp500-valuace/main/data/mzm_ratio.json`

Místo `USERNAME` vložte své skutečné uživatelské jméno na GitHubu.

Příklad:

`https://raw.githubusercontent.com/pavelkohout/pkohout-sp500-valuace/main/data/mzm_ratio.json`

Pak celý obsah `wix_embed.html` vložte do HTML prvku na stránce Wix.

## Ve Wixu

1. otevřete editor stránky `Valuace S&P 500`
2. přidejte nebo označte **Embed Code / HTML iframe**
3. zvolte vložení kódu
4. vložte celý obsah `wix_embed.html`
5. nastavte výšku prvku přibližně na 600–700 px
6. publikujte web.

---

# Co už potom nemusíte dělat

Nemusíte:

- spouštět Thonny,
- mít zapnutý Mac,
- ručně stahovat S&P 500,
- ručně kontrolovat nový M2,
- ručně přepisovat JSON,
- každý měsíc měnit Wix.

GitHub workflow běží samo.

---

# Důležitá poznámka k datům

Aktuální valuační bod může mít například:

- S&P 500: datum 7. října
- Foreign-Adjusted MZM: datum 31. srpna

To není chyba. S&P 500 je denní řada, zatímco peněžní zásoba a některé její komponenty vycházejí měsíčně nebo čtvrtletně se zpožděním.

JSON proto exportuje obě data zvlášť.

---

# Metodika

Balíček zachovává výpočet z původního skriptu:

`MZM proxy = M2MNS - RMFSL + MMMFFAQ027S / 1000`

`foreign share = ROWCESQ027S / BOGZ1LM883164115Q`

`Foreign-Adjusted MZM = MZM proxy / (1 - foreign share)`

`raw ratio = S&P 500 / Foreign-Adjusted MZM`

`Valuační index = 100 × raw ratio / 0,15`

Před rokem 1982 se pro historické prodloužení preferuje oficiální řada MZMSL, stejně jako v předchozí verzi skriptu.

---

# Když něco nefunguje

Nejdříve otevřete GitHub → repository → **Actions**.

- zelená fajfka = automat proběhl správně
- červený křížek = otevřete běh a zkopírujte mi chybovou hlášku

Není třeba chybu řešit samostatně.
