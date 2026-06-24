import os
from sqlalchemy import create_engine, text

# 🔍 We will scan the current directory and its parent for your database file
current_dir = os.getcwd()
parent_dir = os.path.dirname(current_dir)

# Add any database filenames you found in Step 1 to this list if they are different:
possible_db_names = ["nexus.db", "sql_app.db", "dev.db", "database.db"]
target_db_path = None

# Scan to locate the real file
for folder in [current_dir, parent_dir]:
    for db_name in possible_db_names:
        full_path = os.path.join(folder, db_name)
        if os.path.exists(full_path):
            target_db_path = full_path
            break
    if target_db_path:
        break

if not target_db_path:
    print("❌ Could not find your active SQLite database file automatically.")
    print(f"Please look inside your project and find the filename, then run this manual command:")
    print("sqlite3 <your_db_name>.db \"ALTER TABLE messages ADD COLUMN media_url VARCHAR(500);\"")
else:
    print(f"🎯 Found live database file at: {target_db_path}")
    DATABASE_URL = f"sqlite:///{target_db_path}"
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

    with engine.connect() as conn:
        try:
            print("🛠️ Injecting 'media_url' column into the 'messages' table...")
            conn.execute(text("ALTER TABLE messages ADD COLUMN media_url VARCHAR(500);"))
            conn.commit()
            print("✅ SUCCESS: Database structure updated cleanly!")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("ℹ️ Column already exists in the database. You are good to go!")
            else:
                print(f"❌ Operation failed: {e}")