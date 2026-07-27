import json
import re
import sqlite3
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
CHROMA_SQLITE_PATH = BACKEND_DIR / "chroma_db" / "chroma.sqlite3"
OUTPUT_PATH = BACKEND_DIR / "data" / "articles_index.json"

EMBEDDED_ARTICLE_PATTERN = re.compile(
    r"(?P<prefix>\d+\[|\d+\*)?"
    r"(?P<number>\d{1,4}[A-Z])\.\s+"
    r"(?P<title>[^—\n]+?)\s*\.?—"
)


def article_sort_key(row: dict) -> tuple[int, str]:
    number = str(row.get("number", ""))
    digits = ""
    suffix = ""
    for char in number:
        if char.isdigit():
            digits += char
        else:
            suffix += char
    return (int(digits) if digits else 9999, suffix)


def normalize_embedded_number(raw_number: str, parent_number: str) -> str:
    raw_number = str(raw_number).strip().upper()
    parent_digits = "".join(char for char in str(parent_number) if char.isdigit())
    match = re.fullmatch(r"(\d+)([A-Z])", raw_number)
    if not match:
        return raw_number

    digits, suffix = match.groups()
    # PDF footnote markers sometimes merge into the Article number, e.g.
    # "132A" inside Article 32 means footnote 1 + Article 32A.
    if parent_digits and len(digits) > len(parent_digits) and digits.endswith(parent_digits):
        digits = parent_digits
    return f"{digits}{suffix}"


def clean_title(raw_title: str) -> str:
    return re.sub(r"\s+", " ", raw_title.strip(" []\n\t."))


def split_embedded_articles(rows: list[dict]) -> list[dict]:
    split_rows = []
    seen_numbers = set()

    for row in rows:
        parent_number = str(row.get("number", "")).strip().upper()
        content = str(row.get("content", "")).strip()
        embedded_matches = []

        for match in EMBEDDED_ARTICLE_PATTERN.finditer(content):
            embedded_number = normalize_embedded_number(match.group("number"), parent_number)
            if embedded_number == parent_number:
                continue
            embedded_matches.append((match, embedded_number))

        if not embedded_matches:
            if parent_number not in seen_numbers:
                split_rows.append(row)
                seen_numbers.add(parent_number)
            continue

        first_match = embedded_matches[0][0]
        parent_content = content[: first_match.start()].rstrip(" [\n\t")
        if parent_number not in seen_numbers:
            split_rows.append({**row, "content": parent_content})
            seen_numbers.add(parent_number)

        for index, (match, embedded_number) in enumerate(embedded_matches):
            if embedded_number in seen_numbers:
                continue

            body_start = match.end()
            body_end = embedded_matches[index + 1][0].start() if index + 1 < len(embedded_matches) else len(content)
            body = content[body_start:body_end].strip(" []\n\t")
            title = clean_title(match.group("title"))
            embedded_content = f"Article {embedded_number}: {title}\n{row.get('part', '')}\n\n{body}".strip()

            split_rows.append(
                {
                    "number": embedded_number,
                    "title": title,
                    "part": row.get("part", ""),
                    "type": "article",
                    "content": embedded_content,
                }
            )
            seen_numbers.add(embedded_number)

    split_rows.sort(key=article_sort_key)
    return split_rows


def export_articles_index() -> None:
    if not CHROMA_SQLITE_PATH.exists():
        raise FileNotFoundError(f"Chroma SQLite database not found: {CHROMA_SQLITE_PATH}")

    query = """
        SELECT
            number_meta.string_value AS number,
            title_meta.string_value AS title,
            part_meta.string_value AS part,
            type_meta.string_value AS type,
            document_meta.string_value AS content
        FROM embedding_metadata AS number_meta
        JOIN embedding_metadata AS title_meta
            ON title_meta.id = number_meta.id AND title_meta.key = 'title'
        JOIN embedding_metadata AS part_meta
            ON part_meta.id = number_meta.id AND part_meta.key = 'part'
        JOIN embedding_metadata AS type_meta
            ON type_meta.id = number_meta.id AND type_meta.key = 'type'
        JOIN embedding_metadata AS document_meta
            ON document_meta.id = number_meta.id AND document_meta.key = 'chroma:document'
        WHERE number_meta.key = 'number'
            AND type_meta.string_value = 'article'
        ORDER BY CAST(number_meta.string_value AS INTEGER), number_meta.string_value
    """

    with sqlite3.connect(CHROMA_SQLITE_PATH) as connection:
        connection.row_factory = sqlite3.Row
        rows = [dict(row) for row in connection.execute(query).fetchall()]

    rows = split_embedded_articles(rows)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Exported {len(rows)} articles to {OUTPUT_PATH}")


if __name__ == "__main__":
    export_articles_index()
