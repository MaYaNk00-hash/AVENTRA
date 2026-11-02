"""
Database Migration and Schema Bootstrap Script for AVENTRA.
Executes schema creation, constraint validation, and genesis seed idempotently.
"""

import sys
import os
import time

from sqlalchemy import inspect
from backend.database.session import engine, seed_database, DATABASE_URL
from backend.database.models import Base


def run_migrations():
    print(f"[MIGRATION] Connecting to target database: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}")
    max_retries = 10
    retry_delay = 2

    for attempt in range(1, max_retries + 1):
        try:
            # 1. Connect and create all tables
            Base.metadata.create_all(bind=engine)
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            print(f"[MIGRATION] Schema verified. {len(tables)} tables present: {', '.join(tables)}")

            # 2. Seed initial fixtures and genesis ledger block
            seed_database()
            print("[MIGRATION] Database seeding and cryptographic ledger verification completed successfully.")
            return True
        except Exception as e:
            print(f"[MIGRATION] Attempt {attempt}/{max_retries} failed: {str(e)}")
            if attempt < max_retries:
                print(f"[MIGRATION] Waiting {retry_delay}s before retrying...")
                time.sleep(retry_delay)
            else:
                print("[MIGRATION] FATAL: Unable to connect and migrate database.")
                raise e


if __name__ == "__main__":
    success = run_migrations()
    sys.exit(0 if success else 1)
