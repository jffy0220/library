import os
import psycopg2
from werkzeug.security import generate_password_hash

DB_CFG = dict(
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", "5432")),
    dbname=os.getenv("DB_NAME", "snippets_db"),
    user=os.getenv("DB_USER", "snip_user"),
    password=os.getenv("DB_PASSWORD", "snip_pass"),
)

def main():
    username = input("New username: ").strip()
    password = input("New password: ").strip()
    pw_hash = generate_password_hash(password)  # PBKDF2-SHA256 by default

    with psycopg2.connect(**DB_CFG) as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (username, pw_hash))
        conn.commit()
    print("Done. (If username existed already, it was left unchanged.)")

if __name__ == "__main__":
    main()
