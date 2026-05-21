#!/usr/bin/env python3
"""
build_publications.py
---------------------
Parses ``norets_publications.bib`` and rewrites the three publication
sections of ``index.html`` in place, between paired ``BEGIN`` / ``END``
HTML comments.

Run locally (``python3 build_publications.py``) or by the GitHub Actions
workflow on every push.  No external dependencies -- only the Python
standard library.

Custom BibTeX fields consumed:
    pdf              relative URL to the paper PDF
    code             relative URL to replication code archive
    codelabel        label text for the code link (default: "zip")
    replication      external URL to a replication package
    appendix         relative URL to a web/online appendix
    appendixlabel    label text for the appendix link
    extension        relative URL to an extension or companion paper
    extlabel         label text for the extension link
    note             extra free-form HTML appended after the citation
    status           one of: published, forthcoming, working, old_working

The script preserves the order entries appear in the .bib file (which
mirrors the desired order on the website).
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------- config

HERE = Path(__file__).resolve().parent
BIB_FILE  = HERE / "norets_publications.bib"
HTML_FILE = HERE / "index.html"

# Coauthor webpages (extend as needed).  Keys are matched against the
# normalised "First Last" form of each author name.
COAUTHOR_URLS: dict[str, str] = {
    "Ulrich Mueller":   "http://www.princeton.edu/~umueller",
    "Ulrich Müller":    "http://www.princeton.edu/~umueller",
    "Xun Tang":         "https://www.tang-xun.com/",
    "Kenichi Shimizu":  "https://www.kenichi-shimizu.com/",
}

MONTH_NAMES = {
    "jan": "January",  "feb": "February", "mar": "March",
    "apr": "April",    "may": "May",      "jun": "June",
    "jul": "July",     "aug": "August",   "sep": "September",
    "oct": "October",  "nov": "November", "dec": "December",
    "1": "January",    "2": "February",   "3": "March",
    "4": "April",      "5": "May",        "6": "June",
    "7": "July",       "8": "August",     "9": "September",
    "10": "October",   "11": "November",  "12": "December",
}

# --------------------------------------------------------------------- parsing

def strip_braces(value: str) -> str:
    """Remove one or more layers of outer braces; collapse internal ones."""
    value = value.strip()
    # Repeatedly strip a matched pair of outer braces.
    while len(value) >= 2 and value[0] == "{" and value[-1] == "}":
        # Make sure those braces are actually paired (count depth).
        depth = 0
        for i, ch in enumerate(value):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and i != len(value) - 1:
                    return value  # outer braces not paired
        value = value[1:-1].strip()
    return value


# Minimal LaTeX -> Unicode for the characters that appear in this file.
LATEX_REPLACEMENTS = [
    (r'\\"\{u\}',  "ü"), (r'\\"u',  "ü"),
    (r'\\"\{o\}',  "ö"), (r'\\"o',  "ö"),
    (r'\\"\{a\}',  "ä"), (r'\\"a',  "ä"),
    (r"\\'\{e\}",  "é"), (r"\\'e",  "é"),
    (r"\\'\{a\}",  "á"), (r"\\'a",  "á"),
    (r"\\`\{e\}",  "è"), (r"\\`e",  "è"),
    (r"\\~\{n\}",  "ñ"), (r"\\~n",  "ñ"),
    (r"--",        "–"),
    (r"\\&",       "&"),
]

def latex_to_text(s: str) -> str:
    """Convert the LaTeX escapes used in our .bib to plain Unicode."""
    for pattern, repl in LATEX_REPLACEMENTS:
        s = re.sub(pattern, repl, s)
    # Strip any leftover braces inside the string.
    s = s.replace("{", "").replace("}", "")
    return s


def parse_bib(text: str) -> list[dict]:
    """Return a list of entries (dicts of {field: value, _type, _key})."""
    # Strip % comments to end-of-line, but leave the body untouched.
    text = re.sub(r"(?m)^%.*$", "", text)

    entries = []
    i = 0
    n = len(text)
    while i < n:
        # Skip whitespace.
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            break
        if text[i] != "@":
            i += 1
            continue

        # Read @type
        i += 1
        start = i
        while i < n and (text[i].isalpha() or text[i] == "_"):
            i += 1
        entry_type = text[start:i].lower()

        # Skip whitespace, expect '{'
        while i < n and text[i].isspace():
            i += 1
        if i >= n or text[i] != "{":
            continue
        i += 1

        # Read key up to first comma
        start = i
        while i < n and text[i] not in ",":
            i += 1
        key = text[start:i].strip()
        i += 1  # skip comma

        # Now read field = value pairs until matching '}' (depth 0).
        fields: dict[str, str] = {}
        while i < n:
            # Skip whitespace and stray commas
            while i < n and (text[i].isspace() or text[i] == ","):
                i += 1
            if i >= n:
                break
            if text[i] == "}":
                i += 1
                break
            # Field name
            start = i
            while i < n and text[i] not in "=":
                i += 1
            field_name = text[start:i].strip().lower()
            i += 1  # skip '='
            # Skip whitespace
            while i < n and text[i].isspace():
                i += 1
            if i >= n:
                break

            # Read value: braced, quoted, or bare token
            if text[i] == "{":
                depth = 1
                i += 1
                vstart = i
                while i < n and depth > 0:
                    if text[i] == "{":
                        depth += 1
                    elif text[i] == "}":
                        depth -= 1
                        if depth == 0:
                            break
                    i += 1
                value = text[vstart:i]
                i += 1  # skip closing '}'
            elif text[i] == '"':
                i += 1
                vstart = i
                while i < n and text[i] != '"':
                    i += 1
                value = text[vstart:i]
                i += 1  # skip closing quote
            else:
                vstart = i
                while i < n and text[i] not in ",}":
                    i += 1
                value = text[vstart:i].strip()

            fields[field_name] = strip_braces(value)

        entry = {"_type": entry_type, "_key": key, **fields}
        entries.append(entry)
    return entries


# --------------------------------------------------------------------- model

def split_authors(raw: str) -> list[str]:
    """Split a BibTeX 'author' field on ' and ' and normalise each name to
    Given-Family (e.g. 'Norets, Andriy' -> 'Andriy Norets')."""
    if not raw:
        return []
    parts = re.split(r"\s+and\s+", raw.strip())
    names = []
    for p in parts:
        p = latex_to_text(p)
        if "," in p:
            last, first = [s.strip() for s in p.split(",", 1)]
            names.append(f"{first} {last}".strip())
        else:
            names.append(p.strip())
    return names


def render_author_link(name: str) -> str:
    """Return an HTML fragment for the author, hyperlinked if we know them."""
    url = COAUTHOR_URLS.get(name)
    safe = html.escape(name)
    if url:
        return f'<a href="{html.escape(url)}">{safe}</a>'
    return safe


def join_with_oxford(items: list[str]) -> str:
    """'A', 'B', 'C' -> 'A, B, and C'  ;  'A', 'B' -> 'A and B'  ;  'A' -> 'A'."""
    if len(items) == 0:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def month_name(value: str) -> str:
    """Map a biblatex month value to a full English month name."""
    if not value:
        return ""
    key = value.strip().lower()
    return MONTH_NAMES.get(key, value.strip())


def link_text_from_url(url: str) -> str:
    """Pick the link text from a URL's file extension (e.g. .pdf -> 'pdf')."""
    m = re.search(r"\.([A-Za-z0-9]+)(?:$|[?#])", url)
    if not m:
        return "link"
    ext = m.group(1).lower()
    if ext in ("pdf", "zip", "tar", "gz", "tgz", "html", "txt", "bst", "csv"):
        return ext
    return "link"


def capitalize_first(s: str) -> str:
    if not s:
        return s
    return s[0].upper() + s[1:]


def render_resource_links(entry: dict) -> str:
    """Render the inline 'pdf, replication package' links right after title."""
    parts = []
    if entry.get("pdf"):
        parts.append(f'<a href="{html.escape(entry["pdf"])}">pdf</a>')
    if entry.get("replication"):
        parts.append(
            f'<a href="{html.escape(entry["replication"])}">Replication package</a>'
        )
    return ", ".join(parts)


def render_extras(entry: dict) -> str:
    """Render trailing sentences for code, appendix, extension and note."""
    bits = []

    # Primary code archive.
    if entry.get("code"):
        url   = entry["code"]
        label = entry.get("codelabel") or "Replication code"
        bits.append(
            f' {capitalize_first(label)}: '
            f'<a href="{html.escape(url)}">{link_text_from_url(url)}</a>.'
        )
    # Secondary code archive (some papers have two).
    if entry.get("code2"):
        url   = entry["code2"]
        label = entry.get("code2label") or "Replication code"
        bits.append(
            f' {capitalize_first(label)}: '
            f'<a href="{html.escape(url)}">{link_text_from_url(url)}</a>.'
        )
    # Web / online appendix.
    if entry.get("appendix"):
        url   = entry["appendix"]
        label = entry.get("appendixlabel") or "Web appendix"
        bits.append(
            f' {capitalize_first(label)}: '
            f'<a href="{html.escape(url)}">{link_text_from_url(url)}</a>.'
        )
    # Extension paper.
    if entry.get("extension"):
        url   = entry["extension"]
        label = entry.get("extlabel") or "Extension"
        bits.append(
            f' {capitalize_first(label)}: '
            f'<a href="{html.escape(url)}">{link_text_from_url(url)}</a>.'
        )
    # Free-form note (allowed to contain HTML).  Skip the placeholder
    # "forthcoming" since render_published already says "forthcoming in X".
    if entry.get("note"):
        note = entry["note"].strip()
        if note.lower() != "forthcoming":
            bits.append(f' {note}')
    return "".join(bits)


def render_published(entry: dict) -> str:
    title = latex_to_text(entry.get("title", ""))
    authors = split_authors(entry.get("author", ""))
    coauthors = authors[1:]  # Norets is always the first author here.

    journal = latex_to_text(entry.get("journaltitle") or entry.get("journal", ""))
    volume  = entry.get("volume", "")
    number  = entry.get("number", "")
    pages   = latex_to_text(entry.get("pages", ""))
    year    = entry.get("year", "")
    month   = month_name(entry.get("month", ""))
    status  = entry.get("status", "")

    pieces = [f'"{html.escape(title)}"']

    res = render_resource_links(entry)
    if res:
        pieces.append(res)

    if coauthors:
        with_str = "with " + join_with_oxford([render_author_link(a) for a in coauthors])
        pieces.append(with_str)

    # Journal portion
    if status == "forthcoming":
        journal_str = f"forthcoming in <cite>{html.escape(journal)}</cite>"
    else:
        journal_str = f"<cite>{html.escape(journal)}</cite>"
    pieces.append(journal_str)

    # Volume / Issue / Date / Pages -- only meaningful once an issue exists,
    # so we suppress all of them for forthcoming papers.
    if status != "forthcoming":
        vol_issue = []
        if volume:
            vol_issue.append(f"Volume {html.escape(volume)}")
        if number:
            vol_issue.append(f"Issue {html.escape(number)}")
        if vol_issue:
            pieces.append(", ".join(vol_issue))

        if month and year:
            pieces.append(f"{month} {html.escape(year)}")
        elif year:
            pieces.append(html.escape(year))

        if pages:
            pieces.append(f"pp. {pages}")

    citation = ", ".join(p for p in pieces if p) + "."
    citation += render_extras(entry)
    return citation


def render_working(entry: dict) -> str:
    title = latex_to_text(entry.get("title", ""))
    authors = split_authors(entry.get("author", ""))
    coauthors = authors[1:]
    note = entry.get("note", "")

    pieces = [f'"{html.escape(title)}"']
    res = render_resource_links(entry)
    if res:
        pieces.append(res)
    if coauthors:
        pieces.append("with " + join_with_oxford([render_author_link(a) for a in coauthors]))
    if note:
        pieces.append(html.escape(note))
    citation = ", ".join(p for p in pieces if p) + "."
    citation += render_extras({k: v for k, v in entry.items() if k != "note"})
    return citation


def render_old_working(entry: dict) -> str:
    title = latex_to_text(entry.get("title", ""))
    authors = split_authors(entry.get("author", ""))
    coauthors = authors[1:]

    pieces = [f'"{html.escape(title)}"']
    res = render_resource_links(entry)
    if res:
        pieces.append(res)
    if coauthors:
        pieces.append("with " + join_with_oxford([render_author_link(a) for a in coauthors]))
    citation = ", ".join(p for p in pieces if p) + "."
    citation += render_extras(entry)
    return citation


# --------------------------------------------------------------------- output

def render_section(entries: list[dict], renderer) -> str:
    items = [f"      <li>{renderer(e)}</li>" for e in entries]
    if not items:
        items = ["      <li><em>(none)</em></li>"]
    return "\n".join(items)


SECTION_RE = re.compile(
    r"(<!--\s*BEGIN:\s*{name}[^>]*-->)(.*?)(<!--\s*END:\s*{name}\s*-->)",
    re.DOTALL,
)

def replace_section(html_text: str, name: str, body: str) -> str:
    pattern = re.compile(
        rf"(<!--\s*BEGIN:\s*{re.escape(name)}[^>]*-->)(.*?)(<!--\s*END:\s*{re.escape(name)}\s*-->)",
        re.DOTALL,
    )
    repl = rf"\1\n{body}\n    \3"
    new_html, count = pattern.subn(repl, html_text)
    if count == 0:
        raise SystemExit(f"ERROR: marker pair for section '{name}' not found in {HTML_FILE}.")
    if count > 1:
        raise SystemExit(f"ERROR: multiple marker pairs for section '{name}' in {HTML_FILE}.")
    return new_html


def main() -> int:
    if not BIB_FILE.exists():
        print(f"ERROR: cannot find {BIB_FILE}", file=sys.stderr)
        return 2
    if not HTML_FILE.exists():
        print(f"ERROR: cannot find {HTML_FILE}", file=sys.stderr)
        return 2

    bib_text  = BIB_FILE.read_text(encoding="utf-8")
    html_text = HTML_FILE.read_text(encoding="utf-8")

    entries = parse_bib(bib_text)

    by_status: dict[str, list[dict]] = {
        "working": [],
        "published_or_forthcoming": [],
        "old_working": [],
    }
    for e in entries:
        s = e.get("status", "").lower()
        if s in ("published", "forthcoming"):
            by_status["published_or_forthcoming"].append(e)
        elif s == "working":
            by_status["working"].append(e)
        elif s == "old_working":
            by_status["old_working"].append(e)
        else:
            print(f"WARNING: entry '{e.get('_key')}' has no recognised status; skipping.",
                  file=sys.stderr)

    sections = {
        "working-papers":      render_section(by_status["working"],                 render_working),
        "published-papers":    render_section(by_status["published_or_forthcoming"], render_published),
        "old-working-papers":  render_section(by_status["old_working"],             render_old_working),
    }

    new_html = html_text
    for name, body in sections.items():
        new_html = replace_section(new_html, name, body)

    if new_html == html_text:
        print("index.html is already up to date.")
    else:
        HTML_FILE.write_text(new_html, encoding="utf-8")
        print(f"Updated {HTML_FILE} with "
              f"{len(by_status['working'])} working, "
              f"{len(by_status['published_or_forthcoming'])} published/forthcoming, "
              f"{len(by_status['old_working'])} old-working entries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
        "old_working": [],
    }
    for e in entries:
        s = e.get("status", "").lower()
        if s in ("published", "forthcoming"):
            by_status["published_or_forthcoming"].append(e)
        elif s == "working":
            by_status["working"].append(e)
        elif s == "old_working":
            by_status["old_working"].append(e)
        else:
            print(f"WARNING: entry '{e.get('_key')}' has no recognised status; skipping.",
                  file=sys.stderr)

    sections = {
        "working-papers":      render_section(by_status["working"],                  render_working),
        "published-papers":    render_section(by_status["published_or_forthcoming"], render_published),
        "old-working-papers":  render_section(by_status["old_working"],              render_old_working),
    }

    new_html = html_text
    for name, body in sections.items():
        new_html = replace_section(new_html, name, body)

    if new_html == html_text:
        print("index.html is already up to date.")
    else:
        HTML_FILE.write_text(new_html, encoding="utf-8")
        print(f"Updated {HTML_FILE} with "
              f"{len(by_status['working'])} working, "
              f"{len(by_status['published_or_forthcoming'])} published/forthcoming, "
              f"{len(by_status['old_working'])} old-working entries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
