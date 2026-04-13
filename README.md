# Tisza Tracker

Hungarian government promise tracker. Monitors daily media coverage via RSS feeds, ranks articles by relevance using semantic similarity, and links them to specific campaign promises made by the Tisza party.

## Pipeline

```
tt filter   →  tt rank   →  tt fetch   →  tt match   →  tt html / tt email
  (RSS)       (scoring)    (full text)   (promises)     (output)
```

- **filter** — fetch RSS feeds, apply per-topic regex patterns to title + summary
- **rank** — compute semantic similarity (Sentence-Transformers) between topic query and article titles
- **fetch** — store RSS summaries for all ranked entries; download full article text (via trafilatura) for entries above `fetch_threshold`
- **match** — link articles to government promises using per-promise regex pre-filter + semantic scoring against title + summary
- **html / email** — generate HTML reports or send digests via SMTP

## Databases

- `all_feed_entries.db` — global RSS archive for deduplication
- `papers.db` — current run processing (filter → rank → match)
- `matched_entries_history.db` — long-term archive of matched articles
- `article_text.db` — extracted article body text (separate to keep main DBs lean)
- `promises.db` — promise definitions, status tracking, article-promise links

## Configuration

Main config: `config.yaml` (feeds, defaults, database paths)

Topic configs: `topics/*.yaml` (per-topic regex patterns, ranking queries, feed selection)

Promise configs: `promises/*.yaml` (per-promise regex filter + semantic ranking query)

### Key defaults

- `rank_threshold: 0.25` — minimum score to display in output
- `fetch_threshold: 0.40` — minimum score to download full article text
- `ranking_negative_penalty: 0.20` — penalty for negative query terms (sport, weather, celebrity)
- `time_window_days: 30` — RSS entry age filter

## RSS feeds

13 active Hungarian media sources across the political spectrum:

- Independent: Telex, 444.hu, HVG, Nepszava
- Large portals: Index, 24.hu, Hirado.hu
- Business: Portfolio, Vilaggazdasag
- Right-leaning: Magyar Nemzet, Mandiner, 168.hu
- English-language: Hungary Today, Budapest Times

## Promise tracking

148 promises extracted from the Tisza party election programme ("A mukodo es embersages Magyarorszag alapjai", 2026), organized into 10 policy categories mapped to monitoring topics.

Each promise has a `filter_pattern` (regex for fast pre-filtering against title + summary) and a `ranking_query` (semantic similarity query for scoring).

### Promise tracker

Status legend: :white_check_mark: kept | :hourglass_flowing_sand: in progress | :x: broken | :black_square_button: not yet started

### Gazdasag (economy, tax, budget, agriculture)

| ID | Promise | Status | Articles |
|---|---|---|---|
| GAZ-001 | Hazahozzuk és hatékonyan felhasználjuk a jelenleg befagyasztott uniós forrásokat. | :black_square_button: | |
| GAZ-002 | Megfelezzük a vállalkozások adminisztrációs terheit. | :black_square_button: | |
| GAZ-003 | Négy év alatt legalább másfélszeresére emeljük az innovációra fordított forrásokat. _2030_ | :black_square_button: | |
| GAZ-004 | 2026. június 1-től felfüggesztjük az Európán kívüli vendégmunkások behozatalát. _2026-06-01_ | :black_square_button: | |
| GAZ-005 | A K+F kiadást 2030-ra a GDP 2%-ára emeljük, majd közelítjük a 3%-ot. _2030_ | :black_square_button: | |
| GAZ-006 | Megerősítjük a versenyfelügyelet függetlenségét, és átalakítjuk a közbeszerzési rendszert. | :black_square_button: | |
| GAZ-007 | A diplomások arányát legalább az EU átlagára (43%) emeljük. | :black_square_button: | |
| ADO-001 | 15%-ról 9%-ra csökkentjük a minimálbér adóját. | :black_square_button: | |
| ADO-002 | A mediánbér alatti 2,2 millió dolgozó adóját is csökkentjük. | :black_square_button: | |
| ADO-003 | 1 milliárd Ft feletti vagyonra évi 1%-os vagyonadót vezetünk be. | :black_square_button: | |
| ADO-004 | A vényköteles gyógyszerek áfáját 0%-ra csökkentjük. | :black_square_button: | |
| ADO-005 | A tűzifa és az egészséges élelmiszerek áfáját 5%-ra mérsékeljük. | :black_square_button: | |
| ADO-006 | Széles körben újra elérhetővé tesszük a katát. | :black_square_button: | |
| ADO-007 | Semmilyen munkabért terhelő adót nem emelünk. | :black_square_button: | |
| KOL-001 | 2030-ra teljesítjük a maastrichti kritériumokat. _2030_ | :black_square_button: | |
| KOL-002 | Előkészítjük az euró bevezetését, belátható céldátummal. | :black_square_button: | |
| KOL-003 | Átvilágítjuk a teljes költségvetést, megismerjük a titkosított szerződéseket. | :black_square_button: | |
| KOL-004 | Újratárgyaljuk/felmondjuk az országnak kedvezőtlen, titkosított szerződéseket. | :black_square_button: | |
| AGR-001 | 5%-ra csökkentjük az egészséges élelmiszerek áfáját. | :black_square_button: | |
| AGR-002 | Visszaállítjuk az élelmiszer-biztonsági hatóságok függetlenségét. | :black_square_button: | |
| AGR-003 | Nem engedjük csökkenteni a magyar gazdáknak járó EU-támogatásokat. | :black_square_button: | |
| AGR-004 | Felülvizsgáljuk a Földtörvényt, előnyben részesítjük a ténylegesen gazdálkodó fiatalokat. | :black_square_button: | |

### Korrupcio (anti-corruption, transparency)

| ID | Promise | Status | Articles |
|---|---|---|---|
| KOR-001 | Csatlakozunk az Európai Ügyészséghez (EPPO). | :black_square_button: | |
| KOR-002 | Létrehozzuk a Nemzeti Vagyonvisszaszerzési Hivatalt. | :black_square_button: | |
| KOR-003 | Kivizsgáljuk az elmúlt évek korrupciós botrányait (Paks II, MNB-alapítványok, MCC, Hatvanpuszta stb.). | :black_square_button: | |
| KOR-004 | 20 évre visszamenőleg vagyonosodási vizsgálat képviselőkre, politikusokra és családtagjaikra. | :black_square_button: | |
| KOR-005 | Független Korrupciómegelőzési Felügyeletet hozunk létre. | :black_square_button: | |
| KOR-006 | Jogi védelmet biztosítunk a bejelentőknek (whistleblower-védelem). | :black_square_button: | |
| KOR-007 | Nemzeti Szerződéstárat hozunk létre (online, kereshető). | :black_square_button: | |

### Igazsagszolgaltatas (rule of law, justice, civil society)

| ID | Promise | Status | Articles |
|---|---|---|---|
| JOG-001 | Két ciklusra korlátozzuk a miniszterelnöki mandátumot. | :black_square_button: | |
| JOG-002 | Megszüntetjük a rendeleti kormányzást. | :black_square_button: | |
| JOG-003 | Visszaállítjuk a közmédia függetlenségét, új médiatörvényt alkotunk. | :black_square_button: | |
| JOG-004 | Kormányváltás után azonnal felfüggesztjük a közmédia hírszolgáltatását. | :black_square_button: | |
| JOG-005 | Kivizsgáljuk a Pegasus-lehallgatási botrányt. | :black_square_button: | |
| JOG-006 | Megszüntetjük a Szuverenitásvédelmi Hivatalt. | :black_square_button: | |
| JOG-007 | Átláthatóbb, arányosabb választási rendszert alkotunk. | :black_square_button: | |
| JOG-008 | Feloldjuk a titkosított 2000-es és 3000-es kormányhatározatokat. | :black_square_button: | |
| JOG-009 | Létrehozzuk a Gyermekvédelmi Ombudsmant és a Betegjogi Ombudsmant. | :black_square_button: | |
| JOG-010 | Államivá és nonprofit-tá tesszük a végrehajtást, megszüntetjük a végrehajtói kamarát. | :black_square_button: | |
| CIV-001 | Az álcivil szervezetek finanszírozását azonnal leállítjuk. | :black_square_button: | |
| CIV-002 | 2027-től jelentősen emeljük a civil szervezeteknek juttatott forrásokat. _2027_ | :black_square_button: | |
| CIV-003 | Nyilvános, kereshető online adatbázis a megítélt és elutasított támogatásokról. | :black_square_button: | |

### Egeszsegugy (healthcare)

| ID | Promise | Status | Articles |
|---|---|---|---|
| EGU-001 | Az állami egészségügyre fordított kiadásokat 2030-ra a GDP 7%-ára emeljük. _2030_ | :black_square_button: | |
| EGU-002 | Minden régióban szuperkórházat fejlesztünk. | :black_square_button: | |
| EGU-003 | Várólistákat 2027 végére csökkentjük: fekvőbeteg max 6 hó, járóbeteg max 2 hó. _2027_ | :black_square_button: | |
| EGU-004 | 2027 végére minden régióban a mentő 15 percen belül a helyszínre érkezik. _2027_ | :black_square_button: | |
| EGU-005 | Nővér-orvos arányt 1,6-ról 2,5-re emeljük. | :black_square_button: | |
| EGU-006 | Önálló Egészségügyi Minisztériumot hozunk létre. | :black_square_button: | |
| EGU-007 | 4 éven belül 10%-kal csökkentjük a daganatos megbetegedések számát. | :black_square_button: | |
| EGU-008 | Minden vidéki kórházat megtartunk. | :black_square_button: | |
| EGU-009 | 30 Mrd Ft/év egészségügyi ösztöndíjprogram hiányszakmákban. | :black_square_button: | |

### Oktatas (education, culture)

| ID | Promise | Status | Articles |
|---|---|---|---|
| OKT-001 | Önálló Oktatási Minisztériumot hozunk létre. | :black_square_button: | |
| OKT-002 | Tanköteles kor emelése 18 évre. | :black_square_button: | |
| OKT-003 | 25%-os béremelés a nevelést segítő dolgozóknak. | :black_square_button: | |
| OKT-004 | Megszüntetjük az állami tankönyv-monopóliumot. | :black_square_button: | |
| OKT-005 | Visszaállítjuk az egyetemek autonómiáját, megszüntetjük a KEKVA-modellt. | :black_square_button: | |
| OKT-006 | 2035-ig legalább egy magyar egyetemet a globális TOP 200-ba juttatunk. _2035_ | :black_square_button: | |
| OKT-007 | Visszaszerezzük az MCC-nek juttatott állami vagyont. | :black_square_button: | |
| OKT-008 | Az első alapdiploma megszerzését a lehető legszélesebb körben tandíjmentessé tesszük. | :black_square_button: | |
| OKT-009 | Magyar diákok újra részt vehessenek Erasmus és Horizon programokban. | :black_square_button: | |
| KULT-001 | 25%-os általános béremelés és lakhatási program a kulturális dolgozóknak. | :black_square_button: | |
| KULT-002 | Politikamentes kulturális irányítást biztosítunk. | :black_square_button: | |
| KULT-003 | Pártsemleges Nemzeti Sajtóalapot hozunk létre. | :black_square_button: | |

### Szocialis (pensions, child protection, family, equality)

| ID | Promise | Status | Articles |
|---|---|---|---|
| NYUG-001 | Megtartjuk a 13. és 14. havi nyugdíjat. | :black_square_button: | |
| NYUG-002 | Nyugdíjas SZÉP-kártya: évi 200 ezer Ft ill. 100 ezer Ft. | :black_square_button: | |
| NYUG-003 | Garantált minimum öregségi és rokkantsági nyugdíj: havi 120 ezer Ft. | :black_square_button: | |
| NYUG-004 | Duplájára emeljük az időskorúak járadékát. | :black_square_button: | |
| NYUG-005 | 50%-kal megemeljük az otthonápolási díjakat. | :black_square_button: | |
| NYUG-006 | Bevezetjük a Férfiak 40 programot (40 év szolgálat után korai nyugdíj). | :black_square_button: | |
| GYVD-001 | Feltárjuk az elmúlt évtizedek gyermekvédelmi bűncselekményeit. | :black_square_button: | |
| GYVD-002 | 20%-kal növeljük a gyermekvédelmi ágazat működési költségvetését. | :black_square_button: | |
| GYVD-003 | 25%-kal azonnal megemeljük a gyermekvédelmi dolgozók bérét. | :black_square_button: | |
| GYVD-004 | 2030-ra felújítjuk a gyermekotthonokat. _2030_ | :black_square_button: | |
| GYVD-005 | Eltöröljük az egyedülállók örökbefogadásának korlátozását. | :black_square_button: | |
| CSAL-001 | Duplájára emeljük a családi pótlékot. | :black_square_button: | |
| CSAL-002 | Duplájára emeljük a GYES-t és a GYET-et. | :black_square_button: | |
| CSAL-003 | Duplájára emeljük az anyasági támogatást. | :black_square_button: | |
| CSAL-004 | Az apaszabadság időtartamát 3 hétre emeljük, az állam fizeti. | :black_square_button: | |
| CSAL-005 | 25%-os általános béremelés a szociális szektorban. | :black_square_button: | |
| CSAL-006 | 700 ezer nehéz sorsú gyermeknek évi 100 ezer Ft iskolakezdési támogatás. | :black_square_button: | |
| CSAL-007 | Válás esetén nem kell visszafizetni a CSOK-ot. | :black_square_button: | |
| NOI-001 | Betartatjuk az egyenlő munkáért egyenlő bér elvét, bértranszparencia-törvényt hozunk. | :black_square_button: | |
| NOI-002 | Felszámoljuk a menstruációs szegénységet. | :black_square_button: | |
| ROMA-001 | Átalakítjuk a közmunkát, valódi átjárást biztosítunk a munkaerőpiacra. | :black_square_button: | |
| ROMA-002 | Megkezdjük a szegregált oktatás felszámolását. | :black_square_button: | |

### Kozlekedes (transport, energy, housing)

| ID | Promise | Status | Articles |
|---|---|---|---|
| KOZ-001 | 10 éven belül megfelezzük a vasúti járművek átlagéletkorát. | :black_square_button: | |
| KOZ-002 | Vasúti fővonalakon legalább 100 km/h átlagsebesség. | :black_square_button: | |
| KOZ-003 | 50%-ra növeljük a villamosított vasúti pályák arányát. | :black_square_button: | |
| KOZ-004 | Országos kátyúmentesítési program, megduplázzuk a közútfenntartási kiadásokat. | :black_square_button: | |
| KOZ-005 | Megépítjük az M200-M8-as és megkezdjük az M9-es déli gyorsforgalmi utat. | :black_square_button: | |
| KOZ-006 | Galvani-híd és Soroksári-Duna-híd Budapesten, új Tisza-híd Szegeden. | :black_square_button: | |
| KOZ-007 | A 35 éves autópálya-koncessziós szerződést felülvizsgáljuk, csökkentjük az útdíjakat. | :black_square_button: | |
| KOZ-008 | Egész napos, óránkénti InterCity 6 fő vonalon. | :black_square_button: | |
| KOZ-009 | Minden 500 fő feletti településen legalább napi 5 tömegközlekedési járat. | :black_square_button: | |
| KOZ-010 | Repülőtéri vasúti kapcsolat kiépítése Budapest belvárosával. | :black_square_button: | |
| ENR-001 | Megtartjuk és szociális alapon kiterjesztjük a rezsicsökkentést. | :black_square_button: | |
| ENR-002 | A magyar otthonok legalább 25%-ánál javítjuk az energiahatékonyságot 10 éven belül. | :black_square_button: | |
| ENR-003 | 2035-ig megszüntetjük az orosz energiafüggőséget. _2035_ | :black_square_button: | |
| ENR-004 | 2040-ig megduplázzuk a megújuló energia arányát. _2040_ | :black_square_button: | |
| ENR-005 | ~1000 milliárd Ft-ot fordítunk lakossági és vállalati energiakorszerűsítésre. | :black_square_button: | |
| ENR-006 | Évente 100 ezer lakás energetikai korszerűsítése. | :black_square_button: | |
| ENR-007 | Eltöröljük a szélerőművek telepítését akadályozó korlátozásokat. | :black_square_button: | |
| ENR-008 | Teljes körűen felülvizsgáljuk a PAKS II. projektet és finanszírozását. | :black_square_button: | |
| LAK-001 | Megduplázzuk a lakásépítések számát. | :black_square_button: | |
| LAK-002 | Több tízezer új bérlakást építünk. | :black_square_button: | |
| LAK-003 | Fiatalok számára legalább 50%-kal növeljük a kollégiumi férőhelyeket. | :black_square_button: | |
| LAK-004 | 20 ezer új férőhely korszerű nyugdíjasotthonokban. | :black_square_button: | |
| LAK-005 | Az évtized végére senki lakhelye ne legyen komfort nélküli. _2030_ | :black_square_button: | |

### Kornyezetvedelem (environment, waste, water, animal welfare)

| ID | Promise | Status | Articles |
|---|---|---|---|
| KRN-001 | Önálló környezetvédelmi minisztériumot hozunk létre. | :black_square_button: | |
| KRN-002 | Megduplázzuk a természetvédelmi kezelés és ellenőrzés kapacitását. | :black_square_button: | |
| KRN-003 | Felülvizsgáljuk az akkumulátorgyárak működését. | :black_square_button: | |
| KRN-004 | 2030-ra minden településen az egészségügyi határérték alá szorítjuk a légszennyezést. _2030_ | :black_square_button: | |
| KRN-005 | Évente 1 millió tonnával növeljük a szén-dioxid-nyelő kapacitást. | :black_square_button: | |
| KRN-006 | Zéró tolerancia a védett és Natura 2000 területeken történő jogellenes beépítésekre. | :black_square_button: | |
| HUL-001 | Felülvizsgáljuk a MOHU 35 éves hulladékkoncessziós szerződését. | :black_square_button: | |
| HUL-002 | 2030-ra legalább 55%-ra növeljük a települési hulladék újrahasznosítási arányát. _2030_ | :black_square_button: | |
| HUL-003 | 3 éven belül kitakarítjuk az országot (illegális lerakók felszámolása). | :black_square_button: | |
| VIZ-001 | Programot indítunk a Balaton megmentéséért. | :black_square_button: | |
| VIZ-002 | 2030-ig javítjuk vizeink minőségét, egyenlő hozzáférést biztosítunk. _2030_ | :black_square_button: | |
| VIZ-003 | A vízhálózati veszteséget 15-20%-ra csökkentjük. | :black_square_button: | |
| ALV-001 | Országos hatáskörű állatjóléti hatóságot hozunk létre. | :black_square_button: | |
| ALV-002 | Minden megyeszékhelyen minősített állatmenhelyet hozunk létre. | :black_square_button: | |
| ALV-003 | Országos ivartalanítási program. | :black_square_button: | |
| VID-001 | 10 falunként évente 1 milliárd Ft közösségi fejlesztési keret. | :black_square_button: | |
| VID-002 | Önálló Vidékfejlesztési Minisztériumot hozunk létre. | :black_square_button: | |

### Kulpolitika (foreign policy)

| ID | Promise | Status | Articles |
|---|---|---|---|
| KUL-001 | Brüsszelből hazahozzuk a befagyasztott uniós ezermilliárdokat. | :black_square_button: | |
| KUL-002 | Megállítjuk az ICC-ből való kilépést. | :black_square_button: | |
| KUL-003 | Nem támogatjuk Ukrajna gyorsított EU-felvételét; népszavazást tartunk róla. | :black_square_button: | |
| KUL-004 | Stratégiai partnerséget építünk az USA-val. | :black_square_button: | |

### Altalanos (general, defence, migration, demographics, digital)

| ID | Promise | Status | Articles |
|---|---|---|---|
| ALL-001 | Megszüntetjük a vármegye elnevezést és a főispáni pozíciót. | :black_square_button: | |
| ALL-002 | 2030-ra nullára csökkentjük a közigazgatási és piaci bérek közötti különbséget. _2030_ | :black_square_button: | |
| ALL-003 | Budapest-törvényt alkotunk a kormány-főváros partnerség kereteiről. | :black_square_button: | |
| ALL-004 | Visszaadjuk az elvont feladatokat, hatásköröket és forrásokat az önkormányzatoknak. | :black_square_button: | |
| BIZ-001 | Nem küldünk katonát az orosz-ukrán háborúba. | :black_square_button: | |
| BIZ-002 | Nem állítjuk vissza a sorkötelezettséget. | :black_square_button: | |
| BIZ-003 | 2035-ig a védelmi kiadásokat a NATO 5%-os szintjére emeljük. _2035_ | :black_square_button: | |
| BIZ-004 | Fokozatosan 150 ezer alá csökkentjük a regisztrált bűnesetek számát. | :black_square_button: | |
| MIG-001 | Fenntartjuk a déli határkerítést, megerősítjük a határvédelmet. | :black_square_button: | |
| MIG-002 | 2026. június 1-től megtiltjuk új munkavállalási engedélyek kiadását nem EU-s vendégmunkásoknak. _2026-06-01_ | :black_square_button: | |
| MIG-003 | Felszámoljuk a letelepedési kötvények rendszerét. | :black_square_button: | |
| DEM-001 | 2035-ig megállítjuk a népességfogyást, 2050-re tízmillió fölé. _2035_ | :black_square_button: | |
| DEM-002 | "Vár a hazád!" program: 8 éven belül hazahozunk 200 ezer külföldi magyart. | :black_square_button: | |
| DEM-003 | Születéskor várható élettartam 80 évre emelése. | :black_square_button: | |
| DIG-001 | Minden magyar állampolgárnak személyes MI-asszisztenst fejlesztünk. | :black_square_button: | |
| DIG-002 | Magyar nyelvi modellt építünk MI-alkalmazások fejlesztéséhez. | :black_square_button: | |
| DIG-003 | 50 ezer közszolgálati dolgozót képzünk gyakorlati MI-használatra. | :black_square_button: | |

### Promise status lifecycle

`made` → `in_progress` → `kept` / `broken` / `partially_kept` / `abandoned` / `modified`

Status changes are tracked with timestamps and evidence in an audit trail.

## CLI reference

```
tt filter   [--topic NAME] [--json]
tt rank     [--topic NAME] [--json]
tt fetch    [--topic NAME] [--threshold 0.4] [--force] [--json]
tt match    [--topic NAME] [--threshold 0.3] [--json]
tt html     [--topic NAME]
tt email    [--topic NAME] [--mode auto|ranked] [--dry-run]
tt query    [--history|--all-feeds] [--search TERM] [--fuzzy TERM] [--min-rank 0.3] [--since DATE] [--json]
tt purge    [--days N | --all]
tt export-recent [--days 60]
tt status   [--json]
tt config   show | get KEY | set KEY VALUE | validate
tt topic    list | show NAME | add NAME
tt promise  list | show ID | sync | status ID STATUS | link ID ENTRY_ID | stats
```

## Tech stack

- Python 3.10+
- SQLite (5 databases, FTS5 trigram + keyword indexes)
- Sentence-Transformers (paraphrase-multilingual-MiniLM-L12-v2)
- feedparser, trafilatura, requests, Click, PyYAML

## Setup

```
pip install -e .
tt status
```
