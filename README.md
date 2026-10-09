# Tisza Tracker

Hungarian government promise tracker. Monitors daily media coverage via RSS feeds, links articles to specific campaign promises made by the Tisza party, and derives each promise's status from what those articles report the government did.

**How to read the statuses.** A status is computed from all coverage since the government took office on 12 May 2026, not from the tone of the latest article:

- **Kept** and **partially kept** need delivery reported by two outlets.
- **In progress** needs one formal step (a bill submitted, a draft published for consultation), or an intention reported by two outlets.
- **Not yet started** means no such evidence has been found. The article matcher misses stories, so it is not proof that nothing happened.
- **Broken** is never assigned automatically. A reversal reported by two outlets is reviewed by a person first.

Criticism, opposition claims, expert opinion and the previous government's record do not count as evidence, and a headline without the article text is never enough for kept or broken. The rules are described under [Status rollup](#status-rollup).

<!-- PROMISES_START -->
### Promise tracker

Status legend: :white_check_mark: kept | :yellow_circle: partially kept | :hourglass_flowing_sand: in progress | :x: broken | :black_square_button: not yet started

Article badges: ✓ delivered | ◐ partly delivered | → formal step | ○ announced | ⏳ delayed | ⚠ reversal reported, not yet confirmed (what the article reports the government did; quotes are verbatim)

### Gazdasag (economy, tax, budget, agriculture)

| ID | Promise | Status | Articles |
|---|---|---|---|
| ADO-001 | 15%-ról 9%-ra csökkentjük a minimálbér adóját. | :hourglass_flowing_sand: | ○ [300 milliárdos kiesést okozna a Tisza-kormány szja-csökkentési terve](https://hvg.hu/gazdasag/20260512_niveus-tisza-szja-csokkentes-karman-andras-300-milliard-kieses) — "A Tisza-kormány frissen kinevezett pénzügyminisztere, Kármán András a parlamenti meghallgatásán bejelentést tett a személyi jövedelemadó ...", ○ [Vége a nagy béremeléseknek Magyarországon, szja-csökkentéssel kompenzálhat a ...](https://hvg.hu/360/20260930_bertargyalas-vkf-minimalber-garantalt-berminimum-mennyi-lesz-2027-szja-csokkentes) — "Jövőre a kormány csökkenti az szja-t, legnagyobb, 6 százalékpontos mértékben a minimálbérnél, cserébe a bruttó minimálbér bőven 10 százal...", ○ [Kármán András: Januártól jön az szja-csökkentés](https://telex.hu/gazdasag/2026/05/12/karman-andras-januar-szja-csokkentes) — "Kármán András frissen kinevezett pénzügyminiszter a Pénzügyi és Költségvetési Bizottság előtti meghallgatása után, kedden a Parlamentben ..." |
| ADO-002 | A mediánbér alatti 2,2 millió dolgozó adóját is csökkentjük. | :black_square_button: |  |
| ADO-003 | 1 milliárd Ft feletti vagyonra évi 1%-os vagyonadót vezetünk be. | :hourglass_flowing_sand: | → [Megjelent a vagyonadó-csomag - Ezzel indokolja a kormány az új adó bevezetését](https://www.portfolio.hu/gazdasag/20261006/megjelent-a-vagyonado-csomag-ezzel-indokolja-a-kormany-az-uj-ado-bevezeteset-867786) — "Magyar Péter kedd délután jelentette be a vagyonadó részletszabályait, a kata adózást érintő módosítások mellett.", → [Magyar Péter bejelentette, jön a vagyonadó és az egyszerűbb, de nagyobb terhe...](https://nepszava.hu/3334286_vagyonado-kata-magyar-peter-adotorvenyek-bejelentes) — "A vagyonadót 2027 januárjában vezetik be: az egymilliárd forint feletti vagyonokra évi egyszázalékos, a 100 milliárd forint feletti vagyo...", → [Szép csendben új adót vet ki Magyarországon a Tisza-kormány: több tízezer emb...](https://www.vg.hu/vilaggazdasag-magyar-gazdasag/2026/10/ado-vagyonado-exit-ado-tisza-karman-andras?utm_source=hirstart&utm_medium=referral&utm_campaign=hiraggregator) — "Az október 6-án társadalmi egyeztetésre bocsátott tervezet szerint az egymilliárd forint feletti nettó vagyonra évi 1 százalékos, a 100 m..." |
| ADO-004 | A vényköteles gyógyszerek áfáját 0%-ra csökkentjük. | :hourglass_flowing_sand: | ✓ [Fontos tájékoztatást adott ki a NAV és a Pénzügyminisztérium a szeptemberi gy...](https://index.hu/gazdasag/2026/08/25/penzugyminiszterium-adohatosag-afamentes-gyogyszerek-tajekoztatas/) — "szeptember 1-jétől áfamentessé válnak a kizárólag orvosi rendelvényre kiadható gyógyszerek, valamint a humán gyógyászati célú magisztráli...", → [Elszámíthatta magát a Tisza-kormány, kétséges, hogy szeptember elsejével való...](https://nepszava.hu/3330529_gyogyszer-afa-csokkentes-tisza-kormany-venykoteles-patikak) — "A Tisza egyik kampányígéretét - „a vényköteles gyógyszerek áfáját 0 százalékra csökkentjük” - valóra váltó törvénytervezetet augusztus 4-...", → [Gyógyszeráfa-csökkentés: januárra csúszik egy fontos könnyítés a betegeknek](https://mandiner.hu/belfold/2026/07/gyogyszerafa-csokkentes-januarra-csuszik-egy-fontos-konnyites-a-betegeknek) — "Szeptember 1-jétől áfamentessé teszi a kormány a vényköteles gyógyszereket" |
| ADO-005 | A tűzifa és az egészséges élelmiszerek áfáját 5%-ra mérsékeljük. | :black_square_button: | ○ [A nullás gyógyszeráfa csak bemelegítés a sokkal többe kerülő lakossági adócsö...](https://telex.hu/g7/kozelet/2026/07/23/afacsokkentes-ado-tisza-gyogyszer-tamogatas-tuzifa-elelmiszer) — "Magyar Péter ma úgy nyilatkozott, hogy a tűzifa áfáját 27 százalékról 5-re tervezik csökkenteni az idei télre, ez 10 milliárd forintba ke..." |
| ADO-006 | Széles körben újra elérhetővé tesszük a katát. | :hourglass_flowing_sand: | → [Magyar Péter bejelentette, jön a vagyonadó és az egyszerűbb, de nagyobb terhe...](https://nepszava.hu/3334286_vagyonado-kata-magyar-peter-adotorvenyek-bejelentes) — "A kormány döntött hétvégi ülésén a kisadózó vállalkozások tételes adója egyszerűsítéséről is.", → [Magyar Péter bejelentette a vagyonadó és a kata részleteit](https://telex.hu/gazdasag/2026/10/06/magyar-peter-bejelentes-kata-bovites-vagyonado) — "A kormány döntött a milliárdosok vagyonadójának részleteiről, a kata adózás kibővítéséről, és a profi labdarúgók és egyéb sportolók adókö...", → [Visszatérhet a kata régi előnye, de van egy bökkenő: a vagyonadó miatt már a ...](https://www.vg.hu/vilaggazdasag-magyar-gazdasag/2026/10/kata-vagyonado-magyar-kereskedelmi-es-iparkamara?utm_source=hirstart&utm_medium=referral&utm_campaign=hiraggregator) — "A szervezet csütörtöki közleménye szerint a kormány társadalmi egyeztetésre bocsátott katajavaslata több kamarai kezdeményezést is tartal..." |
| ADO-007 | Semmilyen munkabért terhelő adót nem emelünk. | :black_square_button: |  |
| AGR-001 | 5%-ra csökkentjük az egészséges élelmiszerek áfáját. | :black_square_button: |  |
| AGR-002 | Visszaállítjuk az élelmiszer-biztonsági hatóságok függetlenségét. | :black_square_button: |  |
| AGR-003 | Nem engedjük csökkenteni a magyar gazdáknak járó EU-támogatásokat. | :black_square_button: |  |
| AGR-004 | Felülvizsgáljuk a Földtörvényt, előnyben részesítjük a ténylegesen gazdálkodó fiatalokat. | :black_square_button: |  |
| GAZ-001 | Hazahozzuk és hatékonyan felhasználjuk a jelenleg befagyasztott uniós forrásokat. | :hourglass_flowing_sand: | ✓ [Bemondta Kármán András, mikor indulhatnak meg az uniós pénzek Magyarországra](https://www.portfolio.hu/unios-forrasok/20260530/bemondta-karman-andras-mikor-indulhatnak-meg-az-unios-penzek-magyarorszagra-840102) — "Megszületett az elmúlt évtized legjelentősebb pénzügyi megállapodása Magyarország és az Európai Bizottság között, ennek révén mintegy 16,...", ◐ [Magyar Péter a HVG-nek: Voltak pillanatok, amikor úgy reagáltam a bizottsági ...](https://hvg.hu/360/20260529_magyar-peter-unios-forrasok-europai-bizottsag-korrupcioellenes-csomag) — "Több hetes rendkívül intenzív tárgyalássorozat után az Európa Bizottság elnöke és a magyar miniszterelnök közös brüsszeli sajtótájékoztat...", ◐ [Pénzt adnak Magyarországnak, ha Magyar Péter lemond az orosz energiáról – bej...](https://www.vg.hu/vilaggazdasag-magyar-gazdasag/2026/06/magyarorszag-mondjon-le-az-orosz-energiarol-unios-bank?utm_source=hirstart&utm_medium=referral&utm_campaign=hiraggregator) — "A múlt heti uniós megállapodás, amely lehetővé teszi Magyarország számára, hogy hozzáférjen a korábban zárolt 16,4 milliárd euróhoz, lehe..." |
| GAZ-002 | Megfelezzük a vállalkozások adminisztrációs terheit. | :black_square_button: |  |
| GAZ-003 | Négy év alatt legalább másfélszeresére emeljük az innovációra fordított forrásokat. | :black_square_button: | ○ [Tanács Zoltán gyökeres állami és kormányzati változásokat jelentett be](https://www.portfolio.hu/gazdasag/20260917/tanacs-zoltan-gyokeres-allami-es-kormanyzati-valtozasokat-jelentett-be-863548) — "a kormány négy év alatt a GDP 2 százaléka fölé, hosszabb távon pedig 3 százalék környékére emelné a magyar kutatás-fejlesztési és innovác...", ○ [Tanács Zoltánék felráznák a magyar kutatást: több pénz, új missziók és teljes...](https://www.portfolio.hu/gazdasag/20260904/tanacs-zoltanek-felraznak-a-magyar-kutatast-tobb-penz-uj-missziok-es-teljes-rendszeratalakitas-jon-860558) — "A GDP jelenlegi mintegy 1,3 százalékáról 2030-ra 2, 2035-re pedig 3 százalékra emelné a kutatás-fejlesztésre és innovációra (KFI) fordíto..." |
| GAZ-004 | 2026. június 1-től felfüggesztjük az Európán kívüli vendégmunkások behozatalát. | :yellow_circle: | ✓ [Megjelent: szombattól nem adnak ki vendégmunkás-tartózkodási engedélyeket Mag...](https://hvg.hu/itthon/20260605_vendegmunkas-tartozkodasi-engedelyek) — "Magyarország nem ad ki ezentúl vendégmunkás-tartózkodási engedélyt, csak foglalkoztatási engedéllyel jöhetnek külföldi dolgozók – jelent ...", ◐ [Döntött Magyar Péter kormánya: azonnali hatállyal vége a jelenlegi vendégmunk...](https://www.portfolio.hu/gazdasag/20260605/dontott-magyar-peter-kormanya-azonnali-hatallyal-vege-a-jelenlegi-vendegmunkas-rendszernek-841496) — "A kormány pénteken kihirdetett rendelete lezárja a vendégmunkás-tartózkodási engedélyen alapuló külföldi munkavállalási csatornát: a jövő...", ◐ [Szigorít a kormány, új szabályok jönnek a külföldi munkavállalók foglalkoztat...](https://index.hu/belfold/2026/06/05/vendegmunkas-tartozkodasi-engedely-magyarorszag-kormanyrendelet-magyar-kozlony/) — "Magyarországon a jövőben nem adnak ki vendégmunkás-tartózkodási engedélyt külföldi munkavállalóknak, miután a kormány módosította a vonat..." |
| GAZ-005 | A K+F kiadást 2030-ra a GDP 2%-ára emeljük, majd közelítjük a 3%-ot. | :black_square_button: |  |
| GAZ-006 | Megerősítjük a versenyfelügyelet függetlenségét, és átalakítjuk a közbeszerzési rendszert. | :hourglass_flowing_sand: | → [Leállítják a túlárazásokat, teljes átalakítás és új vezető jön a Közbeszerzés...](https://index.hu/belfold/2026/09/04/karman-andras-kozbeszerzesi-es-ellatasi-foigazgatosag-foigazgato-palyazat/) — "Megnyílt a pályázat a Közbeszerzési és Ellátási Főigazgatóság főigazgatói pozíciójára – jelentette be Facebookon Kármán András pénzügymin...", → [„Egy kormány nem zárhat ki egy ajánlattevőt pusztán politikai alapon” – Vitéz...](https://444.hu/2026/08/07/egy-kormany-nem-zarhat-ki-egy-ajanlattevot-pusztan-politikai-alapon-vitezy-elmagyarazta-hogyan-nyerhetett-ismet-kozbeszerzest-meszaros-lorinc-cege?utm_source=rss_feed&utm_medium=rss&utm_campaign=rss_syndication) — "Arra utasította a GYSEV-et, hogy gyorsítsa fel saját sínhegesztési kapacitásának kiépítését, hogy 2027-től lényegesen kevésbé szoruljon k...", → [Kiszóríthatják az EU GDP-jének 15 százalékából Kínát](https://www.portfolio.hu/unios-forrasok/20260710/kiszorithatjak-az-eu-gdp-jenek-15-szazalekabol-kinat-848740) — "Hamarosan bemutatja az Európai Bizottság azt a közbeszerzési reformot, amely lehetővé tenné a tagállami hatóságok számára, hogy előnyben ..." |
| GAZ-007 | A diplomások arányát legalább az EU átlagára (43%) emeljük. | :black_square_button: |  |
| KOL-001 | 2030-ra teljesítjük a maastrichti kritériumokat. | :black_square_button: |  |
| KOL-002 | Előkészítjük az euró bevezetését, belátható céldátummal. | :hourglass_flowing_sand: | → [Tíz éve közelebb volt az euró bevezetéséhez Magyarország, mint most](https://telex.hu/g7/penz/2026/06/25/euro-bevezetes-maastrichti-kriterium-hiany-adossag-inflacio-kamat) — "Egyetlen feltételét sem teljesíti Magyarország az euró bevezetésének az Európai Bizottság idei konvergenciajelentése szerint, vagyis távo...", ○ [Elkezdtek felkészülni a befektetők az euró bevezetésére, így lehet most renge...](https://index.hu/gazdasag/2026/05/12/eurobevezetes-euro-euroovezet-forint-bevezetes-europai-unio/) — "A kormányzati tervek szerint a 2030-as időhorizont jelöli ki ezt a céldátumot.", ○ [Megszólalt az EKB első embere a magyar euróbevezetésről](https://www.portfolio.hu/gazdasag/20260724/megszolalt-az-ekb-elso-embere-a-magyar-eurobevezetesrol-851752) — "Christine Lagarde jegybankelnök úgy reagált, hogy üdvözli minden pozitív szándékot, de a folyamat a csatlakozni vágyó országtól függ." |
| KOL-003 | Átvilágítjuk a teljes költségvetést, megismerjük a titkosított szerződéseket. | :hourglass_flowing_sand: | → [Kormánydöntések: Átvilágítás a gyermekvédelemben, titkosított szerződések nyi...](https://24.hu/belfold/2026/05/13/kormanydontesek-atvilagitas-a-gyermekvedelemben-titkositott-szerzodesek-nyilvanossagra-hozasa-vagyonado/) — "Felülvizsgálják a titkosított nemzetközi szerződéseket és a titkosított kormányhatározatokat, ezeket nyilvánosságra is tervezik hozni." |
| KOL-004 | Újratárgyaljuk/felmondjuk az országnak kedvezőtlen, titkosított szerződéseket. | :black_square_button: |  |

### Korrupcio (anti-corruption, transparency)

| ID | Promise | Status | Articles |
|---|---|---|---|
| KOR-001 | Csatlakozunk az Európai Ügyészséghez (EPPO). | :white_check_mark: | ✓ [Nem a szuverenitást, hanem az állami szintre emelt korrupciót veszélyezteti a...](https://telex.hu/velemeny/2026/08/22/europai-ugyeszseg-eppo-csatlakozas-nemzeti-szuverenitas-korrupcio-eu) — "Különösebb hírverés nélkül jelent meg a sajtóban 2026. július 10. napján, hogy Magyarország csatlakozási kérelmét az Európai Ügyészség (E...", ✓ [Jövőre kezdheti meg működését Magyarországon az új korrupcióellenes szerv](https://index.hu/belfold/2026/09/29/magyarorszag-europai-ugyeszseg-eppo-europai-unio-korrupcio/) — "Ezt az Európai Bizottság június 10-én elfogadta, majd a határozat augusztus 2-án hatályba is lépett, így azóta Magyarország is hivatalosa...", → [Kármán Andrásnál és Görög Mártánál nem akárki járt: a románok rettegett korru...](https://www.vg.hu/kozelet/2026/09/karman-andras-gorog-marta-romanok-korrupcio-fougyesz?utm_source=hirstart&utm_medium=referral&utm_campaign=hiraggregator) — "Hivatalosan is megkezdődtek Magyarország Európai Ügyészséghez való csatlakozásának előkészületei, így akár már 2027-ben megjelenhet az or..." |
| KOR-002 | Létrehozzuk a Nemzeti Vagyonvisszaszerzési Hivatalt. | :white_check_mark: | ✓ [Orbán Árontól a Lánczi-féle Mikulásig: négy ügy az NVVH előtt](https://nepszava.hu/3333757_nvvh-korrupcio-vizsgalat-orban-aron-mikulas-negy-ugy) — "Az Unger Anna által vezetett Nemzeti Vagyonvisszaszerzési és Vagyonvédelmi Hivatal (NVVH) bejelentette, hogy négy, korábban más hatóságok...", ✓ [Vagyonvisszaszerzés: 60 ezer milliárd forintnyi közpénzt lophattak el Magyaro...](https://www.portfolio.hu/gazdasag/20260828/vagyonvisszaszerzes-60-ezer-milliard-forintnyi-kozpenzt-lophattak-el-magyarorszagon-iden-indul-az-elso-vizsgalat-859076) — "Unger Anna hangsúlyozta: személyes feladata a hivatal működésének elindítása lesz, a személyzet várhatóan 200 fős lesz.", ✓ [Várhat börtön a NER-vezérekre? Unger Anna a HVG-Címlapsztoriban](https://hvg.hu/itthon/20260915_hvg-cimlapsztori-unger-nehez-posony-vagyonvisszaszerzes) — "a Tisza-kormány által létrehozott Nemzeti Vagyonvisszaszerzési és Vagyonvédelmi Hivatal nemrég megválasztott elnökével, illetve Nehéz-Pos..." |
| KOR-003 | Kivizsgáljuk az elmúlt évek korrupciós botrányait (Paks II, MNB-alapítványok, MCC, Hatvanpuszta stb.). | :hourglass_flowing_sand: | ◐ [Büntetőeljárás indult Hatvanpuszta ügyében](https://www.portfolio.hu/gazdasag/20260827/buntetoeljaras-indult-hatvanpuszta-ugyeben-858634) — "A Fejér Vármegyei Rendőr-főkapitányság Gazdaságvédelmi Osztálya Tényi István feljelentése nyomán rendelte el a nyomozást, amelyet jelenle...", → [Indul az MNB-alapítványok vizsgálata, Matolcsy Györgyöt és fiát is a bizottsá...](https://nepszava.hu/3331642_mnb-alapitvanyok-parlamenti-vizsgalobizottsag) — "Megkezdi munkáját az MNB Működésével Kapcsolatos Visszaéléseit Feltáró Vizsgálóbizottság, a mai napon egyelőre várhatóan ügyrendi kérdése...", → [Tisza-kormány: fontos szavazás várható ma a parlamentben](https://www.portfolio.hu/gazdasag/20260828/tisza-kormany-fontos-szavazas-varhato-ma-a-parlamentben-858832) — "Pénteken megválasztották Unger Annát a Nemzeti Vagyonvisszaszerzési Hivatal vezetőjének." |
| KOR-004 | 20 évre visszamenőleg vagyonosodási vizsgálat képviselőkre, politikusokra és családtagjaikra. | :hourglass_flowing_sand: | → [A Tisza-kormány 20 évre visszamenőleg vizsgálná a politika vezetők vagyonosod...](https://nepszava.hu/3329635_a-tisza-kormany-20-evre-visszamenoleg-vizsgalna-a-politika-vezetok-vagyonosodasat) — "A Tisza-kormány az áfacsökkentés mellett elkezdett tárgyalni a Tisza egy másik fontos vállalását, a vagyonosodási vizsgálatok megindításá...", → [Két új elnökhelyettest kapott az Integritás Hatóság](https://hvg.hu/itthon/20260901_kivalasztottak-az-integritas-hatosag-uj-elnokhelyetteseit) — "Az augusztus 26-án hatályba lépett új szabályozás alapján a hatóság többek között kizárólagos hatáskörrel ellenőrzi a kiemelt közjogi és ...", ○ [Tisza-kormány: vizsgálat indulhat politikusok ellen](https://www.portfolio.hu/gazdasag/20260918/tisza-kormany-vizsgalat-indulhat-politikusok-ellen-863616) — "Magyar Péter vagyonosodási vizsgálatot helyezett kilátásba a politikai elit számára, valamint a 2027-es költségvetésben ígér döntést a ny..." |
| KOR-005 | Független Korrupciómegelőzési Felügyeletet hozunk létre. | :black_square_button: |  |
| KOR-006 | Jogi védelmet biztosítunk a bejelentőknek (whistleblower-védelem). | :black_square_button: |  |
| KOR-007 | Nemzeti Szerződéstárat hozunk létre (online, kereshető). | :black_square_button: |  |

### Igazsagszolgaltatas (rule of law, justice, civil society)

| ID | Promise | Status | Articles |
|---|---|---|---|
| CIV-001 | Az álcivil szervezetek finanszírozását azonnal leállítjuk. | :black_square_button: |  |
| CIV-002 | 2027-től jelentősen emeljük a civil szervezeteknek juttatott forrásokat. | :black_square_button: |  |
| CIV-003 | Nyilvános, kereshető online adatbázis a megítélt és elutasított támogatásokról. | :black_square_button: |  |
| JOG-001 | Két ciklusra korlátozzuk a miniszterelnöki mandátumot. | :black_square_button: |  |
| JOG-002 | Megszüntetjük a rendeleti kormányzást. | :hourglass_flowing_sand: | ✓ [Kormányalakítás: meglepetést ígért Magyar Péter a Karmelitából](https://www.portfolio.hu/gazdasag/20260515/kormanyalakitas-meglepetest-igert-magyar-peter-a-karmelitabol-836924) — "Jelentős fordulatot jelent a külpolitikában, hogy bekérették az orosz nagykövetet a Kárpátalját ért dróntámadások miatt, valamint megszűn..." |
| JOG-003 | Visszaállítjuk a közmédia függetlenségét, új médiatörvényt alkotunk. | :hourglass_flowing_sand: | ✓ [Kannibált foghattak Budapesten, elfogadták az új médiatörvényt – Newscast](https://hvg.hu/itthon/20260624_kannibalt-foghattak-budapesten-elfogadtak-az-uj-mediatorvenyt-newscast) — "Kannibált foghattak Budapesten, elfogadták az új médiatörvényt – Newscast", → [Hivatalos: vallott a Tisza, így alakítja át a közmédiát, minden megváltozik –...](https://www.vg.hu/kozelet/2026/06/kozmedia-tisza-mtva-atalakitas-tarr-zoltan-megszunik?utm_source=hirstart&utm_medium=referral&utm_campaign=hiraggregator) — "Az imént benyújtottuk a közmédia teljes átalakítására vonatkozó törvényjavaslatunkat. Ez a törvényjavaslat a független, objektív közmédia...", → [Jó iránynak tartják a közmédiáról szóló törvényjavaslatot, de Vona Gábor szer...](https://nepszava.hu/3325929_jo-iranynak-tartjak-a-kozmediarol-szolo-torvenyjavaslatot-de-vona-gabor-szerint-a-tisza-sunyi-volt) — "Pénteken nyújtották be a Tisza Párt képviselői, Hantosi István, Melléthei-Barna Márton és Kulcsár Krisztián a médiatörvény módosításáról ..." |
| JOG-004 | Kormányváltás után azonnal felfüggesztjük a közmédia hírszolgáltatását. | :black_square_button: |  |
| JOG-005 | Kivizsgáljuk a Pegasus-lehallgatási botrányt. | :black_square_button: |  |
| JOG-006 | Megszüntetjük a Szuverenitásvédelmi Hivatalt. | :white_check_mark: | ✓ [Megszavazták a Szuverenitásvédelmi Hivatal megszüntetését](https://telex.hu/belfold/2026/06/30/parlament-szavazas-szuverenitasvedelmi-hivatal-megszuntetes) — "Az Országgyűlés 135 igen szavazattal, 44 nem ellenében, 6 tartózkodás mellett a keddi rendkívüli ülésen megszavazta a Tisza Párt képvisel...", ✓ [Megszüntették a Szuverenitásvédelmi Hivatalt, Magyar Péter reformot ígért a v...](https://hvg.hu/itthon/20260701_megszuntettek-a-szuverenitasvedelmi-hivatalt-magyar-peter-reformot-igert-a-vizellatasban-newscast) — "Megszüntették a Szuverenitásvédelmi Hivatalt", ✓ [Orbán politikai furkósbotjának megszüntetéséről és a polgármesteri fizetések ...](https://hvg.hu/itthon/20260630_parlament-szuverenitasvedelmi-hivatal-lanczi-tamas-polgarmester-fizetes-szavazas-elo-kozvetites-percrol-percre) — "A Lánczi-féle Szuverenitásvédelmi Hivatal megszüntetéséről szavazott ma az Országgyűlés." |
| JOG-007 | Átláthatóbb, arányosabb választási rendszert alkotunk. | :hourglass_flowing_sand: | ○ [Élőben jött a bejelentés Magyar Pétertől: 2030-ban már új választási rendszer...](https://www.vg.hu/kozelet/2026/06/maygar-peter-felszolalas-orszaggyules-parlament?utm_source=hirstart&utm_medium=referral&utm_campaign=hiraggregator) — "a következő választásokat már egy arányosabb rendszerben rendezik meg Magyarországon.", ○ [Melléthei-Barna Márton: jön az új választási törvény, nem lesz alkotmányos vá...](https://www.portfolio.hu/gazdasag/20260716/mellethei-barna-marton-jon-az-uj-valasztasi-torveny-nem-lesz-alkotmanyos-valsaghelyzet-850010) — "az új alkotmány elfogadása, és várhatóan annak népszavazással történő megerősítése után a prioritások közt egy új választási törvény elfo..." |
| JOG-008 | Feloldjuk a titkosított 2000-es és 3000-es kormányhatározatokat. | :black_square_button: |  |
| JOG-009 | Létrehozzuk a Gyermekvédelmi Ombudsmant és a Betegjogi Ombudsmant. | :black_square_button: |  |
| JOG-010 | Államivá és nonprofit-tá tesszük a végrehajtást, megszüntetjük a végrehajtói kamarát. | :black_square_button: |  |

### Egeszsegugy (healthcare)

| ID | Promise | Status | Articles |
|---|---|---|---|
| EGU-001 | Az állami egészségügyre fordított kiadásokat 2030-ra a GDP 7%-ára emeljük. | :black_square_button: |  |
| EGU-002 | Minden régióban szuperkórházat fejlesztünk. | :black_square_button: |  |
| EGU-003 | Várólistákat 2027 végére csökkentjük: fekvőbeteg max 6 hó, járóbeteg max 2 hó. | :hourglass_flowing_sand: | → [Miniszteri biztost neveztek ki a közel harmincezres protézisműtéti várólisták...](https://www.portfolio.hu/gazdasag/20260717/miniszteri-biztost-neveztek-ki-a-kozel-harmincezres-protezismuteti-varolistak-csokkentesere-850534) — "Hegedűs Zsolt Csaba egészségügyi miniszter július 1-jei hatállyal Zahár Ákost nevezte ki az ortopédiai-traumatológiai várólisták csökkent...", → [Svéd Tamás államtitkár őszintén: Csodák nincsenek, négy év múlva sem lesz élv...](https://hvg.hu/itthon/20260623_hegedus-zsolt-egeszsegugy-atalakitasa-miniszterium-kivalasa-szakember-toborzas-konferencia-ebx) — "a miniszter továbbá bejelentette, hogy miniszteri biztosa lesz a sürgősségi ellátásnak (Bognár Zsolt gyermeksebész és sürgősségi szakorvo...", ○ [Fordulat jöhet az egészségügyben, sok beteget érinthet a kormány döntése](https://index.hu/belfold/2026/09/22/csipoprotezis-terdprotezis-mutet-egeszsegugy-varolista/) — "Hegedűs Zsolt egészségügyi miniszter az RTL Híradónak azt mondta, a kormány megszüntetné azt a szabályt, amely szerint a 35 fölötti testt..." |
| EGU-004 | 2027 végére minden régióban a mentő 15 percen belül a helyszínre érkezik. | :black_square_button: |  |
| EGU-005 | Nővér-orvos arányt 1,6-ról 2,5-re emeljük. | :black_square_button: |  |
| EGU-006 | Önálló Egészségügyi Minisztériumot hozunk létre. | :white_check_mark: | ✓ [Hegedűs Zsolt az újabb kánikula előtt bejelentette, 32 kórházból 18-ban már e...](https://nepszava.hu/3329916_hegedus-zsolt-egeszsegugy-kozpenzek-felhasznalasa-venykoteles-gyogyszerek-korhazi-fertozesek-szervezeti-atalakitas) — "A tárcavezető szerint a Tisza-kormány, az újonnan létrehozott Egészségügyi Minisztérium a felelősség áthárítása, a problémák eltakarása, ...", ✓ [Nagy átalakítás jön az egészségügyben és a gyógyszereknél, szűk keresztmetsze...](https://www.portfolio.hu/gazdasag/20260615/nagy-atalakitas-jon-az-egeszsegugyben-es-a-gyogyszereknel-szuk-keresztmetszet-marad-a-penz-az-uj-allamtitkar-beszelt-a-celokrol-843444) — "A Belügyminisztériumból kiváló egészségügyi szaktárca 158 szakmai munkatárssal indul, puritán működési modellben – ismertette Ilku Lívia,...", → [„Én kimondom: kórházakat kell bezárni” – a Magyar Orvosi Kamara elnöke szerin...](https://hvg.hu/itthon/20260528_almos-peter-ilku-livia-korhazbezaras-orvosok) — "Álmos Péter megérti, hogy még csak most áll fel az egészségügyi minisztérium, de úgy fogalmazott, hogy „miközben épül a ház, ég a tető”." |
| EGU-007 | 4 éven belül 10%-kal csökkentjük a daganatos megbetegedések számát. | :black_square_button: |  |
| EGU-008 | Minden vidéki kórházat megtartunk. | :black_square_button: | ○ [Kórházbezárásokban és a magánegészségügy helyzetbe hozásában gondolkodik a ti...](https://magyarnemzet.hu/belfold/2026/06/korhazbezaras-maganegeszsegugy-tisza-allamtitkar-sved-tamas?utm_source=hirstart&utm_medium=referral&utm_campaign=hiraggregator) — "Kórházbezárásokban és a magánegészségügy helyzetbe hozásában gondolkodik a tiszás államtitkár" |
| EGU-009 | 30 Mrd Ft/év egészségügyi ösztöndíjprogram hiányszakmákban. | :black_square_button: |  |

### Oktatas (education, culture)

| ID | Promise | Status | Articles |
|---|---|---|---|
| KULT-001 | 25%-os általános béremelés és lakhatási program a kulturális dolgozóknak. | :black_square_button: |  |
| KULT-002 | Politikamentes kulturális irányítást biztosítunk. | :black_square_button: |  |
| KULT-003 | Pártsemleges Nemzeti Sajtóalapot hozunk létre. | :black_square_button: |  |
| OKT-001 | Önálló Oktatási Minisztériumot hozunk létre. | :hourglass_flowing_sand: | ✓ [Az új oktatási tárca már le is számolt egy népszerű iskolaigazgatóval, indokl...](https://magyarnemzet.hu/belfold/2026/07/az-uj-oktatasi-tarca-mar-le-is-szamolt-egy-nepszeru-iskolaigazgatoval-indoklast-var-a-polgarmester?utm_source=hirstart&utm_medium=referral&utm_campaign=hiraggregator) — "Az új oktatási tárca már le is számolt egy népszerű iskolaigazgatóval, indoklást vár a polgármester" |
| OKT-002 | Tanköteles kor emelése 18 évre. | :black_square_button: |  |
| OKT-003 | 25%-os béremelés a nevelést segítő dolgozóknak. | :black_square_button: |  |
| OKT-004 | Megszüntetjük az állami tankönyv-monopóliumot. | :black_square_button: |  |
| OKT-005 | Visszaállítjuk az egyetemek autonómiáját, megszüntetjük a KEKVA-modellt. | :hourglass_flowing_sand: | → [Gyökeres változások jönnek az egyetemeken, Lannert Judit megkezdte a tárgyalá...](https://index.hu/belfold/2026/06/16/lannert-judit-egyeztetes-rektorok-kekvak-katz-sandor-felsooktatasi-allamtitkar/) — "Az oktatási és gyermekügyi miniszter közölte, hogy megkezdték a párbeszédet a közérdekű vagyonkezelő alapítványok (kekvák) rendszerének k...", → [Meglépi a tárca: szinte a teljes vezetést lecserélik a vitatott alapítványokn...](https://www.portfolio.hu/gazdasag/20260828/meglepi-a-tarca-szinte-a-teljes-vezetest-lecserelik-a-vitatott-alapitvanyoknal-magyarorszagon-859054) — "A kiválasztási folyamat végén összesen 168 pozíció betöltéséről született döntés, ami a testületi tagság 98 százalékos cseréjét jelenti.", → [A kormány belenyúl a NER párhuzamos valóságába: visszaveszik a kiszervezett K...](https://444.hu/2026/05/20/a-kormany-belenyul-a-ner-parhuzamos-valosagaba-visszaveszik-a-kiszervezett-kekva-kat?utm_source=rss_feed&utm_medium=rss&utm_campaign=rss_syndication) — "A módosítás a FIDESZ ideológiai hátországának legfontosabb intézményét, az MCC-t is érinti." |
| OKT-006 | 2035-ig legalább egy magyar egyetemet a globális TOP 200-ba juttatunk. | :black_square_button: |  |
| OKT-007 | Visszaszerezzük az MCC-nek juttatott állami vagyont. | :hourglass_flowing_sand: | → [Mennek a vesztőhelyre a közérdekű vagyonkezelők, döntött Magyar Péter](https://www.portfolio.hu/gazdasag/20260715/mennek-a-vesztohelyre-a-kozerdeku-vagyonkezelok-dontott-magyar-peter-849690) — "A kormányhatározat szerint július 31-ével 16 szervezet szűnik meg, mindegyik mellé elszámolási biztost rendeltek ki." |
| OKT-008 | Az első alapdiploma megszerzését a lehető legszélesebb körben tandíjmentessé tesszük. | :black_square_button: |  |
| OKT-009 | Magyar diákok újra részt vehessenek Erasmus és Horizon programokban. | :yellow_circle: | ✓ [Az Erasmusra vár az albérletpiac is](https://nepszava.hu/3324374_az-erasmusra-var-az-alberletpiac-is) — "A korábban befagyasztott uniós források feloldásának egyenes következménye, hogy újraindul az Erasmus program a magyar diákok számára, ez...", ✓ [Megszűnik a tanárképzés az NKE-n, nyilvánosak a kórházi fertőzésekre vonatkoz...](https://hvg.hu/itthon/20260907_megszunik-a-tanarkepzes-az-nke-n-nyilvanosak-a-korhazi-fertozesekre-vonatkozo-adatok-newscast) — "Visszatér az Erasmus-program.", ◐ [Lannert Judit: Visszatér az Erasmus a magyar egyetemekre](https://hvg.hu/itthon/20260904_lannert-judit-erasmus-program-magyar-egyetemek) — "Visszatér az Erasmus-program a magyar egyetemekre – jelentette be Lannert Judit oktatási és gyermekügyi miniszter a Facebookon." |

### Szocialis (pensions, child protection, family, equality)

| ID | Promise | Status | Articles |
|---|---|---|---|
| CSAL-001 | Duplájára emeljük a családi pótlékot. | :black_square_button: |  |
| CSAL-002 | Duplájára emeljük a GYES-t és a GYET-et. | :black_square_button: |  |
| CSAL-003 | Duplájára emeljük az anyasági támogatást. | :black_square_button: |  |
| CSAL-004 | Az apaszabadság időtartamát 3 hétre emeljük, az állam fizeti. | :black_square_button: |  |
| CSAL-005 | 25%-os általános béremelés a szociális szektorban. | :black_square_button: |  |
| CSAL-006 | 700 ezer nehéz sorsú gyermeknek évi 100 ezer Ft iskolakezdési támogatás. | :black_square_button: |  |
| CSAL-007 | Válás esetén nem kell visszafizetni a CSOK-ot. | :black_square_button: |  |
| GYVD-001 | Feltárjuk az elmúlt évtizedek gyermekvédelmi bűncselekményeit. | :black_square_button: |  |
| GYVD-002 | 20%-kal növeljük a gyermekvédelmi ágazat működési költségvetését. | :black_square_button: |  |
| GYVD-003 | 25%-kal azonnal megemeljük a gyermekvédelmi dolgozók bérét. | :black_square_button: |  |
| GYVD-004 | 2030-ra felújítjuk a gyermekotthonokat. | :black_square_button: |  |
| GYVD-005 | Eltöröljük az egyedülállók örökbefogadásának korlátozását. | :black_square_button: |  |
| NOI-001 | Betartatjuk az egyenlő munkáért egyenlő bér elvét, bértranszparencia-törvényt hozunk. | :black_square_button: |  |
| NOI-002 | Felszámoljuk a menstruációs szegénységet. | :black_square_button: |  |
| NYUG-001 | Megtartjuk a 13. és 14. havi nyugdíjat. | :black_square_button: |  |
| NYUG-002 | Nyugdíjas SZÉP-kártya: évi 200 ezer Ft ill. 100 ezer Ft. | :black_square_button: |  |
| NYUG-003 | Garantált minimum öregségi és rokkantsági nyugdíj: havi 120 ezer Ft. | :black_square_button: |  |
| NYUG-004 | Duplájára emeljük az időskorúak járadékát. | :black_square_button: |  |
| NYUG-005 | 50%-kal megemeljük az otthonápolási díjakat. | :black_square_button: |  |
| NYUG-006 | Bevezetjük a Férfiak 40 programot (40 év szolgálat után korai nyugdíj). | :black_square_button: |  |
| ROMA-001 | Átalakítjuk a közmunkát, valódi átjárást biztosítunk a munkaerőpiacra. | :black_square_button: |  |
| ROMA-002 | Megkezdjük a szegregált oktatás felszámolását. | :black_square_button: |  |

### Kozlekedes (transport, energy, housing)

| ID | Promise | Status | Articles |
|---|---|---|---|
| ENR-001 | Megtartjuk és szociális alapon kiterjesztjük a rezsicsökkentést. | :black_square_button: |  |
| ENR-002 | A magyar otthonok legalább 25%-ánál javítjuk az energiahatékonyságot 10 éven belül. | :black_square_button: |  |
| ENR-003 | 2035-ig megszüntetjük az orosz energiafüggőséget. | :hourglass_flowing_sand: | → [Elstartolt a Portfolio Energy Investment Forum 2026 – a magyar energetika leg...](https://www.portfolio.hu/gazdasag/20261008/elstartolt-a-portfolio-energy-investment-forum-2026-a-magyar-energetika-legfontosabb-kerdesei-kerulnek-teritekre-868162) — "Magyarország október 1-jén sikeresen csatlakozott az európai kiegyenlítő energia szabályozási platformokhoz, megteremtve annak lehetőségé...", ○ [Erre várt Kapitány István, Ursula von der Leyen megadta neki a zöld jelzést: ...](https://www.vg.hu/nemzetkozi-gazdasag/2026/09/ursula-von-der-leyen-ensz-klimaugyi-ules-orosz-foldgaz?utm_source=hirstart&utm_medium=referral&utm_campaign=hiraggregator) — "Ursula von der Leyen részt vett az ENSZ klímaügyi ülésén, ahol felszólalásában kijelentette, hogy az Európai Unió 2027-re teljesen leváli...", ○ [Hidegzuhany, kimondta a szakértő: Magyarországnak fel kell készülnie az orosz...](https://www.vg.hu/vilaggazdasag-magyar-gazdasag/2026/10/orosz-gaz-importtilalom-europai-unio-2027-ellatasi-lanc?utm_source=hirstart&utm_medium=referral&utm_campaign=hiraggregator) — "Magyarország 2027 őszére orosz földgáz nélkül is biztosítani tudja az ország ellátását – jelentette ki Kapitány István gazdasági és energ..." |
| ENR-004 | 2040-ig megduplázzuk a megújuló energia arányát. | :black_square_button: |  |
| ENR-005 | ~1000 milliárd Ft-ot fordítunk lakossági és vállalati energiakorszerűsítésre. | :hourglass_flowing_sand: | → [Fontos bejelentést tett Kapitány István – példátlanul nagy energetikai progra...](https://www.portfolio.hu/unios-forrasok/20260625/fontos-bejelentest-tett-kapitany-istvan-peldatlanul-nagy-energetikai-programot-inditanak-845662) — "Megnyílik az a pályázat, amelynek keretében példátlan léptékű, 1,5 milliárd eurós fejlesztési program indul európai uniós forrásokból a m..." |
| ENR-006 | Évente 100 ezer lakás energetikai korszerűsítése. | :black_square_button: |  |
| ENR-007 | Eltöröljük a szélerőművek telepítését akadályozó korlátozásokat. | :hourglass_flowing_sand: | → [Majdnem eltűnt, most mégis az egyik legfelkapottabb beruházás lehet Magyarors...](https://www.portfolio.hu/uzlet/20260725/majdnem-eltunt-most-megis-az-egyik-legfelkapottabb-beruhazas-lehet-magyarorszagon-851398) — "A Gazdasági és Energetikai Minisztérium 2030 végéig összesen 4 000 megawattnyi hálózati csatlakozási lehetőséget kíván biztosítani az új ..." |
| ENR-008 | Teljes körűen felülvizsgáljuk a PAKS II. projektet és finanszírozását. | :black_square_button: |  |
| KOZ-001 | 10 éven belül megfelezzük a vasúti járművek átlagéletkorát. | :black_square_button: | ○ [Új tram-trainek vidéken, BZ-ket leváltó akkus motorvonatok, modernebb és gyor...](https://telex.hu/belfold/2026/07/22/baross-gabor-vasutfejlesztesi-terv-magyar-peter-vitezy-david) — "Vitézy Dávid vállalta, hogy a Baross Gábor-terv alapján tíz éven belül megfelezik a vasúti járművek átlagéletkorát, a vonalak fejlesztésé..." |
| KOZ-002 | Vasúti fővonalakon legalább 100 km/h átlagsebesség. | :black_square_button: |  |
| KOZ-003 | 50%-ra növeljük a villamosított vasúti pályák arányát. | :black_square_button: |  |
| KOZ-004 | Országos kátyúmentesítési program, megduplázzuk a közútfenntartási kiadásokat. | :black_square_button: |  |
| KOZ-005 | Megépítjük az M200-M8-as és megkezdjük az M9-es déli gyorsforgalmi utat. | :black_square_button: |  |
| KOZ-006 | Galvani-híd és Soroksári-Duna-híd Budapesten, új Tisza-híd Szegeden. | :black_square_button: |  |
| KOZ-007 | A 35 éves autópálya-koncessziós szerződést felülvizsgáljuk, csökkentjük az útdíjakat. | :black_square_button: |  |
| KOZ-008 | Egész napos, óránkénti InterCity 6 fő vonalon. | :hourglass_flowing_sand: | → [Vitézy Dávid: Ausztria segítette ki hazánkat a nyári utazási főszezonban](https://www.portfolio.hu/uzlet/20260621/vitezy-david-ausztria-segitette-ki-hazankat-a-nyari-utazasi-foszezonban-844664) — "A helyzet hosszú távú megoldása érdekében az új kormány a frissen megnyílt uniós forrásokból 35 új InterCity-motorvonat beszerzését indít...", → [Vitézy Dávid: Legalább 35 új InterCity-motorvonatot tudunk beszerezni](https://telex.hu/belfold/2026/06/03/vitezy-david-35-uj-intercity-motorvonat-beszerzes-mav-flottacsere-unios-forrasok-felszabaditasa) — "Legalább 35 új InterCity-motorvonatot tud beszerezni a MÁV az Európai Bizottsággal kötött 16,4 milliárd eurós uniós megállapodás eredmény..." |
| KOZ-009 | Minden 500 fő feletti településen legalább napi 5 tömegközlekedési járat. | :black_square_button: |  |
| KOZ-010 | Repülőtéri vasúti kapcsolat kiépítése Budapest belvárosával. | :black_square_button: |  |
| LAK-001 | Megduplázzuk a lakásépítések számát. | :black_square_button: |  |
| LAK-002 | Több tízezer új bérlakást építünk. | :black_square_button: |  |
| LAK-003 | Fiatalok számára legalább 50%-kal növeljük a kollégiumi férőhelyeket. | :black_square_button: |  |
| LAK-004 | 20 ezer új férőhely korszerű nyugdíjasotthonokban. | :black_square_button: |  |
| LAK-005 | Az évtized végére senki lakhelye ne legyen komfort nélküli. | :black_square_button: |  |

### Kornyezetvedelem (environment, waste, water, animal welfare)

| ID | Promise | Status | Articles |
|---|---|---|---|
| ALV-001 | Országos hatáskörű állatjóléti hatóságot hozunk létre. | :black_square_button: |  |
| ALV-002 | Minden megyeszékhelyen minősített állatmenhelyet hozunk létre. | :black_square_button: |  |
| ALV-003 | Országos ivartalanítási program. | :black_square_button: |  |
| HUL-001 | Felülvizsgáljuk a MOHU 35 éves hulladékkoncessziós szerződését. | :hourglass_flowing_sand: | → [Vitézy Dávid: a kekvák vagyona visszakerül az államhoz](https://www.portfolio.hu/unios-forrasok/20260605/vitezy-david-a-kekvak-vagyona-visszakerul-az-allamhoz-841442) — "Bejelentették a vagyonnyilatkozati rendszer szigorítását, a magántőkealapok végső tulajdonosainak átláthatóvá tételét, valamint a Budapes..." |
| HUL-002 | 2030-ra legalább 55%-ra növeljük a települési hulladék újrahasznosítási arányát. | :black_square_button: |  |
| HUL-003 | 3 éven belül kitakarítjuk az országot (illegális lerakók felszámolása). | :black_square_button: |  |
| KRN-001 | Önálló környezetvédelmi minisztériumot hozunk létre. | :black_square_button: |  |
| KRN-002 | Megduplázzuk a természetvédelmi kezelés és ellenőrzés kapacitását. | :black_square_button: |  |
| KRN-003 | Felülvizsgáljuk az akkumulátorgyárak működését. | :hourglass_flowing_sand: | → [Felfüggesztik a kínai Semcorp tevékenységét Debrecenben, a fideszes polgármes...](https://nepszava.hu/3327058_semcorp-debrecen-felfuggesztes-pogarmester-taltos-szikra-mozgalom) — "„A környezetvédelmi hatóság felfüggeszti a Semcorp tevékenységét. Nincs kivétel. A szabályok betartása mindenkire kötelező”", → [A debreceni CATL szabálytalanul engedett a csatornába zöld folyadékot, megbír...](https://nepszava.hu/3324923_debreceni-akkumulatorgyar-catl-szabalytalansag-zold-folyadek-kormanyhivatal-birsag) — "Szabálytalanul engedtek a csatornába zöld színű, folyékony hulladékot, ezért CATL debreceni akkumulátorgyára ellen eljárást indított a Ha...", ○ [A kormány keresztbefekszik a CATL-akkugyár debreceni bővítésének](https://hvg.hu/gazdasag/20260531_tarkanyi-zsolt-catl-akkugyar-debrecen-bovites) — "Egyúttal kitért arra is, hogy az új kabinet az eddigieknél szigorúbban fogja szabályozni az akkuipar működését, melynek részeként a hatós..." |
| KRN-004 | 2030-ra minden településen az egészségügyi határérték alá szorítjuk a légszennyezést. | :black_square_button: |  |
| KRN-005 | Évente 1 millió tonnával növeljük a szén-dioxid-nyelő kapacitást. | :black_square_button: |  |
| KRN-006 | Zéró tolerancia a védett és Natura 2000 területeken történő jogellenes beépítésekre. | :hourglass_flowing_sand: | → [Újabb részletek derültek ki a Velencei-tó kormányzati megmentéséről, Gajdos L...](https://www.portfolio.hu/gazdasag/20260717/ujabb-reszletek-derultek-ki-a-velencei-to-kormanyzati-megmenteserol-gajdos-laszlo-mar-felkerte-a-szakertoi-csapatot-850302) — "Újabb részletek derültek ki a Velencei-tó kormányzati megmentéséről, Gajdos László már felkérte a szakértői csapatot" |
| VID-001 | 10 falunként évente 1 milliárd Ft közösségi fejlesztési keret. | :black_square_button: |  |
| VID-002 | Önálló Vidékfejlesztési Minisztériumot hozunk létre. | :black_square_button: |  |
| VIZ-001 | Programot indítunk a Balaton megmentéséért. | :black_square_button: |  |
| VIZ-002 | 2030-ig javítjuk vizeink minőségét, egyenlő hozzáférést biztosítunk. | :black_square_button: |  |
| VIZ-003 | A vízhálózati veszteséget 15-20%-ra csökkentjük. | :black_square_button: |  |

### Kulpolitika (foreign policy)

| ID | Promise | Status | Articles |
|---|---|---|---|
| KUL-001 | Brüsszelből hazahozzuk a befagyasztott uniós ezermilliárdokat. | :black_square_button: |  |
| KUL-002 | Megállítjuk az ICC-ből való kilépést. | :black_square_button: |  |
| KUL-003 | Nem támogatjuk Ukrajna gyorsított EU-felvételét; népszavazást tartunk róla. | :hourglass_flowing_sand: | → [Magyarország megakadályozta, hogy az EU egységes álláspontot rögzítsen Ukrajn...](https://444.hu/2026/06/24/magyarorszag-megakadalyozta-hogy-az-eu-egyseges-allaspontot-rogzitsen-ukrajna-csatlakozasarol?utm_source=rss_feed&utm_medium=rss&utm_campaign=rss_syndication) — "Magyarország kedden megakadályozta, hogy az EU 27 tagállama nevében levél menjen az Európai Tanácshoz és a Bizottsághoz, amely a tagállam...", → [A magyar kormány befékezett Ukrajna csatlakozásánál](https://telex.hu/kulfold/2026/06/24/eu-europai-unio-tanacsa-ukrajna-moldova-csatlakozas) — "Amíg a csúcstalálkozó következtetései politikai állásfoglalások, a Politico cikke szerint a kormány a gyakorlatban is befékezett: kedden ...", ○ [Magyar Péter bejelentette, véget vet a hazánkat sújtó napi egymillió eurós  m...](https://www.portfolio.hu/unios-forrasok/20260618/magyar-peter-bejelentette-veget-vet-a-hazankat-sujto-napi-egymillio-euros-migracios-buntetesnek-844252) — "Ukrajna csatlakozásával kapcsolatban a kormány az érdemalapú bővítés mellett áll ki, és nem támogatja az összes tárgyalási fejezet egyide..." |
| KUL-004 | Stratégiai partnerséget építünk az USA-val. | :hourglass_flowing_sand: | → [Orbán Viktor megoldotta – a tiszások most kilincselnek Amerikában az orosz ol...](https://magyarnemzet.hu/kulfold/2026/09/szankciomentessegert-kilincsel-a-tisza-amerikaban?utm_source=hirstart&utm_medium=referral&utm_campaign=hiraggregator) — "A szankciós törvény arra hatalmazza fel az elnököt, hogy akár 100 százalékos vámot vessen ki azon országok amerikai exportjára, amelyek a..." |

### Altalanos (general, defence, migration, demographics, digital)

| ID | Promise | Status | Articles |
|---|---|---|---|
| ALL-001 | Megszüntetjük a vármegye elnevezést és a főispáni pozíciót. | :black_square_button: |  |
| ALL-002 | 2030-ra nullára csökkentjük a közigazgatási és piaci bérek közötti különbséget. | :black_square_button: |  |
| ALL-003 | Budapest-törvényt alkotunk a kormány-főváros partnerség kereteiről. | :black_square_button: |  |
| ALL-004 | Visszaadjuk az elvont feladatokat, hatásköröket és forrásokat az önkormányzatoknak. | :black_square_button: |  |
| BIZ-001 | Nem küldünk katonát az orosz-ukrán háborúba. | :black_square_button: |  |
| BIZ-002 | Nem állítjuk vissza a sorkötelezettséget. | :black_square_button: |  |
| BIZ-003 | 2035-ig a védelmi kiadásokat a NATO 5%-os szintjére emeljük. | :hourglass_flowing_sand: | → [Mészáros Krisztián elárulta, miben lehet Magyarország NATO-szerepe](https://www.portfolio.hu/unios-forrasok/20260714/meszaros-krisztian-elarulta-miben-lehet-magyarorszag-nato-szerepe-849474) — "Az új kabinet azóta egy kormányhatározatot is elfogadott arról, hogyan lehet ezt fenntartható pályán elérni." |
| BIZ-004 | Fokozatosan 150 ezer alá csökkentjük a regisztrált bűnesetek számát. | :black_square_button: |  |
| DEM-001 | 2035-ig megállítjuk a népességfogyást, 2050-re tízmillió fölé. | :black_square_button: |  |
| DEM-002 | "Vár a hazád!" program: 8 éven belül hazahozunk 200 ezer külföldi magyart. | :black_square_button: |  |
| DEM-003 | Születéskor várható élettartam 80 évre emelése. | :black_square_button: |  |
| DIG-001 | Minden magyar állampolgárnak személyes MI-asszisztenst fejlesztünk. | :black_square_button: |  |
| DIG-002 | Magyar nyelvi modellt építünk MI-alkalmazások fejlesztéséhez. | :black_square_button: |  |
| DIG-003 | 50 ezer közszolgálati dolgozót képzünk gyakorlati MI-használatra. | :black_square_button: |  |
| MIG-001 | Fenntartjuk a déli határkerítést, megerősítjük a határvédelmet. | :black_square_button: |  |
| MIG-002 | 2026. június 1-től megtiltjuk új munkavállalási engedélyek kiadását nem EU-s vendégmunkásoknak. | :hourglass_flowing_sand: | ◐ [A vendégmunkáskérdésről még szeptemberben újabb egyeztetés jöhet](https://www.portfolio.hu/gazdasag/20260920/a-vendegmunkaskerdesrol-meg-szeptemberben-ujabb-egyeztetes-johet-863738) — "Mint ismert, június 6-án a kormányzat leállította az új vendégmunkás-tartózkodási engedélyek kiadását.", → [Szinte még ki se mondták, máris lecsapott a vendégmunkásokra a kormány](https://www.vg.hu/vilaggazdasag-magyar-gazdasag/2026/06/vendegmunkas-magyar-peter-munkaero-kolcsonzo?utm_source=hirstart&utm_medium=referral&utm_campaign=hiraggregator) — "A Magyar Közlönyben olvasható jogszabály már kihirdetését követő napon hatályba lép, gátat vetve ezzel a munkaerő-kölcsönző cégek által a..." |
| MIG-003 | Felszámoljuk a letelepedési kötvények rendszerét. | :black_square_button: |  |

<!-- PROMISES_END -->

## Pipeline

```
tt filter  →  tt rank  →  tt fetch  →  tt match  →  tt classify  →  tt report
  (RSS)      (scoring)   (full text)  (promises)    (LLM evidence)  (README table)
```

- **filter** — fetch RSS feeds, apply per-topic regex patterns to title + summary
- **rank** — compute semantic similarity (Sentence-Transformers) between topic query and article titles
- **fetch** — store RSS summaries for all ranked entries; download full article text (via trafilatura) for entries above `fetch_threshold`
- **match** — link articles to government promises using per-promise regex pre-filter + semantic scoring against title + summary
- **classify** — two-pass LLM evidence extraction on each matched article, then a status rollup (see below)
- **report** — render the promise tracker markdown table into README.md

### LLM classification (`tt classify`)

Semantic similarity catches *topically related* articles, but many of those only
glance off the promise, and a critical tone is not a broken promise. Two passes
through an OpenAI-compatible model, cached per `prompt_version`:

1. **Relevance gate** (`model`, default `gpt-5-nano`) — title + summary only.
   Returns `{relevant, confidence, reason}`. Articles that fail the gate are
   recorded with signal `none` without calling pass 2.
2. **Evidence extraction** (`pass2_model`, default `gpt-5-mini` at low
   reasoning effort) — the full article text. An article that passes the gate
   without a stored body has it downloaded first. The model is told who
   governs and since when, and the article's outlet, publication date and the
   promise's deadline. It does not pick a verdict; it reports *who did what*:
   `actor`, `evidence_type` (delivered / formal step / stated intent / delay /
   reversal / no signal), `scope`, `event_date` and a verbatim `quote`.

Code then turns that record into a **signal**
(`kept | partial | step | intent | delay | reversal | none`) under fixed rules:

- only acts of the current government count (or of a counterparty such as the
  European Commission whose decision delivers or blocks the outcome); opinions,
  opposition claims and the previous government's record are `none`;
- nothing published or dated before the government took office counts;
- the quote must be found verbatim in the article, otherwise the evidence is
  dropped;
- a headline without a body never yields `kept`, `partial` or `reversal`.

Results are stored in `promises.db` (`llm_classifications` table). Re-running
`tt classify` only processes new links, links whose extraction is from an older
prompt, and links whose last attempt failed (up to `max_attempts` runs). The gate
is asked once per link: its rejections stay, and an article that passed goes
straight to extraction when it is re-read. Use `--force` to redo everything
including the gate, `--limit N` for testing, or `--promise ID` to scope to one
promise.

### Status rollup

After classification the status of every promise is recomputed from **all** of
its evidence since the government took office. There is no sliding window and
no confidence threshold; what counts is the kind of evidence and how many
distinct outlets report it:

| Status | Needs |
|---|---|
| kept | delivery reported by 2 outlets |
| partially kept | full or partial delivery reported by 2 outlets |
| in progress | 1 formal step, or an intention reported by 2 outlets |
| not started | anything less |
| broken | never set automatically (see below) |

Some findings are not published but listed by `tt promise review` for a human
decision:

- a government **reversal** reported by 2 outlets with no later progress
  (confirm with `tt promise status ID broken --evidence "..."`);
- a **deadline** that lapsed more than `deadline_grace_days` ago with no
  delivery on record — the matcher may simply have missed the story;
- delivery reported by a **single** outlet;
- a manual status that disagrees with the evidence.

A status set with `tt promise status` is **locked**: the rollup leaves it alone
until `tt promise unlock ID`. Every automatic change is written to the history
with the IDs of the articles it rests on. A promise is not re-rated while some
of its links still wait to be classified.

Each promise has a `kind` in its YAML:

- `one_off` — a deliverable (a law, an institution, a payment); done once it exists.
- `target` — a measurable outcome due by `deadline` or by the end of the term.
  It cannot be judged broken before that date.
- `ongoing` — a standing commitment ("we will not…", "we keep…"). It is never
  `kept` before the term ends; evidence of compliance keeps it in progress.

Without a `kind`, a year-only deadline means `target` and anything else `one_off`.

### Checking a prompt or model change (`tt eval`)

`src/tisza_tracker/system/eval/labelled_set.json` holds 99 hand-labelled
promise–article pairs and 8 synthetic articles (four of them genuine reversals,
which the real corpus does not contain). `tt eval` runs the extraction over them
and fails if more than one real article reads as a reversal, a synthetic reversal
is missed, or agreement with the labels drops below 85%. `tt eval --recorded`
scores the stored model outputs without API calls; the test suite does the same.
Article bodies are not in the repository: they are read from
`<data dir>/eval_bodies/`, then `article_text.db`, then the article URL.

### Report behaviour

`tt report` only shows the top **`top_n_in_report`** articles per promise
(default 3), ranked by strength of evidence, then LLM confidence, then semantic
score. A reversal report ranks last until the promise has been marked broken.
Articles with signal `none` are excluded entirely. Each article gets a
badge for what it reports (`✓` delivered, `◐` partly delivered, `→` formal step,
`○` announced, `⏳` delayed, `⚠` reversal reported but not confirmed) and the
Hungarian sentence the model cited, which is only shown when it was found
verbatim in the article.

## Databases

- `all_feed_entries.db` — global RSS archive for deduplication
- `papers.db` — current run processing (filter → rank → match)
- `matched_entries_history.db` — long-term archive of matched articles
- `article_text.db` — extracted article body text (separate to keep main DBs lean)
- `promises.db` — promise definitions, status tracking, article-promise links, LLM evidence

`tt filter` writes a timestamped backup of `matched_entries_history.db` before
purging (keeps the 3 most recent). The RSS dedup archive
(`all_feed_entries.db`) is not backed up — it is large and the pipeline
rebuilds it from feeds.

## Configuration

Main config: `config.yaml` (feeds, defaults, database paths)

Topic configs: `topics/*.yaml` (per-topic regex patterns, ranking queries, feed selection)

Promise configs: `promises/*.yaml` (per-promise kind, deadline, regex filter + semantic ranking query)

At run time everything is read from the data directory (`~/.tisza_tracker/config/`, or
`$TISZA_TRACKER_DATA_DIR/config/`), which is seeded once from
`src/tisza_tracker/system/config/`. Later edits to the copies in the repository have to
be copied there to take effect.

### Key defaults

- `rank_threshold: 0.25` — minimum score to display in output
- `fetch_threshold: 0.40` — minimum score to download full article text
- `ranking_negative_penalty: 0.20` — penalty for negative query terms (sport, weather, celebrity)
- `time_window_days: 30` — RSS entry age filter

### LLM classification config (`llm_classification:` block)

- `model` — OpenAI-compatible model for the relevance gate (default `gpt-5-nano`)
- `pass2_model` — model for the evidence extraction (default `gpt-5-mini`)
- `pass2_reasoning_effort: "low"` — set to `null` for endpoints that reject the parameter
- `base_url` — override to point at a local endpoint; falls back to `OPENAI_BASE_URL` env or OpenAI
- `api_key_env` / `api_key_file` — key source; defaults to `OPENAI_API_KEY` env var
- `max_candidates_per_promise: 20` — cap links sent to the LLM per promise per run (cost control)
- `top_n_in_report: 3` — articles shown per promise in the tracker table
- `prompt_version: "v1"` — bump to invalidate cached extractions (gate results are kept;
  `--force` redoes those too). A prompt change in the code invalidates them by itself.
- `max_attempts: 3` — runs after which a link that keeps failing is given up
- `min_body_chars: 300` — a shorter body counts as headline-only
- `pass1_enabled` / `pass2_enabled` — toggle either pass independently
- `rollup.min_outlets: 2` — outlets needed for kept, partially kept and a reversal
- `rollup.deadline_grace_days: 30`
- `rollup.auto_publish_broken: false` — `true` publishes a corroborated reversal as broken
  without review

The top-level `government:` block (`election_date`, `took_office`) sets the date
before which nothing counts as evidence.

## RSS feeds

13 active Hungarian media sources across the political spectrum:

- Independent: Telex, 444.hu, HVG, Nepszava
- Large portals: Index, 24.hu, Hirado.hu
- Business: Portfolio, Vilaggazdasag
- Right-leaning: Magyar Nemzet, Mandiner, 168.hu
- English-language: Hungary Today, Budapest Times

### Promise status lifecycle

`made` → `in_progress` → `kept` / `broken` / `partially_kept` / `abandoned` / `modified`

The rollup assigns `made`, `in_progress`, `partially_kept` and `kept`; `broken`,
`abandoned` and `modified` are set by hand. Status changes are tracked with
timestamps, source (rollup or manual), evidence and article IDs in an audit trail.

## CLI reference

```
tt filter   [--topic NAME] [--json]
tt rank     [--topic NAME] [--json]
tt fetch    [--topic NAME] [--threshold 0.4] [--force] [--json]
tt match    [--topic NAME] [--threshold 0.3] [--json]
tt classify [--force] [--limit N] [--promise ID] [--skip-rollup] [--json]
tt eval     [--recorded] [--model NAME] [--limit N] [--json]
tt report   [--readme PATH] [-o FILE]
tt query    [--history|--all-feeds] [--search TERM] [--fuzzy TERM] [--min-rank 0.3] [--since DATE] [--json]
tt purge    [--days N | --all]
tt export-recent [--days 60]
tt status   [--json]
tt config   show | get KEY | set KEY VALUE | validate
tt topic    list | show NAME | add NAME
tt promise  list | show ID | sync | status ID STATUS [--no-lock] | unlock ID | review
            | link ID ENTRY_ID | stats
```

## Tech stack

- Python 3.10+
- SQLite (5 databases, FTS5 trigram + keyword indexes)
- Sentence-Transformers (paraphrase-multilingual-MiniLM-L12-v2)
- OpenAI-compatible chat API (`gpt-5-nano` relevance gate, `gpt-5-mini` evidence extraction)
- feedparser, trafilatura, requests, Click, PyYAML

## Setup

```
pip install -e .
tt status
```

### Scheduled runs

`run_pipeline.sh` runs from a local checkout. It starts with `git pull --rebase`,
so a pull request merged on GitHub is in use from the next run (a change to the
script itself from the run after that). It then runs the six stages, lists the
promises awaiting review, rewrites the tracker table at the top of this README
and pushes the result to `main`. If the pull fails (no network, or a conflict
with a local commit) the run continues on the code already checked out and says
so. Changes to `config.yaml`, `topics/` or `promises/` still have to be copied to
the data directory (see [Configuration](#configuration)).
