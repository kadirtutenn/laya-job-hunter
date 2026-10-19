"""
Browser Navigator & Task Observer Agent: Drives the browser using DOM Perception and Laya decisions.
Supports persistent user profiles, headful interactive sessions, and LinkedIn-specific job feeds.
"""

from __future__ import annotations

import logging
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from job_hunter.dom_perception import DOMPerception
from job_hunter.extractor import JobExtractor
from job_hunter.laya_client import LayaClient
from job_hunter.models import CandidateProfile, JobPosting

logger = logging.getLogger(__name__)

DEFAULT_CHROME_PROFILE_DIR = str(Path.home() / ".job_hunter" / "chrome_profile")


def cleanup_chrome_locks(profile_dir: Path):
    """Safely cleans up stale Chromium SingletonLock files to prevent hung starts."""
    # Never remove Chromium's singleton files while its owner is still alive.
    # Doing so lets a second Playwright process start against the same profile,
    # which can close the first browser and surface as TargetClosedError.
    lock = profile_dir / "SingletonLock"
    if lock.is_symlink():
        try:
            owner = lock.resolve(strict=False).name.rsplit("-", 1)[-1]
            if owner.isdigit():
                import os
                os.kill(int(owner), 0)
                return
        except ProcessLookupError:
            pass
        except PermissionError:
            return
        except (OSError, RuntimeError, ValueError):
            # Unreadable or malformed lock: leave it in place rather than risk
            # corrupting a profile that may still be owned by Chromium.
            return

    for pattern in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        try:
            for p in profile_dir.glob(pattern):
                if p.is_symlink() or p.exists():
                    p.unlink(missing_ok=True)
        except Exception as e:
            logger.debug(f"Lock cleanup notice: {e}")


def build_linkedin_search_url(
    keywords: str = "Python Backend",
    location: str = "Turkey",
    workplace_types: Optional[List[str]] = None,
    easy_apply_only: bool = False,
    date_posted: Optional[str] = None,
    experience_levels: Optional[List[str]] = None,
) -> str:
    """Builds a precise LinkedIn Job Search URL from high-level filter criteria."""
    params: Dict[str, Any] = {
        "keywords": keywords,
        "location": location,
    }

    # Workplace Types: 1=On-site, 2=Remote, 3=Hybrid
    if workplace_types:
        mapping = {"onsite": "1", "remote": "2", "hybrid": "3"}
        codes = [mapping[wt.lower()] for wt in workplace_types if wt.lower() in mapping]
        if codes:
            params["f_WT"] = ",".join(codes)

    # Easy Apply
    if easy_apply_only:
        params["f_AL"] = "true"

    # Date Posted: r86400 (24h), r604800 (week), r2592000 (month)
    if date_posted:
        date_map = {"past_24h": "r86400", "past_week": "r604800", "past_month": "r2592000"}
        if date_posted in date_map:
            params["f_TPR"] = date_map[date_posted]

    # Experience Levels: 1=Intern, 2=Entry, 3=Associate, 4=Mid-Senior
    if experience_levels:
        exp_map = {"internship": "1", "entry": "2", "associate": "3", "mid_senior": "4"}
        codes = [exp_map[el.lower()] for el in experience_levels if el.lower() in exp_map]
        if codes:
            params["f_E"] = ",".join(codes)

    encoded = urllib.parse.urlencode(params)
    return f"https://www.linkedin.com/jobs/search/?{encoded}"


class BrowserNavigator:
    """Task Observer and Browser Driver powered by Playwright and Laya decisions."""

    def __init__(
        self,
        laya_client: LayaClient,
        headless: bool = True,
        max_steps: int = 30,
        model: str = "laya",
        user_data_dir: Optional[str] = None,
    ):
        self.client = laya_client
        self.headless = headless
        self.max_steps = max_steps
        self.model = model
        self.user_data_dir = user_data_dir or str(Path.home() / ".job_hunter" / "chrome_profile")
        self.visited_urls: set[str] = set()

    def check_linkedin_session(self) -> bool:
        """Checks whether a valid logged-in session exists in user_data_dir via li_at cookie or SQLite DB."""
        profile_dir = Path(self.user_data_dir)
        if not profile_dir.exists():
            return False

        # 1. Non-invasive, lock-free SQLite check directly from Cookies DB (no browser instance needed)
        cookies_db = profile_dir / "Default" / "Cookies"
        if cookies_db.exists():
            try:
                import sqlite3
                conn = sqlite3.connect(f"file:{cookies_db}?mode=ro", uri=True)
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM cookies WHERE name = 'li_at' AND host_key LIKE '%linkedin%' LIMIT 1;")
                row = cur.fetchone()
                conn.close()
                if row:
                    return True
            except Exception as e:
                logger.debug(f"Direct cookies DB check note: {e}")

        # If a headful browser session is currently running, do NOT spawn a competing headless context
        if (profile_dir / "SingletonLock").exists() or (profile_dir / "SingletonSocket").exists():
            return False

        # 2. Fallback to Playwright headless check when browser is idle
        from playwright.sync_api import sync_playwright
        try:
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir),
                    headless=True,
                    args=["--no-sandbox"],
                )
                cookies = context.cookies(["https://www.linkedin.com", "https://www.linkedin.com/feed/"])
                has_li_at = any(c.get("name") == "li_at" and len(c.get("value", "")) > 10 for c in cookies)
                context.close()
                return has_li_at
        except Exception as e:
            logger.debug(f"Session check error: {e}")
            return False

    def open_interactive_login(self, target_url: str = "https://www.linkedin.com/login") -> bool:
        """
        Launches Chrome on screen (headful) using the persistent user data directory,
        allowing the user to log in to LinkedIn or another portal.
        Cookies and session tokens persist for all subsequent automated runs.
        Keeps the window open comfortably so user can complete 2FA / checkpoint without crashing.
        """
        from playwright.sync_api import sync_playwright
        import time

        profile_dir = Path(self.user_data_dir)
        profile_dir.mkdir(parents=True, exist_ok=True)
        # Reuse an already-open interactive profile rather than launching a
        # competing persistent context that can disconnect the live window.
        lock = profile_dir / "SingletonLock"
        if lock.is_symlink():
            try:
                owner = lock.resolve(strict=False).name.rsplit("-", 1)[-1]
                if owner.isdigit():
                    import os
                    os.kill(int(owner), 0)
                    logger.info("LinkedIn profile already has an open Chrome window; using its saved session.")
                    return self.check_linkedin_session()
            except (ProcessLookupError, FileNotFoundError):
                pass
            except PermissionError:
                logger.warning("Cannot verify profile lock owner; avoiding a second Chrome launch.")
                return self.check_linkedin_session()
            except (OSError, RuntimeError, ValueError):
                logger.warning("Cannot safely verify Chrome profile lock; avoiding a second launch.")
                return self.check_linkedin_session()

        cleanup_chrome_locks(profile_dir)

        logger.info(f"Opening interactive browser window with profile at: {profile_dir}")
        print(f"\n[+] Chrome penceresi ekranınızda açılıyor...")
        print(f"    Profil Dizini: {profile_dir}")
        print(f"    Gidilen Adres: {target_url}")
        print("    Lütfen açılan pencerede LinkedIn hesabınıza giriş yapın.")
        print("    Giriş tamamlandığında sistem oturumu kalıcı olarak kaydedecektir.\n")

        logged_in = False
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=False,
                args=["--no-sandbox", "--remote-debugging-port=9222"],
                viewport={"width": 1280, "height": 900},
            )
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.goto(target_url, wait_until="domcontentloaded")
            except Exception as e:
                logger.warning(f"Initial navigation notice: {e}")

            # Keep the login window under user control. A stale li_at cookie can
            # exist in a profile, so cookie presence must never close the window.
            print("    Pencere siz kapatana kadar açık kalacak. Giriş yaptıktan sonra kapatabilirsiniz.")
            try:
                while context.pages and not page.is_closed():
                    time.sleep(1)
            except Exception as e:
                logger.debug(f"Login window closed: {e}")

            try:
                all_cookies = context.cookies()
                logged_in = any(c.get("name") == "li_at" and len(c.get("value", "")) > 10 for c in all_cookies)
                context.close()
            except Exception:
                pass

        if logged_in:
            print("[+] LinkedIn oturumu ve çerezler kalıcı olarak kaydedildi!\n")
        else:
            logged_in = self.check_linkedin_session()
            if logged_in:
                print("[+] LinkedIn oturumu ve çerezler doğrulandı!\n")
            else:
                print("[!] Pencere kapatıldı. Oturum durumu güncellendi.\n")
        return logged_in

    def navigate_and_harvest(
        self,
        start_url: str,
        profile: CandidateProfile,
        on_job_found: Optional[Callable[[JobPosting], None]] = None,
        on_batch_found: Optional[Callable[[List[JobPosting]], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
        max_jobs: int = 5,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> List[JobPosting]:
        """
        Navigates starting from start_url, observing DOM elements and letting
        Laya decide which job to inspect next.
        """
        from playwright.sync_api import sync_playwright

        def emit(msg: str):
            logger.info(msg)
            if on_log:
                try:
                    on_log(msg)
                except Exception:
                    pass

        harvested_jobs: List[JobPosting] = []
        profile_dir = Path(self.user_data_dir)
        profile_dir.mkdir(parents=True, exist_ok=True)
        cleanup_chrome_locks(profile_dir)

        is_linkedin = "linkedin.com" in start_url
        emit(f"🌐 Tarayıcı başlatılıyor ({'Görünür / Headful' if not self.headless else 'Headless'})...")

        with sync_playwright() as p:
            attached_browser = None
            attached_to_user_browser = False
            lock = profile_dir / "SingletonLock"
            if lock.is_symlink():
                try:
                    owner = lock.resolve(strict=False).name.rsplit("-", 1)[-1]
                    if owner.isdigit():
                        import os
                        os.kill(int(owner), 0)
                        attached_browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
                        if not attached_browser.contexts:
                            raise RuntimeError("Açık Chrome'da kullanılabilir profil bulunamadı.")
                        context = attached_browser.contexts[0]
                        attached_to_user_browser = True
                        emit("🔗 Açık LinkedIn Chrome oturumuna bağlanıldı.")
                except ProcessLookupError:
                    attached_browser = None
                except PermissionError as e:
                    raise RuntimeError("Chrome profilinin sahibi doğrulanamadı; güvenli bağlantı kurulamadı.") from e
                except Exception as e:
                    raise RuntimeError(
                        "LinkedIn Chrome açık ancak uzaktan bağlantı etkin değil. "
                        "Chrome'u kapatıp dashboard'daki LinkedIn Giriş Yap düğmesiyle bir kez yeniden açın."
                    ) from e

            if not attached_to_user_browser:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir),
                    headless=self.headless,
                    args=["--no-sandbox"],
                    viewport={"width": 1366, "height": 900},
                )

            # Turbo Optimization: Abort heavy images, fonts, media, and trackers across all tabs
            def block_heavy_assets(route):
                req = route.request
                if req.resource_type in ("image", "font", "media") or any(
                    req.url.lower().endswith(ext)
                    for ext in (".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".woff", ".woff2", ".ttf", ".ico", ".mp4")
                ):
                    try:
                        route.abort()
                    except Exception:
                        pass
                else:
                    try:
                        route.continue_()
                    except Exception:
                        pass

            if not attached_to_user_browser:
                context.route("**/*", block_heavy_assets)

            # Keep the user's authenticated feed tab intact when attaching.
            page = context.new_page() if attached_to_user_browser else (context.pages[0] if context.pages else context.new_page())
            detail_page = context.new_page()

            emit(f"🔍 Arama sayfasına gidiliyor: {start_url}")
            try:
                page.goto(start_url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(3000)
            except Exception as e:
                emit(f"❌ Sayfa yüklenemedi: {e}")
                if not attached_to_user_browser:
                    context.close()
                return harvested_jobs

            step = 0
            effective_max_steps = max(self.max_steps, max_jobs * 3 + 100)
            while step < effective_max_steps and len(harvested_jobs) < max_jobs:
                if should_stop and should_stop():
                    emit("⏹️ Kullanıcı isteğiyle ilan taraması durduruldu.")
                    break
                step += 1
                curr_url = page.url
                self.visited_urls.add(curr_url)

                # Special LinkedIn Split-Panel & Card Handling
                if is_linkedin:
                    if "authwall" in curr_url or "checkpoint" in curr_url or "login" in curr_url:
                        emit("❌ LinkedIn oturumu açık değil (Authwall / Giriş ekranı engeli)! Lütfen önce 'LinkedIn Giriş Yap' butonu ile hesabınıza giriş yapın.")
                        break

                    try:
                        page.wait_for_selector(
                            '[componentkey*="job-card-component-ref-"], div[data-testid="lazy-column"], .jobs-search__results-list, .jobs-search-results-list, .scaffold-layout__list, .base-card, a[href*="/jobs/view/"]',
                            timeout=6000,
                        )
                    except Exception:
                        pass

                    # Dismiss any blocking guest modal / pop-up if present
                    page.evaluate("""
                    () => {
                        const dismissBtn = document.querySelector('button[aria-label="Dismiss"], .modal__dismiss, button[data-tracking-control-name="public_jobs_contextual-sign-in-modal_modal_dismiss"]');
                        if (dismissBtn) {
                            try { dismissBtn.click(); } catch(e) {}
                        }
                        const modal = document.querySelector('.contextual-sign-in-modal, .sign-in-modal, .join-form__form-container');
                        if (modal) {
                            modal.remove();
                            document.body.style.overflow = 'auto';
                        }
                    }
                    """)

                    # Comprehensive Left-Panel & Multi-Card Extraction (Supports both modern SPA LazyColumn & classic links)
                    linkedin_cards = page.evaluate("""
                    () => {
                        const items = [];
                        const seenIds = new Set();

                        // 1. Query modern SPA cards, attribute containers, and classic links
                        const candidateElements = Array.from(document.querySelectorAll(
                            '[componentkey*="job-card-component-ref-"], [data-occludable-job-id], [data-job-id], a[href*="/jobs/view/"], a.base-card__full-link, a.job-card-list__title, a.job-card-container__link, li.jobs-search-results__list-item, div.job-card-container'
                        ));

                        for (const el of candidateElements) {
                            let jobId = '';

                            // 1a. Modern LinkedIn SPA componentkey (e.g. job-card-component-ref-4471256693)
                            const compKey = el.getAttribute('componentkey') || '';
                            const compMatch = compKey.match(/job-card-component-ref-(\\d{8,12})/);
                            if (compMatch) {
                                jobId = compMatch[1];
                            }

                            // 1b. Direct ID extraction from data attributes
                            if (!jobId) {
                                const attrJobId = el.getAttribute('data-job-id') || el.getAttribute('data-occludable-job-id');
                                if (attrJobId && /^\\d{8,12}$/.test(attrJobId)) {
                                    jobId = attrJobId;
                                }
                            }

                            // 1c. Regex from link URL
                            if (!jobId && el.tagName && el.tagName.toLowerCase() === 'a') {
                                const href = el.href || '';
                                if (!href.includes('/company/')) {
                                    const match = href.match(/(\\d{8,12})/);
                                    if (match) jobId = match[1];
                                }
                            }

                            if (!jobId || seenIds.has(jobId)) continue;
                            seenIds.add(jobId);

                            // Extract title and company from card context
                            let title = '';
                            let company = '';

                            // 2a. Try button aria-label (e.g. "... başlıklı iş ilanını kapat")
                            const dismissBtn = el.querySelector('button[aria-label*="başlıklı"], button[aria-label*="job opening"], button[aria-label*="title"]');
                            if (dismissBtn) {
                                const label = dismissBtn.getAttribute('aria-label') || '';
                                const m = label.match(/(.*?)\\s+(?:başlıklı|job opening)/i);
                                if (m && m[1]) title = m[1].trim();
                            }

                            // 2b. Extract from inner paragraph tags (modern structure)
                            const pElements = Array.from(el.querySelectorAll('p'));
                            for (const p of pElements) {
                                const rawText = (p.innerText || '').trim();
                                if (!rawText || rawText.includes('Görüntülendi') || rawText.includes('Viewed')) continue;

                                if (!title) {
                                    const span = p.querySelector('span[aria-hidden="true"], span');
                                    title = (span ? span.innerText : rawText).trim().replace(/\\s+/g, ' ');
                                    title = title.replace(/\\(Doğrulanmış iş ilanı\\)/gi, '').replace(/\\(Verified.*?\\)/gi, '').trim();
                                } else if (!company) {
                                    company = rawText.replace(/\\s+/g, ' ');
                                    break;
                                }
                            }

                            // 2c. Fallbacks for classic card DOM
                            const card = el.closest('li') || el.closest('div.base-card') || el.closest('.job-card-container') || el;
                            if (!company && card) {
                                const compEl = card.querySelector('.job-card-container__company-name, .artdeco-entity-lockup__subtitle, .base-search-card__subtitle, h4, .job-card-container__primary-description');
                                if (compEl) company = compEl.innerText.trim().replace(/\\s+/g, ' ');
                            }
                            if ((!title || title.length < 3) && card) {
                                const titleEl = card.querySelector('.job-card-list__title, h3, strong, a.base-card__full-link, [data-qa="job-title"]');
                                if (titleEl) title = titleEl.innerText.trim().replace(/\\s+/g, ' ');
                            }

                            const fullText = company ? `${title} @ ${company}` : title;

                            items.push({
                                href: 'https://www.linkedin.com/jobs/view/' + jobId + '/',
                                job_id: jobId,
                                text: (fullText || ('Job ' + jobId)).slice(0, 100),
                            });
                        }

                        return items;
                    }
                    """)

                    unvisited = [c for c in linkedin_cards if c["href"] not in self.visited_urls]

                    if linkedin_cards and (step == 1 or getattr(self, "_last_cards_count", 0) != len(linkedin_cards)):
                        self._last_cards_count = len(linkedin_cards)
                        emit(f"📊 Sol panelde {len(linkedin_cards)} ilan kartı tespit edildi (Kalan işlenecek: {len(unvisited)}).")

                    if unvisited:
                        # Process available cards on current page in rapid batches of up to 4
                        self._consecutive_empty_scrolls = 0
                        batch_size = min(4, max_jobs - len(harvested_jobs), len(unvisited))
                        batch_targets = unvisited[:batch_size]

                        current_batch_extracted: List[JobPosting] = []
                        batch_summaries = [t["text"][:35] for t in batch_targets]
                        emit(f"⚡ [Batch] {len(batch_targets)} ilan aynı anda toplanıyor: {', '.join(batch_summaries)}...")
                        has_opened_detail = False

                        for target in batch_targets:
                            if should_stop and should_stop():
                                emit("⏹️ Kullanıcı isteğiyle ilan taraması durduruldu.")
                                break
                            if len(harvested_jobs) >= max_jobs:
                                break

                            job_url = target["href"]
                            self.visited_urls.add(job_url)

                            try:
                                # Throttle LinkedIn detail navigations. This is
                                # a courtesy delay, not a guarantee against
                                # LinkedIn rate limits or account restrictions.
                                if is_linkedin and has_opened_detail:
                                    detail_page.wait_for_timeout(3000)
                                    if should_stop and should_stop():
                                        emit("⏹️ Kullanıcı isteğiyle ilan taraması durduruldu.")
                                        break
                                detail_page.goto(job_url, wait_until="domcontentloaded", timeout=18000)
                                has_opened_detail = True
                                # Smart selector wait: proceed the millisecond content renders
                                try:
                                    detail_page.wait_for_selector(
                                        '#job-details, .jobs-description__content, [data-testid="job-details"], .jobs-box__html-content',
                                        timeout=2500,
                                    )
                                except Exception:
                                    pass

                                job = JobExtractor.extract_from_page(detail_page, job_url, fallback_text=target["text"])
                                if job and not any(j.id == job.id for j in harvested_jobs):
                                    harvested_jobs.append(job)
                                    current_batch_extracted.append(job)
                            except Exception as e:
                                error_text = str(e).lower()
                                if (
                                    "target page, context or browser has been closed" in error_text
                                    or "target closed" in error_text
                                ):
                                    emit("❌ Tarayıcı penceresi kapandı; geçersiz sekmelerle devam etmemek için arama durduruldu.")
                                    return harvested_jobs
                                emit(f"⚠️ İlan okunurken hata ({job_url}): {e}")

                        # Deliver the entire batch to orchestrator for concurrent Laya analysis!
                        if on_batch_found and current_batch_extracted:
                            on_batch_found(current_batch_extracted)
                        elif on_job_found and current_batch_extracted:
                            for j in current_batch_extracted:
                                on_job_found(j)

                        continue
                    else:
                        # Only scroll or paginate when ALL currently visible cards have been processed
                        consecutive_empty_scrolls = getattr(self, "_consecutive_empty_scrolls", 0) + 1
                        self._consecutive_empty_scrolls = consecutive_empty_scrolls

                        emit("📜 Sol liste kaydırılarak yeni ilanlar yükleniyor...")
                        page.evaluate("""
                        () => {
                            // Find and scroll left list container specifically (LazyColumn or scaffold)
                            const list = document.querySelector(
                                'div[data-testid="lazy-column"], div[data-component-type="LazyColumn"], .scaffold-layout__list, .jobs-search-results-list, .jobs-search__results-list, ul.scaffold-layout__list-container, div[tabindex="-1"], section.two-pane-serp-page__detail-view'
                            );
                            if (list) {
                                list.scrollTop += 800;
                            }
                            window.scrollBy(0, 800);

                            // Try clicking 'See more jobs' or show more button if present
                            const seeMoreBtn = document.querySelector('button.infinite-scroller__show-more-button, button[aria-label="See more jobs"], button.see-more-jobs');
                            if (seeMoreBtn) {
                                try { seeMoreBtn.click(); } catch(e) {}
                            }
                        }
                        """)
                        page.wait_for_timeout(2500)

                        # Only after 4 unsuccessful scrolls on this page, transition to next page via pagination
                        if consecutive_empty_scrolls >= 4:
                            current_start = 0
                            parsed_u = urllib.parse.urlparse(page.url)
                            qs = urllib.parse.parse_qs(parsed_u.query)
                            if "start" in qs:
                                try:
                                    current_start = int(qs["start"][0])
                                except Exception:
                                    current_start = 0
                            next_start = current_start + 25
                            qs["start"] = [str(next_start)]
                            new_query = urllib.parse.urlencode(qs, doseq=True)
                            next_page_url = urllib.parse.urlunparse((
                                parsed_u.scheme, parsed_u.netloc, parsed_u.path,
                                parsed_u.params, new_query, parsed_u.fragment
                            ))
                            emit(f"⏩ [Sayfalama] Mevcut sayfadaki tüm ilanlar bitti, sonraki sayfaya geçiliyor (&start={next_start})...")
                            self._consecutive_empty_scrolls = 0
                            try:
                                if is_linkedin:
                                    page.wait_for_timeout(3000)
                                    if should_stop and should_stop():
                                        emit("⏹️ Kullanıcı isteğiyle ilan taraması durduruldu.")
                                        break
                                page.goto(next_page_url, wait_until="domcontentloaded", timeout=25000)
                                page.wait_for_timeout(3000)
                            except Exception as e:
                                emit(f"Sayfa geçişi uyarısı: {e}")
                        continue

                # Generic / WWR / General Portals DOM Perception
                raw_links = page.evaluate("""
                () => {
                    const links = Array.from(document.querySelectorAll('a[href]'));
                    const seen = new Set();
                    const results = [];
                    for (const a of links) {
                        const href = a.href;
                        if (!href || seen.has(href)) continue;
                        const text = (a.innerText || a.textContent || '').trim().replace(/\\s+/g, ' ');
                        const isJobLink = (
                            href.includes('/remote-jobs/') ||
                            href.includes('/job/') ||
                            href.includes('/jobs/') ||
                            href.includes('/jobs/view/') ||
                            href.includes('/position/') ||
                            href.includes('/career/') ||
                            href.includes('/careers/') ||
                            a.className.toLowerCase().includes('job')
                        ) && !href.includes('/post-a-job') && !href.includes('/find-your-plan') && text.length > 5;

                        if (isJobLink) {
                            seen.add(href);
                            results.push({
                                href: href,
                                text: text.slice(0, 100)
                            });
                        }
                    }
                    return results;
                }
                """)

                unvisited = [l for l in raw_links if l["href"] not in self.visited_urls]

                if not unvisited:
                    logger.info("No more unvisited job links on screen, scrolling down...")
                    page.evaluate("window.scrollBy(0, 1000)")
                    page.wait_for_timeout(1500)
                    continue

                # Decide next job choice using Laya
                criteria = {}
                candidate_map = {}
                for idx, cand in enumerate(unvisited[:8]):
                    key = f"job_{idx}"
                    criteria[key] = cand["text"]
                    candidate_map[key] = cand

                criteria["scroll_down"] = "Scroll down for more listings"

                state_desc = (
                    f"Candidate Profile: {profile.name} - {profile.title}\n"
                    f"Skills: {', '.join(profile.core_skills[:6])}\n"
                    f"Current Page: {page.title()}\n"
                    f"Harvested: {len(harvested_jobs)} / {max_jobs} jobs"
                )

                questions = {
                    "next_job_choice": {
                        "type": "choice",
                        "instructions": "Which job opening should the browser navigate to and inspect next?",
                        "criteria": criteria,
                    }
                }

                try:
                    dec = self.client.decide(state=state_desc, questions=questions, model=self.model)
                    chosen_key = dec.get("answers", {}).get("next_job_choice", {}).get("choice", "scroll_down")
                except Exception as e:
                    logger.warning(f"Laya decision failed, using first unvisited: {e}")
                    chosen_key = "job_0"

                logger.info(f"Step {step}: Laya selected '{chosen_key}' -> {criteria.get(chosen_key, '')[:50]}")

                if chosen_key == "scroll_down" or chosen_key not in candidate_map:
                    page.evaluate("window.scrollBy(0, 1000)")
                    page.wait_for_timeout(1500)
                    continue

                selected_candidate = candidate_map[chosen_key]
                job_url = selected_candidate["href"]
                self.visited_urls.add(job_url)

                try:
                    logger.info(f"Opening job: {job_url}")
                    page.goto(job_url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(1500)

                    job = JobExtractor.extract_from_page(page, job_url, fallback_text=selected_candidate["text"])
                    if job and not any(j.id == job.id for j in harvested_jobs):
                        harvested_jobs.append(job)
                        logger.info(f"[+] Successfully harvested: '{job.title}' at {job.company}")
                        if on_job_found:
                            on_job_found(job)
                except Exception as e:
                    logger.warning(f"Failed extracting job at {job_url}: {e}")

                try:
                    page.goto(start_url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(1000)
                except Exception:
                    pass

            if not attached_to_user_browser:
                context.close()

        return harvested_jobs
