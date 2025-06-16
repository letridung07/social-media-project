import sqlite3
import os
from datetime import datetime

# Construct the path to the database file
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'app.db')

def add_column_if_not_exists(cursor, table_name, column_name, column_type):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [info[1] for info in cursor.fetchall()]
    if column_name not in columns:
        try:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
            print(f"Column {column_name} added to {table_name} table.")
        except sqlite3.OperationalError as e:
            print(f"Error adding column {column_name} to {table_name}: {e}")
            # This might happen if the column was added in a way PRAGMA table_info didn't catch,
            # or if there's another issue. For simple ADD COLUMN, "duplicate column name" is common.
            if "duplicate column name" in str(e):
                print(f"Column {column_name} likely already exists in {table_name}.")
            else:
                # Re-raise if it's not a duplicate column error, as it might be something else.
                raise
    else:
        print(f"Column {column_name} already exists in {table_name} table.")

def main():
    print(f"Connecting to database at: {DB_PATH}")
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        print("Attempting to add 'last_used' column to 'hashtag' table...")
        # For DATETIME, SQLite doesn't have a native type, TEXT or INTEGER (for Unix epoch) is common.
        # Using TEXT to store ISO format datetime strings, or rely on SQLAlchemy's type affinity.
        # For manual ALTER, being explicit is good. Using TEXT.
        add_column_if_not_exists(cursor, "hashtag", "last_used", "DATETIME")

        print("Attempting to add 'usage_count' column to 'post_hashtags' table...")
        add_column_if_not_exists(cursor, "post_hashtags", "usage_count", "INTEGER DEFAULT 1")

        # Set initial values for existing rows if columns were newly added and need defaults
        # For 'last_used', set to current time for existing hashtags
        cursor.execute(f"PRAGMA table_info(hashtag)")
        if 'last_used' in [info[1] for info in cursor.fetchall()]:
            # Check if any last_used is NULL (can happen if column was added without default for existing rows)
            # Only update if it's NULL to avoid overwriting existing values if script is run multiple times.
            update_last_used_sql = "UPDATE hashtag SET last_used = ? WHERE last_used IS NULL"
            cursor.execute(update_last_used_sql, (datetime.utcnow().isoformat(),))
            if cursor.rowcount > 0:
                print(f"Initialized 'last_used' for {cursor.rowcount} existing rows in 'hashtag' table.")

        # For 'usage_count', set to 1 for existing associations
        cursor.execute(f"PRAGMA table_info(post_hashtags)")
        if 'usage_count' in [info[1] for info in cursor.fetchall()]:
            update_usage_count_sql = "UPDATE post_hashtags SET usage_count = 1 WHERE usage_count IS NULL" # Or some other logic if default 1 wasn't applied to old rows
            cursor.execute(update_usage_count_sql)
            if cursor.rowcount > 0:
                print(f"Initialized 'usage_count' for {cursor.rowcount} existing rows in 'post_hashtags' table.")


        conn.commit()
        print("Database schema changes applied successfully (if any were needed).")

    except sqlite3.Error as e:
        print(f"Database error: {e}")
        if conn:
            conn.rollback()
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")

if __name__ == '__main__':
    main()
