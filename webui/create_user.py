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
    role = (input("Role [user/moderator/admin] (default user): ") or "user").strip().lower() or "user"
    if role not in {"user", "moderator", "admin"}:
        print("Invalid role; defaulting to 'user'.")
        role = "user"

    pw_hash = generate_password_hash(password)  # PBKDF2-SHA256 by default

    with psycopg2.connect(**DB_CFG) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (username, password_hash, role)
            VALUES (%s, %s, %s)
            ON CONFLICT (username) DO UPDATE
                SET password_hash = EXCLUDED.password_hash,
                    role = EXCLUDED.role
            """,
            (username, pw_hash, role),
        )
        conn.commit()
    print("Done. Existing users are updated with the provided password and role.")

if __name__ == "__main__":
    main()