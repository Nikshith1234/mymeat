import sqlite3

conn = sqlite3.connect("meatcraft.db")
try:
    conn.execute("ALTER TABLE orders ADD COLUMN kitchen_status VARCHAR(20) NOT NULL DEFAULT 'pending'")
    conn.commit()
    print("Migration done: kitchen_status column added.")
except sqlite3.OperationalError as e:
    if "duplicate column" in str(e).lower():
        print("Column already exists, skipping.")
    else:
        raise
finally:
    conn.close()
