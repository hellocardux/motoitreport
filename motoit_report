# motoit_report.py
# Genera un report HTML interattivo con tabella e grafici senza avviare server

import re
import time
from dataclasses import dataclass
from typing import List, Dict, Optional
from urllib.parse import urljoin
from pathlib import Path

import requests
from bs4 import BeautifulSoup
import pandas as pd
import plotly.graph_objs as go
from plotly.offline import plot

# -----------------------------
# Parsing helpers
# -----------------------------
def text_clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def parse_price(txt: str) -> Optional[int]:
    m = re.search(r"(\d{1,3}(?:[\.\s]\d{3})+|\d+)\s*€", txt)
    if not m:
        return None
    raw = m.group(1).replace(".", "").replace(" ", "")
    try:
        return int(raw)
    except ValueError:
        return None

def parse_year(txt: str) -> Optional[int]:
    m = re.search(r"\b(20\d{2}|19\d{2})\b", txt)
    if not m:
        return None
    y = int(m.group(1))
    if 1990 <= y <= 2035:
        return y
    return None

def parse_km(txt: str) -> Optional[int]:
    m = re.search(r"Km\s*:?[\s\-]*([\d\. ]+)", txt, flags=re.IGNORECASE)
    if not m:
        return None
    raw = m.group(1).replace(".", "").replace(" ", "")
    try:
        return int(raw)
    except ValueError:
        return None

def parse_location(txt: str) -> Optional[str]:
    m = re.search(r"([A-Za-zÀ-ÿ'’\-\s]+)\s*\([A-Z]{2}\)", txt)
    if m:
        return text_clean(m.group(0))
    return None

def has_listings(soup: BeautifulSoup) -> bool:
    txt = soup.get_text(" ", strip=True)
    return any(k in txt for k in ["annunci", "Prezzo", "km", "CBR", "usate"])

def listing_blocks(soup: BeautifulSoup):
    sel = (
        "article, li, div.card, div.result, div.list-item, "
        "div[class*='Listing'], div[class*='Result']"
    )
    nodes = soup.select(sel)
    return nodes if nodes else [soup]

def extract_primary_link(node) -> Optional[str]:
    a = node.find("a", href=True)
    if not a:
        return None
    href = a["href"]
    if href.startswith("/"):
        href = urljoin("https://www.moto.it", href)
    return href

# -----------------------------
# Scraper
# -----------------------------
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
}

@dataclass
class ScrapeConfig:
    search_url: str
    delay_sec: float
    max_pages: int
    headers: Dict[str, str]
    brand: str
    model: str

def fetch(url: str, headers: Dict[str, str]) -> BeautifulSoup:
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")

def discover_pages(base_url: str, headers: Dict[str, str], max_pages: int, delay: float) -> List[str]:
    pages = [base_url.rstrip("/")]
    try:
        soup = fetch(base_url, headers)
        hrefs = {a.get("href", "") for a in soup.find_all("a")}
        nums = set()
        for h in hrefs:
            if not h:
                continue
            m = re.search(r"/pagina-(\d+)", h)
            if m:
                nums.add(int(m.group(1)))
        if nums:
            for i in range(2, min(max(nums), max_pages) + 1):
                pages.append(f"{base_url.rstrip('/')}/pagina-{i}")
            return pages
    except Exception:
        pass

    for i in range(2, max_pages + 1):
        url = f"{base_url.rstrip('/')}/pagina-{i}"
        try:
            soup = fetch(url, headers)
            if not has_listings(soup):
                break
            pages.append(url)
        except requests.HTTPError as e:
            code = getattr(e.response, "status_code", None)
            if code == 404:
                break
        time.sleep(delay)
    return pages

def parse_page(url: str, headers: Dict[str, str], brand: str, model: str) -> List[Dict]:
    soup = fetch(url, headers)
    items = []
    for node in listing_blocks(soup):
        txt = text_clean(node.get_text(" ", strip=True))
        brand_ok = (brand.lower() in txt.lower()) if brand else True
        model_ok = (model.lower().replace(" ", "") in txt.lower().replace(" ", "")) if model else True
        price = parse_price(txt)
        year = parse_year(txt)
        if not (brand_ok and model_ok and price and year):
            continue
        km = parse_km(txt)
        loc = parse_location(txt)
        href = extract_primary_link(node) or url
        items.append({
            "brand": brand or "",
            "model": model or "",
            "year": year,
            "price_eur": price,
            "km": km,
            "location": loc,
            "source_url": href
        })
    return items

def run_scrape(cfg: ScrapeConfig) -> pd.DataFrame:
    pages = discover_pages(cfg.search_url, cfg.headers, cfg.max_pages, cfg.delay_sec)
    rows = []
    for p in pages:
        rows.extend(parse_page(p, cfg.headers, cfg.brand, cfg.model))
        time.sleep(cfg.delay_sec)
    df = pd.DataFrame(rows).drop_duplicates()
    if not df.empty:
        df = df.sort_values(["year", "price_eur"], ascending=[True, True])
    return df

def build_url(brand: str, model: str) -> str:
    b = text_clean(brand).lower().replace(" ", "-")
    m = text_clean(model).lower().replace(" ", "-")
    return f"https://www.moto.it/moto-usate/{b}/{m}"

# -----------------------------
# Report HTML
# -----------------------------
HTML_TEMPLATE = """<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <title>Report Moto.it — Prezzo vs Anno</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link rel="stylesheet" href="https://cdn.datatables.net/1.13.8/css/dataTables.bootstrap5.min.css">
  <style>
    body { padding: 20px; background: #f8f9fa; }
    .card { border-radius: 12px; }
    .chart-card { padding: 16px; background: #fff; border-radius: 12px; border: 1px solid #eee; box-shadow: 0 2px 10px rgba(0,0,0,0.04); }
    .muted { color: #6c757d; }
    .smallcaps { font-variant: all-small-caps; letter-spacing: .5px; }
  </style>
</head>
<body>
  <div class="container-fluid">
    <h2 class="mb-2">Usato Moto.it — Prezzo vs Anno</h2>
    <p class="muted">Ricerca: <span class="smallcaps">{{SEARCH_LABEL}}</span> • URL: <a href="{{SEARCH_URL}}" target="_blank" rel="noopener">{{SEARCH_URL}}</a> • Annunci: <b>{{N_ROWS}}</b></p>

    <div class="row g-4">
      <div class="col-lg-8">
        <div class="chart-card">
          <h5 class="mb-3">Prezzo vs Anno</h5>
          {{SCATTER_DIV}}
        </div>
      </div>
      <div class="col-lg-4">
        <div class="chart-card">
          <h5 class="mb-3">Prezzo medio per anno</h5>
          {{LINE_DIV}}
          <hr>
          <div class="row">
            <div class="col-6">
              <div class="p-2 border rounded text-center">
                <div class="muted small">Anno medio più economico</div>
                <div class="fs-4">{{MIN_YEAR}}<div class="muted">€{{MIN_MEAN}}</div></div>
              </div>
            </div>
            <div class="col-6">
              <div class="p-2 border rounded text-center">
                <div class="muted small">Anno medio più costoso</div>
                <div class="fs-4">{{MAX_YEAR}}<div class="muted">€{{MAX_MEAN}}</div></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="row g-4 mt-1">
      <div class="col-12">
        <div class="card p-3">
          <h5 class="mb-3">Statistiche per anno</h5>
          <div class="table-responsive">
            <table class="table table-sm" id="stats-table">
              <thead>
                <tr><th>Anno</th><th>#</th><th>Media €</th><th>Mediana €</th><th>Min €</th><th>Max €</th></tr>
              </thead>
              <tbody>
                {{STATS_TBODY}}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <div class="row g-4 mt-1">
      <div class="col-12">
        <div class="card p-3">
          <h5 class="mb-3">Annunci</h5>
          <div class="table-responsive">
            <table class="table table-striped" id="ads-table" style="width:100%">
              <thead>
                <tr><th>Anno</th><th>Prezzo €</th><th>Km</th><th>Luogo</th><th>Link</th></tr>
              </thead>
              <tbody>
                {{ADS_TBODY}}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <footer class="mt-4 text-muted small">
      Se Moto.it cambia il markup, aggiorna i selettori nel parser. Report generato offline, nessun server richiesto.
    </footer>
  </div>

  <script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
  <script src="https://cdn.datatables.net/1.13.8/js/jquery.dataTables.min.js"></script>
  <script src="https://cdn.datatables.net/1.13.8/js/dataTables.bootstrap5.min.js"></script>
  <script>
  $(function(){
    $('#ads-table').DataTable({ pageLength: 25, order: [[0, 'asc'], [1, 'asc']] });
    $('#stats-table').DataTable({ searching: false, paging: false, info: false, order: [[0, 'asc']] });
  });
  </script>
</body>
</html>
"""

def render_table_rows_stats(stats_df: pd.DataFrame) -> str:
    rows = []
    for y, row in stats_df.iterrows():
        rows.append(
            f"<tr><td>{int(y)}</td><td>{int(row['count'])}</td><td>{int(round(row['mean']))}</td>"
            f"<td>{int(round(row['median']))}</td><td>{int(row['min'])}</td><td>{int(row['max'])}</td></tr>"
        )
    return "\n".join(rows)

def render_table_rows_ads(df: pd.DataFrame) -> str:
    rows = []
    for _, r in df.iterrows():
        link = r.get("source_url") or ""
        a = f'<a href="{link}" target="_blank" rel="noopener">apri</a>' if link else ""
        km = "" if pd.isna(r.get("km")) else int(r.get("km"))
        loc = "" if pd.isna(r.get("location")) else r.get("location")
        rows.append(
            f"<tr><td>{int(r['year'])}</td><td>{int(r['price_eur'])}</td><td>{km}</td><td>{loc}</td><td>{a}</td></tr>"
        )
    return "\n".join(rows)

def make_scatter(df: pd.DataFrame):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["year"], y=df["price_eur"], mode="markers",
        name="Annunci", hovertemplate="Anno %{x}<br>€%{y}<extra></extra>"
    ))
    fig.update_layout(
        height=420, margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title="Anno", yaxis_title="Prezzo (€)", template="plotly_white"
    )
    return plot(fig, include_plotlyjs="cdn", output_type="div")

def make_line(stats_df: pd.DataFrame):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[int(x) for x in stats_df.index],
        y=stats_df["mean"],
        mode="lines+markers",
        name="Prezzo medio",
        hovertemplate="Anno %{x}<br>Media €%{y:.0f}<extra></extra>"
    ))
    fig.update_layout(
        height=320, margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title="Anno", yaxis_title="Prezzo medio (€)", template="plotly_white"
    )
    return plot(fig, include_plotlyjs=False, output_type="div")

def main():
    # Parametri base. Se vuoi cambiare modello o URL, modificali qui.
    brand = "Honda"
    model = "CBR 650 R"
    custom_url = ""  # se vuoi impostare direttamente l'URL di Moto.it, mettilo qui
    max_pages = 12
    delay_sec = 0.8

    search_url = custom_url.strip() or build_url(brand, model)

    cfg = ScrapeConfig(
        search_url=search_url,
        delay_sec=delay_sec,
        max_pages=max_pages,
        headers=DEFAULT_HEADERS.copy(),
        brand=brand,
        model=model,
    )

    print(f"Raccolgo annunci da: {cfg.search_url}")
    df = run_scrape(cfg)
    if df.empty:
        raise SystemExit("Nessun annuncio trovato")

    # CSV di servizio
    Path("annunci_motoit.csv").write_text(df.to_csv(index=False, encoding="utf-8-sig"), encoding="utf-8")
    print(f"Salvato CSV: annunci_motoit.csv  ({len(df)} righe)")

    # Statistiche per anno
    stats = df.groupby("year")["price_eur"].agg(["count", "mean", "median", "min", "max"]).sort_index()

    min_year = int(stats["mean"].idxmin())
    max_year = int(stats["mean"].idxmax())
    min_mean = int(round(stats.loc[min_year, "mean"]))
    max_mean = int(round(stats.loc[max_year, "mean"]))

    # Grafici
    scatter_div = make_scatter(df)
    line_div = make_line(stats)

    # Tabelle HTML
    stats_tbody = render_table_rows_stats(stats)
    ads_tbody = render_table_rows_ads(df)

    html = (
        HTML_TEMPLATE
        .replace("{{SEARCH_LABEL}}", f"{cfg.brand} {cfg.model}".strip())
        .replace("{{SEARCH_URL}}", cfg.search_url)
        .replace("{{N_ROWS}}", str(len(df)))
        .replace("{{SCATTER_DIV}}", scatter_div)
        .replace("{{LINE_DIV}}", line_div)
        .replace("{{MIN_YEAR}}", str(min_year))
        .replace("{{MAX_YEAR}}", str(max_year))
        .replace("{{MIN_MEAN}}", f"{min_mean}")
        .replace("{{MAX_MEAN}}", f"{max_mean}")
        .replace("{{STATS_TBODY}}", stats_tbody)
        .replace("{{ADS_TBODY}}", ads_tbody)
    )

    out = Path("report_motoit.html")
    out.write_text(html, encoding="utf-8")
    print(f"Report pronto: {out.resolve()}")

if __name__ == "__main__":
    main()
