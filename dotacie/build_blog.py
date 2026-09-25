"""Blogové články o aktuálnych výzvach pre grantove-poradenstvi.cz (Odoo Website Blog).

Výstup do dotacie/blog/:
  <slug>.html           obsah článku na vloženie do Odoo (Upraviť → HTML/kód)
  blog_posts_import.csv import do Webová stránka → Blog → Príspevky (všetky ako nezverejnené)
  index.html            náhľad všetkých článkov v prehliadači

Fakty berie z vyzvy_data.R (uzávierka, alokácia) a z blog_data.POSTS; build zlyhá, ak si odporujú.
"""
import csv
import datetime as dt
import html
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from blog_data import CTA, DISCLAIMER, EU_NOTE, POSTS, ROUNDUP, ROUNDUP_POST  # noqa: E402
from vyzvy_data import R, TODAY  # noqa: E402

OUT = HERE / "blog"
UNVERIFIED = {108, 109, 114, 116}  # sekundárny zdroj alebo chýba uzávierka
DUPLICATE = {85}


def row(idx: int) -> tuple:
    return R[idx - 1]


def cz_date(value: str | dt.date) -> str:
    date = dt.date.fromisoformat(value) if isinstance(value, str) else value
    return f"{date.day}. {date.month}. {date.year}"


def cz_value(value: str) -> str:
    return {"neuvedené": "neuvedeno", "": "neuvedeno"}.get(value, value)


def is_current(idx: int) -> bool:
    deadline = row(idx)[9]
    return idx not in UNVERIFIED | DUPLICATE and (not deadline or dt.date.fromisoformat(deadline) > TODAY)


def esc(text: str) -> str:
    """Escape textu; **tučné** sa zmení na <strong>."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html.escape(text, quote=False))


def section(inner: str) -> str:
    # s_text_block: v Odoo editore sa blok dá ďalej upravovať ako bežný textový snippet
    return ('<section class="s_text_block pt16 pb16" data-snippet="s_text_block" data-name="Text">\n'
            f'<div class="container s_allow_columns">\n{inner}\n</div>\n</section>')


def table(head: list[str] | None, rows: list[list[str]]) -> str:
    """Bunky sú už escapované HTML; bez hlavičky je prvý stĺpec <th> (tabuľka faktov)."""
    out = ['<table class="table table-sm table-bordered">']
    if head:
        out.append("<thead><tr>" + "".join(f"<th>{esc(h)}</th>" for h in head) + "</tr></thead>")
    out.append("<tbody>")
    for first, *rest in rows:
        tag = "th" if head is None else "td"
        out.append(f"<tr><{tag}>{first}</{tag}>" + "".join(f"<td>{c}</td>" for c in rest) + "</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def footer() -> str:
    return (f'<h2>{esc(CTA[0])}</h2>\n<p>{esc(CTA[1])} <a href="/contactus">{esc(CTA[2])}</a></p>\n'
            f'<p class="small text-muted">{esc(DISCLAIMER.format(date=cz_date(TODAY)))}</p>')


def render_post(post: dict) -> str:
    parts = [f'<p class="lead">{esc(post["perex"])}</p>',
             table(None, [[esc(label), esc(value)] for label, value in post["facts"]])]
    for heading, intro, bullets in post["sections"]:
        parts.append(f"<h2>{esc(heading)}</h2>")
        if intro:
            parts.append(f"<p>{esc(intro)}</p>")
        if bullets:
            parts.append("<ul>\n" + "\n".join(f"<li>{esc(b)}</li>" for b in bullets) + "\n</ul>")
    links = " · ".join(f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{esc(label)}</a>'
                       for label, url in post["sources"])
    parts.append(f"<p><strong>Oficiální zdroje:</strong> {links}</p>")
    parts.append(footer())
    return section("\n".join(parts))


def roundup_rows(ids: tuple, overrides: dict) -> tuple[str, str]:
    first = row(ids[0])
    amount = overrides.get("max") or " / ".join(v for v in (cz_value(first[8]), first[7]) if v != "neuvedené")
    if "deadline" in overrides:
        deadline = overrides["deadline"]
    elif first[9]:
        days = (dt.date.fromisoformat(first[9]) - TODAY).days
        deadline = cz_date(first[9]) + (f" (za {days} dní)" if days <= 14 else "")
    else:
        deadline = "průběžně"
    return amount, deadline


def render_roundup() -> str:
    by_slug = {p["slug"]: p for p in POSTS}
    parts = [f'<p class="lead">{esc(ROUNDUP_POST["perex"])}</p>']
    for heading, items in ROUNDUP:
        rows = []
        for ids, title, who, slug, overrides in items:
            assert all(is_current(i) for i in ids), (ids, title)
            amount, deadline = roundup_rows(ids, overrides)
            new = " <strong>NOVÉ</strong>" if all(row(i)[0] != "Tvoj zoznam" for i in ids) else ""
            detail = f'<br/><em>Podrobně: {esc(by_slug[slug]["title"])}</em>' if slug else ""
            rows.append([esc(title) + new + detail, esc(who), esc(amount), esc(deadline)])
        parts.append(f"<h2>{esc(heading)}</h2>")
        parts.append(table(["Výzva", "Pro koho", "Max. dotace / míra podpory", "Uzávěrka"], rows))
    eu = [i for i in range(1, len(R) + 1) if row(i)[1].startswith("EK") and is_current(i)]
    parts.append(f"<h2>{esc(EU_NOTE[0])}</h2>\n<p>{esc(EU_NOTE[1].format(count=len(eu)))}</p>")
    parts.append(footer())
    return section("\n".join(parts))


def plain(fragment: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", fragment))
    return re.sub(r"\s+", " ", text)


def check(post: dict, body: str) -> None:
    """Uzávierka a alokácia z tabuľky výziev musia byť v článku – blog a xlsx si nesmú odporovať."""
    text = plain(body)
    for idx in post["ids"]:
        zdroj, _, _, _, _, _, allocation, _, max_grant, deadline, *_ = row(idx)
        expected = [cz_date(deadline)] if deadline else []
        expected += [v for v in (allocation, max_grant) if v not in ("neuvedené", "") and "(" not in v]
        for value in expected:
            if value not in text:
                raise SystemExit(f"{post['slug']}: v článku chýba {value!r} z R[{idx}] ({zdroj})")
    for field, limit in (("meta", 160), ("title", 70)):
        if len(post[field]) > limit:
            raise SystemExit(f"{post['slug']}: {field} má {len(post[field])} znakov (max {limit})")


def preview(articles: list[tuple[dict, str]]) -> str:
    toc = "\n".join(f'<li><a href="#{p["slug"]}">{esc(p["title"])}</a></li>' for p, _ in articles)
    body = "\n".join(f'<article id="{p["slug"]}"><h1>{esc(p["title"])}</h1>\n<p><em>{esc(p["subtitle"])}</em></p>\n'
                     f"{content}</article><hr/>" for p, content in articles)
    return f"""<!DOCTYPE html>
<html lang="cs"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Náhled blogu – aktuální výzvy</title>
<style>
body{{font:16px/1.55 system-ui,sans-serif;max-width:860px;margin:0 auto;padding:16px;color:#1b1b1b;background:#fff}}
table{{border-collapse:collapse;width:100%;margin:12px 0}}th,td{{border:1px solid #ccc;padding:6px 8px;text-align:left;vertical-align:top}}
th{{background:#f3f5f8;width:30%}}thead th{{width:auto}}.lead{{font-size:1.15em}}.small{{font-size:.85em}}.text-muted{{color:#666}}
</style></head><body>
<p class="small text-muted">Náhled – stav k {cz_date(TODAY)}. Do Odoo se vkládá obsah souborů &lt;slug&gt;.html nebo CSV import.</p>
<ol>{toc}</ol>
{body}
</body></html>
"""


def main() -> None:
    OUT.mkdir(exist_ok=True)
    articles = [(ROUNDUP_POST, render_roundup())]
    for post in POSTS:
        body = render_post(post)
        check(post, body)
        articles.append((post, body))
    check(ROUNDUP_POST, articles[0][1])
    for post, body in articles:
        (OUT / f"{post['slug']}.html").write_text(body + "\n", encoding="utf-8")
    with open(OUT / "blog_posts_import.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["name", "subtitle", "teaser_manual", "website_meta_title", "website_meta_description",
                         "website_meta_keywords", "is_published", "content"])
        for post, body in articles:
            writer.writerow([post["title"], post["subtitle"], post["perex"], post["title"], post["meta"],
                             post["keywords"], "False", body])
    (OUT / "index.html").write_text(preview(articles), encoding="utf-8")
    print(f"{OUT}: {len(articles)} článkov")


if __name__ == "__main__":
    main()
