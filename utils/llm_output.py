import re


def extract_text(content) -> str:
    """Normalize an LLM .content value into a plain string.
    Some models (e.g. Gemini with thought signatures) return a list of
    content blocks like [{'type': 'text', 'text': ..., 'extras': {...}}]
    instead of a plain string. str(content) on that list stringifies the
    whole structure, which caused the SQL syntax error and the corrupted
    curated question.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content)


def clean_sql(content) -> str:
    """"Extract plain SQL text and strip markdown code fences if present."""
    text = extract_text(content).strip()
    match = re.search(r"```(?:sql)?\s*\n?(.*?)\n?```", text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text


def clean_python(content) -> str:
    """Extract plain python code and strip markdown code fences if present."""
    text = extract_text(content).strip()
    match = re.search(r"```(?:python|py)?\s*\n?(.*?)\n?```", text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text