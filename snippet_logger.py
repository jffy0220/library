import os
import sys
import datetime as dt
import psycopg2

DB_CFG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "snippets_db"),
    "user": os.getenv("DB_USER", "snip_user"),
    "password": os.getenv("DB_PASSWORD", "snip_pass"),
}

HELP = """
Commands:
  add                 Add a new snippet (guided prompts)
  search              Search snippets (by book, date, or keywords)
  list [N]            List last N snippets (default 10)
  help                Show this help
  quit/exit           Leave the program
"""

def connect():
    return psycopg2.connect(**DB_CFG)

def prompt_nonempty(label):
    while True:
        val = input(f"{label}: ").strip()
        if val:
            return val

def prompt_optional(label):
    val = input(f"{label} (optional): ").strip()
    return val if val else None

def add_snippet(conn):
    print("\nAdd a snippet\n")
    book_name = prompt_nonempty("Book name")
    page_number = prompt_optional("Page number")
    chapter = prompt_optional("Chapter")
    verse = prompt_optional("Verse")
    date_read = prompt_optional("Date read (YYYY-MM-DD)")

    print("Paste the snippet text; end with 'END'")
    lines = []
    while True:
        line = input()
        if line.strip() == "END":
            break
        lines.append(line)
    text_snippet = "\n".join(lines).strip()

    print("Add your thoughts (optional); end with 'END'")
    tlines = []
    while True:
        line = input()
        if line.strip() == "END":
            break
        tlines.append(line)
    thoughts = ("\n".join(tlines).strip()) or None

    sql = """
      INSERT INTO snippets (date_read, book_name, page_number, chapter, verse, text_snippet, thoughts)
      VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    with conn.cursor() as cur:
        cur.execute(sql, (date_read, book_name, page_number, chapter, verse, text_snippet, thoughts))
    conn.commit()
    print("✓ Saved.\n")

def list_snippets(conn, n=10):
    sql = """
      SELECT id, created_utc, book_name, page_number, chapter, verse
      FROM snippets
      ORDER BY id DESC
      LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (n,))
        rows = cur.fetchall()
    for r in rows:
        print(r)

def search_snippets(conn):
    print("\nSearch by:")
    print(" 1) Book name")
    print(" 2) Date read (YYYY-MM-DD)")
    print(" 3) Keywords (full text)")
    choice = input("> ").strip()
    cur = conn.cursor()
    if choice == "1":
        book = prompt_nonempty("Book contains")
        cur.execute("SELECT id, book_name, text_snippet FROM snippets WHERE book_name ILIKE %s", (f"%{book}%",))
    elif choice == "2":
        d = prompt_nonempty("Date (YYYY-MM-DD)")
        cur.execute("SELECT id, book_name, text_snippet FROM snippets WHERE date_read = %s", (d,))
    elif choice == "3":
        q = prompt_nonempty("Keywords")
        cur.execute("""
          SELECT id, book_name, ts_rank_cd(to_tsvector('english', text_snippet || ' ' || coalesce(thoughts,'')), plainto_tsquery(%s)) AS score,
                 left(text_snippet, 200)
          FROM snippets
          WHERE to_tsvector('english', text_snippet || ' ' || coalesce(thoughts,'')) @@ plainto_tsquery(%s)
          ORDER BY score DESC LIMIT 20
        """, (q, q))
    else:
        return
    for row in cur.fetchall():
        print(row)

def main():
    conn = connect()
    print("Book Snippets CLI (PostgreSQL)")
    while True:
        cmd = input("> ").strip().lower()
        if cmd in ("quit", "exit"):
            break
        elif cmd == "add":
            add_snippet(conn)
        elif cmd.startswith("list"):
            list_snippets(conn)
        elif cmd == "search":
            search_snippets(conn)
        else:
            print(HELP)
    conn.close()

if __name__ == "__main__":
    main()
