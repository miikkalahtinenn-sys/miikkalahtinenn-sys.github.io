# Kiekkoaamu

Suomenkielinen NHL-sivusto: yön tulokset, maalit, maalikoostelinkit, tulevat ottelut, sarjataulukko, pistepörssi ja kaikki suomalaiset.
Sivusto päivittyy itsestään GitHub Actionsilla: otteluiden aikaan (n. klo 0–9 Suomen aikaa) 10 minuutin välein, muulloin kerran tunnissa.
Tiedot haetaan NHL:n julkisesta rajapinnasta. Ylläpito ei vaadi palvelinta eikä maksa mitään (verkkotunnusta lukuun ottamatta).

## Käyttöönotto (n. 20 min)

### 1. GitHub-tili ja repositorio
1. Luo tili osoitteessa https://github.com (ilmainen).
2. Luo uusi **julkinen** (Public) repositorio. Nimi:
   - jos sinulla on jo oma verkkotunnus: esim. `kiekkoaamu`
   - jos et vielä: **`<käyttäjänimesi>.github.io`** (silloin sivu toimii heti osoitteessa `https://<käyttäjänimesi>.github.io/`)
   > Julkinen repositorio on tärkeä: GitHub Actions on julkisissa repositorioissa ilmainen. Yksityisessä ilmaiskiintiö (2000 min/kk) loppuisi kesken.
3. Valitse repositoriossa **Add file → Upload files** ja raahaa tämän paketin *sisältö* (ei itse kansiota) sivulle. Paina **Commit changes**.
   - Tarkista, että kansio `.github/workflows/` tuli mukaan (pisteellä alkavat kansiot jäävät joskus pois). Jos ei tullut: **Add file → Create new file**, nimeksi `.github/workflows/update.yml` ja sisällöksi saman tiedoston sisältö tästä paketista.

### 2. Asetukset
1. **Settings → Pages → Build and deployment → Source: GitHub Actions**
2. **Settings → Actions → General → Workflow permissions: Read and write permissions** → Save
3. Muokkaa `config.json` (kynäkuvake GitHubissa):
   - `baseUrl`: sivun osoite, esim. `https://kiekkoaamu.fi` tai `https://<käyttäjänimesi>.github.io`
   - `contactEmail` ja `ownerName`: tarvitaan tietosuojaselosteeseen ja oikaisupyyntöjä varten
   - `siteName`: halutessasi muu nimi
4. **Actions → Päivitä ja julkaise → Run workflow**. Noin minuutin päästä sivu on verkossa.

### 3. Oma verkkotunnus (suositus)
1. Osta verkkotunnus mistä tahansa .fi-välittäjältä (esim. 10–20 €/v). Älä käytä nimessä sanaa "NHL" – se on NHL:n tavaramerkki.
2. Lisää välittäjän DNS-asetuksiin A-tietueet: `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153` (ja `www`-alitunnukselle CNAME → `<käyttäjänimesi>.github.io`).
3. **Settings → Pages → Custom domain**: kirjoita verkkotunnus, odota tarkistus, rastita **Enforce HTTPS**.
4. Päivitä `config.json`-tiedoston `baseUrl` samaksi.

### 4. Näkyvyys hakukoneissa
1. Lisää sivu Google Search Consoleen (https://search.google.com/search-console) ja lähetä `https://<osoite>/sitemap.xml`.
2. Tee sama Bing Webmaster Toolsissa.

## Tiedostot
| Polku | Sisältö |
|---|---|
| `scripts/build.py` | Hakee tiedot ja rakentaa sivuston kansioon `_site/` |
| `web/` | Etusivu, tyylit, fontit, tieto- ja tietosuojasivut |
| `data/archive/` | Päättyneiden otteluiden tiedot (ottelusivuja varten) – päivittyy automaattisesti |
| `data/history.json` | Suomalaisten pistekehitys – päivittyy automaattisesti |
| `config.json` | Nimi, osoite, yhteystiedot, etusivun tiedotteet |
| `.github/workflows/update.yml` | Ajastus ja julkaisu |
| `tests/` | Testiaineisto: `python tests/make_fixtures.py && KA_FIXTURES=tests/fixtures KA_NOW=2026-11-05T05:00:00Z python scripts/build.py` |

## Laillisuus – mitä on otettu huomioon
- **Ei logoja eikä videoita.** Joukkueet näytetään nimillä ja virallisilla lyhenteillä. Maalikoosteet ovat linkkejä NHL:n omiin julkaisuihin (YouTube, NHL.com).
- **Riippumattomuus kerrotaan selvästi** jokaisen sivun alalaidassa ja Tietoa-sivulla; tavaramerkit mainitaan omistajiensa omina.
- **Tietosuoja:** ei evästeitä, ei kävijäseurantaa, fontit omalta palvelimelta (ei Google Fonts -yhteyttä). Suosikkijoukkue tallentuu vain kävijän omaan selaimeen. Tietosuojaseloste: `web/tietosuoja.html`.
- **Tietojen haku on maltillista** (enintään ~10 min välein) ja sivulla tunnistettava User-Agent.

**Huomioi itse** (en ole lakimies – tämä ei ole oikeudellinen neuvo):
- NHL:n rajapinta on julkinen mutta epävirallinen ja dokumentoimaton. NHL.comin käyttöehdot voivat rajoittaa tietojen automaattista käyttöä. Lue ne ja noudata niitä.
- Yksittäiset tulokset ja tilastot ovat faktoja, mutta EU:ssa tietokannoilla on erillinen suoja. Harrastuskäytössä tiivis yhteenveto on eri asia kuin kaupallinen tietojen hyödyntäminen.
- **Jos aiot ansaita sivulla rahaa** (mainokset, sponsorit): hanki lisensoitu tietolähde (NHL:n viralliset datakumppanit) ja siirrä sivusto palveluun, joka sallii kaupallisen käytön (esim. Cloudflare Pages) – GitHub Pages ei ole tarkoitettu ensisijaisesti kaupallisille sivustoille. Lisää silloin myös mainosten vaatimat eväste- ja suostumusasiat.
