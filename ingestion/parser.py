import re

from bs4 import BeautifulSoup, NavigableString


class TenKParser:
    """Extracts the three target sections from 10-K HTML.

    Primary path: follow the filing's own TOC anchors to section boundaries.
    Fallback: heading-pattern heuristics over flattened text.
    """

    ITEM_SPANS = {
        "business": ("1", "1a"),
        "risk_factors": ("1a", "1b"),
        "mdna": ("7", "7a"),
    }

    HEADING_WORDS = {
        "1": ["business"],
        "1a": ["risk", "factors"],
        "1b": ["unresolved"],
        "7": ["management"],
        "7a": ["quantitative"],
    }

    @staticmethod
    def _clean(text):
        return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()

    def parse(self, html):
        """HTML -> {section_name: section_text}"""
        soup = BeautifulSoup(html, "lxml")
        try:
            sections = self._parse_by_anchors(soup)
        except ValueError:
            sections = self._parse_by_headings(soup)
        self._validate(sections)
        return sections

    def _validate(self, sections):
        for name, body in sections.items():
            if not 5_000 <= len(body) <= 400_000:
                raise ValueError(f"{name}: implausible length {len(body)}")
            if re.match(r"item\s+\d+[a-c]?\.?\s+\D{0,60}\d", body[:100], re.I):
                raise ValueError(f"{name}: looks like a TOC slice")

    def _anchor_map(self, soup):
        """item code ('1a') -> the element where that item starts."""
        anchors = {}
        for a in soup.find_all("a", href=re.compile(r"^#")):
            text = self._clean(a.get_text(" "))
            m = re.match(r"item\s+(\d+[a-c]?)\.?\s*[^\d]*$", text, re.I)
            if m:
                code = m.group(1).lower()
                target = soup.find(id=a["href"][1:])
                if target is not None and code not in anchors:
                    anchors[code] = target

        for el in soup.find_all(id=re.compile(r"^item_?\d", re.I)):
            m = re.match(r"item_?(\d+[a-c]?)(_|$)", el["id"], re.I)
            if m:
                anchors.setdefault(m.group(1).lower(), el)
        return anchors

    def _text_between(self, start_el, end_el):
        """Collect text nodes in document order from one anchor to the next."""
        parts = []
        for node in start_el.next_elements:
            if node is end_el:
                break
            if isinstance(node, NavigableString) and node.parent.name not in (
                "script",
                "style",
            ):
                parts.append(str(node))
        return self._clean(" ".join(parts))

    def _parse_by_anchors(self, soup):
        anchors = self._anchor_map(soup)
        sections = {}
        for name, (start_code, end_code) in self.ITEM_SPANS.items():
            if start_code not in anchors or end_code not in anchors:
                raise ValueError(f"anchors missing for {name}")
            sections[name] = self._text_between(anchors[start_code], anchors[end_code])
        return sections

    def html_to_text(self, html_or_soup):
        soup = (
            html_or_soup
            if isinstance(html_or_soup, BeautifulSoup)
            else BeautifulSoup(html_or_soup, "lxml")
        )
        for tag in soup(["script", "style"]):
            tag.decompose()
        return self._clean(soup.get_text(" "))

    def _heading_pattern(self, code):
        spaced = [r"\s*".join(word) for word in self.HEADING_WORDS[code]]
        return rf"item\s+{code}\.?\s+" + r"\s+".join(spaced) + r"(?!\s*\d)"

    def _heading_candidates(self, text, pattern):
        candidates = []
        for m in re.finditer(pattern, text, re.IGNORECASE):
            before = text[max(0, m.start() - 12) : m.start()].lower()
            if "“" in before or before.endswith("refer to "):
                continue
            candidates.append(m)
        return candidates

    def _parse_by_headings(self, soup):
        text = self.html_to_text(soup)
        sections = {}
        for name, (start_code, end_code) in self.ITEM_SPANS.items():
            starts = self._heading_candidates(text, self._heading_pattern(start_code))
            if not starts:
                raise ValueError(f"{name}: start heading not found")
            start = starts[-1].start()
            ends = [
                m
                for m in self._heading_candidates(text, self._heading_pattern(end_code))
                if m.start() > start
            ]
            if not ends:
                raise ValueError(f"{name}: end heading not found")
            sections[name] = text[start : ends[0].start()]
        return sections
