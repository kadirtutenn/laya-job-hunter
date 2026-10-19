"""
DOM Perception: Extracts interactive elements and text from live browser pages in milliseconds.
No OCR, no screenshot overhead, 100% accurate labels.
"""

from __future__ import annotations

from typing import Any, Dict, List


EXTRACT_DOM_SCRIPT = """
() => {
    function isVisible(el) {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
            return false;
        }
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }

    function getElementText(el) {
        const directText = (el.innerText || el.textContent || '').trim();
        const ariaLabel = el.getAttribute('aria-label') || '';
        const title = el.getAttribute('title') || '';
        const placeholder = el.getAttribute('placeholder') || '';
        return (directText || ariaLabel || title || placeholder).replace(/\\s+/g, ' ').slice(0, 150);
    }

    // 1. Gather interactive candidates: buttons, links, inputs
    const candidateNodes = Array.from(document.querySelectorAll(
        'a[href], button, input, [role="button"], [role="link"], select, textarea, [data-job-id], article, .job-card, .job-item'
    ));

    const elements = [];
    let idx = 0;

    for (const node of candidateNodes) {
        if (!isVisible(node)) continue;
        const text = getElementText(node);
        if (!text && node.tagName.toLowerCase() !== 'input') continue;

        const tag = node.tagName.toLowerCase();
        const href = (tag === 'a' && node.href) ? node.href : '';
        const isJobCard = Boolean(
            href.includes('/job') || 
            href.includes('/career') || 
            href.includes('/position') || 
            node.className.toString().toLowerCase().includes('job') ||
            node.getAttribute('data-job-id')
        );

        // Assign a temporary unique selector attribute for exact clicking
        const refId = 'laya-act-' + (idx++);
        node.setAttribute('data-laya-ref', refId);

        elements.push({
            id: refId,
            tag: tag,
            text: text,
            role: node.getAttribute('role') || tag,
            href: href,
            is_job_card: isJobCard,
            selector: `[data-laya-ref="${refId}"]`
        });

        if (elements.length >= 80) break; // Keep action space compact and within context
    }

    // 2. Extract visible body text (for job descriptions / page context)
    const bodyClone = document.body.cloneNode(true);
    // Remove script, style, nav elements from text reading
    const unwanted = bodyClone.querySelectorAll('script, style, noscript, svg, nav, footer');
    unwanted.forEach(n => n.remove());
    const rawText = (bodyClone.innerText || '').replace(/\\n{3,}/g, '\\n\\n').trim();

    return {
        title: document.title,
        url: window.location.href,
        elements: elements,
        page_text: rawText.slice(0, 8000)
    };
}
"""


class DOMPerception:
    """Performs millisecond-level DOM analysis over Playwright Page."""

    @staticmethod
    def inspect(page: Any) -> Dict[str, Any]:
        """
        Evaluates the DOM script on the page and returns interactive elements & page text.
        """
        try:
            return page.evaluate(EXTRACT_DOM_SCRIPT)
        except Exception as e:
            return {
                "title": "",
                "url": getattr(page, "url", ""),
                "elements": [],
                "page_text": "",
                "error": str(e),
            }
