"""Address cleaning + bad-address flagging, generalized from the original
tng_ticket_process pipeline into pure, stateless functions (no network calls,
no local file paths, no interactive prompts)."""
import csv
import io
import json
import re

DEFAULT_LOCALITY_KEYWORDS = [
    "jalan", "jln", "lorong", "lrg", "lengkok", "persiaran", "psn",
    "taman", "tmn", "kampung", "kg", "bandar", "seksyen", "sek",
    "kawasan", "lot", "batu", "susuran", "solok", "bukit", "lebuh",
    "lebuhraya", "medan", "pekan", "pangsapuri", "apartment", "apt",
    "block", "blok", "tingkat",
]


def clean_postcode(postcode) -> str:
    """Remove any alphabet and special characters from postcode, keeping digits only."""
    if not isinstance(postcode, str):
        return postcode
    return re.sub(r"[^0-9]", "", postcode)


def clean_address(address, postcode_cleaned: str) -> str:
    """
    Clean a raw address string by applying the following rules in order:
      1. Remove special characters except alphabets, numbers, '-', '/', '\\'.
      2. Lowercase everything.
      3. Remove postcode value (already cleaned) from address.
      4. Remove duplicate words (preserving first occurrence).
      5. Strip leading/trailing spaces and collapse extra internal spaces.
    """
    if not isinstance(address, str):
        return address

    address = re.sub(r"[^a-zA-Z0-9\-/\\\ ]", " ", address)
    address = address.lower()

    if isinstance(postcode_cleaned, str) and postcode_cleaned:
        escaped = re.escape(postcode_cleaned)
        address = re.sub(r"\b" + escaped + r"\b", " ", address)

    seen = []
    seen_set = set()
    for word in address.split():
        if word.lower() not in seen_set:
            seen.append(word)
            seen_set.add(word.lower())
    address = " ".join(seen)

    address = re.sub(r" {2,}", " ", address).strip()
    return address


def load_locality_keywords(raw_bytes: bytes, filename: str) -> set:
    """Load locality keywords from an uploaded JSON or CSV file's raw bytes."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    text = raw_bytes.decode("utf-8-sig")

    if ext == "json":
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError("JSON keywords file must be a flat array, e.g. [\"jalan\", ...]")
        return {kw.strip().lower() for kw in data if isinstance(kw, str) and kw.strip()}

    if ext == "csv":
        sample = text[:1024]
        has_header = csv.Sniffer().has_header(sample)
        reader = csv.reader(io.StringIO(text))
        if has_header:
            next(reader, None)
        return {row[0].strip().lower() for row in reader if row and row[0].strip()}

    raise ValueError(f"Unsupported keywords file format: '.{ext}'. Use .json or .csv")


def has_alphanumeric_token(tokens: list) -> bool:
    """Return True if any token is a combo of letters+digits (e.g. 'a23-01', 'b2')."""
    for token in tokens:
        core = re.sub(r"[-/\\]", "", token)
        if re.search(r"[a-zA-Z]", core) and re.search(r"[0-9]", core):
            return True
    return False


def has_pure_number_token(tokens: list) -> bool:
    """Return True if any token is purely numeric (after stripping hyphens/slashes)."""
    for token in tokens:
        core = re.sub(r"[-/\\]", "", token)
        if re.fullmatch(r"[0-9]+", core):
            return True
    return False


def is_all_numbers(tokens: list) -> bool:
    """Return True if EVERY token is purely numeric."""
    return all(re.fullmatch(r"[0-9]+", re.sub(r"[-/\\]", "", t)) for t in tokens)


def get_flags(address, locality_keywords: set) -> list:
    """
    Evaluate an address string against all flagging rules.
    Returns a list of flag codes that apply (empty = address is clean).

    Flag codes
    ----------
    FLAG_0 : blank, null, or whitespace-only address
    FLAG_1 : 3 or fewer tokens
    FLAG_2 : 4-5 tokens with no numbers and no alphanumeric token (e.g. a23-01)
    FLAG_3 : every token is a plain number
    FLAG_4 : 4-5 tokens but none contains a locality keyword (substring match)
    """
    if not isinstance(address, str) or not address.strip():
        return ["FLAG_0"]

    tokens = address.split()
    n = len(tokens)
    flags = []

    if n <= 3:
        flags.append("FLAG_1")

    if is_all_numbers(tokens):
        flags.append("FLAG_3")

    if n in (4, 5):
        has_number = has_pure_number_token(tokens)
        has_alphanum = has_alphanumeric_token(tokens)
        if not has_number and not has_alphanum:
            flags.append("FLAG_2")

    if n in (4, 5):
        found = any(
            kw in token.lower()
            for token in tokens
            for kw in locality_keywords
        )
        if not found:
            flags.append("FLAG_4")

    return flags


def sniff_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t|;").delimiter
    except csv.Error:
        return ","
