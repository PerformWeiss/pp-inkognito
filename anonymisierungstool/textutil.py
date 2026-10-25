import re


def term_regex(terms, flags=0):
    """Ein Regex, der alle Begriffe als ganze Wörter findet (längste zuerst)."""
    terms = sorted({t for t in terms if t}, key=len, reverse=True)
    if not terms:
        return None
    body = "|".join(re.escape(t) for t in terms)
    return re.compile(r"(?<!\w)(?:%s)(?!\w)" % body, flags)


def count_occurrences(text, term):
    rx = term_regex([term])
    return len(rx.findall(text)) if rx else 0


def replace_in_text(text, regex, mapping):
    if regex is None:
        return text
    return regex.sub(lambda m: mapping[m.group(0)], text)
