# Beküldési szabályok

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
2. Futtasd helyben: `python tools/validate_catalog.py` (és a tesztek: `python -m unittest discover -s tools`).
3. Nyiss Pull Requestet a sablon szerint. A leírásban szerepeljen:
   - a repó linkje, és hogy te vagy-e az alkalmazás fejlesztője;
   - ha ismered: a csomagazonosító (`packageName`) és az aláíró tanúsítvány SHA-256 ujjlenyomata (`signingCertSha256`), és honnan származik (pl. a fejlesztő által közzétett érték).
4. A `dist/` könyvtárat **ne** módosítsd: azt a karbantartók generálják és írják alá.

## Automatikus ellenőrzés (GitHub Actions, minden PR-on)

A `.github/workflows/validate.yml` a `tools/validate_catalog.py`-t futtatja. Ellenőrzi:

- a JSON-szintaxist és a sémát, a kötelező mezőket, az ismeretlen mezőket;
- az `id` egyediségét, és hogy a fájlnév egyezik vele;
- a repó-útvonal formátumát (`owner/name`, teljes URL nem fogadható el), és hogy a repó nem szerepel-e már más azonosító alatt;
- a metaadat-ellentmondásokat: ugyanaz a `packageName` vagy `repositoryId` két bejegyzésben, `minVersionCode` csomagnév nélkül, ismétlődő aláíró-ujjlenyomat vagy kulcsszó;
- a `dist/v1/catalog.json` érvényességét és determinisztikus formáját; a `main` ágon az aláírását is.

Az action commit SHA-hoz rögzített, a workflow csak olvasási jogot kap, titkot nem használ, és `pull_request` eseményre fut (nem `pull_request_target`-re).

## Emberi jóváhagyás

A sikeres automatikus ellenőrzés nem elég. Egy karbantartó (CODEOWNERS) kézzel ellenőrzi:

1. a repó létezik és nyilvános; a `repositoryId` egyezik a GitHub által közölttel (`https://api.github.com/repos/<owner>/<repo>` → `id`);
2. a legutóbbi kiadásokban van telepíthető APK, és az aláírója a fejlesztő saját kulcsa (`apksigner verify --print-certs`); ha a PR megad `signingCertSha256`-ot, az egyezik vele; ha `packageName`-et, az egyezik az APK-éval;
3. a licenc és a fenti feltételek teljesülnek, a név és a kulcsszavak nem utánoznak más alkalmazást.

Jóváhagyás után a karbantartó beolvasztja a PR-t, majd helyben (vagy a kulcs tárolásáról hozott döntés szerint) újragenerálja és aláírja a katalógust:

```
python tools/build_catalog.py --serial <a jelenleginél nagyobb szám>
python tools/sign_catalog.py --key <keyId>=<privát kulcs a repón kívül>
python tools/validate_catalog.py --require-signature
```

A `main` ág védelme (a nyilvános publikálás után beállítandó): kötelező review a Code Ownerstől, kötelező sikeres „Katalógus-validáció”, force push tiltva.

## Mit nem fogadunk el?

- Leírást, README-részletet vagy más, harmadik féltől bemásolt szöveget (a katalógusadatok CC0-1.0 alatt vannak).
- Adatot az F-Droid vagy az IzzyOnDroid metaadataiból (azok AGPL-licencűek).
- Más alkalmazást utánzó nevet vagy kulcsszavakat.

## Eltávolítás

Egy bejegyzés eltávolítható, ha a repó megszűnik, a kiadások már nem tartalmaznak APK-t, megváltozik az aláíró, és ezt a fejlesztő nem erősíti meg, vagy biztonsági probléma merül fel.
