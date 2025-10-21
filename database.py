# database.py
"""
Database connection and initialization for RemyAfya backend.
"""
import os
import psycopg

DB_NAME = os.environ.get("POSTGRES_DB", "remyafya")
DB_USER = os.environ.get("POSTGRES_USER", "postgres")
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "postgres")
DB_HOST = os.environ.get("POSTGRES_HOST", "localhost")
DB_PORT = os.environ.get("POSTGRES_PORT", "5432")

def get_connection(dbname=DB_NAME, autocommit=True):
    conn = psycopg.connect(
        dbname=dbname,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        autocommit=autocommit
    )
    return conn

def initialize_database():
    """Create the remyafya database if it doesn't exist."""
    try:
        # Connect to default database to create remyafya if needed
        conn = psycopg.connect(
            dbname="postgres",
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
            autocommit=True
        )
        cur = conn.cursor()
        cur.execute(f"SELECT 1 FROM pg_database WHERE datname = '{DB_NAME}'")
        exists = cur.fetchone()
        if not exists:
            cur.execute(f'CREATE DATABASE {DB_NAME}')
            print(f"Database '{DB_NAME}' created.")
        else:
            print(f"Database '{DB_NAME}' already exists.")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error initializing database: {e}")
        raise

if __name__ == "__main__":
    initialize_database()
