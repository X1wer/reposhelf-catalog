# Beküldési szabályok – vázlat

> Állapot: **vázlat** (2. munkamenet). A PR-sablon, az automatikus GitHub Actions-validáció és az emberi jóváhagyás részletes folyamata a 7. munkamenetben készül el.

## Mit lehet beküldeni?

Olyan nyílt forráskódú Android-alkalmazást, amely:

1. **nyilvános GitHub-repóban** van;
2. **GitHub Releases** formában közzétett, **telepíthető APK-t** ad ki (a forráskód jelenléte önmagában nem elég; AAB nem telepíthető);
3. a kiadott APK-kat **a fejlesztő saját kulcsával** írja alá. Nyilvános teszt- vagy debug-kulccsal aláírt kiadást nem veszünk fel, mert azzal bárki aláírhatna egy hamis frissítést;
4. **OSI- vagy FSF-elfogadott licencű**;
5. nem tartalmaz ismerten rosszindulatú működést, és nem kér az alapfunkciójához nem szükséges, rejtett jogosultságot.

**A katalógusban szereplés nem biztonsági tanúsítás.** A felvétel technikai és formai ellenőrzés, nem teljes biztonsági audit.

## Hogyan?

1. Forkold a repót, és hozz létre egy új fájlt: `apps/<id>.json` (a formátum: [SCHEMA.md](SCHEMA.md)).
2. Futtasd helyben: `python tools/build_catalog.py --check`.
3. Nyiss Pull Requestet. A leírásban szerepeljen:
   - a repó linkje, és hogy te vagy-e az alkalmazás fejlesztője;
   - ha ismered: a csomagazonosító (`packageName`) és az aláíró tanúsítvány SHA-256 ujjlenyomata (`signingCertSha256`), és honnan származik (pl. a fejlesztő által közzétett érték).
4. A `dist/v1/catalog.json`-t **ne** módosítsd: azt a karbantartók generálják és írják alá.

## Mit ellenőrzünk? (a 7. munkamenetben automatizálva)

- JSON-szintaxis és séma, kötelező mezők;
- egyedi `id`, és a fájlnév egyezik vele;
- a repó nem szerepel már más azonosító alatt;
- a repó létezik és nyilvános, a `repositoryId` egyezik a GitHub által közölttel;
- van legalább egy kiadás telepíthető APK-val;
- metaadat-ellentmondások (pl. a `packageName` nem egyezik a kiadott APK-éval);
- emberi jóváhagyás: legalább egy karbantartó review-ja kell.

## Mit nem fogadunk el?

- Leírást, README-részletet vagy más, harmadik féltől bemásolt szöveget (a katalógusadatok CC0-1.0 alatt vannak).
- Adatot az F-Droid vagy az IzzyOnDroid metaadataiból (azok AGPL-licencűek).
- Más alkalmazást utánzó nevet vagy kulcsszavakat.

## Eltávolítás

Egy bejegyzés eltávolítható, ha a repó megszűnik, a kiadások már nem tartalmaznak APK-t, megváltozik az aláíró, és ezt a fejlesztő nem erősíti meg, vagy biztonsági probléma merül fel.
