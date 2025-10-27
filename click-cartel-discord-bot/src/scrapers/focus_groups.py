from __future__ import annotations
from typing import List, Optional, Tuple
from datetime import date
import logging
import re
import urllib.parse

from bs4 import BeautifulSoup

from .base import BaseScraper, Listing

logger = logging.getLogger(__name__)

class FocusGroupsScraper(BaseScraper):
    site_name = "FocusGroups.org"
    base_url = "https://focusgroups.org"
    list_url = f"{self.base_url}/all" if False else "https://focusgroups.org/all"  # keep literal to avoid mypy complaints

    def _abs(self, url: str) -> str:
        return urllib.parse.urljoin(self.base_url, url or "")

    async def scrape(self, session) -> List[Listing]:
        html = await self.fetch_text(session, self.list_url, headers={"User-Agent": "ClickCartelBot/1.0"})
        soup = BeautifulSoup(html, "html.parser")

        listings: List[Listing] = []
        for a in soup.select('a[href^="/category/"]'):
            panel = a.find("div", class_="study-pannel")
            if not panel:
                continue
            href = a.get("href") or ""
            url = self._abs(href)

            title = self._txt(panel.find("div", class_="study-title"))
            if not (title and url):
                continue

            # Skip clinical trials
            method_slug = self._method_from_href(href)
            if method_slug == "clinical-trials":
                continue
            method = self._pretty_method(method_slug)

            dollars = self._txt(panel.select_one(".details .dollars"))
            payout = self._normalize_payout(dollars or title)
            location = self._txt(panel.select_one(".details .location")).replace("located", "", 1).strip()

            # Date on card
            event_text, start, end = self._extract_event_date_from_panel(panel)

            # Image on card (try <img>)
            img_url = ""
            img = panel.select_one("img")
            if img and (img.get("src") or img.get("data-src") or img.get("data-lazy-src")):
                img_url = self._abs(img.get("data-src") or img.get("data-lazy-src") or img.get("src"))
            # If missing date or image, fetch detail page
            if not event_text or not img_url:
                try:
                    detail_html = await self.fetch_text(session, url, headers={"User-Agent": "ClickCartelBot/1.0"})
                    if not event_text:
                        event_text, start, end = self._extract_event_date_from_detail(detail_html)
                    if not img_url:
                        img_url = self._extract_image_from_detail(detail_html) or img_url
                except Exception as e:
                    logger.debug("FocusGroups detail fetch failed: %s", e)

            today = date.today()
            if (end or start) and (end or start) < today:
                continue

            description = self._txt(panel.select_one(".details .description")) or ""

            listings.append(
                Listing(
                    site=self.site_name,
                    title=title,
                    link=url,
                    payout=payout,
                    date_posted=event_text or "",
                    location=location or "Remote",
                    method=method,
                    description=description,
                    image_url=img_url or "",
                )
            )
        logger.info("FocusGroups.org scraped %d listings", len(listings))
        return listings

    def _txt(self, el) -> str:
        return el.get_text(strip=True) if el else ""

    def _method_from_href(self, href: str) -> str:
        parts = href.strip("/").split("/")
        return parts[1] if len(parts) >= 2 and parts[0] == "category" else ""

    def _pretty_method(self, slug: str) -> str:
        slug = (slug or "").lower()
        mapping = {
            "focus-groups": "Focus Group",
            "interview-studies": "Interview",
            "product-testing": "Product Test",
            "diary-studies": "Diary Study",
            "unmoderated-studies": "Unmoderated",
            "survey-panels": "Survey",
        }
        return mapping.get(slug, slug.replace("-", " ").title() if slug else "")

    def _normalize_payout(self, s: str) -> str:
        if not s:
            return ""
        nums = []
        for m in re.findall(r"\$([\d,]+(?:\.\d{2})?)", s):
            try:
                nums.append(float(m.replace(",", "")))
            except ValueError:
                pass
        if not nums:
            return ""
        mx = max(nums)
        return f"${int(mx):,}" if mx.is_integer() else f"${mx:,.2f}"

    # ---- Date helpers ----
    def _extract_event_date_from_panel(self, panel) -> Tuple[str, Optional[date], Optional[date]]:
        txt = panel.get_text(" ", strip=True)
        txt = re.sub(r"Posted:\s*\d{1,2}/\d{1,2}/\d{2,4}", "", txt, flags=re.I)
        cand = self._find_event_date_text(txt)
        if not cand:
            return "", None, None
        start, end, pretty = self._parse_event_date_to_range(cand)
        return pretty, start, end

    def _extract_event_date_from_detail(self, html: str) -> Tuple[str, Optional[date], Optional[date]]:
        soup = BeautifulSoup(html, "html.parser")
        body_text = soup.get_text(" ", strip=True)
        for sel in [".study-date", ".date", ".dates", ".event-date", ".study-details", ".details", "section", "article"]:
            for el in soup.select(sel):
                t = re.sub(r"Posted:\s*\d{1,2}/\d{1,2}/\d{2,4}", "", el.get_text(" ", strip=True), flags=re.I)
                cand = self._find_event_date_text(t)
                if cand:
                    start, end, pretty = self._parse_event_date_to_range(cand)
                    if pretty:
                        return pretty, start, end
        t = re.sub(r"Posted:\s*\d{1,2}/\d{1,2}/\d{2,4}", "", body_text, flags=re.I)
        cand = self._find_event_date_text(t)
        if cand:
            start, end, pretty = self._parse_event_date_to_range(cand)
            if pretty:
                return pretty, start, end
        return "", None, None

    def _extract_image_from_detail(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")

        def pick_src(img) -> str:
            srcset = (img.get("srcset") or "").strip()
            if srcset:
                best_url = ""
                best_w = -1
                for part in srcset.split(","):
                    seg = part.strip()
                    if not seg:
                        continue
                    bits = seg.split()
                    url = bits[0]
                    w = 0
                    if len(bits) > 1 and bits[1].endswith("w"):
                        try:
                            w = int(bits[1][:-1])
                        except Exception:
                            w = 0
                    if w > best_w:
                        best_w = w
                        best_url = url
                if best_url:
                    return self._abs(best_url)
            return self._abs(img.get("data-src") or img.get("data-lazy-src") or img.get("src") or "")

        # Prefer the big article image (usually with overlaid text)
        for sel in ("article img", ".entry-content img", ".post-content img", "figure img"):
            candidates = soup.select(sel)
            if candidates:
                scored = []
                for im in candidates:
                    srcset = (im.get("srcset") or "")
                    width = 0
                    if srcset:
                        try:
                            width = max(
                                int(p.strip().split()[1][:-1])
                                for p in srcset.split(",")
                                if len(p.strip().split()) > 1 and p.strip().split()[1].endswith("w")
                            )
                        except Exception:
                            width = 0
                    scored.append((width, im))
                for _w, im in sorted(scored, key=lambda x: x[0], reverse=True):
                    url = pick_src(im)
                    if url:
                        return url

        og = soup.select_one('meta[property="og:image"]')
        if og and og.get("content"):
            return self._abs(og["content"])

        img = soup.select_one("img")
        if img:
            return pick_src(img)
        return ""

    def _find_event_date_text(self, text: str) -> str:
        months = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        day = r"\d{1,2}(?:st|nd|rd|th)?"
        year = r"(?:,\s*\d{4})?"
        pats = [
            rf"\b{months}\.?\s+{day}\s*[-–]\s*{day}{year}",
            rf"\b{months}\.?\s+{day}\s*[-–]\s*{months}\.?\s+{day}{year}",
            rf"\b{months}\.?\s+{day}{year}",
            r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
            r"\b\d{1,2}/\d{1,2}\s*[-–]\s*\d{1,2}/\d{1,2}(?:/\d{2,4})?\b",
            r"\b\d{1,2}/\d{1,2}\b",
        ]
        for p in pats:
            m = re.search(p, text, flags=re.I)
            if m:
                return m.group(0)
        return ""

    def _parse_event_date_to_range(self, s: str) -> Tuple[Optional[date], Optional[date], str]:
        s = re.sub(r"(\d)(st|nd|rd|th)", r"\1", s)
        s = re.sub(r"\s+", " ", s.strip())
        if not s:
            return None, None, ""
        today = date.today()
        y_def = today.year

        month_map = {
            "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
            "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
            "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
            "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
        }

        m = re.match(r"(?i)^\s*([A-Za-z]+)\.?\s+(\d{1,2})\s*[-–]\s*([A-Za-z]+)\.?\s+(\d{1,2})(?:,\s*(\d{4}))?\s*$", s)
        if m:
            m1, d1, m2, d2, y = m.groups()
            yv = int(y) if y else y_def
            start = date(yv, month_map[m1.lower()], int(d1))
            end = date(yv, month_map[m2.lower()], int(d2))
            return start, end, self._fmt_range(start, end)

        m = re.match(r"(?i)^\s*([A-Za-z]+)\.?\s+(\d{1,2})\s*[-–]\s*(\d{1,2})(?:,\s*(\d{4}))?\s*$", s)
        if m:
            mo, d1, d2, y = m.groups()
            yv = int(y) if y else y_def
            mm = month_map[mo.lower()]
            start = date(yv, mm, int(d1))
            end = date(yv, mm, int(d2))
            return start, end, self._fmt_range(start, end)

        m = re.match(r"(?i)^\s*([A-Za-z]+)\.?\s+(\d{1,2})(?:,\s*(\d{4}))?\s*$", s)
        if m:
            mo, d, y = m.groups()
            yv = int(y) if y else y_def
            mm = month_map[mo.lower()]
            start = end = date(yv, mm, int(d))
            return start, end, self._fmt_range(start, end)

        m = re.match(r"^\s*(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\s*[-–]\s*(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\s*$", s)
        if m:
            m1, d1, y1, m2, d2, y2 = m.groups()
            y1v = int(y1) + 2000 if y1 and len(y1) == 2 else (int(y1) if y1 else y_def)
            y2v = int(y2) + 2000 if y2 and len(y2) == 2 else (int(y2) if y2 else y1v)
            start = date(y1v, int(m1), int(d1))
            end = date(y2v, int(m2), int(d2))
            return start, end, self._fmt_range(start, end)

        m = re.match(r"^\s*(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\s*$", s)
        if m:
            mm, dd, yy = m.groups()
            yv = int(yy) + 2000 if yy and len(yy) == 2 else (int(yy) if yy else y_def)
            start = end = date(yv, int(mm), int(dd))
            return start, end, self._fmt_range(start, end)

        return None, None, ""

    def _fmt_range(self, start: date, end: date) -> str:
        if start == end:
            return start.strftime("%b %d, %Y")
        if start.year == end.year:
            if start.month == end.month:
                return f"{start.strftime('%b')} {start.day}–{end.day}, {start.year}"
            return f"{start.strftime('%b %d')} – {end.strftime('%b %d')}, {start.year}"
        return f"{start.strftime('%b %d, %Y')} – {end.strftime('%b %d, %Y')}"