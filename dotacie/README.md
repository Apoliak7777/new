# Dotačné výzvy ČR – porovnanie pre grantové poradenstvo

Stav k **25. 9. 2026**. Súbor [`vyzvy_CZ_porovnanie_2026-09-25.xlsx`](vyzvy_CZ_porovnanie_2026-09-25.xlsx)
obsahuje **117 výziev**: 105 z pôvodného zoznamu a 12 doplnkov z webu, ktoré v ňom chýbali.

| Hárok | Obsah |
| --- | --- |
| **Súhrn** | počty podľa stavu, relevancie a zdroja; v bunke B3 je dátum „dnes“ – po zmene sa stav prepočíta |
| **Výzvy** | všetky výzvy s filtrom: stav k dátumu, dni do uzávierky, relevancia pre poradenstvo, poznámka, zdroj |
| **Legenda** | vysvetlivky, opravy po overení, výzvy vynechané preto, že sú už uzavreté, a čo sledovať |

## Opravy po overení (25. 9. 2026)

Pri písaní blogu sa výzvy overovali na stránkach poskytovateľov. Časť výziev z pôvodného zoznamu je v skutočnosti
**uzavretá**. V tabuľke majú opravenú uzávierku, pôvodný termín je v stĺpci *Termín – poznámka*:

| Výzva | Zoznam uvádzal | Skutočnosť |
| --- | --- | --- |
| AOPK – OPŽP 17. výzva SC 1.3 a 18. výzva SC 1.6 | otvorené do 30. 10. 2026 | uzavreté 2. 6. 2026, alokácia sa vyčerpala v deň otvorenia |
| OPŽP 104. výzva | uzávierka 25. 9. 2026 | príjem skončil 30. 6. 2026 |
| NZÚ HOUSEnerg bytové domy A–D | do 30. 6. 2028 | výzva 6/2023 ukončená 8. 11. 2025; nástupca **NZÚ 2026+** (bezúročný úver) je doplnený ako riadok 117 |
| EIC Accelerator | 17. 12. 2026 | posledný cut-off plných žiadostí v 2026 je 4. 11. |
| OP ST Transformační úvěr *(doplnok)* | do konca 2026 | NRB pozastavila príjem 10. 6. 2026 |

Ďalšie spresnenia sú v stĺpcoch *Poznámka* a *Overenie / zdroj*:
* **ČRA B2B** má dve fázy: príprava 50 % / 500 tis. Kč, realizácia 40 % a 30 % / 2 mil. Kč ročne.
* **OPZ+ 12. výzva** je len pre zamestnávateľov s viac ako 50 zamestnancami.
* **OP TAK MAS II** dáva 50 % z výdajov 250 tis.–3 mil. Kč.
* **TRANSCom** dáva 30/40/50 % z rozdielu ceny oproti naftovému vozidlu.

**OPZ+ 092 (detské skupiny)** sa overiť nepodarilo. V roku 2026 bola výzva 090 označená ako posledná na budovanie
nových detských skupín.

## Čo sa oplatí riešiť hneď (vysoká relevancia, ešte sa dá podať)

| Výzva | Uzávierka |
| --- | --- |
| TA ČR SIGMA – 18. VS, DC1 komercializácia (štúdia uskutočniteľnosti) | 27. 10. 2026 |
| Praha – pamiatková starostlivosť 2027 | 30. 10. 2026 |
| Kraj Vysočina – podnikateľské vouchery 2026 *(doplnok)* | 30. 10. 2026 |
| ČRA – Program B2B | 10. 11. 2026 |
| OPZ+ 12. výzva – diverzitná a flexibilná pracovná kultúra | 30. 11. 2026 |
| Modernizačný fond – TRANSCom 2/2025 *(doplnok)* | 30. 11. 2026 |
| Modernizačný fond – RES+ 6/2025 agrofotovoltika *(doplnok)* | 30. 6. 2027 |
| **OP TAK – Technologie pro MAS II** – podporuje aj softvér/IT, teda ERP/Odoo *(doplnok)* | 1. 9. 2027 |
| Nová zelená úsporám 2026+ – bytové domy, bezúročný úver *(doplnok)* | 31. 10. 2029 |
| OP Doprava 46. a 47. výzva (dobíjanie) | očakávané |

## Blog pre web (grantove-poradenstvi.cz)

Priečinok [`blog/`](blog/) obsahuje **13 článkov v češtine**: súhrnný *Přehled aktuálních dotačních výzev*
(22 otvorených výziev v 5 skupinách) a 12 podrobných článkov. Každý podrobný článok má:
* perex,
* tabuľku faktov,
* čo výzva podporuje, kto môže žiadať a na čo si dať pozor,
* odkazy na oficiálne zdroje,
* výzvu na kontakt (`/contactus`) a upozornenie na dátum stavu.

| Článok | Výzvy |
| --- | --- |
| `op-tak-technologie-pro-mas-ii` | OP TAK Technologie pro MAS II |
| `vysocina-podnikatelske-vouchery-2026` | Kraj Vysočina – podnikateľské vouchery |
| `ta-cr-sigma-dc1-komercializace` | TA ČR SIGMA DC1 |
| `cra-program-b2b-2027` | ČRA Program B2B |
| `eic-accelerator-2026` | EIC Accelerator |
| `modernizacni-fond-elektricka-nakladni-doprava` | TRANSCom 2/2025, e-lokomotívy, TRANSGov |
| `modernizacni-fond-res-agrofotovoltaika` | RES+ 6/2025 |
| `opz-plus-flexibilni-pracovni-kultura` | OPZ+ 12. výzva |
| `op-doprava-dobijeci-stanice` | OP Doprava 44–48 |
| `nzu-2026-bytove-domy` | NZÚ 2026+ a renovačný pas (NPO 2/2026) |
| `opzp-ekologicke-zateze-a-svahy` | OPŽP 72. a 106. výzva |
| `praha-pamatkova-pece-2027` | Praha – pamiatky 2027 |

Uzávierky a alokácie v článkoch berie build z [`vyzvy_data.py`](vyzvy_data.py). Ak si článok a tabuľka odporujú,
build skončí chybou. Kontroluje aj dĺžku titulku (max 70 znakov) a meta popisu (max 160 znakov).

**Vloženie do Odoo** (Webová stránka → Blog):
1. **Import:** *Blog → Príspevky → ⚙ Importovať záznamy* → [`blog/blog_posts_import.csv`](blog/blog_posts_import.csv).
   * Stĺpce: `name`, `subtitle`, `teaser_manual`, `website_meta_title`, `website_meta_description`,
     `website_meta_keywords`, `is_published`, `content`.
   * Všetky články sa naimportujú **nezverejnené**.
   * Ak má web viac blogov, pridaj stĺpec `blog_id` s názvom blogu. Bez neho Odoo použije prvý blog.
2. **Ručne:** nový príspevok → *HTML/kód* → vložiť obsah `blog/<slug>.html`. Titulok a podnadpis sú v náhľade.

Náhľad všetkých článkov: [`blog/index.html`](blog/index.html) (otvoriť v prehliadači).

**Pred zverejnením skontrolovať:** riadky súhrnného článku bez vlastného článku pochádzajú z pôvodného zoznamu
a neboli overené u poskytovateľa:
* Praha – cestovný ruch 2027,
* Praha – životné prostredie 2027,
* MK ČR – Program záchrany architektonického dedičstva,
* NRB – Nová ELENA,
* JTM,
* NPO – Dostupné nájomné bývanie.

## Nové výzvy pre web – formát zoznamu výziev

[`nove_vyzvy_web.html`](nove_vyzvy_web.html) obsahuje výzvy, ktoré v pôvodnom zozname chýbali. Sú v češtine,
v rovnakom formáte ako zoznam výziev: popis + tabuľka Typ financování / Alokace / Status / Uzávěrka.

* **Sekcia A (7 výziev)** sa dá zverejniť:
  * OP TAK Technologie pro MAS II,
  * Kraj Vysočina – podnikateľské vouchery,
  * Modernizačný fond: TRANSCom, lokomotívy, agrofotovoltika, TRANSGov,
  * NZÚ 2026+ pre bytové domy.
  * OP ST Transformačný úver bol zo sekcie odstránený, príjem je pozastavený.
* **Sekcia B (4 výzvy)** treba pred zverejnením overiť u poskytovateľa:
  * IROP 10. a 120. výzva,
  * NRB Nové úspory energie,
  * SZIF kolo 1.–22. 10. 2026.

Vloženie do Odoo: stránka s výzvami → Upraviť → HTML/kód → vložiť obsah súboru → Uložiť → Zverejniť.

## Upozornenia

* Overenie z 25. 9. 2026 prebehlo cez výsledky vyhľadávania. Oficiálne stránky (sfzp.gov.cz, opzp.cz, praha.eu, …)
  boli z prostredia priamo nedostupné. Pred podaním žiadosti za klienta over vždy text výzvy.
* Relevancia je odhad z pohľadu komerčného grantového poradenstva a dá sa v tabuľke prepísať.

## Pregenerovanie

```bash
pip install openpyxl
python dotacie/build_vyzvy.py   # xlsx
python dotacie/build_blog.py    # blog/ (bez závislostí)
```

Vzorce v xlsx (stav, dni do uzávierky, súhrn) sa prepočítajú pri otvorení v Exceli alebo LibreOffice.
