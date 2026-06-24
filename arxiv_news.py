#!/usr/bin/env python3
"""
Fetch recent arXiv papers in a category and lay them out as a printable,
single-column PDF. LaTeX math in titles and abstracts is properly
TYPESET (real subscripts, superscripts, fractions, Greek) by rendering each
$...$ fragment with matplotlib and embedding it inline at the correct baseline.

Setup (Python 3.8 friendly):
    pip install "arxiv==2.3.2" reportlab pylatexenc matplotlib

Tune the setup in the CONFIG block below.
"""

import os
import re
import shutil
import tempfile
import datetime
import webbrowser

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import arxiv
from pylatexenc.latex2text import LatexNodes2Text

from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame,
                                Paragraph, Spacer, KeepTogether, NextPageTemplate)
from reportlab.platypus.flowables import HRFlowable

# ------------------------------- CONFIG --------------------------------
CATEGORY       = "astro-ph.GA"   # arXiv category
MAX_RESULTS    = 50              # how many recent papers to fetch
MAX_AUTHORS    = 5               # show at most this many authors, then "et al."
DAYS_BACK      = None            # e.g. 2 -> only papers from last 2 days; None -> no filter
PAGE_SIZE      = A4              # A4 or letter
OUTPUT_DIR     = os.path.join(os.path.expanduser("~"), "Desktop", "arXiv_recent")
OPEN_WHEN_DONE = True            # auto-open the PDF when finished
ACCENT         = "#7a1f1f"       # masthead / link accent (deep oxblood)
MATH_DPI       = 300             # resolution of rendered math glyphs
# -----------------------------------------------------------------------


# ---- fonts: borrow DejaVu (broad Unicode coverage) from matplotlib -----
def _register_fonts():
    ttf = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
    faces = {
        "Serif":        "DejaVuSerif.ttf",
        "Serif-Bold":   "DejaVuSerif-Bold.ttf",
        "Serif-Italic": "DejaVuSerif-Italic.ttf",
        "Sans":         "DejaVuSans.ttf",
        "Sans-Bold":    "DejaVuSans-Bold.ttf",
        "Mono":         "DejaVuSansMono.ttf",
    }
    for name, fn in faces.items():
        pdfmetrics.registerFont(TTFont(name, os.path.join(ttf, fn)))


# ---------------------- LaTeX -> typeset / readable ---------------------
_MATH = re.compile(r"(\$\$.+?\$\$|\\\[.+?\\\]|\$.+?\$|\\\(.+?\\\))", re.DOTALL)
_l2t = LatexNodes2Text()

def _xml_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _text_segment(s):
    # Convert stray LaTeX (accents, \&, \textit{}) only if a backslash is present,
    # so ordinary prose is never mangled. Then escape for reportlab markup.
    if "\\" in s:
        try:
            s = _l2t.latex_to_text(s)
        except Exception:
            pass
    return _xml_escape(s)


def _strip_delims(token):
    if token.startswith("$$") and token.endswith("$$"):
        return token[2:-2]
    if token.startswith("$") and token.endswith("$"):
        return token[1:-1]
    if token.startswith(r"\(") and token.endswith(r"\)"):
        return token[2:-2]
    if token.startswith(r"\[") and token.endswith(r"\]"):
        return token[2:-2]
    return token


class MathRenderer:
    """Render $...$ fragments to baseline-anchored PNGs, embeddable in reportlab."""

    def __init__(self, workdir, dpi=300, max_w=240.0):
        self.dir = workdir
        self.dpi = dpi
        self.max_w = max_w          # clamp width (pt) so wide display math fits a column
        self.cache = {}
        self.n = 0

    def _png(self, tex, fontsize):
        # 1) measure baseline (stable across matplotlib versions)
        fig = plt.figure(figsize=(0.01, 0.01))
        t = fig.text(0, 0, f"${tex}$", fontsize=fontsize)
        fig.canvas.draw()
        bb = t.get_window_extent(fig.canvas.get_renderer())
        sdpi = fig.dpi
        w = (bb.x1 - bb.x0) / sdpi * 72.0
        asc = bb.y1 / sdpi * 72.0
        desc = -bb.y0 / sdpi * 72.0
        plt.close(fig)
        h = asc + desc
        if w <= 0 or h <= 0:
            raise ValueError("empty math box")
        # 2) render exact-size, baseline anchored
        path = os.path.join(self.dir, f"m{self.n}.png")
        self.n += 1
        fig = plt.figure(figsize=(w / 72.0, h / 72.0), dpi=self.dpi)
        fig.text(0, desc / h, f"${tex}$", fontsize=fontsize, va="baseline", ha="left")
        fig.savefig(path, dpi=self.dpi, transparent=True)
        plt.close(fig)
        return path, w, h, desc

    def tag(self, tex, fontsize):
        key = (tex, round(fontsize, 1))
        if key not in self.cache:
            self.cache[key] = self._png(tex, fontsize)
        path, w, h, desc = self.cache[key]
        if w > self.max_w:                      # scale down oversized equations
            s = self.max_w / w
            w, h, desc = w * s, h * s, desc * s
        return (f'<img src="{path}" width="{w:.2f}" height="{h:.2f}" '
                f'valign="{-desc:.2f}"/>')

    def inline(self, raw, fontsize):
        """Turn a string with $...$ math into reportlab paragraph markup."""
        out = []
        for seg in _MATH.split(raw):
            if not seg:
                continue
            if _MATH.fullmatch(seg):
                tex = _strip_delims(seg).strip()
                try:
                    out.append(self.tag(tex, fontsize))
                    continue
                except Exception:
                    # fall back to readable unicode text for this fragment
                    try:
                        out.append(_xml_escape(_l2t.latex_to_text("$" + tex + "$")))
                    except Exception:
                        out.append(_xml_escape(tex))
            else:
                out.append(_text_segment(seg))
        return "".join(out)


# ------------------------------ fetching --------------------------------
def fetch_papers(category, max_results, max_authors, days_back):
    search = arxiv.Search(
        query=f"cat:{category}",
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )
    client = arxiv.Client()
    cutoff = None
    if days_back is not None:
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_back)

    papers = []
    for r in client.results(search):
        if cutoff is not None and r.published < cutoff:
            continue
        names = [a.name for a in r.authors]
        authors = "; ".join(names[:max_authors]) + ("; et al." if len(names) > max_authors else "")
        papers.append({
            "url": r.entry_id,
            "title": " ".join(r.title.split()),
            "authors": authors,
            "abstract": " ".join(r.summary.split()),
            "published": r.published,
        })
    return papers


# --------------------------- PDF construction ---------------------------
def build_pdf(papers, outfile, category, pagesize, math, accent):
    PW, PH = pagesize
    M = 2.0 * cm                       # page margin
    colw = PW - 2 * M                  # single full-width column
    masthead_h = 2.7 * cm              # reserved on page 1
    footer_h = 0.7 * cm
    acc = HexColor(accent)

    st_id = ParagraphStyle("id", fontName="Mono", fontSize=8, leading=11,
                           textColor=HexColor("#666666"), spaceAfter=4)
    st_title = ParagraphStyle("title", fontName="Serif-Bold", fontSize=13.5,
                              leading=16, spaceAfter=4, textColor=HexColor("#111111"))
    st_auth = ParagraphStyle("auth", fontName="Serif-Italic", fontSize=9.3,
                             leading=12, textColor=HexColor("#333333"), spaceAfter=4)
    st_abs = ParagraphStyle("abs", fontName="Serif", fontSize=9.8, leading=13.6,
                            alignment=TA_JUSTIFY)
    BODY_FS, TITLE_FS = 9.8, 13.5

    def footer(canvas, doc):
        canvas.setFont("Sans", 7.5)
        canvas.setFillColor(HexColor("#888888"))
        canvas.drawCentredString(PW / 2.0, M - 0.5 * cm,
                                 f"arXiv {category}   \u00b7   page {doc.page}")

    def first_page(canvas, doc):
        canvas.saveState()
        top = PH - M
        canvas.setFillColor(acc)
        canvas.setFont("Sans-Bold", 9)
        canvas.drawString(M, top - 9, "ARXIV DAILY")
        canvas.setFillColor(HexColor("#111111"))
        canvas.setFont("Serif-Bold", 26)
        canvas.drawString(M, top - 38, category)
        canvas.setFont("Sans", 9.5)
        canvas.setFillColor(HexColor("#555555"))
        stamp = datetime.datetime.now().strftime("%A, %d %B %Y")
        canvas.drawString(M, top - 54, f"{stamp}    \u00b7    {len(papers)} recent submissions")
        rule_y = top - 64
        canvas.setStrokeColor(HexColor("#111111"))
        canvas.setLineWidth(2)
        canvas.line(M, rule_y, PW - M, rule_y)
        canvas.setLineWidth(0.5)
        canvas.line(M, rule_y - 3, PW - M, rule_y - 3)
        footer(canvas, doc)
        canvas.restoreState()

    def later_page(canvas, doc):
        canvas.saveState()
        footer(canvas, doc)
        canvas.restoreState()

    first_h = (PH - M - masthead_h) - M
    f_first = Frame(M, M, colw, first_h, id="f1", leftPadding=0, rightPadding=0,
                    topPadding=0, bottomPadding=0)
    full_h = PH - 2 * M - footer_h
    f_full = Frame(M, M, colw, full_h, id="f2", leftPadding=0, rightPadding=0,
                   topPadding=0, bottomPadding=0)

    doc = BaseDocTemplate(outfile, pagesize=pagesize,
                          leftMargin=M, rightMargin=M, topMargin=M, bottomMargin=M)
    doc.addPageTemplates([
        PageTemplate(id="first", frames=[f_first], onPage=first_page),
        PageTemplate(id="later", frames=[f_full], onPage=later_page),
    ])

    # page 1 uses 'first' (with masthead); switch to 'later' from page 2 on
    story = [NextPageTemplate("later")]
    for i, p in enumerate(papers, start=1):
        idline = (f'[{i}] <a href="{p["url"]}"><font color="{accent}">'
                  f'{_xml_escape(p["url"])}</font></a> \u00b7 '
                  f'{p["published"].strftime("%d %b %Y")}')
        head = [
            Paragraph(idline, st_id),
            Paragraph(math.inline(p["title"], TITLE_FS), st_title),
            Paragraph(_text_segment(p["authors"]), st_auth),
        ]
        story.append(KeepTogether(head))
        story.append(Paragraph(math.inline(p["abstract"], BODY_FS), st_abs))
        story.append(Spacer(1, 6))
        story.append(HRFlowable(width="100%", thickness=0.5,
                                color=HexColor("#cccccc"), spaceAfter=10))

    doc.build(story)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    _register_fonts()

    papers = fetch_papers(CATEGORY, MAX_RESULTS, MAX_AUTHORS, DAYS_BACK)
    print(f"Fetched {len(papers)} papers from {CATEGORY}.")
    if not papers:
        print("Nothing to write (raise MAX_RESULTS or clear DAYS_BACK).")
        return

    date = datetime.datetime.now().strftime("%d%b%y")
    outfile = os.path.join(OUTPUT_DIR, f"arXiv_{CATEGORY}_{date}.pdf")

    workdir = tempfile.mkdtemp(prefix="arxiv_math_")
    try:
        math = MathRenderer(workdir, dpi=MATH_DPI)
        PW, _ = PAGE_SIZE
        math.max_w = (PW - 2 * (2.0 * cm)) * 0.95
        build_pdf(papers, outfile, CATEGORY, PAGE_SIZE, math, ACCENT)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    print(f"Wrote {outfile}")
    if OPEN_WHEN_DONE:
        webbrowser.open("file://" + os.path.abspath(outfile))


if __name__ == "__main__":
    main()
