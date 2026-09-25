"""Obsah blogu (čeština) pre build_blog.py. Čísla a termíny musia sedieť s vyzvy_data.R – build to kontroluje.

POSTS: slug, ids (riadky v R, 1-based), title (max 70 znakov), subtitle, perex, meta (max 160 znakov),
keywords, facts [(popis, hodnota)], sections [(nadpis, úvodný odsek alebo None, [odrážky])], sources [(názov, URL)].
V texte **tučné** → <strong>.
"""

CTA = ("Potřebujete pomoc se žádostí?",
       "Posoudíme, zda váš záměr splňuje podmínky výzvy, spočítáme možnou dotaci a připravíme kompletní žádost "
       "včetně příloh.",
       "Napište nám přes kontaktní formulář.")

DISCLAIMER = ("Informace vycházejí z vyhlášení výzvy a zveřejněných podkladů k {date}. Závazné jsou vždy aktuální "
              "podmínky poskytovatele; termíny a alokace se mohou změnit.")

EU_NOTE = ("Evropské programy pro mezinárodní konsorcia",
           "Kromě výše uvedených výzev je aktuálně otevřeno ještě {count} výzev programů Evropské komise (Horizont "
           "Evropa, Evropský obranný fond, CEF, Digitální Evropa, EIC a další). Jsou určeny především mezinárodním "
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
        ((107,), "Kraj Vysočina – Podnikatelské vouchery 2026", "podnikatelé s provozovnou na Vysočině",
         "vysocina-podnikatelske-vouchery-2026", {}),
        ((44,), "TA ČR SIGMA – 18. veřejná soutěž, DC1 (komercializace)", "malé podniky a startupy",
         "ta-cr-sigma-dc1-komercializace", {}),
        ((3,), "Česká rozvojová agentura – Program B2B", "firmy plánující projekt v rozvojové zemi",
         "cra-program-b2b-2026", {}),
        ((59,), "EIC Accelerator", "inovativní MSP a startupy (deep-tech)", "eic-accelerator-2026", {}),
        ((58,), "OP Zaměstnanost+ – 12. výzva: diverzitní a flexibilní pracovní kultura",
         "zaměstnavatelé, OSVČ, NNO, obce", "opz-plus-12-vyzva-flexibilni-prace", {}),
        ((110,), "Modernizační fond – TRANSCom 2/2025: elektrické nákladní vozy", "silniční nákladní dopravci",
         "modernizacni-fond-transcom-2-2025", {}),
        ((111,), "Modernizační fond – nové elektrické lokomotivy", "železniční nákladní dopravci",
         "modernizacni-fond-transcom-2-2025", {}),
        ((112,), "Modernizační fond – RES+ 6/2025: agrofotovoltaika", "zemědělští podnikatelé",
         "modernizacni-fond-res-agrofotovoltaika", {}),
        ((115,), "OP Spravedlivá transformace – Transformační úvěr",
         "podnikatelé v Karlovarském, Ústeckém a Moravskoslezském kraji", "op-st-transformacni-uver", {}),
        ((86,), "Národní rozvojová banka – Nová ELENA (projekty EPC)", "veřejný sektor a firmy", None, {}),
    ]),
    ("Doprava a elektromobilita", [
        ((94, 95, 96, 93), "OP Doprava – výzvy 44–46 a 48: dobíjecí stanice pro osobní auta",
         "vlastníci a provozovatelé dobíjecí infrastruktury, i firmy", "op-doprava-dobijeci-stanice",
         {"max": "55–80 % podle výzvy", "deadline": "vyhlášení 8–12/2026"}),
        ((97,), "OP Doprava – 47. výzva: rychlodobíjení nákladních vozidel",
         "vlastníci a provozovatelé dobíjecí infrastruktury, i firmy", "op-doprava-dobijeci-stanice",
         {"deadline": "vyhlášení 10/2026, konec 1/2027"}),
    ]),
    ("Bydlení a budovy", [
        ((73, 71, 72, 74), "Nová zelená úsporám – HOUSEnerg pro bytové domy (A–D)",
         "SVJ, bytová družstva, vlastníci bytových domů", "nzu-housenerg-bytove-domy",
         {"max": "až 50 % (novostavby 150 000 Kč na byt)"}),
        ((57,), "NPO – Renovační pas budovy a dotační poradenství", "poradci zapsaní v evidenci SFŽP",
         "npo-renovacni-pas-poradenstvi", {}),
        ((61,), "NPO – Dostupné nájemní bydlení, výzva I", "obce a developeři (projekty nad 250 mil. Kč)", None,
         {"max": "zvýhodněný úvěr až 1,2 mld. Kč / 80 %"}),
    ]),
    ("Obce, krajina a životní prostředí", [
        ((46, 47), "OPŽP / AOPK – 17. a 18. výzva: přírodě blízká opatření a biodiverzita",
         "obce, vlastníci pozemků, firmy, NNO", "opzp-aopk-priroda-biodiverzita", {"max": "až 100 %"}),
        ((50,), "OPŽP – 72. výzva: staré ekologické zátěže", "obce, firmy, stát", "opzp-ekologicke-zateze-svahy", {}),
        ((60,), "OPŽP – 106. výzva: stabilita svahů", "obce, vlastníci pozemků, NNO", "opzp-ekologicke-zateze-svahy",
         {}),
        ((67,), "Just Transition Mechanism – úvěrový nástroj pro veřejný sektor",
         "obce a kraje v uhelných regionech", None, {"max": "grant + úvěr EIB",
                                                      "deadline": "kolové, další kolo 16. 2. 2027"}),
        ((98, 99, 100), "Praha – Grantový program životního prostředí 2027", "pražské NNO, SVJ, fyzické osoby",
         "praha-granty-zivotni-prostredi-2027", {"max": "450–600 tis. Kč, až 100 %"}),
    ]),
    ("Kultura, památky a cestovní ruch", [
        ((1, 2), "Praha – Program podpory cestovního ruchu 2027 (opatření I a II)",
         "organizátoři kongresů a akcí v Praze", "praha-cestovni-ruch-2027", {"max": "až 2 mil. Kč, 30–100 %"}),
        ((48,), "Praha – Památková péče 2027", "vlastníci památkově významných objektů v Praze",
         "praha-pamatkova-pece-2027", {}),
        ((27,), "Ministerstvo kultury – Program záchrany architektonického dědictví", "vlastníci kulturních památek",
         None, {}),
    ]),
    ("Sociální oblast a zaměstnanost", [
        ((105,), "OP Zaměstnanost+ – 92. výzva: dětské skupiny", "firmy (firemní dětské skupiny), obce, NNO",
         "opz-plus-92-vyzva-detske-skupiny", {"deadline": "vyhlášení 3/2027, uzávěrka 30. 11. 2027"}),
        ((75,), "SZP – 54.78 Podpora poradenství, individuální poradenství", "poradci s certifikací ADVIGREEN",
         None, {}),
    ]),
]

POSTS = []
