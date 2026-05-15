"""
LinkedIn Auto-Apply Bot (Playwright) — 2026 Search-List Strategy (v3 FIXED)
============================================================================

ROOT CAUSES FIXED in this version
-----------------------------------
1. _fill_application returned False immediately because LinkedIn's "Next" button
   aria-label timing caused every click attempt to fail → now uses robust
   _advance_step() with DOM-mutation detection and 3× retry.

2. Phone widget: LinkedIn uses a country-code <select> + number <input> combo.
   Now correctly targets only the number sub-field.

3. LinkedIn custom typeahead/combobox dropdowns (div[role='combobox']) were
   ignored — now handled by _handle_typeahead_dropdowns().

4. Label detection used only label[for=id] — LinkedIn also wraps labels in
   <span> and uses aria-labelledby.  Now uses _get_field_context() which checks
   multiple strategies.

5. No retry on missed clicks — _advance_step() retries up to 3× per step.

6. Form filler had no profile data (name, city, title). Now accepts a full
   UserProfile dataclass and fills any field LinkedIn asks.

7. Modal detection updated to 2026 LinkedIn DOM selectors.

Strategy (unchanged):
  1. Build search URL with f_AL=true (Easy Apply filter)
  2. Scroll list to load all cards
  3. For each card → click it → wait for right pane → click Easy Apply
  4. Fill multi-step form → submit or close (safe mode)
"""

import sys
import io
import argparse
import os
import platform
import re
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import json

# ── Windows UTF-8 ─────────────────────────────────────────────────────────────
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, Page

# ── Logging ───────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def log_error(msg: str) -> None:
    log(f"[ERROR] {msg}\n{traceback.format_exc()}")


# ── User profile ──────────────────────────────────────────────────────────────

@dataclass
class UserProfile:
    """Holds all data needed to auto-fill LinkedIn Easy Apply forms."""
    email:            str = ""
    phone:            str = ""
    first_name:       str = ""
    last_name:        str = ""
    full_name:        str = ""
    city:             str = ""
    current_title:    str = ""
    years_experience: str = "2"
    linkedin_url:     str = ""
    github_url:       str = ""
    portfolio_url:    str = ""
    salary_expected:  str = "0"
    notice_period:    str = "30"
    requires_visa:    str = "No"
    authorized:       str = "Yes"
    gender:           str = ""
    pronouns:         str = ""
    veteran_status:   str = "I am not a protected veteran"
    disability:       str = "I don't wish to answer"


# ── Selector constants ─────────────────────────────────────────────────────────

CARD_SELECTORS = [
    "li.jobs-search-results__list-item",
    "li[data-occludable-job-id]",
    ".job-card-container",
    ".jobs-search-results-list li",
    "ul.jobs-search-results__list > li",
    "li.ember-view.jobs-search-results__list-item",
    ".scaffold-layout__list-item",
]

EASY_APPLY_SELECTORS = [
    "button[aria-label*='Easy Apply']",
    "button[aria-label*='easy apply']",
    "button.jobs-apply-button",
    "button:has-text('Easy Apply')",
    "button:has-text('Easy apply')",
    ".jobs-apply-button--top-card",
    "div.jobs-apply-button-container button",
    ".artdeco-button--primary:has-text('Easy Apply')",
    ".artdeco-button--primary:has-text('Apply')",
]

# Updated for 2026 LinkedIn DOM
MODAL_SELECTORS = [
    ".jobs-easy-apply-modal",
    "[data-test-modal]",
    ".artdeco-modal__content",
    "[aria-modal='true']",
    "[role='dialog']",
    ".jobs-easy-apply-content",
]

NEXT_BUTTON_SELECTORS = [
    'button[aria-label="Continue to next step"]',
    'button[aria-label*="Continue to next step"]',
    'button[aria-label*="Next"]',
    'button[aria-label*="Continue"]',
    'button.artdeco-button--primary:has-text("Next")',
    'button.artdeco-button--primary:has-text("Continue")',
    'button:has-text("Next")',
    'button:has-text("Continue")',
    '[data-easy-apply-next-button-id="next"]',
    '[data-easy-apply-next-button-id="continue"]',
]

REVIEW_BUTTON_SELECTORS = [
    'button[aria-label*="Review your application"]',
    'button[aria-label*="Review"]',
    'button:has-text("Review your application")',
    'button:has-text("Review")',
    '[data-easy-apply-next-button-id="review-application"]',
]

SUBMIT_BUTTON_SELECTORS = [
    'button[aria-label="Submit application"]',
    'button[aria-label*="Submit application"]',
    'button:has-text("Submit application")',
    'button[data-easy-apply-next-button-id="submit-application"]',
    'button.artdeco-button--primary:has-text("Submit")',
]

# ── Generic helpers ───────────────────────────────────────────────────────────

def _first(page: Page, selectors: list, timeout: int = 5000):
    """Return first visible element matching any selector, or None."""
    for sel in selectors:
        try:
            el = page.wait_for_selector(sel, timeout=timeout, state="visible")
            if el:
                return el
        except Exception:
            pass
    return None


def _click_first(page: Page, selectors: list, timeout: int = 5000) -> bool:
    el = _first(page, selectors, timeout)
    if el:
        try:
            el.scroll_into_view_if_needed()
            el.click()
            return True
        except Exception:
            pass
    return False


def _safe_text(el) -> str:
    try:
        return (el.inner_text() or "").strip()
    except Exception:
        return ""


def _safe_attr(el, attr: str) -> str:
    try:
        return (el.get_attribute(attr) or "").strip()
    except Exception:
        return ""


def _get_field_context(page: Page, el) -> str:
    """
    Build a context string for a form element using multiple label strategies:
    - label[for=id]
    - aria-label attribute
    - aria-labelledby → text of referenced element
    - placeholder
    - nearest legend (fieldset)
    - parent div text content
    """
    parts = []
    try:
        el_id       = _safe_attr(el, "id")
        aria_label  = _safe_attr(el, "aria-label").lower()
        placeholder = _safe_attr(el, "placeholder").lower()
        parts.append(aria_label)
        parts.append(placeholder)

        if el_id:
            lbl = page.query_selector(f'label[for="{el_id}"]')
            if lbl:
                parts.append(_safe_text(lbl).lower())

        aria_labelledby = _safe_attr(el, "aria-labelledby")
        if aria_labelledby:
            for ref_id in aria_labelledby.split():
                ref = page.query_selector(f"#{ref_id}")
                if ref:
                    parts.append(_safe_text(ref).lower())

        # Walk up to find a label/legend/heading nearby
        parent = el.evaluate_handle("el => el.closest('fieldset,div,li,section')")
        if parent:
            try:
                p_el = parent.as_element()
                if p_el:
                    legend = p_el.query_selector("legend, label, h3, h4, span.t-bold")
                    if legend:
                        parts.append(_safe_text(legend).lower())
            except Exception:
                pass
    except Exception:
        pass
    return " ".join(parts)


# ── Bot class ─────────────────────────────────────────────────────────────────

class LinkedInBot:
    """LinkedIn Easy Apply bot — 2026 search-list-first strategy, full form-filler."""

    def __init__(self, profile: UserProfile):
        self.profile  = profile
        self._pw      = None
        self.browser  = None
        self.page     = None
        self.applied: List[Dict] = []
        self._debug_dir = Path("data/output")
        self._debug_dir.mkdir(parents=True, exist_ok=True)

    # ── Browser lifecycle ─────────────────────────────────────────────────────

    def start(self) -> bool:
        log("[BROWSER] Launching Chromium (headed)…")
        try:
            self._pw = sync_playwright().start()
            IS_WIN   = platform.system() == "Windows"
            headless = os.environ.get("LINKEDIN_BOT_HEADLESS", "0") == "1"

            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--disable-infobars",
                "--disable-extensions",
            ]
            if not IS_WIN:
                launch_args.append("--no-sandbox")

            self.browser = self._pw.chromium.launch(
                headless=headless,
                slow_mo=50,
                args=launch_args,
            )
            ctx = self.browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            self.page = ctx.new_page()
            self.page.set_default_timeout(15_000)
            log("[BROWSER] Ready")
            return True
        except Exception:
            log_error("Browser launch failed — run: playwright install chromium")
            return False

    def close(self) -> None:
        for obj, name in [(self.browser, "browser"), (self._pw, "playwright")]:
            try:
                if obj:
                    if name == "browser":
                        self.browser.close()
                        self.browser = None
                    else:
                        self._pw.stop()
                        self._pw = None
            except Exception as e:
                log(f"[WARN] {name} close: {e}")

    # ── Login ─────────────────────────────────────────────────────────────────

    def login(self) -> bool:
        log("[LOGIN] → https://www.linkedin.com/login")
        try:
            self.page.goto("https://www.linkedin.com/login",
                           wait_until="domcontentloaded", timeout=60_000)
            time.sleep(2)

            email_sel = ["#username", "input[name='session_key']", "input[type='email']"]
            pass_sel  = ["#password", "input[name='session_password']", "input[type='password']"]
            for sel in email_sel:
                try:
                    el = self.page.query_selector(sel)
                    if el and el.is_visible():
                        el.fill(self.profile.email)
                        break
                except Exception:
                    pass
            for sel in pass_sel:
                try:
                    el = self.page.query_selector(sel)
                    if el and el.is_visible():
                        el.fill(self.profile.password)
                        break
                except Exception:
                    pass
            _click_first(self.page, ['button[type="submit"]', '.btn__primary--large'])
            log("[LOGIN] Submitted — waiting…")

            for _ in range(90):
                time.sleep(1)
                url = self.page.url
                if any(k in url for k in ["/feed", "/jobs", "/mynetwork", "/messaging"]):
                    log(f"[LOGIN] ✅ Logged in ({url})")
                    return True
                if any(k in url for k in ["checkpoint", "captcha", "challenge"]):
                    log("[LOGIN] ⚠️  CAPTCHA — complete it in the browser (3 min timeout)")
                    for _ in range(180):
                        time.sleep(1)
                        if any(k in self.page.url for k in ["/feed", "/jobs", "/mynetwork"]):
                            log("[LOGIN] ✅ Verification done")
                            return True
                    log("[LOGIN] Verification timed out")
                    return False
                if "authwall" in url:
                    log("[LOGIN] Blocked — check credentials")
                    return False

            log(f"[LOGIN] Timed out — URL: {self.page.url}")
            return False
        except Exception:
            log_error("Login error")
            return False

    # ── Search & Apply loop ───────────────────────────────────────────────────

    def search_and_apply(
        self,
        keywords: str,
        location: str,
        resume_path: str,
        max_applications: int = 10,
        auto_submit: bool = False,
    ) -> Tuple[int, int]:
        from urllib.parse import quote_plus
        kw  = quote_plus(keywords)
        loc = quote_plus(location) if location else ""

        url = f"https://www.linkedin.com/jobs/search/?keywords={kw}&f_AL=true&sortBy=R"
        if loc:
            url += f"&location={loc}"

        log(f"[SEARCH] → {url}")
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        except Exception as e:
            log(f"[SEARCH] Navigation failed: {e}")
            return 0, 0

        time.sleep(3)
        self._dismiss_modals()

        applied  = 0
        skipped  = 0
        page_num = 0

        while applied < max_applications:
            page_num += 1
            log(f"\n[PAGE {page_num}] Collecting job cards…")
            self._scroll_list_panel()
            cards = self._get_job_cards()
            if not cards:
                log("[SEARCH] No job cards found — stopping")
                break

            log(f"[PAGE {page_num}] Found {len(cards)} job cards")

            for idx, card in enumerate(cards):
                if applied >= max_applications:
                    break

                job_title, company, job_id = self._click_card_get_info(card, idx)
                if not job_title:
                    log(f"  [{idx+1}] Could not open card — skipping")
                    skipped += 1
                    continue

                log(f"\n  [{idx+1}/{len(cards)}] {job_title} @ {company}  (ID: {job_id})")

                easy_btn = self._find_easy_apply_in_pane()
                if not easy_btn:
                    log(f"  [SKIP] No Easy Apply button found")
                    skipped += 1
                    continue

                if self._already_applied():
                    log(f"  [SKIP] Already applied")
                    skipped += 1
                    continue

                log(f"  [CLICK] Easy Apply → clicking…")
                try:
                    easy_btn.scroll_into_view_if_needed()
                    time.sleep(0.4)
                    easy_btn.click()
                    time.sleep(2.5)
                except Exception as e:
                    log(f"  [SKIP] Click failed: {e}")
                    skipped += 1
                    continue

                # Wait for modal
                modal = _first(self.page, MODAL_SELECTORS, timeout=8000)
                if not modal:
                    log(f"  [SKIP] Easy Apply modal did not open")
                    # Debug: dump visible buttons
                    self._debug_buttons("no_modal")
                    skipped += 1
                    continue

                log(f"  [MODAL] ✅ Modal opened — beginning form fill")

                success = self._fill_application(
                    title=job_title,
                    company=company,
                    resume_path=resume_path,
                    auto_submit=auto_submit,
                )

                if success:
                    applied += 1
                    self.applied.append({
                        "job_id":    job_id,
                        "title":     job_title,
                        "company":   company,
                        "applied_at": datetime.now().isoformat(),
                        "submitted": auto_submit,
                    })
                    log(f"  ✅ Applied! (Total: {applied})")
                else:
                    skipped += 1
                    log(f"  [SKIP] Form fill failed (Total skipped: {skipped})")

                time.sleep(2)

            if applied < max_applications:
                if not self._go_next_page():
                    log("\n[SEARCH] No more pages — done")
                    break
                time.sleep(3)

        return applied, skipped

    # ── Card helpers ──────────────────────────────────────────────────────────

    def _scroll_list_panel(self) -> None:
        for sel in [".jobs-search-results-list", ".scaffold-layout__list", ".jobs-search-results__list"]:
            try:
                panel = self.page.query_selector(sel)
                if panel:
                    for _ in range(5):
                        self.page.evaluate("(el) => el.scrollBy(0, 800)", panel)
                        time.sleep(0.7)
                    return
            except Exception:
                pass
        for _ in range(4):
            self.page.evaluate("window.scrollBy(0, 600)")
            time.sleep(0.7)
        self.page.evaluate("window.scrollTo(0, 0)")

    def _get_job_cards(self) -> list:
        for sel in CARD_SELECTORS:
            try:
                cards = self.page.query_selector_all(sel)
                if cards:
                    log(f"  [CARDS] '{sel}' → {len(cards)} cards")
                    return cards
            except Exception:
                pass
        try:
            cards = self.page.query_selector_all("[data-job-id], [data-occludable-job-id]")
            if cards:
                return cards
        except Exception:
            pass
        return []

    def _click_card_get_info(self, card, idx: int):
        job_id = ""
        try:
            job_id = (
                card.get_attribute("data-job-id") or
                card.get_attribute("data-occludable-job-id") or ""
            )
            if not job_id:
                urn = card.get_attribute("data-entity-urn") or ""
                m = re.search(r"jobPosting:(\d+)", urn)
                if m:
                    job_id = m.group(1)
        except Exception:
            pass

        try:
            card.scroll_into_view_if_needed()
            time.sleep(0.3)
            card.click()
            time.sleep(2.5)
        except Exception as e:
            log(f"    [WARN] Card click failed: {e}")
            return "", "", ""

        title = self._get_detail_text([
            ".job-details-jobs-unified-top-card__job-title h1",
            ".job-details-jobs-unified-top-card__job-title",
            "h1.jobs-unified-top-card__job-title",
            ".jobs-unified-top-card__job-title",
            ".job-details h1",
            "h1.t-24",
            "h1",
        ])
        company = self._get_detail_text([
            ".job-details-jobs-unified-top-card__company-name",
            "a.job-details-jobs-unified-top-card__company-name",
            ".jobs-unified-top-card__company-name",
            "a.jobs-unified-top-card__company-name",
            ".job-details-jobs-unified-top-card__primary-description-container a",
        ])
        return title or f"Job {job_id}", company or "Unknown", job_id

    def _get_detail_text(self, selectors: list) -> str:
        for sel in selectors:
            try:
                el = self.page.query_selector(sel)
                if el and el.is_visible():
                    t = el.inner_text().strip()
                    if t:
                        return t
            except Exception:
                pass
        return ""

    # ── Find Easy Apply button ────────────────────────────────────────────────

    def _find_easy_apply_in_pane(self):
        for sel in EASY_APPLY_SELECTORS:
            try:
                el = self.page.wait_for_selector(sel, timeout=4000, state="visible")
                if el:
                    txt  = _safe_text(el).lower()
                    aria = _safe_attr(el, "aria-label").lower()
                    if "company site" in txt or "company site" in aria:
                        log("  [INFO] External apply — skipping")
                        return None
                    if "applied" in aria and "easy apply" not in aria:
                        log("  [INFO] Already-applied indicator")
                        return None
                    return el
            except Exception:
                pass

        # Scan all buttons
        try:
            for btn in self.page.query_selector_all("button"):
                try:
                    if not btn.is_visible():
                        continue
                    txt  = _safe_text(btn).lower()
                    aria = _safe_attr(btn, "aria-label").lower()
                    full = txt + " " + aria
                    if "easy apply" in full and "company site" not in full:
                        return btn
                except Exception:
                    pass
        except Exception:
            pass

        self._debug_buttons("no_easy_apply")
        return None

    def _already_applied(self) -> bool:
        try:
            txt = self.page.inner_text("body").lower()
            return "you've already applied" in txt or "already applied" in txt
        except Exception:
            return False

    # ── Pagination ────────────────────────────────────────────────────────────

    def _go_next_page(self) -> bool:
        try:
            nxt = _first(self.page, [
                'button[aria-label="View next page"]',
                'button[aria-label*="next"]',
                ".artdeco-pagination__button--next",
            ], timeout=3000)
            if nxt and nxt.is_enabled():
                nxt.click()
                time.sleep(3)
                return True
        except Exception:
            pass
        return False

    # ── Multi-step form filler ────────────────────────────────────────────────

    def _fill_application(
        self,
        title: str,
        company: str,
        resume_path: str,
        auto_submit: bool,
    ) -> bool:
        MAX_STEPS = 40
        uploaded_resume = False
        step_hash_prev  = ""

        for step in range(1, MAX_STEPS + 1):
            time.sleep(1.5)
            log(f"    [Step {step}]")

            # ── Confirmation text? ──
            body_text = ""
            try:
                body_text = self.page.inner_text("body").lower()
            except Exception:
                pass

            if any(x in body_text for x in [
                "application sent", "application submitted",
                "successfully applied", "your application was sent",
            ]):
                log(f"    [OK] ✅ Application confirmed!")
                return True

            # ── Detect stall ──
            try:
                cur_hash = str(hash(self.page.content()))
                if cur_hash == step_hash_prev and step > 2:
                    log("    [WARN] DOM unchanged — possible stall, retrying fill")
                step_hash_prev = cur_hash
            except Exception:
                pass

            # ── 1. Upload resume ──
            if not uploaded_resume and resume_path and Path(resume_path).exists():
                uploaded_resume = self._upload_resume(resume_path)

            # ── 2. Fill all form fields ──
            self._fill_all_fields()

            # ── 3. Check for Submit button ──
            submit = _first(self.page, SUBMIT_BUTTON_SELECTORS, timeout=2000)
            if submit and submit.is_visible() and submit.is_enabled():
                log("    [SUBMIT] Submit button found!")
                if auto_submit:
                    try:
                        submit.scroll_into_view_if_needed()
                        submit.click()
                        time.sleep(3)
                        log(f"    [OK] ✅ Submitted: {title} @ {company}")
                        return True
                    except Exception as e:
                        log(f"    [WARN] Submit click error: {e}")
                        return False
                else:
                    log(f"    [SAFE] ✅ Form complete (auto-submit OFF) — {title} @ {company}")
                    self._close_modal()
                    return True

            # ── 4. Try Review button ──
            review = _first(self.page, REVIEW_BUTTON_SELECTORS, timeout=2000)
            if review and review.is_visible() and review.is_enabled():
                log("      >> Clicking Review…")
                if self._safe_click_and_wait(review):
                    continue

            # ── 5. Try Next / Continue button ──
            advanced = self._advance_step()
            if advanced:
                continue

            # ── No action possible ──
            log("    [STOP] Could not advance — dumping buttons and closing")
            self._debug_buttons(f"step_{step}")
            self._close_modal()
            return False

        log("    [WARN] Max steps reached")
        self._close_modal()
        return False

    def _advance_step(self) -> bool:
        """Find and click Next/Continue with up to 3 retries and DOM-change detection."""
        for attempt in range(3):
            btn = _first(self.page, NEXT_BUTTON_SELECTORS, timeout=3000)
            if not btn:
                return False
            if not btn.is_visible() or not btn.is_enabled():
                time.sleep(0.5)
                continue

            txt = _safe_text(btn)
            log(f"      >> Clicking: '{txt}' (attempt {attempt+1})")

            try:
                pre_html = self.page.content()
                btn.scroll_into_view_if_needed()
                btn.click()

                # Wait for DOM change (up to 4 s)
                waited = 0
                while waited < 4000:
                    time.sleep(0.3)
                    waited += 300
                    try:
                        new_html = self.page.content()
                        if new_html != pre_html:
                            log(f"      >> DOM changed after {waited}ms ✅")
                            return True
                    except Exception:
                        break
                else:
                    log(f"      >> DOM unchanged after click (attempt {attempt+1})")
            except Exception as e:
                log(f"      [WARN] Click error: {e}")

            time.sleep(0.5)
        return False

    def _safe_click_and_wait(self, btn) -> bool:
        try:
            pre = self.page.content()
            btn.scroll_into_view_if_needed()
            btn.click()
            for _ in range(15):
                time.sleep(0.3)
                if self.page.content() != pre:
                    return True
        except Exception:
            pass
        return False

    # ── Resume upload ─────────────────────────────────────────────────────────

    def _upload_resume(self, resume_path: str) -> bool:
        try:
            file_inputs = self.page.query_selector_all('input[type="file"]')
            for fi in file_inputs:
                try:
                    if not fi.is_visible():
                        # Make visible via JS
                        self.page.evaluate(
                            "el => { el.style.display = 'block'; el.style.opacity = '1'; }", fi
                        )
                    fi.set_input_files(resume_path)
                    log(f"      >> Resume uploaded: {Path(resume_path).name}")
                    time.sleep(2)
                    return True
                except Exception as fe:
                    log(f"      [WARN] Upload attempt error: {fe}")
        except Exception:
            pass
        return False

    # ── Fill all visible form fields ──────────────────────────────────────────

    def _fill_all_fields(self) -> None:
        """Fill every fillable form element on the current step."""
        self._fill_phone_field()
        self._fill_text_inputs()
        self._fill_textareas()
        self._fill_native_selects()
        self._fill_radio_groups()
        self._fill_checkboxes()
        self._fill_typeahead_dropdowns()

    # ── Phone field ───────────────────────────────────────────────────────────

    def _fill_phone_field(self) -> None:
        """Handle LinkedIn's phone number combo: country-code select + number input."""
        phone_selectors = [
            'input[id*="phoneNumber"]',
            'input[name*="phone"]',
            'input[type="tel"]',
            'input[placeholder*="Phone"]',
            'input[placeholder*="phone"]',
            'input[placeholder*="Mobile"]',
            'input[aria-label*="Phone"]',
            'input[aria-label*="phone"]',
            'input[aria-label*="Mobile"]',
        ]
        for sel in phone_selectors:
            try:
                el = self.page.query_selector(sel)
                if el and el.is_visible() and el.is_enabled():
                    v = el.input_value()
                    if not v or not v.strip():
                        el.triple_click()
                        el.fill(self.profile.phone)
                        log(f"      >> Phone filled: {self.profile.phone}")
                    break
            except Exception:
                pass

    # ── Text / number inputs ──────────────────────────────────────────────────

    def _fill_text_inputs(self) -> None:
        p = self.profile
        try:
            for inp in self.page.query_selector_all(
                'input[type="text"], input[type="number"], '
                'input[type="tel"], input[type="email"], input:not([type])'
            ):
                try:
                    if not inp.is_visible() or not inp.is_enabled():
                        continue
                    if inp.get_attribute("type") == "file":
                        continue
                    curr = (inp.input_value() or "").strip()
                    if curr:
                        continue  # already filled

                    ctx = _get_field_context(self.page, inp)
                    val = self._map_context_to_value(ctx, inp, p)
                    if val:
                        inp.triple_click()
                        inp.fill(val)
                        log(f"      >> Filled text [{ctx[:40]}] = '{val}'")
                except Exception:
                    pass
        except Exception:
            pass

    def _map_context_to_value(self, ctx: str, inp, p: "UserProfile") -> str:
        """Return the right value based on field context keywords."""
        c = ctx.lower()

        # Name fields
        if any(w in c for w in ["first name", "firstname"]):
            return p.first_name or p.full_name.split()[0] if p.full_name else p.first_name
        if any(w in c for w in ["last name", "lastname", "surname"]):
            parts = p.full_name.split()
            return p.last_name or (parts[-1] if len(parts) > 1 else "")
        if any(w in c for w in ["full name", "your name"]) and "email" not in c:
            return p.full_name

        # Contact
        if any(w in c for w in ["email", "e-mail"]) and "name" not in c:
            return p.email
        if any(w in c for w in ["phone", "mobile", "contact", "tel"]):
            return p.phone

        # Location / address
        if any(w in c for w in ["city", "location", "address", "where"]) and "company" not in c:
            return p.city or "Open to relocation"

        # Experience / career
        if any(w in c for w in ["year", "experience", "exp", "years of", "how long", "worked"]):
            return p.years_experience
        if any(w in c for w in ["current title", "job title", "position", "role"]) and "company" not in c:
            return p.current_title or "Software Engineer"
        if any(w in c for w in ["current company", "employer", "organisation", "organization"]) and "position" not in c:
            return "Previous Company"

        # Salary / compensation
        if any(w in c for w in ["salary", "expected", "ctc", "lpa", "compensation", "package"]):
            return p.salary_expected

        # Notice / availability
        if any(w in c for w in ["notice", "period", "joining", "availability", "start"]):
            return p.notice_period

        # Links
        if any(w in c for w in ["linkedin", "linkedin.com", "profile"]):
            return p.linkedin_url or "https://linkedin.com"
        if any(w in c for w in ["github", "gitlab"]):
            return p.github_url or "https://github.com"
        if any(w in c for w in ["website", "portfolio", "url", "link"]):
            return p.portfolio_url or p.linkedin_url or "https://linkedin.com"

        # Visa / authorization
        if any(w in c for w in ["visa", "sponsorship"]):
            return "No"

        # Number-type fields: default 0
        try:
            if inp.get_attribute("type") == "number":
                return "0"
        except Exception:
            pass

        return ""

    # ── Textareas ─────────────────────────────────────────────────────────────

    def _fill_textareas(self) -> None:
        p = self.profile
        try:
            for ta in self.page.query_selector_all("textarea"):
                try:
                    if not ta.is_visible() or not ta.is_enabled():
                        continue
                    if (ta.input_value() or "").strip():
                        continue
                    ctx = _get_field_context(self.page, ta)
                    c   = ctx.lower()
                    if any(w in c for w in ["cover letter", "message", "additional", "summary", "describe"]):
                        val = (
                            f"I am excited about this opportunity at {p.city or 'your company'} "
                            f"and believe my {p.years_experience} year(s) of experience as "
                            f"{p.current_title or 'a software professional'} make me a strong candidate. "
                            "I look forward to contributing to your team."
                        )
                        ta.fill(val)
                        log(f"      >> Textarea filled: cover/summary")
                    elif any(w in c for w in ["why", "motivation", "interest", "passion"]):
                        ta.fill(
                            "I am passionate about contributing to your team and believe "
                            "my skills align well with this position."
                        )
                        log(f"      >> Textarea filled: motivation")
                except Exception:
                    pass
        except Exception:
            pass

    # ── Native <select> dropdowns ─────────────────────────────────────────────

    def _fill_native_selects(self) -> None:
        p = self.profile
        try:
            for sel_el in self.page.query_selector_all("select"):
                try:
                    if not sel_el.is_visible():
                        continue
                    curr = sel_el.input_value()
                    if curr:
                        continue
                    ctx = _get_field_context(self.page, sel_el)
                    c   = ctx.lower()

                    # Try to match a known answer
                    chosen = None
                    if any(w in c for w in ["authorized", "eligible", "legally", "work in"]):
                        chosen = self._select_option_by_text(sel_el, ["yes", "i am"])
                    elif any(w in c for w in ["visa", "sponsorship"]):
                        chosen = self._select_option_by_text(sel_el, ["no", "i do not"])
                    elif any(w in c for w in ["notice", "availability"]):
                        chosen = self._select_option_by_text(sel_el, ["30", "one month", "immediate"])
                    elif any(w in c for w in ["gender"]):
                        if p.gender:
                            chosen = self._select_option_by_text(sel_el, [p.gender])
                        else:
                            chosen = self._select_option_by_text(sel_el, ["prefer not", "decline"])
                    elif any(w in c for w in ["veteran"]):
                        chosen = self._select_option_by_text(sel_el, ["not a protected", "no", "decline"])
                    elif any(w in c for w in ["disability"]):
                        chosen = self._select_option_by_text(sel_el, ["don't wish", "decline", "no"])
                    elif any(w in c for w in ["pronouns"]):
                        chosen = self._select_option_by_text(sel_el, ["prefer not", "decline"])

                    if not chosen:
                        # Pick first non-placeholder option
                        self._select_first_valid_option(sel_el)
                except Exception:
                    pass
        except Exception:
            pass

    def _select_option_by_text(self, sel_el, keywords: list) -> bool:
        """Select <option> whose text matches any keyword. Returns True on success."""
        try:
            for opt in sel_el.query_selector_all("option"):
                v = _safe_attr(opt, "value")
                t = _safe_text(opt).lower()
                for kw in keywords:
                    if kw.lower() in t:
                        sel_el.select_option(value=v)
                        return True
        except Exception:
            pass
        return False

    def _select_first_valid_option(self, sel_el) -> None:
        try:
            for opt in sel_el.query_selector_all("option"):
                v = _safe_attr(opt, "value")
                t = _safe_text(opt).lower()
                skip = ("select", "choose", "please", "--", "pick", "", "none")
                if v and t and not any(w in t for w in skip):
                    sel_el.select_option(value=v)
                    return
        except Exception:
            pass

    # ── Radio buttons ─────────────────────────────────────────────────────────

    def _fill_radio_groups(self) -> None:
        p = self.profile
        try:
            for fs in self.page.query_selector_all("fieldset"):
                try:
                    radios = fs.query_selector_all('input[type="radio"]')
                    if not radios:
                        continue
                    if any(r.is_checked() for r in radios):
                        continue  # already has a selection

                    # Get question context from fieldset legend/label
                    legend = fs.query_selector("legend, .fb-form-element__label, label")
                    q_text = _safe_text(legend).lower() if legend else ""

                    # Smart radio selection
                    target_label = None
                    if any(w in q_text for w in ["authorized", "eligible", "legally allowed"]):
                        target_label = "yes"
                    elif any(w in q_text for w in ["sponsor", "visa"]):
                        target_label = "no"
                    elif any(w in q_text for w in ["remote", "hybrid", "onsite", "on-site"]):
                        target_label = "yes"
                    elif any(w in q_text for w in ["willing to travel", "travel"]):
                        target_label = "yes"
                    elif any(w in q_text for w in ["relocate", "relocation"]):
                        target_label = "yes"

                    clicked = False
                    if target_label:
                        for r in radios:
                            lbl = ""
                            r_id = _safe_attr(r, "id")
                            if r_id:
                                lbl_el = self.page.query_selector(f'label[for="{r_id}"]')
                                if lbl_el:
                                    lbl = _safe_text(lbl_el).lower()
                            val = _safe_attr(r, "value").lower()
                            if target_label in lbl or target_label in val:
                                r.click()
                                clicked = True
                                log(f"      >> Radio: '{q_text[:30]}' → '{target_label}'")
                                break

                    if not clicked:
                        # Fallback: click first enabled radio
                        for r in radios:
                            try:
                                if r.is_enabled():
                                    r.click()
                                    time.sleep(0.2)
                                    break
                            except Exception:
                                pass
                except Exception:
                    pass
        except Exception:
            pass

    # ── Checkbox agreements ───────────────────────────────────────────────────

    def _fill_checkboxes(self) -> None:
        try:
            for cb in self.page.query_selector_all('input[type="checkbox"]'):
                try:
                    if not cb.is_visible() or cb.is_checked():
                        continue
                    cb_id = _safe_attr(cb, "id")
                    label_txt = ""
                    if cb_id:
                        lbl = self.page.query_selector(f'label[for="{cb_id}"]')
                        if lbl:
                            label_txt = _safe_text(lbl).lower()
                    if any(w in label_txt for w in ["agree", "privacy", "terms", "consent", "confirm"]):
                        cb.click()
                        time.sleep(0.2)
                        log(f"      >> Checkbox agreed: '{label_txt[:40]}'")
                except Exception:
                    pass
        except Exception:
            pass

    # ── LinkedIn custom typeahead / combobox dropdowns ────────────────────────

    def _fill_typeahead_dropdowns(self) -> None:
        """
        Handle LinkedIn's JS-driven combobox selects.
        These are <input role='combobox'> or <div role='combobox'> elements
        that open a <ul> list on click.
        """
        p = self.profile
        try:
            combos = self.page.query_selector_all(
                "input[role='combobox'], div[role='combobox']"
            )
            for combo in combos:
                try:
                    if not combo.is_visible() or not combo.is_enabled():
                        continue
                    curr = ""
                    try:
                        curr = combo.input_value()
                    except Exception:
                        try:
                            curr = _safe_text(combo)
                        except Exception:
                            pass
                    if curr:
                        continue

                    ctx = _get_field_context(self.page, combo)
                    c   = ctx.lower()

                    # Determine what to type/select
                    search_text = None
                    if any(w in c for w in ["city", "location", "where"]):
                        search_text = p.city or "Remote"
                    elif any(w in c for w in ["authorized", "eligible", "legally"]):
                        search_text = "Yes"
                    elif any(w in c for w in ["sponsor", "visa"]):
                        search_text = "No"
                    elif any(w in c for w in ["notice", "period"]):
                        search_text = "30"
                    elif any(w in c for w in ["country"]):
                        search_text = "India"
                    elif any(w in c for w in ["gender"]):
                        search_text = "Prefer not to say"
                    elif any(w in c for w in ["veteran"]):
                        search_text = "No"
                    elif any(w in c for w in ["disability"]):
                        search_text = "No"

                    if search_text:
                        self._interact_typeahead(combo, search_text)
                except Exception:
                    pass
        except Exception:
            pass

    def _interact_typeahead(self, combo, search_text: str) -> bool:
        """Click a combobox, type search text, wait for options, select first match."""
        try:
            combo.click()
            time.sleep(0.5)
            try:
                combo.fill(search_text)
            except Exception:
                self.page.keyboard.type(search_text)
            time.sleep(1.0)

            # Look for dropdown list
            option_selectors = [
                ".typeahead-v2__option",
                ".basic-typeahead__selectable",
                "li[role='option']",
                ".search-typeahead-v2__hit",
                "div[role='option']",
                ".autocomplete__item",
            ]
            for opt_sel in option_selectors:
                try:
                    options = self.page.query_selector_all(opt_sel)
                    if options:
                        options[0].click()
                        log(f"      >> Typeahead selected for '{search_text}'")
                        time.sleep(0.5)
                        return True
                except Exception:
                    pass

            # Fallback: press Enter / Tab to confirm typed text
            self.page.keyboard.press("Enter")
            time.sleep(0.4)
            return False
        except Exception:
            return False

    # ── Modal close ───────────────────────────────────────────────────────────

    def _close_modal(self) -> None:
        try:
            btn = _first(self.page, [
                'button[aria-label="Dismiss"]',
                'button[aria-label="Close"]',
                'button.artdeco-modal__dismiss',
                '[data-test-modal-close-btn]',
            ], timeout=3000)
            if btn:
                btn.click()
                time.sleep(0.8)
                discard = _first(self.page, [
                    'button[data-test-dialog-primary-btn]',
                    'button:has-text("Discard")',
                    'button:has-text("Leave")',
                    '.artdeco-button--primary:has-text("Discard")',
                ], timeout=3000)
                if discard:
                    discard.click()
                    time.sleep(0.5)
        except Exception:
            pass

    def _dismiss_modals(self) -> None:
        for sel in [
            'button[aria-label="Dismiss"]',
            'button[aria-label="Close"]',
            'button.modal__dismiss',
            '[data-test-modal-close-btn]',
        ]:
            try:
                el = self.page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    time.sleep(0.4)
            except Exception:
                pass

    # ── Debug helpers ─────────────────────────────────────────────────────────

    def _debug_buttons(self, tag: str = "debug") -> None:
        """Log visible buttons and optionally capture a screenshot."""
        try:
            visible = []
            for b in self.page.query_selector_all("button"):
                try:
                    if b.is_visible():
                        t = _safe_text(b)
                        a = _safe_attr(b, "aria-label")
                        if t or a:
                            visible.append(f"'{t or a}'")
                except Exception:
                    pass
            log(f"    [DEBUG] Visible buttons ({tag}): {visible[:10]}")

            # Screenshot for post-mortem analysis
            try:
                ss_path = self._debug_dir / f"debug_{tag}_{datetime.now().strftime('%H%M%S')}.png"
                self.page.screenshot(path=str(ss_path))
                log(f"    [DEBUG] Screenshot → {ss_path}")
            except Exception:
                pass
        except Exception:
            pass

    # ── Main run ──────────────────────────────────────────────────────────────

    def run(
        self,
        keywords: str,
        location: str,
        resume_path: str,
        max_applications: int = 10,
        auto_submit: bool = False,
    ) -> None:
        log("=" * 60)
        log("  LinkedIn Easy Apply Bot  (2026 v3 — Full Form Filler)")
        log("=" * 60)
        log(f"  Keywords    : {keywords}")
        log(f"  Location    : {location or 'Any'}")
        log(f"  Max apps    : {max_applications}")
        log(f"  Auto-submit : {auto_submit}")
        log(f"  Resume      : {resume_path}")
        log(f"  Profile     : {self.profile.full_name} | {self.profile.city}")
        log("=" * 60)

        applied, skipped = self.search_and_apply(
            keywords=keywords,
            location=location,
            resume_path=resume_path,
            max_applications=max_applications,
            auto_submit=auto_submit,
        )

        log("\n" + "=" * 60)
        log("  SUMMARY")
        log("=" * 60)
        log(f"  Applied     : {applied}")
        log(f"  Skipped     : {skipped}")
        log("=" * 60)

        try:
            p = Path.cwd() / f"linkedin_applications_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            p.write_text(json.dumps(self.applied, indent=2), encoding="utf-8")
            log(f"\n[FILE] Log: {p}")
        except Exception:
            pass


# ── Entry point ───────────────────────────────────────────────────────────────

def run_bot(args) -> None:
    if not Path(args.resume).exists():
        log(f"[FATAL] Resume not found: {args.resume}")
        sys.exit(1)
    log(f"  [OK] Resume: {Path(args.resume).name}")

    # Build profile from CLI args
    full_name = args.full_name or f"{args.first_name or ''} {args.last_name or ''}".strip()
    profile = UserProfile(
        email=args.email,
        phone=args.phone,
        first_name=args.first_name or (full_name.split()[0] if full_name else ""),
        last_name=args.last_name or (full_name.split()[-1] if len(full_name.split()) > 1 else ""),
        full_name=full_name,
        city=args.city or "",
        current_title=args.current_title or "",
        years_experience=str(args.years_experience or 2),
        linkedin_url=args.linkedin_url or "",
        github_url=args.github_url or "",
        portfolio_url=args.portfolio_url or "",
        salary_expected=str(args.salary_expected or 0),
        notice_period=str(args.notice_period or 30),
        requires_visa=args.requires_visa or "No",
        authorized=args.authorized or "Yes",
    )
    # Attach password so login() can use it
    profile.password = args.password

    bot = LinkedInBot(profile)
    try:
        if not bot.start():
            log("[FATAL] Browser failed — run: playwright install chromium")
            sys.exit(1)

        if not bot.login():
            log("[FATAL] Login failed — check email/password")
            time.sleep(20)
            bot.close()
            sys.exit(1)

        bot.run(
            keywords=args.keywords,
            location=args.location,
            resume_path=args.resume,
            max_applications=args.max,
            auto_submit=args.auto_submit,
        )

    except KeyboardInterrupt:
        log("\n[STOP] Bot stopped by user")
    except Exception:
        log_error("Unexpected error")
    finally:
        bot.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="LinkedIn Easy Apply Bot (2026 v3)")
    # Required
    ap.add_argument("--email",            required=True)
    ap.add_argument("--password",         required=True)
    ap.add_argument("--keywords",         required=True)
    ap.add_argument("--resume",           required=True)
    ap.add_argument("--phone",            required=True)
    # Optional search
    ap.add_argument("--max",              type=int, default=5)
    ap.add_argument("--location",         default="")
    ap.add_argument("--auto-submit",      action="store_true")
    # Profile (for form filling)
    ap.add_argument("--full-name",        default="", dest="full_name")
    ap.add_argument("--first-name",       default="", dest="first_name")
    ap.add_argument("--last-name",        default="", dest="last_name")
    ap.add_argument("--city",             default="")
    ap.add_argument("--current-title",    default="", dest="current_title")
    ap.add_argument("--years-experience", type=int, default=2, dest="years_experience")
    ap.add_argument("--linkedin-url",     default="", dest="linkedin_url")
    ap.add_argument("--github-url",       default="", dest="github_url")
    ap.add_argument("--portfolio-url",    default="", dest="portfolio_url")
    ap.add_argument("--salary-expected",  default="0", dest="salary_expected")
    ap.add_argument("--notice-period",    default="30", dest="notice_period")
    ap.add_argument("--requires-visa",    default="No", dest="requires_visa")
    ap.add_argument("--authorized",       default="Yes")
    run_bot(ap.parse_args())