# Cardux's Motorbike Report — GUI + scraping Moto.it
# Anno robusto senza range predefiniti, report HTML Plotly, Guida integrata,
# cartella di default: Desktop/<modello>, credito Instagram cliccabile.

import re
import time
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import urljoin
import webbrowser
import sys
import os

# scraping deps
import requests
from bs4 import BeautifulSoup
import pandas as pd
import plotly.graph_objs as go
from plotly.offline import plot

# GUI
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

APP_TITLE = "Cardux's Motorbike Report"
APP_CREDIT_TEXT = "@fuori.tempo.massimo"
APP_CREDIT_URL = "https://www.instagram.com/fuori.tempo.massimo"

# ==============================
# Config e regex
# ==============================
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Anni plausibili in assoluto, non legati al modello
YEAR_MIN, YEAR_MAX = 1990, 2035

YEAR_PAT = re.compile(r"\b(19\d{2}|20\d{2})\b")
DATE_PAT = re.compile(r"\b(0?[1-9]|1[0-2])\s*[/\-]\s*(20\d{2}|19\d{2})\b")

LABEL_NEAR_PAT = re.compile(
    r"(?:^|[\s:;,.|])(?:anno|immatricolazione|immatricolata|prima immatricolazione|mese\s*/\s*anno)(?:[\s:;,.|]|$)",
    re.IGNORECASE,
)

NEG_CONTEXT_PAT = re.compile(
    r"(?:aggiornato|pubblicato|garanzia|fino al|tagliando|revisione|bollo|promo|copyright|©)",
    re.IGNORECASE,
)

# ==============================
# Helpers parsing
# ==============================
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
    return any(k in txt for k in ["annunci", "Prezzo", "km", "usate"])

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

# ==============================
# Estrazione anno robusta
# ==============================
def extract_year_from_text(txt: str) -> Optional[int]:
    """
    Cerca l'anno dando priorità a label chiare. Anni isolati sono deboli.
    """
    if not txt:
        return None
    txt_norm = " " + re.sub(r"\s+", " ", txt) + " "

    # 1) Mese/Anno affidabile
    m = DATE_PAT.search(txt_norm)
    if m:
        y = int(m.group(2))
        if YEAR_MIN <= y <= YEAR_MAX:
            return y

    # 2) Anno vicino a label entro 16 char
    cands = []
    for m in YEAR_PAT.finditer(txt_norm):
        y = int(m.group(1))
        if not (YEAR_MIN <= y <= YEAR_MAX):
            continue
        i, j = m.span()
        window = txt_norm[max(0, i - 16): min(len(txt_norm), j + 16)]
        label = bool(LABEL_NEAR_PAT.search(window))
        neg = bool(NEG_CONTEXT_PAT.search(window))

        if label and not neg:
            extra = 1 if DATE_PAT.search(window) else 0
            cands.append((y, 10 + extra))    # alto punteggio se label presente
        elif not label:
            cands.append((y, 1 if not neg else -5))  # anni isolati, punteggio basso

    if not cands:
        return None

    # Ordina per punteggio, a parità prendi l'anno più piccolo
    cands.sort(key=lambda t: (t[1], -t[0]))
    best_y, best_score = cands[-1]
    if best_score <= 1:
        return None
    return best_y

def parse_year_from_detail(url: str, headers: Dict[str, str]) -> Optional[int]:
    """
    Legge l'anno dal blocco specifiche dell'annuncio, non dall'intera pagina.
    """
    try:
        s = fetch(url, headers)
    except Exception:
        return None

    containers = []
    containers += s.select("dl, .scheda, .specifiche, .dati-tecnici, .vehicle-specs, table, ul")
    containers = containers or [s]

    for box in containers:
        text = " " + re.sub(r"\s+", " ", box.get_text(" ", strip=True)) + " "

        m = re.search(
            r"(?:Anno|Immatricolazione|Immatricolata|Prima immatricolazione)[^\d]{0,12}(19\d{2}|20\d{2})",
            text, flags=re.IGNORECASE,
        )
        if m:
            y = int(m.group(1))
            if YEAR_MIN <= y <= YEAR_MAX:
                return y

        m2 = DATE_PAT.search(text)
        if m2:
            y = int(m2.group(2))
            if YEAR_MIN <= y <= YEAR_MAX:
                return y

        y3 = extract_year_from_text(text)
        if y3:
            return y3

    return None

# ==============================
# Scraper
# ==============================
@dataclass
class ScrapeConfig:
    search_url: str
    delay_sec: float
    max_pages: int
    headers: Dict[str, str]
    brand: str
    model: str
    verify_detail_year: bool = True  # opzione per precisione

def fetch(url: str, headers: Dict[str, str]) -> BeautifulSoup:
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")

def discover_pages(base_url: str, headers: Dict[str, str], max_pages: int, delay: float, log=None) -> List[str]:
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
    except Exception as e:
        if log:
            log(f"Impossibile stimare la paginazione: {e}. Procedo incrementale.")

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

def parse_page(url: str, headers: Dict[str, str], brand: str, model: str, verify_detail_year: bool, log=None) -> List[Dict]:
    soup = fetch(url, headers)
    items = []
    for node in listing_blocks(soup):
        txt = text_clean(node.get_text(" ", strip=True))

        # filtro blando per marca/modello, niente range anni
        if brand and brand.lower() not in txt.lower():
            continue
        if model and model.lower().replace(" ", "") not in txt.lower().replace(" ", ""):
            continue

        price = parse_price(txt)
        if price is None:
            continue

        year_source = None
        year = extract_year_from_text(txt)
        if year is not None:
            year_source = "card"

        href = extract_primary_link(node) or url

        # Fallback: pagina dettaglio se manca l'anno
        if verify_detail_year and href and year is None:
            y2 = parse_year_from_detail(href, headers)
            if y2 is not None:
                year = y2
                year_source = "detail"

        # Accettiamo solo se un anno è stato determinato
        if year is None:
            if log:
                log("Saltato annuncio: anno non trovato su card e dettaglio")
            continue

        km = parse_km(txt)
        loc = parse_location(txt)

        if log:
            log(f"OK anno={year} [{year_source}]  prezzo={price}  url={href}")

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

def run_scrape(cfg: ScrapeConfig, progress_cb=None, log=None) -> pd.DataFrame:
    pages = discover_pages(cfg.search_url, cfg.headers, cfg.max_pages, cfg.delay_sec, log=log)
    total = len(pages)
    rows = []
    for idx, p in enumerate(pages, start=1):
        if log:
            log(f"Pagina {idx}/{total}: {p}")
        rows.extend(parse_page(p, cfg.headers, cfg.brand, cfg.model, cfg.verify_detail_year, log=log))
        if progress_cb:
            progress_cb(idx, total)
        time.sleep(cfg.delay_sec)

    df = pd.DataFrame(rows).drop_duplicates()
    if not df.empty:
        df = df.sort_values(["year", "price_eur"], ascending=[True, True])
    return df

# ==============================
# Report HTML
# ==============================
HTML_TEMPLATE = """<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <title>Report Moto.it — Prezzo vs Anno</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link rel="stylesheet" href="https://cdn.datatables.net/1.13.8/css/dataTables.bootstrap5.min.css">
  <style>
    body { padding: 20px; background: #0f1115; color: #e6e6e6; }
    a { color: #61dafb; }
    .card { border-radius: 12px; background:#131722; border:1px solid #1e2330; }
    .chart-card { padding: 16px; background: #131722; border-radius: 12px; border: 1px solid #1e2330; box-shadow: 0 2px 10px rgba(0,0,0,0.25); }
    .muted { color: #9aa0a6; }
    .smallcaps { font-variant: all-small-caps; letter-spacing: .5px; }
    .table { color: #e6e6e6; }
    .table thead th { color:#c9d1d9; }
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

    <footer class="mt-4 muted small">
      Report generato offline, nessun server richiesto.
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
    out = []
    for y, row in stats_df.iterrows():
        out.append(
            f"<tr><td>{int(y)}</td><td>{int(row['count'])}</td>"
            f"<td>{int(round(row['mean']))}</td><td>{int(round(row['median']))}</td>"
            f"<td>{int(row['min'])}</td><td>{int(row['max'])}</td></tr>"
        )
    return "\n".join(out)

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
        xaxis_title="Anno", yaxis_title="Prezzo (€)", template="plotly_dark"
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
        xaxis_title="Anno", yaxis_title="Prezzo medio (€)", template="plotly_dark"
    )
    return plot(fig, include_plotlyjs=False, output_type="div")

def generate_report(df: pd.DataFrame, brand: str, model: str, search_url: str, out_path: Path) -> None:
    stats = df.groupby("year")["price_eur"].agg(["count", "mean", "median", "min", "max"]).sort_index()
    min_year = int(stats["mean"].idxmin())
    max_year = int(stats["mean"].idxmax())
    min_mean = int(round(stats.loc[min_year, "mean"]))
    max_mean = int(round(stats.loc[max_year, "mean"]))

    scatter_div = make_scatter(df)
    line_div = make_line(stats)
    stats_tbody = render_table_rows_stats(stats)
    ads_tbody = render_table_rows_ads(df)

    html = (
        HTML_TEMPLATE
        .replace("{{SEARCH_LABEL}}", f"{brand} {model}".strip())
        .replace("{{SEARCH_URL}}", search_url)
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
    out_path.write_text(html, encoding="utf-8")

# ==============================
# Utility path Desktop
# ==============================
def default_desktop_dir() -> Path:
    home = Path.home()
    for candidate in ["Desktop", "Scrivania"]:
        p = home / candidate
        if p.exists():
            return p
    return home

def desktop_model_dir(model: str) -> Path:
    safe = re.sub(r"[^\w\-\s\.]", "_", model.strip()) or "Report"
    return default_desktop_dir() / safe

# ==============================
# GUI
# ==============================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("900x700")
        self.minsize(860, 640)
        self.report_path: Optional[Path] = None
        self.csv_path: Optional[Path] = None

        self._user_outdir_modified = False  # se l’utente tocca la cartella, non auto-aggiorno più

        s = ttk.Style()
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        s.configure("Sub.TLabel", font=("Segoe UI", 10))
        s.configure("TButton", padding=8)
        s.configure("Accent.TButton", padding=8)
        s.configure("Footer.TLabel", font=("Segoe UI", 9, "italic"))

        self._build_header()
        self._build_form()
        self._build_progress()
        self._build_log()
        self._build_footer()

    def _build_header(self):
        header = ttk.Frame(self, padding=(16, 16, 16, 8))
        header.pack(fill="x")
        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").pack(side="left")
        right = ttk.Frame(header)
        right.pack(side="right")
        ttk.Button(right, text="Guida", command=self.open_help).pack(side="right")
        ttk.Label(right, text="Comparativa usato Moto.it con report interattivo", style="Sub.TLabel", foreground="#666").pack(side="right", padx=(0,10))

    def _build_form(self):
        frm = ttk.Frame(self, padding=(16, 8, 16, 8))
        frm.pack(fill="x")

        self.brand_var = tk.StringVar(value="Honda")
        self.model_var = tk.StringVar(value="CBR 650 R")
        self.url_var = tk.StringVar(value="")
        self.pages_var = tk.IntVar(value=12)
        self.delay_var = tk.DoubleVar(value=1.0)
        # cartella default: Desktop/<modello>
        self.outdir_var = tk.StringVar(value=str(desktop_model_dir(self.model_var.get())))
        self.verify_detail_var = tk.BooleanVar(value=True)

        # aggiorna cartella quando cambia modello, finché l'utente non la modifica manualmente
        def on_model_change(*_):
            if not self._user_outdir_modified:
                self.outdir_var.set(str(desktop_model_dir(self.model_var.get())))
        self.model_var.trace_add("write", on_model_change)

        grid = ttk.Frame(frm)
        grid.pack(fill="x")

        ttk.Label(grid, text="Marca").grid(row=0, column=0, sticky="w", padx=(0,8), pady=4)
        ttk.Entry(grid, textvariable=self.brand_var, width=24).grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(grid, text="Modello").grid(row=0, column=2, sticky="w", padx=(16,8), pady=4)
        ttk.Entry(grid, textvariable=self.model_var, width=24).grid(row=0, column=3, sticky="w", pady=4)

        ttk.Label(grid, text="URL ricerca Moto.it (opzionale)").grid(row=1, column=0, sticky="w", padx=(0,8), pady=4)
        ttk.Entry(grid, textvariable=self.url_var, width=60).grid(row=1, column=1, columnspan=3, sticky="we", pady=4)

        ttk.Label(grid, text="Pagine max").grid(row=2, column=0, sticky="w", padx=(0,8), pady=4)
        ttk.Spinbox(grid, from_=1, to=30, textvariable=self.pages_var, width=6).grid(row=2, column=1, sticky="w", pady=4)
        ttk.Label(grid, text="Ritardo richieste (s)").grid(row=2, column=2, sticky="w", padx=(16,8), pady=4)
        ttk.Spinbox(grid, from_=0.0, to=5.0, increment=0.1, textvariable=self.delay_var, width=6).grid(row=2, column=3, sticky="w", pady=4)

        ttk.Checkbutton(grid, text="Verifica anno su pagina dettaglio", variable=self.verify_detail_var).grid(row=3, column=0, columnspan=2, sticky="w", pady=4)

        ttk.Label(grid, text="Cartella output").grid(row=4, column=0, sticky="w", padx=(0,8), pady=4)
        row4 = ttk.Frame(grid)
        row4.grid(row=4, column=1, columnspan=3, sticky="we", pady=4)
        self.out_entry = ttk.Entry(row4, textvariable=self.outdir_var)
        self.out_entry.pack(side="left", fill="x", expand=True)
        def on_outdir_edit(_):
            self._user_outdir_modified = True
        self.out_entry.bind("<Key>", on_outdir_edit)
        ttk.Button(row4, text="Sfoglia", command=self.choose_outdir).pack(side="left", padx=(8,0))

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(6, 0))
        self.run_btn = ttk.Button(btns, text="Genera report", command=self.on_run, style="Accent.TButton")
        self.run_btn.pack(side="left")
        self.open_btn = ttk.Button(btns, text="Apri report", command=self.open_report, state="disabled")
        self.open_btn.pack(side="left", padx=8)
        self.open_folder_btn = ttk.Button(btns, text="Apri cartella", command=self.open_folder)
        self.open_folder_btn.pack(side="left")

    def _build_progress(self):
        box = ttk.Frame(self, padding=(16, 8, 16, 8))
        box.pack(fill="x")
        self.status_var = tk.StringVar(value="Pronto")
        ttk.Label(box, textvariable=self.status_var).pack(anchor="w")
        self.pbar = ttk.Progressbar(box, mode="determinate", maximum=100)
        self.pbar.pack(fill="x", pady=(6,0))

    def _build_log(self):
        frm = ttk.Frame(self, padding=(16, 8, 16, 8))
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Log").pack(anchor="w")
        self.txt = tk.Text(frm, height=12, wrap="word", font=("Consolas", 10))
        self.txt.pack(fill="both", expand=True)
        self.txt.configure(state="disabled")

    def _build_footer(self):
        footer = ttk.Frame(self, padding=(16, 4, 16, 12))
        footer.pack(fill="x")
        sep = ttk.Separator(footer)
        sep.pack(fill="x", pady=(0,6))
        link = ttk.Label(footer, text=APP_CREDIT_TEXT, style="Footer.TLabel", anchor="center", foreground="#4ea9ff", cursor="hand2")
        link.pack(fill="x")
        def open_ig(_):
            webbrowser.open_new_tab(APP_CREDIT_URL)
        link.bind("<Button-1>", open_ig)

    # ---------- Guida ----------
    def open_help(self):
        win = tk.Toplevel(self)
        win.title("Guida rapida")
        win.geometry("700x520")
        txt = tk.Text(win, wrap="word", font=("Segoe UI", 10))
        txt.pack(fill="both", expand=True)
        guide = """
COME SI USA

1) Inserisci Marca e Modello. In alternativa incolla l'URL di ricerca di Moto.it.
2) Pagine max controlla quante pagine di annunci vengono lette.
3) Ritardo richieste è la pausa tra le pagine. Se vedi blocchi, alza a 1.0–1.2 s.
4) Lascia attivo "Verifica anno su pagina dettaglio" per migliore precisione sull'anno.
5) La cartella di output di default è Desktop/<modello>. Puoi cambiarla con "Sfoglia".
6) Premi "Genera report". A fine corsa apri il report HTML o la cartella.

COSA PRODUCE

- report_motoit.html: pagina interattiva con scatter Prezzo vs Anno, media per anno,
  tabella annunci e statistiche.
- annunci_motoit.csv: elenco completo degli annunci raccolti.

ERRORI TIPICI E SOLUZIONI

- "Nessun annuncio trovato":
  • URL o filtro non restituisce risultati, oppure markup cambiato.
  • Prova a incollare direttamente l'URL di Moto.it della ricerca.
  • Riduci pagine max a 5 e riprova.

- "Scraping fallito" o tempo scaduto:
  • Rete lenta o blocco temporaneo del sito. Aumenta il ritardo nelle richieste.
  • Verifica di avere installato lxml:  pip install lxml

- Anno errato in qualche annuncio:
  • Tieni abilitato "Verifica anno su pagina dettaglio" per leggere le specifiche interne.
  • Se l'annuncio ha più anni (garanzia, tagliando), il programma privilegia "Anno" o "Immatricolazione".
  • Alza il ritardo a 1.0–1.2 s per evitare blocchi mentre apre il dettaglio.

- Report si apre ma grafici vuoti:
  • Apri l'HTML con un browser moderno (Chrome, Edge, Firefox).
  • Se usi estensioni restrittive, prova in incognito.

NOTE

- Non esagerare con il numero di pagine. Mantieni un comportamento rispettoso verso il sito.
- Gli anni non hanno range predefiniti: il report usa esattamente quelli trovati negli annunci.
        """.strip()
        txt.insert("1.0", guide)
        txt.configure(state="disabled")
        ttk.Button(win, text="Chiudi", command=win.destroy).pack(pady=8)

    # ---------- utils GUI ----------
    def choose_outdir(self):
        d = filedialog.askdirectory(initialdir=self.outdir_var.get() or str(Path.cwd()))
        if d:
            self.outdir_var.set(d)
            self._user_outdir_modified = True

    def log(self, msg: str):
        self.txt.configure(state="normal")
        self.txt.insert("end", msg + "\n")
        self.txt.see("end")
        self.txt.configure(state="disabled")

    def set_status(self, msg: str):
        self.status_var.set(msg)
        self.update_idletasks()

    def set_progress(self, done: int, total: int):
        pct = int(round(100 * done / max(1, total)))
        self.pbar["value"] = pct
        self.set_status(f"Avanzamento: {done}/{total} pagine • {pct}%")

    # ---------- actions ----------
    def on_run(self):
        if self.run_btn["state"] == "disabled":
            return
        brand = self.brand_var.get().strip()
        model = self.model_var.get().strip()
        url = self.url_var.get().strip()
        pages = max(1, int(self.pages_var.get()))
        delay = max(0.0, float(self.delay_var.get()))
        outdir = Path(self.outdir_var.get().strip()) if self.outdir_var.get().strip() else desktop_model_dir(model)
        verify_detail = bool(self.verify_detail_var.get())
        outdir.mkdir(parents=True, exist_ok=True)

        if not url and (not brand or not model):
            messagebox.showerror("Errore", "Inserisci Marca e Modello oppure un URL di ricerca Moto.it.")
            return

        self.run_btn["state"] = "disabled"
        self.open_btn["state"] = "disabled"
        self.pbar["value"] = 0
        self.txt.configure(state="normal"); self.txt.delete("1.0", "end"); self.txt.configure(state="disabled")
        self.set_status("Preparazione...")

        t = threading.Thread(
            target=self._do_work,
            args=(brand, model, url, pages, delay, outdir, verify_detail),
            daemon=True
        )
        t.start()

    def _do_work(self, brand, model, url, pages, delay, outdir: Path, verify_detail: bool):
        try:
            search_url = url or self.build_url(brand, model)
            self.log(f"URL ricerca: {search_url}")
            cfg = ScrapeConfig(
                search_url=search_url,
                delay_sec=delay,
                max_pages=pages,
                headers=DEFAULT_HEADERS.copy(),
                brand=brand,
                model=model,
                verify_detail_year=verify_detail
            )

            def ui_log(m): self.after(0, self.log, m)
            def ui_prog(i, tot): self.after(0, self.set_progress, i, tot)

            self.after(0, self.set_status, "Scraping in corso...")
            df = run_scrape(cfg, progress_cb=ui_prog, log=ui_log)

            if df.empty:
                self.after(0, self.set_status, "Nessun annuncio trovato")
                self.after(0, self._finish_with_error, "Nessun annuncio trovato per i parametri indicati.")
                return

            csv_path = outdir / "annunci_motoit.csv"
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")

            report_path = outdir / "report_motoit.html"
            self.after(0, self.set_status, "Genero report...")
            generate_report(df, brand, model, search_url, report_path)

            self.report_path = report_path
            self.csv_path = csv_path
            self.after(0, self.log, f"Salvato CSV: {csv_path}")
            self.after(0, self.log, f"Report pronto: {report_path}")
            self.after(0, self.set_status, "Completato")
            self.after(0, self._enable_open)
        except Exception as e:
            self.after(0, self._finish_with_error, str(e))

    def _enable_open(self):
        self.run_btn["state"] = "normal"
        self.open_btn["state"] = "normal"

    def _finish_with_error(self, msg: str):
        self.run_btn["state"] = "normal"
        self.open_btn["state"] = "disabled"
        messagebox.showerror("Errore", msg)

    def open_report(self):
        if not self.report_path or not self.report_path.exists():
            messagebox.showwarning("Attenzione", "Nessun report da aprire.")
            return
        webbrowser.open_new_tab(self.report_path.as_uri())

    def open_folder(self):
        folder = Path(self.outdir_var.get() or ".")
        if not folder.exists():
            messagebox.showwarning("Attenzione", "Cartella non trovata.")
            return
        try:
            if os.name == "nt":
                os.startfile(str(folder))  # type: ignore
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", str(folder)])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception:
            webbrowser.open_new_tab(folder.as_uri())

    @staticmethod
    def build_url(brand: str, model: str) -> str:
        b = text_clean(brand).lower().replace(" ", "-")
        m = text_clean(model).lower().replace(" ", "-")
        return f"https://www.moto.it/moto-usate/{b}/{m}"

if __name__ == "__main__":
    app = App()
    app.mainloop()
