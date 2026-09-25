# Dotačné výzvy ČR – porovnanie pre grantové poradenstvo

Stav k **25. 9. 2026**. Súbor [`vyzvy_CZ_porovnanie_2026-09-25.xlsx`](vyzvy_CZ_porovnanie_2026-09-25.xlsx)
obsahuje **116 výziev**: 105 z pôvodného zoznamu a 11 doplnkov z webu, ktoré v ňom chýbali.

| Hárok | Obsah |
| --- | --- |
| **Súhrn** | počty podľa stavu, relevancie a zdroja; v bunke B3 je dátum „dnes“ – po zmene sa stav prepočíta |
| **Výzvy** | všetky výzvy s filtrom: stav k dátumu, dni do uzávierky, relevancia pre poradenstvo, poznámka, zdroj |
| **Legenda** | vysvetlivky, výzvy vynechané preto, že sú už uzavreté, a čo sledovať |

## Čo sa oplatí riešiť hneď (vysoká relevancia, ešte sa dá podať)

| Výzva | Uzávierka |
| --- | --- |
| TA ČR SIGMA – 18. VS, DC1 komercializácia (štúdia uskutočniteľnosti) | 27. 10. 2026 |
| AOPK – OPŽP 17. výzva SC 1.3 a 18. výzva SC 1.6 (100 %) | 30. 10. 2026 |
| Praha – pamiatková starostlivosť 2027 | 30. 10. 2026 |
| Kraj Vysočina – podnikateľské vouchery 2026 *(doplnok)* | 30. 10. 2026 |
| ČRA – Program B2B | 10. 11. 2026 |
| OPZ+ 12. výzva – diverzitná a flexibilná pracovná kultúra (100 %) | 30. 11. 2026 |
| Modernizačný fond – TRANSCom 2/2025 *(doplnok)* | 30. 11. 2026 |
| Modernizačný fond – RES+ 6/2025 agrofotovoltika *(doplnok)* | 30. 6. 2027 |
| **OP TAK – Technologie pro MAS II** – podporuje aj softvér/IT, teda ERP/Odoo *(doplnok)* | 1. 9. 2027 |
| NZÚ HOUSEnerg – bytové domy A, C, D | 30. 6. 2028 |
| OP Doprava 46. a 47. výzva (dobíjanie), OPZ+ 92. výzva (detské skupiny) | očakávané |

## Nové výzvy pre web (grantove-poradenstvi.cz)

[`nove_vyzvy_web.html`](nove_vyzvy_web.html) obsahuje 11 výziev, ktoré v pôvodnom zozname chýbali. Sú v češtine
a v rovnakom formáte (popis + tabuľka Typ financování / Alokace / Status / Uzávěrka):

* **sekcia A (7 výziev)** – dá sa zverejniť: OP TAK Technologie pro MAS II, Kraj Vysočina – podnikateľské vouchery,
  Modernizačný fond (TRANSCom, lokomotívy, agrofotovoltika, TRANSGov), OP ST Transformačný úver;
* **sekcia B (4 výzvy)** – pred zverejnením overiť u poskytovateľa: IROP 10. a 120. výzva, NRB Nové úspory energie,
  SZIF kolo 1.–22. 10. 2026.

Vloženie do Odoo: stránka s výzvami → Upraviť → HTML/kód → vložiť obsah súboru → Uložiť → Zverejniť.

## Upozornenia

* Údaje z pôvodného zoznamu nie sú overené u poskytovateľov.
* Doplnky (OP TAK, IROP, NRB, SZIF, Modernizačný fond, Vysočina) sú z výsledkov vyhľadávania; odkaz na zdroj je
  v stĺpci *Overenie / zdroj*. Pred ponukou klientovi každú výzvu overiť u poskytovateľa.
* Relevancia je odhad z pohľadu komerčného grantového poradenstva a dá sa v tabuľke prepísať.

## Pregenerovanie

```bash
pip install openpyxl
python dotacie/build_vyzvy.py
```

Vzorce (stav, dni do uzávierky, súhrn) sa prepočítajú pri otvorení v Exceli alebo LibreOffice.
