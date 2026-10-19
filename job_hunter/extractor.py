"""
Job Extractor & Normalizer: Parses raw page DOM or text into structured JobPosting objects.
"""

from __future__ import annotations

import html
import re
import urllib.parse
from typing import Any, Dict, List, Optional
from job_hunter.models import JobPosting


class JobExtractor:
    """Extracts structured JobPosting records from page DOM or text."""

    @staticmethod
    def extract_from_page(page: Any, url: str, fallback_text: str = "") -> JobPosting:
        """
        Extracts structured job posting details from an active Playwright page.
        Supports common ATS formats (Greenhouse, Lever, Workable, WeWorkRemotely, etc.).
        """
        # 1. Try extracting structured data from JSON-LD if present (Schema.org/JobPosting)
        json_ld_data = page.evaluate("""
        () => {
            const scripts = Array.from(document.querySelectorAll('script[type="application/ld+json"]'));
            for (const script of scripts) {
                try {
                    const parsed = JSON.parse(script.innerText);
                    const item = Array.isArray(parsed) ? parsed.find(x => x['@type'] === 'JobPosting') : (parsed['@type'] === 'JobPosting' ? parsed : null);
                    if (item) return item;
                } catch(e) {}
            }
            return null;
        }
        """)

        if json_ld_data and isinstance(json_ld_data, dict):
            title = json_ld_data.get("title") or page.title()
            hiring_org = json_ld_data.get("hiringOrganization", {})
            company = hiring_org.get("name") if isinstance(hiring_org, dict) else ""
            location = "Remote"
            job_loc = json_ld_data.get("jobLocation", {})
            if isinstance(job_loc, dict):
                address = job_loc.get("address", {})
                if isinstance(address, dict):
                    location = address.get("addressLocality") or address.get("addressCountry") or "Remote"
            desc = json_ld_data.get("description") or ""
            clean_desc = html.unescape(re.sub(r"<[^>]+>", " ", desc))
            clean_desc = re.sub(r"\s+", " ", clean_desc).strip()
            return JobPosting(
                title=title,
                company=company or "Company",
                location=location,
                url=url,
                description=clean_desc[:6000],
                source="json-ld",
            )

        # 2. Heuristic DOM extraction
        extracted = page.evaluate("""
        () => {
            // Expand full description if 'Show more' / 'Daha fazla göster' is present
            const showMoreBtn = document.querySelector(
                'button[aria-label*="Show more"], button[aria-label*="Daha fazla"], .jobs-description__footer-button, button.show-more-less-html__button--more'
            );
            if (showMoreBtn) {
                try { showMoreBtn.click(); } catch(e) {}
            }

            // Find job title (h1 or prominent header)
            const h1 = document.querySelector('.job-details-jobs-unified-top-card__job-title, .top-card-layout__job-title, .top-card-layout__title, .listing-header-container h1, h1, .job-title, [data-qa="job-title"]');
            const title = h1 ? h1.innerText.trim() : '';

            // Find company name
            const compEl = document.querySelector('.job-details-jobs-unified-top-card__company-name, .top-card-layout__first-subline a, a[data-tracking-control-name="public_jobs_topcard-org-name"], a[href*="/company/"], .topcard__org-name-link, .topcard__flavor, .company-card__company-name, .listing-header-container h2, .company-name, [data-qa="company-name"], .employer, .company');
            const company = compEl ? compEl.innerText.trim() : '';

            // Find location
            const locEl = document.querySelector('.job-details-jobs-unified-top-card__bullet, .topcard__flavor--bullet, .location, [data-qa="job-location"], .workplace, .listing-header-container .location');
            const location = locEl ? locEl.innerText.trim() : '';

            // Find main content
            const contentEl = document.querySelector('#job-details, .jobs-description__content, .jobs-box__html-content, .show-more-less-html__markup, [data-testid="job-details"], main, article, #job-description, .job-description, .content, .description') || document.body;
            const text = contentEl ? contentEl.innerText.trim() : '';

            // Check Easy Apply
            const easyApplyBtn = document.querySelector('.jobs-apply-button, button[aria-label*="Easy Apply"], button[aria-label*="Kolay Başvuru"], .jobs-apply-button--top-card');
            const hasEasyApply = Boolean(easyApplyBtn);

            return {
                title: title,
                company: company,
                location: location,
                text: text,
                has_easy_apply: hasEasyApply
            };
        }
        """)

        title = extracted.get("title") or ""
        company = extracted.get("company") or ""
        location = extracted.get("location") or "Remote"
        description = extracted.get("text") or ""
        has_easy_apply = bool(extracted.get("has_easy_apply", False))

        # Fallback from URL slug if title is missing or generic domain
        parsed_url = urllib.parse.urlparse(url)
        slug = parsed_url.path.strip("/").split("/")[-1]

        # Clean generic site titles
        if not title or any(domain in title.lower() for domain in ["weworkremotely", "just a moment", "remote jobs"]):
            if fallback_text and len(fallback_text) > 10:
                # Clean up badge words like '2d', 'boosted', 'featured'
                cleaned = re.sub(r"\b(\d+[dhm]|boosted\s*listing|boosted|featured|full-time)\b", "", fallback_text, flags=re.I)
                title = cleaned.strip()
            elif slug:
                parts = slug.replace("-", " ").title().split()
                if len(parts) >= 2:
                    if not company:
                        company = parts[0]
                    title = " ".join(parts[1:])
                else:
                    title = slug.replace("-", " ").title()

        if not company or company.lower() in ("tech company", "company"):
            if fallback_text and "@" in fallback_text:
                parts = fallback_text.split("@")
                company = parts[-1].strip()
                if not title or title.lower() in ("tech company", "company", "software engineer"):
                    title = parts[0].strip()
            elif (m := re.search(r'-at-([a-z0-9\-]+)-\d+', url)):
                company = m.group(1).replace("-", " ").title()
            elif " at " in title:
                parts = title.split(" at ", 1)
                title = parts[0].strip()
                company = parts[1].split("-")[0].split("|")[0].strip()
            elif " - " in title:
                parts = title.split(" - ", 1)
                company = parts[0].strip()
                title = parts[1].strip()
            elif slug and "-" in slug:
                company = slug.split("-")[0].title()
            else:
                company = "Tech Company"

        return JobPosting(
            title=title,
            company=company,
            location=location,
            url=url,
            description=description[:6000],
            has_easy_apply=has_easy_apply,
            source="dom",
        )

    @staticmethod
    def extract_from_card(card_data: Dict[str, Any], base_url: str = "") -> JobPosting:
        """
        Creates a JobPosting from listing summary data or card elements.
        """
        title = card_data.get("title") or "Software Engineer"
        company = card_data.get("company") or "Technology Company"
        location = card_data.get("location") or "Remote"
        url = card_data.get("url") or base_url
        description = card_data.get("description") or f"Position: {title} at {company}. Location: {location}."
        tags = card_data.get("tags") or []

        return JobPosting(
            title=title,
            company=company,
            location=location,
            url=url,
            description=description,
            tags=tags,
            source="card",
        )
