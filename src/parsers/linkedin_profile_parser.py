from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from parsers.html_cleaner import clean_text

class LinkedInProfileParser:
    """
    Heuristic parser for LinkedIn public profile HTML.
    Tries multiple strategies:
      1) JSON-LD / application/ld+json blocks.
      2) OpenGraph / meta tags for names, headline, image.
      3) Fallback DOM selectors commonly present on public profiles.
    """

    def __init__(self, logger=None):
        self.log = logger

    def _log_debug(self, msg: str):
        if self.log:
            self.log.debug(msg)

    def _log_info(self, msg: str):
        if self.log:
            self.log.info(msg)

    def parse_profile(self, url: str, html: str) -> Dict[str, Any]:
        soup = BeautifulSoup(html, "lxml")

        data: Dict[str, Any] = {
            "fullName": None,
            "headline": None,
            "followers": None,
            "profilePicture": None,
            "education": [],
            "experience": [],
            "location": None,
            "about": None,
            "skills": [],
            "profileUrl": url,
        }

        # Strategy 1: JSON-LD blocks
        for script in soup.find_all("script", {"type": "application/ld+json"}):
            try:
                payload = json.loads(script.string or "{}")
            except Exception:
                continue
            if isinstance(payload, dict):
                self._extract_from_jsonld(payload, data)
            elif isinstance(payload, list):
                for item in payload:
                    if isinstance(item, dict):
                        self._extract_from_jsonld(item, data)

        # Strategy 2: meta tags (OpenGraph / standard)
        self._extract_from_meta(soup, data)

        # Strategy 3: DOM heuristics (public profile markup may vary)
        self._extract_from_dom(soup, data)

        # Normalize and clean
        data["fullName"] = clean_text(data["fullName"])
        data["headline"] = clean_text(data["headline"])
        data["location"] = clean_text(data["location"])
        data["about"] = clean_text(data["about"])
        data["skills"] = [clean_text(s) for s in data["skills"] if s]
        data["education"] = [self._clean_obj(ed) for ed in data["education"]]
        data["experience"] = [self._clean_obj(ex) for ex in data["experience"]]

        return data

    def _clean_obj(self, obj: Dict[str, Any]) -> Dict[str, Any]:
        return {k: clean_text(v) if isinstance(v, str) else v for k, v in obj.items()}

    def _extract_from_jsonld(self, payload: Dict[str, Any], data: Dict[str, Any]) -> None:
        typ = payload.get("@type") or payload.get("type")
        if not typ:
            return

        # Person schema
        if isinstance(typ, str) and typ.lower() == "person":
            data["fullName"] = data["fullName"] or payload.get("name")
            data["headline"] = data["headline"] or payload.get("jobTitle")
            img = payload.get("image")
            if isinstance(img, dict):
                data["profilePicture"] = data["profilePicture"] or img.get("url")
            elif isinstance(img, str):
                data["profilePicture"] = data["profilePicture"] or img
            # Location
            loc = payload.get("address") or payload.get("homeLocation")
            if isinstance(loc, dict):
                data["location"] = data["location"] or loc.get("addressLocality") or loc.get("name")

        # Work experience (as worksFor or alumniOf details)
        works_for = payload.get("worksFor")
        if isinstance(works_for, dict):
            company = works_for.get("name")
            if company:
                data["experience"].append({"company": company, "role": payload.get("jobTitle"), "duration": None})

        # Education
        alumni_of = payload.get("alumniOf")
        if isinstance(alumni_of, dict):
            institution = alumni_of.get("name")
            if institution:
                data["education"].append({"degree": None, "institution": institution, "year": None})

    def _extract_from_meta(self, soup, data: Dict[str, Any]) -> None:
        def meta(name: str, attr: str = "property") -> Optional[str]:
            m = soup.find("meta", {attr: name})
            return m.get("content") if m and m.has_attr("content") else None

        full_name = meta("og:title") or meta("profile:first_name") or meta("name", "name")
        if full_name:
            data["fullName"] = data["fullName"] or full_name

        headline = meta("og:description") or meta("description", "name")
        if headline:
            data["headline"] = data["headline"] or headline

        image = meta("og:image")
        if image:
            data["profilePicture"] = data["profilePicture"] or image

        # Followers sometimes appear in meta descriptions like "X followers"
        desc = meta("description", "name") or meta("og:description")
        if desc:
            m = re.search(r"(\d[\d,\.]*)\s+(followers|connections)", desc, flags=re.I)
            if m:
                try:
                    data["followers"] = int(m.group(1).replace(",", "").replace(".", ""))
                except Exception:
                    pass

        # Location hints can appear in og:title or description
        if desc and not data["location"]:
            m2 = re.search(r"Based in ([^.|,]+)", desc, flags=re.I)
            if m2:
                data["location"] = m2.group(1).strip()

    def _extract_from_dom(self, soup, data: Dict[str, Any]) -> None:
        # Public profile name
        if not data["fullName"]:
            name_el = soup.select_one("h1, .pv-text-details__left-panel h1, .text-heading-xlarge")
            if name_el:
                data["fullName"] = name_el.get_text(strip=True)

        # Headline / about
        if not data["headline"]:
            headline_el = soup.select_one(".pv-text-details__left-panel .text-body-medium, .text-body-medium")
            if headline_el:
                data["headline"] = headline_el.get_text(" ", strip=True)

        if not data["about"]:
            about_sel = soup.select_one("#about ~ div .pv-shared-text-with-see-more .visually-hidden, section#about p")
            if about_sel:
                data["about"] = about_sel.get_text(" ", strip=True)

        # Location
        if not data["location"]:
            loc_el = soup.select_one(".pv-text-details__left-panel .text-body-small.inline")
            if loc_el:
                data["location"] = loc_el.get_text(" ", strip=True)

        # Profile picture
        if not data["profilePicture"]:
            img_el = soup.select_one("img.pv-top-card-profile-picture__image, img.pv-top-card-profile-picture__image--show")
            if img_el and img_el.get("src"):
                data["profilePicture"] = img_el["src"]

        # Followers/connections text appears near top card
        if data["followers"] is None:
            fl_el = soup.find(string=re.compile(r"(followers|connections)", re.I))
            if fl_el:
                m = re.search(r"(\d[\d,\.]*)", fl_el)
                if m:
                    try:
                        data["followers"] = int(m.group(1).replace(",", "").replace(".", ""))
                    except Exception:
                        pass

        # Education items
        for ed in soup.select("section#education ~ ul li, section.pv-profile-section.education-section li"):
            inst = ed.select_one(".pv-entity__school-name, .t-16.t-black.t-bold")
            degree = ed.select_one(".pv-entity__degree-name .pv-entity__comma-item, .t-14.t-black.t-normal")
            year = ed.select_one(".pv-entity__dates time, .pv-entity__date-range span:nth-of-type(2)")
            edu_obj = {
                "degree": inst and degree.get_text(" ", strip=True) or None,
                "institution": inst.get_text(" ", strip=True) if inst else None,
                "year": year.get_text(strip=True) if year else None
            }
            if edu_obj["institution"] or edu_obj["degree"]:
                data["education"].append(edu_obj)

        # Experience items
        for ex in soup.select("section#experience ~ ul li, section.pv-profile-section.experience-section li"):
            company = ex.select_one(".pv-entity__secondary-title, .t-14.t-black.t-normal")
            role = ex.select_one(".t-16.t-black.t-bold, .pv-entity__summary-info h3")
            duration = ex.select_one(".pv-entity__bullet-item-v2, .pv-entity__date-range span:nth-of-type(2)")
            exp_obj = {
                "company": company.get_text(" ", strip=True) if company else None,
                "role": role.get_text(" ", strip=True) if role else None,
                "duration": duration.get_text(" ", strip=True) if duration else None
            }
            if exp_obj["company"] or exp_obj["role"]:
                data["experience"].append(exp_obj)

        # Skills (public pages often hide skills; try common selectors)
        for sk in soup.select("span.pv-skill-category-entity__name-text, .pv2 .t-14.t-black.t-bold"):
            txt = sk.get_text(" ", strip=True)
            if txt and txt.lower() not in {"", "skills"}:
                data["skills"].append(txt)