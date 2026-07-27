import json
import sqlite3
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
CHROMA_SQLITE_PATH = BACKEND_DIR / "chroma_db" / "chroma.sqlite3"
OUTPUT_PATH = BACKEND_DIR / "data" / "articles_index.json"


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

    rows.sort(key=article_sort_key)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Exported {len(rows)} articles to {OUTPUT_PATH}")


if __name__ == "__main__":
    export_articles_index()
