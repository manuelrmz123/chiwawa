import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def run_migration():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL not found in .env file")

    schema_path = Path(__file__).parent / "schema.sql"
    sql = schema_path.read_text()

    print("Connecting to Neon...")
    conn = psycopg2.connect(db_url)
    conn.autocommit = True

    with conn.cursor() as cur:
        print("Running schema...")
        cur.execute(sql)

    conn.close()
    print("Done. All tables created successfully.")

if __name__ == "__main__":
    run_migration()
