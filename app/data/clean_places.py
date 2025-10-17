import sqlite3

db_path = "app/data/places.db"

conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute("UPDATE places SET latitude = NULL WHERE latitude = 'None';")
cur.execute("UPDATE places SET longitude = NULL WHERE longitude = 'None';")

conn.commit()
conn.close()
