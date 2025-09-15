import os, getpass
import psycopg2
from passlib.hash import bcrypt
from dotenv import load_dotenv

load_dotenv()

DB_CFG = dict(
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", "5432")),
    dbname=os.getenv("DB_NAME", "snippets_db"),
    user=os.getenv("DB_USER", "snip_user"),
    password=os.getenv("DB_PASSWORD", "snip_pass"),
)

def main():
    username = input("New username: ").strip()
    password = getpass.getpass("New password: ")
    pw_hash = bcrypt.hash(password)

    with psycopg2.connect(**DB_CFG) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s) ON CONFLICT (username) DO NOTHING",
            (username, pw_hash),
        )
        conn.commit()
    print("Done. (If username existed already, it was unchanged.)")

if __name__ == "__main__":
    main()
