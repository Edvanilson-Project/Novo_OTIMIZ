import psycopg2
import sys
import json

conn = psycopg2.connect(
    host="localhost",
    port=5444,
    database="otimiz_db",
    user="otimiz_admin",
    password="otimiz_password"
)
cur = conn.cursor()

schedule_id = 434
cur.execute("SELECT id, metadata FROM schedules WHERE id = %s", (schedule_id,))
row = cur.fetchone()
print(f"Schedule {row[0]} Metadata Keys:")
print(list(row[1].keys()) if row[1] else "None")

cur.execute('SELECT id, metadata FROM "duty_assignments" WHERE "scheduleId" = %s LIMIT 1', (schedule_id,))
row = cur.fetchone()
print(f"\nDuty {row[0]} Metadata Keys:")
print(list(row[1].keys()) if row[1] else "None")

