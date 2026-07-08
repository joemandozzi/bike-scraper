"""Frame-size extraction.

Every listing that matches a keyword is shown -- size is informational,
not a filter, by default (see `strict_size_filter` in config.yaml if you
want non-matching sizes dropped instead of just labeled).
"""
import re


def title_matches_keyword(title, keyword):
    """Craigslist's own search falls back to loosely-related or even
    cross-category results when a query has few exact hits (e.g. "GT GTB"
    can surface Ferrari parts or used cars). Require the literal keyword
    phrase to appear in the title so that noise gets dropped before we
    bother fetching each listing's detail page.
    """
    return keyword.strip().lower() in title.lower()


_LETTER_ALIASES = {
    "xs": "XS",
    "x-small": "XS",
    "xsmall": "XS",
    "extra small": "XS",
    "extra-small": "XS",
    "s": "S",
    "small": "S",
    "m": "M",
    "medium": "M",
    "l": "L",
    "large": "L",
    "xl": "XL",
    "x-large": "XL",
    "xlarge": "XL",
    "extra large": "XL",
    "extra-large": "XL",
}

# Explicit "NNcm" mention, e.g. "54cm" or "54 cm".
_CM_RE = re.compile(r"\b(\d{2})\s?cm\b", re.IGNORECASE)
# "size 52", "size: 52", "sz 52", "size S", "size Small"
_SIZE_KEYWORD_RE = re.compile(r"\bsiz(?:e|ing)?\s*[:\-]?\s*([A-Za-z0-9-]+)", re.IGNORECASE)
# Standalone single-letter abbreviations are case-sensitive (uppercase only)
# to cut down on false positives -- a lowercase "s"/"m"/"l" is far more
# likely to just be an ordinary word. Spelled-out words (Small, Medium, ...)
# don't have that ambiguity, so those are matched case-insensitively via the
# scoped inline flag below.
_LETTER_RE = re.compile(
    r"\b(XS|XL|S|M|L|(?i:Extra[- ]?Small|Extra[- ]?Large|X-?Large|Small|Medium|Large))\b"
)


def _normalize(token):
    token = token.strip()
    lower = token.lower()
    if lower in _LETTER_ALIASES:
        return _LETTER_ALIASES[lower]
    m = re.match(r"^(\d{2})\s?cm$", lower)
    if m:
        return m.group(1)
    if re.match(r"^\d{2}$", token):
        return token
    return None


def extract_size(frame_size_field, text):
    """Return a normalized size string ("52", "S", "XS", ...) found in the
    structured frame-size field or free text, or None if no size at all
    could be determined.
    """
    if frame_size_field:
        normalized = _normalize(frame_size_field)
        if normalized:
            return normalized

    haystacks = [frame_size_field, text]
    for haystack in haystacks:
        if not haystack:
            continue
        m = _CM_RE.search(haystack)
        if m:
            return m.group(1)
        m = _SIZE_KEYWORD_RE.search(haystack)
        if m:
            normalized = _normalize(m.group(1))
            if normalized:
                return normalized
        m = _LETTER_RE.search(haystack)
        if m:
            return _normalize(m.group(1))

    return None


def normalize_config_size(raw):
    """Normalize a size string from config.yaml the same way detected sizes
    are normalized, so config casing (e.g. "s" vs "S") doesn't silently fail
    to match. Falls back to the original token if it isn't a recognized
    form, rather than dropping it.
    """
    return _normalize(raw) or raw


def evaluate_size(frame_size_field, text, allowed_sizes):
    """Return (detected_size: str | None, in_target: bool | None).

    in_target is None when no size could be determined at all (so callers
    can distinguish "unknown" from "known and out of range").
    """
    detected = extract_size(frame_size_field, text)
    if detected is None:
        return None, None
    return detected, (detected in allowed_sizes)
