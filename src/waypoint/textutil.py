"""Text helpers: HTML to text, language guess, boilerplate trimming."""
from __future__ import annotations

import html
import re
import unicodedata

from bs4 import BeautifulSoup

_PT_WORDS = {
    "de", "para", "com", "você", "voce", "não", "nao", "uma", "dos", "das", "experiência",
    "experiencia", "conhecimento", "vaga", "requisitos", "atividades", "será", "sera", "nosso",
    "nossa", "em", "e", "que", "os", "as", "trabalho", "desejável", "diferenciais",
}
_EN_WORDS = {
    "the", "and", "you", "with", "for", "our", "experience", "will", "are", "your", "we",
    "requirements", "of", "to", "in", "is", "work", "team", "skills", "preferred",
}

_BLOCK_TAGS = ["p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "br", "tr", "section"]


def html_to_text(raw: str) -> str:
    """Convert (possibly HTML-escaped) HTML into readable plain text, keeping line breaks."""
    if not raw:
        return ""
    s = html.unescape(raw)
    if "<" not in s:
        return normalize_ws(s)
    soup = BeautifulSoup(s, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    for li in soup.find_all("li"):
        li.insert_before("\n- ")
    for tag in soup.find_all(_BLOCK_TAGS):
        tag.insert_after("\n")
    return normalize_ws(soup.get_text())


def normalize_ws(s: str) -> str:
    s = s.replace("\r", "\n").replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in s.split("\n")]
    out: list[str] = []
    for ln in lines:
        if ln or (out and out[-1]):
            out.append(ln)
    return "\n".join(out).strip()


def guess_lang(text: str) -> str:
    words = re.findall(r"[a-zA-ZÀ-ÿ]+", text.lower()[:4000])
    pt = sum(w in _PT_WORDS for w in words)
    en = sum(w in _EN_WORDS for w in words)
    return "pt" if pt > en else "en"


_BOILERPLATE = re.compile(
    r"(equal (employment )?opportunity|we are an equal|eeo statement|reasonable accommodation|"
    r"pay transparency|e-verify|igualdade de oportunidades|somos uma empresa que valoriza a diversidade)",
    re.I,
)


def trim_for_llm(text: str, max_chars: int = 12000) -> str:
    """Drop trailing legal boilerplate and cap length to keep prompts cheap."""
    m = _BOILERPLATE.search(text)
    if m and m.start() > len(text) * 0.4:
        text = text[: m.start()]
    return text[:max_chars]


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def fold(s: str) -> str:
    """Lowercase and strip accents (for matching)."""
    return unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
