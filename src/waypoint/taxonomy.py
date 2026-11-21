"""Skill taxonomy: canonicalization of free-text skill names and dictionary matching."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import get_close_matches
from functools import lru_cache

from .settings import taxonomy_data
from .textutil import fold, slugify

_WORD = r"0-9a-z"


@dataclass
class Skill:
    id: str
    name: str
    cat: str
    aliases: list[str]
    canon: list[str] = field(default_factory=list)
    regex: str | None = None
    effort: int = 20


class Taxonomy:
    def __init__(self, data: dict):
        self.categories: dict[str, str] = data.get("categories", {})
        self.skills: dict[str, Skill] = {}
        for s in data["skills"]:
            self.skills[s["id"]] = Skill(
                id=s["id"], name=s["name"], cat=s["cat"], aliases=list(s.get("aliases", [])),
                canon=list(s.get("canon", [])), regex=s.get("regex"), effort=int(s.get("effort", 20)),
            )
        # lookup index for canonicalization (folded strings)
        self._index: dict[str, str] = {}
        for sk in self.skills.values():
            for a in [sk.id, sk.id.replace("_", " "), sk.name, *sk.aliases, *sk.canon]:
                self._index.setdefault(_key(a), sk.id)
        # text matchers for the dictionary baseline
        self._matchers: list[tuple[str, re.Pattern, re.Pattern | None]] = []
        for sk in self.skills.values():
            alts = sorted({fold(a) for a in sk.aliases}, key=len, reverse=True)
            pat = re.compile(
                rf"(?<![{_WORD}])(?:{'|'.join(re.escape(a) for a in alts)})(?![{_WORD}+#])"
            ) if alts else None
            extra = re.compile(sk.regex) if sk.regex else None
            self._matchers.append((sk.id, pat, extra))  # type: ignore[arg-type]

    # ---------- canonicalization ----------
    def canonicalize(self, name: str) -> list[str]:
        """Map a free-text skill name to taxonomy ids. Unknown -> ["other:<slug>"]."""
        k = _key(name)
        if not k:
            return []
        if k in self._index:
            return [self._index[k]]
        # "Python (pandas, numpy)" -> try the head and the parenthesis content
        head = _key(re.sub(r"\(.*?\)", "", name))
        if head and head in self._index:
            return [self._index[head]]
        found = self.find_in_text(name)
        if found:
            return sorted(found)
        close = get_close_matches(k, list(self._index), n=1, cutoff=0.92)
        if close:
            return [self._index[close[0]]]
        return [f"other:{slugify(name)[:40]}"]

    def name_of(self, skill_id: str) -> str:
        if skill_id in self.skills:
            return self.skills[skill_id].name
        return skill_id.split(":", 1)[-1].replace("-", " ")

    def category_of(self, skill_id: str) -> str:
        return self.skills[skill_id].cat if skill_id in self.skills else "other"

    def effort_of(self, skill_id: str) -> int:
        return self.skills[skill_id].effort if skill_id in self.skills else 20

    # ---------- dictionary matching ----------
    def find_in_text(self, text: str) -> set[str]:
        folded = fold(text)
        out: set[str] = set()
        for sid, pat, extra in self._matchers:
            if (pat is not None and pat.search(folded)) or (extra is not None and extra.search(text)):
                out.add(sid)
        return out

    def prompt_vocabulary(self) -> str:
        """Compact list of canonical names, grouped by category, for the LLM prompt."""
        groups: dict[str, list[str]] = {}
        for s in self.skills.values():
            groups.setdefault(s.cat, []).append(s.name)
        return "\n".join(f"- {self.categories.get(c, c)}: {', '.join(names)}" for c, names in groups.items())


def _key(s: str) -> str:
    return re.sub(r"\s+", " ", fold(s).strip(" .:-*•")).strip()


@lru_cache(maxsize=1)
def get_taxonomy() -> Taxonomy:
    return Taxonomy(taxonomy_data())
