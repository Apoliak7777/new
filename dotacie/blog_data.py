"""Obsah blogu (čeština) pre build_blog.py. Čísla a termíny musia sedieť s vyzvy_data.R – build to kontroluje.

POSTS: slug, ids (riadky v R, 1-based), title (max 70 znakov), subtitle, perex, meta (max 160 znakov),
keywords, facts [(popis, hodnota)], sections [(nadpis alebo None = pokračovanie, úvodný odsek alebo None, [odrážky])], sources [(názov, URL)].
V texte **tučné** → <strong>.
"""

CTA = ("Potřebujete pomoc se žádostí?",
       "Posoudíme, zda váš záměr splňuje podmínky výzvy, spočítáme možnou dotaci a připravíme kompletní žádost "
       "včetně příloh.",
       "Napište nám přes kontaktní formulář.")

DISCLAIMER = ("Informace vycházejí z vyhlášení výzvy a zveřejněných podkladů k {date}. Závazné jsou vždy aktuální "
              "podmínky poskytovatele; termíny a alokace se mohou změnit.")

EU_NOTE = ("Evropské programy pro mezinárodní konsorcia",
           "Kromě výše uvedených výzev jsou otevřené desítky výzev programů Evropské komise (Horizont Evropa, "
           "Evropský obranný fond, CEF, Digitální Evropa a další). Jsou určeny především mezinárodním "
           "konsorciím výzkumných organizací a firem. Pokud o účasti v konsorciu uvažujete, ozvěte se – pomůžeme "
           "najít vhodnou výzvu i partnery.")

ROUNDUP_POST = {
    "slug": "prehled-aktualnich-dotacnich-vyzev",
    "ids": (),
    "title": "Přehled aktuálních dotačních výzev – podzim 2026",
    "subtitle": "Otevřené a připravované výzvy pro firmy, obce, SVJ i neziskové organizace",
    "perex": "Vybrali jsme dotační výzvy, do kterých se dá v nejbližších týdnech a měsících podat žádost. U každé "
             "najdete, pro koho je určena, kolik lze získat a do kdy je třeba žádost podat. K nejzajímavějším "
             "výzvám jsme připravili samostatné články s podrobnostmi.",
    "meta": "Aktuální dotační výzvy pro firmy, obce, SVJ a neziskovky: OP TAK, OPŽP, OPZ+, Modernizační fond, "
            "NZÚ a granty Prahy. Uzávěrky a výše podpory.",
    "keywords": "dotace 2026, aktuální výzvy, dotační výzvy, granty, OP TAK, OPŽP, Modernizační fond, NZÚ",
}

# (nadpis skupiny, [(ids, názov, pre koho, slug detailu alebo None, {"max": ..., "deadline": ...})])
ROUNDUP = [
    ("Pro firmy a podnikatele", [
        ((106,), "OP TAK – Technologie pro MAS (CLLD), výzva II", "malé a střední podniky na venkově (území MAS)",
         "op-tak-technologie-pro-mas-ii", {}),
        ((107,), "Kraj Vysočina – Podnikatelské vouchery 2026", "podnikatelé se sídlem nebo provozovnou na Vysočině",
         "vysocina-podnikatelske-vouchery-2026", {"max": "podle pravidel programu"}),
        ((44,), "TA ČR SIGMA – 18. veřejná soutěž, DC1 Podpora komercializace VaVaI+", "malé podniky a startupy",
         "ta-cr-sigma-dc1-komercializace", {}),
        ((3,), "Česká rozvojová agentura – Program B2B", "firmy plánující projekt v rozvojové zemi",
         "cra-program-b2b-2027", {"max": "příprava 500 tis. Kč (50 %), realizace 2 mil. Kč ročně"}),
        ((59,), "EIC Accelerator", "inovativní MSP a startupy (deep-tech)", "eic-accelerator-2026",
         {"max": "grant do 2,5 mil. € (70 %) + investice 1–10 mil. €"}),
        ((58,), "OP Zaměstnanost+ – Diverzitní a flexibilní pracovní kultura",
         "zaměstnavatelé s více než 50 zaměstnanci", "opz-plus-flexibilni-pracovni-kultura",
         {"max": "projekt 1–10 mil. Kč"}),
        ((86,), "Národní rozvojová banka – Nová ELENA (projekty EPC)", "veřejný sektor a firmy", None, {}),
    ]),
    ("Doprava a elektromobilita", [
        ((110,), "Modernizační fond – TRANSCom 2/2025: elektrická nákladní vozidla", "silniční nákladní dopravci",
         "modernizacni-fond-elektricka-nakladni-doprava", {"max": "30–50 % z rozdílu ceny, až 2,25 mil. Kč na vůz"}),
        ((111,), "Modernizační fond – TRANSCom 1/2025: elektrické lokomotivy", "železniční nákladní dopravci",
         "modernizacni-fond-elektricka-nakladni-doprava", {"max": "30 % z rozdílu nákladů"}),
        ((94, 96), "OP Doprava – výzvy 44 a 45: dobíjecí stanice pro osobní auta",
         "vlastníci dobíjecí infrastruktury – obce, kraje i firmy", "op-doprava-dobijeci-stanice",
         {"max": "až 80 %", "deadline": "listopad 2026"}),
        ((95,), "OP Doprava – 46. výzva: ultrarychlé dobíjení osobních aut (min. 150 kW)",
         "vlastníci dobíjecí infrastruktury – obce, kraje i firmy", "op-doprava-dobijeci-stanice",
         {"max": "podle výzvy", "deadline": "prosinec 2026"}),
    ]),
    ("Energetika, bydlení a budovy", [
        ((117,), "Nová zelená úsporám 2026+ – renovace bytových domů", "SVJ, bytová družstva, vlastníci bytových domů",
         "nzu-2026-bytove-domy", {"max": "bezúročný úvěr až 750 tis. Kč na byt"}),
        ((57,), "NPO – Renovační pas budovy a dotační poradenství", "poradci zapsaní v evidenci SFŽP",
         "nzu-2026-bytove-domy", {"max": "3 000–8 000 Kč za renovační pas"}),
        ((112,), "Modernizační fond – RES+ 6/2025: agrofotovoltaika", "zemědělští podnikatelé",
         "modernizacni-fond-res-agrofotovoltaika", {}),
        ((61,), "NPO – Dostupné nájemní bydlení, výzva I", "obce a developeři (projekty nad 250 mil. Kč)", None,
         {"max": "zvýhodněný úvěr až 1,2 mld. Kč / 80 %"}),
    ]),
    ("Obce, krajina a životní prostředí", [
        ((50,), "OPŽP – 72. výzva: staré ekologické zátěže", "veřejný sektor, vlastníci a nájemci dotčených území",
         "opzp-ekologicke-zateze-a-svahy", {}),
        ((60,), "OPŽP – 106. výzva: obnova stability svahů", "obce, vlastníci pozemků, NNO, SVJ",
         "opzp-ekologicke-zateze-a-svahy", {}),
        ((67,), "Just Transition Mechanism – úvěrový nástroj pro veřejný sektor",
         "obce a kraje v uhelných regionech", None, {"max": "grant + úvěr EIB",
                                                      "deadline": "kolová, další kolo 16. 2. 2027"}),
        ((98, 99, 100), "Praha – Grantový program životního prostředí 2027 (oblasti I, V a VII)",
         "pražské NNO, SVJ, fyzické osoby", None, {"max": "450–600 tis. Kč na projekt"}),
    ]),
    ("Kultura, památky a cestovní ruch", [
        ((48,), "Praha – Program pro vlastníky památkově významných objektů 2027",
         "vlastníci památek a objektů v pražských památkových rezervacích a zónách", "praha-pamatkova-pece-2027", {}),
        ((1, 2), "Praha – Program podpory cestovního ruchu 2027 (opatření I a II)",
         "organizátoři kongresů a akcí v Praze", None, {"max": "až 2 mil. Kč na akci"}),
        ((27,), "Ministerstvo kultury – Program záchrany architektonického dědictví", "vlastníci kulturních památek",
         None, {}),
    ]),
]

POSTS = [
    {
        "slug": "op-tak-technologie-pro-mas-ii",
        "ids": (106,),
        "title": "Technologie pro MAS II: dotace 50 % na stroje, software a IT",
        "subtitle": "OP TAK podporuje malé a střední podniky na venkově – žádosti do 1. 9. 2027",
        "perex": "Malé a střední firmy na venkově mohou z výzvy Technologie pro MAS (CLLD) II získat dotaci 50 % "
                 "na nové stroje, technologie, software nebo IT infrastrukturu. Výzva s alokací 540 mil. Kč "
                 "přijímá žádosti od 1. 9. 2026 do 1. 9. 2027 – začíná se ale projektovým záměrem u místní akční "
                 "skupiny.",
        "meta": "Technologie pro MAS II (OP TAK): dotace 50 % na stroje, software a IT pro malé a střední firmy "
                "na venkově, až 1,49 mil. Kč. Žádosti do 1. 9. 2027.",
        "keywords": "Technologie pro MAS, OP TAK, CLLD, dotace na stroje, dotace na software, MSP",
        "facts": [
            ("Poskytovatel", "Ministerstvo průmyslu a obchodu – OP TAK, administruje Agentura API"),
            ("Alokace výzvy", "540 000 000 Kč"),
            ("Způsobilé výdaje projektu", "250 000 – 2 999 999 Kč"),
            ("Míra podpory", "50 % pro malé i střední podniky"),
            ("Maximální dotace", "1 490 000 Kč"),
            ("Příjem žádostí", "1. 9. 2026 – 1. 9. 2027 (průběžně, portál ISKP21+)"),
            ("Dokončení projektu", "nejpozději 31. 8. 2028"),
        ],
        "sections": [
            ("Co výzva podporuje",
             "Výzva financuje pořízení nových strojů, technologických zařízení a vybavení, softwaru, IT "
             "infrastruktury a souvisejících služeb. Typicky jde o:",
             ["automatizaci a digitalizaci výroby nebo služeb, robotizaci manipulace a skladu,",
              "software, webová a cloudová řešení, informační systémy (například ERP) a kybernetickou "
              "bezpečnost,",
              "automatizované a modulární prodejny nebo výdejní boxy s provozem 24/7."]),
            (None, "Způsobilý je dlouhodobý hmotný a nehmotný majetek, služby a nepřímé náklady paušálem 7 %.", []),
            ("Kdo může žádat", None,
             ["malé a střední podniky – OSVČ i právnické osoby s IČO a oprávněním k podnikání,",
              "projekt musí proběhnout na území MAS se schváleným programovým rámcem OP TAK,",
              "mimo obce s více než 25 000 obyvateli a mimo hl. m. Prahu,",
              "vyloučené obory (CZ-NACE) uvádí příloha výzvy."]),
            ("Jak podání probíhá", None,
             ["**1. krok:** místní akční skupina vyhlásí vlastní výzvu a vy do ní podáte projektový záměr. Každá "
              "MAS má vlastní termíny a hodnoticí kritéria.",
              "**2. krok:** po výběru záměru v MAS podáte plnou žádost v portálu ISKP21+.",
              "**3. krok:** projekt zrealizujete a dotaci dostanete zpětně (ex post) – nákup je třeba "
              "předfinancovat."]),
            ("Na co si dát pozor", None,
             ["Celostátní uzávěrka 1. 9. 2027 neznamená, že vaše MAS bude přijímat záměry tak dlouho – sledujte "
              "její harmonogram.",
              "Jeden žadatel může mít jen jednu aktivní žádost.",
              "Podporují se pouze nové stroje a zařízení.",
              "V první výzvě byly výdaje způsobilé až od podání žádosti – s nákupem proto nespěchejte."]),
        ],
        "sources": [("Agentura API – Technologie pro MAS II",
                     "https://apiagentura.gov.cz/cs/podporovane-aktivity-optak/technologie-pro-mas-optak/"
                     "technologie-pro-mas-clld-vyzva-ii/"),
                    ("OP TAK", "https://optak.gov.cz/technologie-pro-mas-clld-vyzva-ii/a-610/")],
    },
    {
        "slug": "vysocina-podnikatelske-vouchery-2026",
        "ids": (107,),
        "title": "Podnikatelské vouchery 2026 na Vysočině: inovace i kyberbezpečnost",
        "subtitle": "Fond Vysočiny rozděluje 7 mil. Kč, žádosti do 30. 10. 2026",
        "perex": "Kraj Vysočina sloučil Inovační a Digitální vouchery do jednoho programu. Podnikatelé z kraje "
                 "mohou získat příspěvek na odborné služby – vývoj a testování produktů, optimalizaci procesů, "
                 "digitální audity nebo penetrační testy. Žádosti se podávají do 30. 10. 2026.",
        "meta": "Podnikatelské vouchery 2026 Kraje Vysočina: příspěvek na inovace, digitalizaci a "
                "kyberbezpečnost. Alokace 7 mil. Kč, žádosti do 30. 10. 2026.",
        "keywords": "Podnikatelské vouchery, Kraj Vysočina, Fond Vysočiny, inovační voucher, kyberbezpečnost",
        "facts": [
            ("Poskytovatel", "Kraj Vysočina – Fond Vysočiny, program FV03009"),
            ("Alokace programu", "7 000 000 Kč"),
            ("Příjem žádostí", "23. 3. 2026 – 30. 10. 2026"),
            ("Realizace", "od podpisu smlouvy do 31. 12. 2027"),
            ("Podání", "přes portál fondvysociny.cz"),
        ],
        "sections": [
            ("Co program podporuje",
             "Příspěvek je určen na specializované služby od akreditovaných subjektů, výzkumných organizací a "
             "odborných institucí, například:",
             ["spolupráci na vývoji a inovaci produktů, optimalizaci procesů, testování a design,",
              "audity kybernetické bezpečnosti, GAP analýzy, penetrační testy a zabezpečení cloudu,",
              "digitální audity a strategii digitální transformace firmy."]),
            ("Kdo může žádat", None,
             ["obchodní korporace a OSVČ se sídlem nebo provozovnou v Kraji Vysočina,",
              "firma musela vzniknout nejpozději 31. 12. 2023."]),
            ("Na co si dát pozor", None,
             ["Program nepodporuje nákup komerčního softwaru ani jiného programového vybavení – jen služby.",
              "Služby lze čerpat až po podpisu smlouvy s krajem.",
              "Dodavatel musí splňovat podmínky programu (akreditovaný subjekt, výzkumná organizace nebo odborná "
              "instituce).",
              "Alokace 7 mil. Kč je omezená – s podáním neotálejte. Výši příspěvku a spoluúčasti stanoví "
              "pravidla programu."]),
        ],
        "sources": [("Kraj Vysočina – tisková zpráva",
                     "https://www.kr-vysocina.cz/kraj-vysocina-vyhlasil-podnikatelske-vouchery-2026-sedm-milionu-"
                     "na-sluzby-v-oblasti-inovaci-digitalizace-a-kyberbezpecnosti/d-4136309"),
                    ("Fond Vysočiny – FV03009", "https://www.fondvysociny.cz/dotace/zadosti/FV03009")],
    },
    {
        "slug": "ta-cr-sigma-dc1-komercializace",
        "ids": (44,),
        "title": "TA ČR SIGMA: až 730 000 Kč na studii proveditelnosti pro startupy",
        "subtitle": "18. veřejná soutěž, dílčí cíl 1 Podpora komercializace VaVaI+ – návrhy do 27. 10. 2026",
        "perex": "Technologická agentura ČR otevřela 18. veřejnou soutěž programu SIGMA v dílčím cíli "
                 "„Podpora komercializace VaVaI+“. Malé podniky a startupy mohou získat až 730 000 Kč na ověření "
                 "výsledků výzkumu a přípravu studie proveditelnosti, která je připraví na žádost do EIC "
                 "Accelerator.",
        "meta": "TA ČR SIGMA DC1: až 730 000 Kč (70 %) pro malé podniky a startupy na komercializaci výzkumu a "
                "studii proveditelnosti. Návrhy do 27. 10. 2026.",
        "keywords": "TA ČR, SIGMA, komercializace, studie proveditelnosti, startup, EIC Accelerator",
        "facts": [
            ("Poskytovatel", "Technologická agentura ČR – program SIGMA, dílčí cíl 1"),
            ("Alokace soutěže", "10 000 000 Kč"),
            ("Maximální podpora", "730 000 Kč na projekt"),
            ("Míra podpory", "max. 70 %"),
            ("Soutěžní lhůta", "10. 9. 2026 – 27. 10. 2026"),
            ("Podání", "informační systém SISTA"),
        ],
        "sections": [
            ("Co soutěž podporuje", None,
             ["ověření výsledků aplikovaného výzkumu pro praxi a přípravu komerčního využití průlomových "
              "(deep-tech) řešení,",
              "výchozí technologická připravenost alespoň TRL 4,",
              "hlavním výstupem je studie proveditelnosti v angličtině,",
              "součástí je koučink od TA ČR a cílem příprava firmy na EIC Accelerator."]),
            ("Kdo může žádat", None,
             ["malé podniky se sídlem v ČR včetně nově založených firem a startupů,",
              "projekt řeší žadatel samostatně, bez dalších účastníků."]),
            ("Na co si dát pozor", None,
             ["Při podání v SISTA je povinné označit zájem o synergické aktivity s EIC Accelerator – bez toho "
              "návrh nelze podat.",
              "Omezení pro projekty navazující na 14. veřejnou soutěž (DC1) zkontrolujte v zadávací "
              "dokumentaci.",
              "Alokace vystačí zhruba na 13 projektů s maximální podporou – konkurence bude vysoká.",
              "Studie se píše v angličtině a má obstát i před hodnotiteli EIC."]),
        ],
        "sources": [("TA ČR – program SIGMA", "https://tacr.gov.cz/program/program-sigma/"),
                    ("RIS3 – 18. veřejná soutěž",
                     "https://ris3.gov.cz/aktuality/osmnacta-verejna-soutez-dilci-cil-1-podpora-komercializace-"
                     "vavai-program-na-podporu-aplikovaneho")],
    },
    {
        "slug": "cra-program-b2b-2027",
        "ids": (3,),
        "title": "Program B2B 2027: dotace na podnikání v rozvojových zemích",
        "subtitle": "Česká rozvojová agentura přijímá žádosti do 10. 11. 2026",
        "perex": "Plánujete výrobu, služby nebo investici v rozvojové zemi? Program B2B České rozvojové agentury "
                 "podporuje firmy ve dvou fázích – při přípravě podnikatelského záměru a při jeho realizaci. Výzva "
                 "na rok 2027 byla vyhlášena 18. 9. 2026, žádosti se podávají do 10. 11. 2026.",
        "meta": "Program B2B České rozvojové agentury 2027: dotace na studii proveditelnosti a realizaci "
                "podnikatelských projektů v rozvojových zemích. Uzávěrka 10. 11. 2026.",
        "keywords": "Program B2B, Česká rozvojová agentura, ČRA, rozvojová spolupráce, studie proveditelnosti",
        "facts": [
            ("Poskytovatel", "Česká rozvojová agentura (ČRA)"),
            ("Fáze přípravy", "až 50 % nákladů, max. 500 000 Kč"),
            ("Fáze realizace", "40 % v 1. roce a 30 % ve 2. roce, max. 2 000 000 Kč za kalendářní rok"),
            ("Uzávěrka", "10. 11. 2026 (23:59)"),
            ("Podání", "systém Grantys"),
        ],
        "sections": [
            ("Co program podporuje", None,
             ["**přípravu** – studii proveditelnosti nebo podnikatelský plán,",
              "**realizaci** – projekt v rozvojové zemi (podle klasifikace OECD) s prokazatelným rozvojovým "
              "dopadem a vazbou na cíle udržitelného rozvoje (SDGs),",
              "typické přínosy: nová pracovní místa, přenos technologií a know-how, zapojení místních "
              "dodavatelů, environmentální technologie, zavádění standardů."]),
            ("Kdo může žádat",
             "Obchodní korporace (obchodní společnosti a družstva) registrované v ČR. Předchozí výzvy navíc "
             "vyžadovaly mimo jiné delší historii podnikání a dostatečný obrat vůči požadované dotaci – aktuální "
             "podmínky stanoví text výzvy.", []),
            ("Na co si dát pozor", None,
             ["Hodnotí se rozvojový dopad pro cílovou zemi, ne jen obchodní přínos pro firmu – musí být "
              "měřitelný.",
              "Dotace je spolufinancování – většinu nákladů nese firma.",
              "Kvalitní studie proveditelnosti nebo podnikatelský plán rozhoduje o úspěchu i v realizační fázi."]),
        ],
        "sources": [("ČRA – Program B2B", "https://czechaid.gov.cz/program-b2b"),
                    ("ČRA – dotace", "https://czechaid.gov.cz/dotace")],
    },
    {
        "slug": "eic-accelerator-2026",
        "ids": (59,),
        "title": "EIC Accelerator: grant až 2,5 mil. € a investice pro deep-tech firmy",
        "subtitle": "Poslední letošní uzávěrka plných žádostí je 4. 11. 2026",
        "perex": "EIC Accelerator je nejvýznamnější evropský nástroj pro inovativní startupy a malé a střední "
                 "podniky. Kombinuje grant do 2,5 mil. EUR s kapitálovým vstupem 1–10 mil. EUR. Krátkou žádost lze "
                 "podat kdykoli, plné žádosti se hodnotí k pevným uzávěrkám – poslední v roce 2026 je 4. 11.",
        "meta": "EIC Accelerator 2026: grant do 2,5 mil. EUR (70 %) a investice 1–10 mil. EUR pro startupy a MSP. "
                "Poslední uzávěrka plných žádostí 4. 11. 2026.",
        "keywords": "EIC Accelerator, Horizont Evropa, startup, deep-tech, grant, equity",
        "facts": [
            ("Poskytovatel", "Evropská rada pro inovace (EIC), Horizont Evropa"),
            ("Grant", "jednorázová částka do 2,5 mil. EUR, 70 % způsobilých nákladů"),
            ("Investice", "1–10 mil. EUR (kapitálový vstup nebo kvazi-equity)"),
            ("Rozpočet EIC Accelerator Open 2026", "414 mil. EUR"),
            ("Krátká žádost", "průběžně"),
            ("Uzávěrka plných žádostí", "4. 11. 2026"),
        ],
        "sections": [
            ("Co program podporuje", None,
             ["vývoj a uvedení na trh průlomových inovací,",
              "grant kryje inovační aktivity na úrovni TRL 6–8 dokončené do 24 měsíců,",
              "investiční složka financuje růst a škálování firmy."]),
            ("Kdo může žádat", None,
             ["startupy a malé a střední podniky včetně spin-offů usazené v EU nebo v zemi přidružené "
              "k Horizontu Evropa,",
              "fyzické osoby, které chtějí firmu založit,",
              "v některých případech i menší mid-capy (do 500 zaměstnanců)."]),
            ("Jak podání probíhá", None,
             ["**1. krok:** krátká žádost (short proposal) – kdykoli, výsledkem je GO nebo NO GO.",
              "**2. krok:** po GO plná žádost k některé z uzávěrek.",
              "**3. krok:** pohovor před porotou."]),
            ("Na co si dát pozor", None,
             ["Konkurence je velmi vysoká – uspěje jen malá část žadatelů.",
              "Firma spolufinancuje 30 % nákladů grantové části.",
              "Pro uzávěrku 4. 11. 2026 už musíte mít GO z krátké žádosti; termíny pro rok 2027 zveřejní EIC "
              "v pracovním programu.",
              "Přípravu lze financovat z českých zdrojů – TA ČR SIGMA DC1 podporuje studii proveditelnosti právě "
              "pro EIC Accelerator."]),
        ],
        "sources": [("EIC Accelerator Open",
                     "https://eic.ec.europa.eu/eic-funding-opportunities/eic-accelerator/eic-accelerator-open_en"),
                    ("EIC Work Programme 2026",
                     "https://eic.ec.europa.eu/eic-funding-opportunities/eic-2026-work-programme_en")],
    },
    {
        "slug": "modernizacni-fond-elektricka-nakladni-doprava",
        "ids": (110, 111, 113),
        "title": "Modernizační fond: dotace na elektrické nákladní vozy a lokomotivy",
        "subtitle": "TRANSCom 2/2025 přijímá žádosti do 30. 11. 2026, lokomotivy do 30. 10. 2026",
        "perex": "Dopravci mohou z Modernizačního fondu získat dotaci na náhradu dieselových nákladních aut "
                 "elektrickými. Výzva TRANSCom 2/2025 má alokaci 960 mil. Kč a přijímá žádosti do 30. 11. 2026 "
                 "nebo do vyčerpání peněz. Pro železniční nákladní dopravce běží souběžně výzva na nové elektrické "
                 "lokomotivy s alokací 3,5 mld. Kč.",
        "meta": "Modernizační fond TRANSCom: dotace 30–50 % na elektrická nákladní auta N2/N3 a 30 % na "
                "elektrické lokomotivy. Žádosti do 30. 11. 2026, resp. 30. 10. 2026.",
        "keywords": "Modernizační fond, TRANSCom, elektrické nákladní auto, e-truck, lokomotiva, SFŽP",
        "facts": [
            ("Poskytovatel", "Ministerstvo životního prostředí / SFŽP ČR – Modernizační fond"),
            ("TRANSCom 2/2025 – alokace", "960 000 000 Kč, z toho nejméně 80 % pro vozidla N3"),
            ("TRANSCom 2/2025 – míra podpory",
             "30 % velký, 40 % střední, 50 % malý podnik – z rozdílu ceny elektrického a referenčního dieselového "
             "vozidla"),
            ("Strop na vozidlo N3", "1 350 000 Kč (velký podnik) až 2 250 000 Kč (malý podnik)"),
            ("TRANSCom 2/2025 – příjem žádostí", "2. 2. 2026 – 30. 11. 2026 (12:00) nebo do vyčerpání alokace"),
            ("Elektrické lokomotivy – alokace a příjem", "3 500 000 000 Kč, do 30. 10. 2026 (12:00)"),
        ],
        "sections": [
            ("Elektrická nákladní vozidla (TRANSCom 2/2025)",
             "Výzva podporuje nákup nových elektrických nákladních vozidel kategorie N2 (4,25–12 t) a N3 (nad "
             "12 t) jako náhradu za vozidla se vznětovým motorem. Spolu s vozidly lze pořídit i dobíjecí stanice – "
             "nejvýše jednu na dvě pořizovaná vozidla, s mírou podpory 30 %. Žádat mohou podnikatelé se sídlem "
             "v ČR, kteří provozují silniční nákladní dopravu.", []),
            ("Na co si dát pozor", None,
             ["Nahrazované vozidlo musí být daňově odepsané, řádně provozované v ČR a vyřazené z registru "
              "silničních vozidel.",
              "Počet vyřazených vozidel musí být alespoň stejný jako počet nově pořízených.",
              "Dotace se počítá z rozdílu cen, ne z celé ceny vozidla.",
              "Žádosti se přijímají do vyčerpání alokace – nečekejte na poslední chvíli."]),
            ("Elektrické lokomotivy (TRANSCom 1/2025)",
             "Železniční nákladní dopravci mohou získat podporu na nové elektrické lokomotivy schválené pro "
             "celostátní nebo regionální dráhy a zapsané v evropském registru vozidel (EVR). Podpora činí 30 % "
             "z rozdílu nákladů mezi bezemisním a srovnatelným konvenčním vozidlem. Alokace je "
             "3 500 000 000 Kč, žádosti se přijímají do 30. 10. 2026.", []),
            ("Osobní železniční doprava (TRANSGov 1/2024, 2. kolo)",
             "Druhé kolo s alokací 15 000 000 000 Kč a příjmem do 31. 3. 2027 financuje náhradu dieselových "
             "motorových vozidel elektrickými, bateriovými nebo vodíkovými jednotkami. Je ale určeno pouze "
             "projektům, které v prvním kole získaly kladné stanovisko SFŽP – noví žadatelé se přihlásit nemohou.",
             []),
        ],
        "sources": [("SFŽP – TRANSCom 2/2025",
                     "https://sfzp.gov.cz/dotace-a-pujcky/modernizacni-fond/vyzvy/detail-vyzvy/?id=54"),
                    ("Text výzvy TRANSCom 1/2025 (lokomotivy)",
                     "https://sfzp.gov.cz/files/documents/storage/2025/12/04/1764845675_TRANSCom_1_2025_e-loko_fin.pdf"),
                    ("SFŽP – TRANSGov 1/2024",
                     "https://sfzp.gov.cz/dotace-a-pujcky/modernizacni-fond/vyzvy/detail-vyzvy/?id=50")],
    },
    {
        "slug": "modernizacni-fond-res-agrofotovoltaika",
        "ids": (112,),
        "title": "Agrofotovoltaika s dotací 30 %: výzva RES+ 6/2025 pro zemědělce",
        "subtitle": "Modernizační fond podporuje agrovoltaické elektrárny a baterie na zemědělské půdě",
        "perex": "Zemědělci mohou z Modernizačního fondu získat až 30 % nákladů na agrofotovoltaickou elektrárnu "
                 "s bateriovým úložištěm. Výzva RES+ 6/2025 má alokaci 300 mil. Kč a přijímá žádosti od 15. 1. "
                 "2026 – elektrárna přitom nesmí zemědělskou výrobu na pozemku nahradit.",
        "meta": "RES+ 6/2025 z Modernizačního fondu: dotace až 30 % na agrofotovoltaické elektrárny a baterie "
                "pro zemědělské podnikatele. Alokace 300 mil. Kč.",
        "keywords": "agrofotovoltaika, agrovoltaika, RES+, Modernizační fond, dotace pro zemědělce, FVE",
        "facts": [
            ("Poskytovatel", "Ministerstvo životního prostředí / SFŽP ČR – Modernizační fond"),
            ("Alokace výzvy", "300 000 000 Kč a zásobník projektů až 200 mil. Kč"),
            ("Míra podpory", "max. 30 % způsobilých výdajů"),
            ("Příjem žádostí", "od 15. 1. 2026 do 30. 6. 2027 nebo do vyčerpání alokace"),
            ("Podání", "AIS SFŽP"),
            ("Realizace", "do 3 let od vydání rozhodnutí"),
        ],
        "sections": [
            ("Co výzva podporuje", None,
             ["nové agrofotovoltaické elektrárny s jedním předávacím místem do distribuční nebo přenosové "
              "soustavy,",
              "umístěné na pozemcích evidovaných v registru půdy LPIS,",
              "bateriovou akumulaci s kapacitou 0,2 až 1násobku instalovaného výkonu,",
              "výši podpory vypočítá AIS SFŽP automaticky podle instalovaného výkonu a kapacity baterie."]),
            ("Kdo může žádat",
             "Zemědělský podnikatel zapsaný v evidenci zemědělského podnikatele, který obhospodařuje pozemky "
             "v LPIS a je nebo bude držitelem licence ERÚ na výrobu elektřiny.", []),
            ("Na co si dát pozor", None,
             ["Agrofotovoltaika musí splnit technické parametry dané právními předpisy – u horizontálních "
              "systémů se uvádí výška modulů nejméně 2,1 m nad terénem a zachování alespoň 95 % zemědělsky "
              "využitelné plochy. Přesné podmínky ověřte v textu výzvy.",
              "Pozemek musí zůstat zemědělsky obhospodařovaný.",
              "Alokace se čerpá průběžně – dřívější podání zvyšuje šanci na podporu."]),
        ],
        "sources": [("SFŽP – RES+ 6/2025",
                     "https://sfzp.gov.cz/dotace-a-pujcky/modernizacni-fond/vyzvy/detail-vyzvy/?id=53"),
                    ("Text výzvy RES+ 6/2025",
                     "https://sfzp.gov.cz/files/documents/storage/2025/12/11/1765450450_RES_6_2025_AgroFVE.pdf")],
    },
    {
        "slug": "opz-plus-flexibilni-pracovni-kultura",
        "ids": (58,),
        "title": "OPZ+: až 10 mil. Kč na flexibilní práci a slaďování s rodinou",
        "subtitle": "Výzva Diverzitní a flexibilní pracovní kultura je prodloužena do 30. 11. 2026",
        "perex": "Zaměstnavatelé s více než 50 zaměstnanci mohou z Operačního programu Zaměstnanost plus "
                 "financovat zavedení flexibilních forem práce, podporu rodičů na mateřské a rodičovské dovolené "
                 "nebo rozvoj žen ve vedení. Alokace výzvy byla navýšena na 360 mil. Kč a příjem žádostí prodloužen "
                 "do 30. 11. 2026.",
        "meta": "OP Zaměstnanost plus – Diverzitní a flexibilní pracovní kultura: projekty 1–10 mil. Kč pro "
                "zaměstnavatele nad 50 zaměstnanců. Žádosti do 30. 11. 2026.",
        "keywords": "OPZ+, OP Zaměstnanost plus, flexibilní práce, slaďování, diverzita, dotace pro zaměstnavatele",
        "facts": [
            ("Poskytovatel", "Ministerstvo práce a sociálních věcí – OP Zaměstnanost plus, specifický cíl 1.2"),
            ("Alokace výzvy", "360 000 000 Kč"),
            ("Rozpočet projektu", "1 000 000 – 10 000 000 Kč"),
            ("Délka projektu", "max. 24 měsíců"),
            ("Uzávěrka", "30. 11. 2026"),
            ("Podání", "IS KP21+"),
        ],
        "sections": [
            ("Co výzva podporuje",
             "Výzva patří do specifického cíle 1.2 – vyvážené zastoupení žen a mužů a slaďování pracovního a "
             "soukromého života. Podporuje:",
             ["zavedení flexibilních forem práce,",
              "práci se zaměstnanci na mateřské a rodičovské dovolené a jejich návrat do práce,",
              "inkluzivní a diverzitní pracovní prostředí,",
              "rozvoj žen včetně jejich postupu do vedoucích pozic."]),
            ("Kdo může žádat",
             "Zaměstnavatelé s více než 50 zaměstnanci. Přesnou definici a výčet oprávněných žadatelů uvádí text "
             "výzvy.", []),
            ("Na co si dát pozor", None,
             ["Před podáním je povinné dotazníkové šetření mezi zaměstnavatelem a zaměstnanci – vyhraďte si na "
              "něj čas.",
              "Míra spolufinancování závisí na právní formě žadatele.",
              "Podpora se poskytuje v režimu de minimis a počítá se za celou organizaci – zkontrolujte, kolik "
              "z limitu jste už vyčerpali.",
              "Projekt může trvat nejvýše 24 měsíců."]),
        ],
        "sources": [("ESF ČR – výzva Diverzitní a flexibilní pracovní kultura",
                     "https://www.esfcr.cz/prehled-vyzev-opz-plus/-/asset_publisher/SfUza2tXdZGm/content/"
                     "diverzitni-a-flexibilni-pracovni-kultura-1-?inheritRedirect=false"),
                    ("ESF ČR – jak zažádat",
                     "https://www.esfcr.cz/flexibilita-a-diverzita-v-opz-plus/jak-zazadat-o-projekt")],
    },
    {
        "slug": "op-doprava-dobijeci-stanice",
        "ids": (95,),
        "title": "Dotace na dobíjecí stanice z OP Doprava: výzvy na podzim 2026",
        "subtitle": "Až 80 % na nabíjení elektromobilů – výzvy 44 až 48 pro obce, kraje i firmy",
        "perex": "Ministerstvo dopravy na podzim 2026 postupně vyhlašuje pět výzev Operačního programu Doprava "
                 "na dobíjecí infrastrukturu. Podle dostupných informací jde pravděpodobně o poslední výzvy "
                 "s podporou až 80 %. Žádat mohou i firmy, které stanici postaví a budou ji vlastnit.",
        "meta": "OP Doprava 2026: výzvy 44–48 na dobíjecí stanice pro elektromobily, podpora až 80 %. Pro obce, "
                "kraje i firmy. Přehled termínů a podmínek.",
        "keywords": "dobíjecí stanice, nabíjecí stanice, OP Doprava, elektromobilita, dotace, rychlodobíjení",
        "facts": [
            ("Poskytovatel", "Ministerstvo dopravy – OP Doprava 2021–2027"),
            ("Výzvy 44 a 45", "vyhlášeny koncem srpna 2026, alokace dohromady 250 mil. Kč, příjem do listopadu "
                              "2026"),
            ("Výzva 46", "alokace 315 000 000 Kč, příjem září – prosinec 2026"),
            ("Výzvy 47 a 48", "vyhlašují se postupně na podzim 2026"),
            ("Míra podpory", "až 80 % (liší se podle výzvy)"),
            ("Délka příjmu", "každá výzva zhruba 3 měsíce nebo do vyčerpání alokace"),
        ],
        "sections": [
            ("Co výzvy podporují", None,
             ["**44. výzva** – rychlodobíjecí stanice pro osobní auta ve vybraných prioritních lokalitách,",
              "**45. výzva** – běžné dobíjecí stanice ve městech a obcích,",
              "**46. výzva** – ultrarychlé stanice pro osobní auta v celé ČR s výkonem nejméně 150 kW,",
              "**47. a 48. výzva** – podle harmonogramu OP Doprava dobíjení nákladních vozidel a další běžné "
              "stanice; parametry budou známy při vyhlášení."]),
            ("Kdo může žádat",
             "Subjekt, který bude infrastrukturu vlastnit – typicky kraje, města a obce, ale také firmy, "
             "například obchodní centra, hotely nebo logistické areály. Přesný okruh žadatelů stanoví každá "
             "výzva.", []),
            ("Na co si dát pozor", None,
             ["Výzvy jsou otevřené krátce a mohou skončit dříve vyčerpáním alokace – lokalitu, rezervovaný příkon "
              "od distributora a projekt připravte předem.",
              "Počítejte s požadavky na veřejnou přístupnost stanice a platbu bez registrace (nařízení EU "
              "o infrastruktuře pro alternativní paliva, AFIR).",
              "Aktuální termíny sledujte v harmonogramu výzev OP Doprava."]),
        ],
        "sources": [("OP Doprava – harmonogram výzev", "https://opd3.opd.cz/stranka/harmonogram-vyzev-opd"),
                    ("OP Doprava – 45. výzva", "https://opd3.opd.cz/stranka/vyzva-45/")],
    },
    {
        "slug": "nzu-2026-bytove-domy",
        "ids": (117, 57),
        "title": "Nová zelená úsporám 2026: bezúročný úvěr na renovaci bytových domů",
        "subtitle": "Pro SVJ a bytová družstva – úvěr až 750 000 Kč na byt, žádosti do 31. 10. 2029",
        "perex": "Nová zelená úsporám se pro bytové domy mění. Místo dotace HOUSEnerg, jejíž výzva skončila "
                 "v listopadu 2025, nabízí program od 25. 6. 2026 bezúročný úvěr od bank a stavebních spořitelen – "
                 "úroky za vlastníky platí stát. Podmínkou je renovační pas budovy.",
        "meta": "Nová zelená úsporám 2026 pro SVJ a družstva: bezúročný úvěr až 750 000 Kč na byt, renovační "
                "pas a dotace pro zranitelné domácnosti. Do 31. 10. 2029.",
        "keywords": "Nová zelená úsporám, NZÚ 2026, SVJ, bytový dům, bezúročný úvěr, renovační pas",
        "facts": [
            ("Poskytovatel", "Ministerstvo životního prostředí / SFŽP ČR – Nová zelená úsporám"),
            ("Forma podpory", "bezúročný úvěr (úroky hradí SFŽP) a přímá dotace na byty zranitelných domácností"),
            ("Výše úvěru", "až 750 000 Kč na byt při komplexní renovaci"),
            ("Kdo úvěr poskytuje", "banky a stavební spořitelny, od září 2026"),
            ("Příjem žádostí", "25. 6. 2026 – 31. 10. 2029 nebo do vyčerpání alokace"),
        ],
        "sections": [
            ("Co program podporuje", None,
             ["zateplení obálky budovy,",
              "výměnu zdroje tepla a ohřev vody,",
              "fotovoltaiku a nabíjení elektromobilů,",
              "rekuperaci, hospodaření s vodou a zelené střechy."]),
            ("Kdo může žádat",
             "Společenství vlastníků jednotek, bytová družstva a další vlastníci bytových domů. Na byty "
             "zranitelných domácností mohou SVJ a družstva získat i přímou dotaci – podle tiskové zprávy MŽP až "
             "120 000 Kč na byt.", []),
            ("Renovační pas a dotační poradenství",
             "Renovační pas budovy je podmínkou podpory. Zpracovávají ho poradci zapsaní v evidenci SFŽP, kteří "
             "na něj mohou čerpat příspěvek z výzvy Národního plánu obnovy č. 2/2026 (alokace 200 000 000 Kč, "
             "příjem do 30. 11. 2026):",
             ["3 000 Kč za renovační pas rodinného domu a 5 000 Kč za pas bytového domu,",
              "u domácností ohrožených energetickou chudobou je pas i poradenství zdarma a poradce může získat "
              "až 8 000 Kč."]),
            ("Na co si dát pozor", None,
             ["Dřívější dotace HOUSEnerg pro bytové domy už nejsou k dispozici – výzva skončila 8. 11. 2025 po "
              "vyčerpání alokace.",
              "Projekt nejdřív prochází technickým posouzením SFŽP, teprve potom se sjednává úvěr.",
              "Úvěr je potřeba splácet – u SVJ počítejte s rozhodnutím shromáždění vlastníků."]),
        ],
        "sources": [("Nová zelená úsporám – texty výzev", "https://novazelenausporam.cz/dokumenty/texty-vyzev/"),
                    ("MŽP – tisková zpráva",
                     "https://mzp.gov.cz/cz/pro-media-a-verejnost/aktuality/archiv-tiskovych-zprav/program-nova-"
                     "zelena-usporam-otevira-prijem-zadosti-renovace-domu-podpori-cileneji-a-efektivneji"),
                    ("NPO – výzva 2/2026 Renovační pas",
                     "https://www.narodniprogramzp.cz/nabidka-dotaci/detail-vyzvy/?id=181")],
    },
    {
        "slug": "opzp-ekologicke-zateze-a-svahy",
        "ids": (50, 60),
        "title": "OPŽP: dotace na sanaci ekologických zátěží a sesuvů svahů",
        "subtitle": "72. výzva do 10. 11. 2026 (až 85 %), 106. výzva do 17. 12. 2026 (až 80 %)",
        "perex": "Operační program Životní prostředí má otevřené dvě specializované výzvy pro obce, vlastníky "
                 "pozemků a další subjekty: odstraňování starých ekologických zátěží s alokací 1,7 mld. Kč a "
                 "stabilizaci svahů po sesuvech a skalních řícení se 100 mil. Kč. Obě vyžadují odbornou přípravu "
                 "s dostatečným předstihem.",
        "meta": "OPŽP 72. výzva (ekologické zátěže, až 85 %, do 10. 11. 2026) a 106. výzva (stabilita svahů, "
                "až 80 %, do 17. 12. 2026). Podmínky a přílohy.",
        "keywords": "OPŽP, ekologické zátěže, sanace, sesuvy, svahové deformace, dotace pro obce",
        "facts": [
            ("Poskytovatel", "Ministerstvo životního prostředí / SFŽP ČR – OP Životní prostředí 2021–2027"),
            ("72. výzva – ekologické zátěže",
             "alokace 1 700 000 000 Kč, až 85 % + bonifikace, příjem 29. 1. 2025 – 10. 11. 2026 (IS KP21+)"),
            ("106. výzva – stabilita svahů", "alokace 100 000 000 Kč, až 80 %, příjem 17. 6. 2026 – 17. 12. 2026"),
        ],
        "sections": [
            ("72. výzva: staré ekologické zátěže",
             "Výzva financuje sanaci nejvážněji kontaminovaných lokalit, u nichž analýza rizik prokázala "
             "neakceptovatelné riziko pro zdraví, vodní zdroje nebo ekosystémy a které mají v databázi SEKM "
             "prioritu A1 až A3. Žádat může veřejný sektor, vlastníci a nájemci dotčených území a subjekty "
             "nakládající s odpady.",
             ["bonifikace až +5 % za prioritu zátěže a až +5 % za rozvojový potenciál obce (u 2. a 3. "
              "kategorie),",
              "závěry analýzy rizik musí schválit odbor ekologických škod MŽP (OEREŠ) – analýza zpracovaná bez "
              "jeho účasti není způsobilým výdajem,",
              "formulář prioritizace se získává z databáze SEKM."]),
            ("106. výzva: obnova stability svahů",
             "Výzva podporuje stabilizaci a sanaci extrémních svahových nestabilit a skalních řícení vzniklých "
             "přírodními jevy. Žádat mohou obce, městské části Prahy, dobrovolné svazky obcí, spolky, obecně "
             "prospěšné společnosti, nadace, ústavy, církve, fyzické osoby, SVJ, státní podniky a resortní "
             "organizace MŽP.",
             ["lokalita musí být zdokumentovaná Českou geologickou službou, zapsaná v Registru svahových "
              "deformací a zařazená do kategorie rizika III,",
              "povinnou přílohou je odborné vyjádření ČGS k projektu stabilizačních opatření – ČGS na něj má "
              "20 pracovních dnů, požádejte proto nejpozději v polovině listopadu 2026,",
              "vyjádření ČGS neslouží k zápisu lokality do registru ani ke klasifikaci rizika."]),
        ],
        "sources": [("OPŽP – 72. výzva", "https://opzp.cz/dotace/72-vyzva/"),
                    ("OPŽP – 106. výzva", "https://opzp.cz/dotace/106-vyzva/")],
    },
    {
        "slug": "praha-pamatkova-pece-2027",
        "ids": (48,),
        "title": "Praha: dotace na obnovu památek 2027 – žádosti do 30. 10. 2026",
        "subtitle": "Program pro vlastníky památkově významných objektů, až 65 % nákladů",
        "perex": "Hlavní město Praha vyhlásilo program na obnovu památek pro rok 2027. Vlastníci kulturních "
                 "památek a objektů v pražských památkových rezervacích a zónách mohou získat až 65 % nákladů na "
                 "stavební a restaurátorské práce. Žádosti se podávají do 30. 10. 2026 – a bez závazného "
                 "stanoviska památkářů to nepůjde.",
        "meta": "Praha – Program pro vlastníky památkově významných objektů 2027: až 65 % na obnovu památek, "
                "max. 5 mil. Kč. Žádosti do 30. 10. 2026.",
        "keywords": "Praha, památková péče, dotace na obnovu památek, kulturní památka, památková zóna",
        "facts": [
            ("Poskytovatel", "Hlavní město Praha (vyhlášeno usnesením Rady HMP č. 1449 z 22. 6. 2026)"),
            ("Alokace programu", "47 800 000 Kč"),
            ("Míra podpory", "max. 65 % uznatelných nákladů"),
            ("Maximální dotace", "5 000 000 Kč"),
            ("Uzávěrka", "30. 10. 2026"),
            ("Podání", "formulář na Portálu finanční podpory hl. m. Prahy"),
        ],
        "sections": [
            ("Co program podporuje", None,
             ["stavební a restaurátorské práce, které zachovávají památkovou hodnotu a podstatu objektu,",
              "odstranění graffiti a antigraffitové nátěry,",
              "restaurování movitých kulturních památek umístěných na veřejně přístupném místě v Praze."]),
            ("Na jaké objekty", None,
             ["nemovité kulturní památky na území Prahy,",
              "nemovitosti v pražských památkových rezervacích a památkových zónách."]),
            ("Kdo může žádat",
             "Vlastník nebo spoluvlastníci objektu. Žádat nelze na objekty ve vlastnictví hl. m. Prahy, jiných "
             "územních samosprávných celků, České republiky nebo jiného státu.", []),
            ("Na co si dát pozor", None,
             ["Všechny práce musí být výslovně uvedeny v závazném stanovisku odboru památkové péče MHMP, které je "
              "povinnou součástí žádosti – požádejte o něj s předstihem.",
              "Použijte formulář pro rok 2027 a doložte všechny povinné přílohy.",
              "Mezi dokumenty programu je vzor žádosti, veřejnoprávní smlouvy i hodnoticího formuláře – vyplatí "
              "se je projít ještě před podáním."]),
        ],
        "sources": [("Praha – program pro památkové objekty 2027",
                     "https://praha.eu/web/pamatky/program-pro-pamatkove-objekty-2027"),
                    ("Portál finanční podpory hl. m. Prahy", "https://granty.praha.eu/GrantyPortal/default")],
    },
]
