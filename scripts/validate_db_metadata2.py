import psycopg2
import sys

def main():
    conn = psycopg2.connect(
        host="localhost",
        port=5444,
        database="otimiz_db",
        user="otimiz_admin",
        password="otimiz_password"
    )
    cur = conn.cursor()

    schedule_id = 434

    # Check schedules
    cur.execute("SELECT id, metadata->'operational_time_reports' FROM schedules WHERE id = %s", (schedule_id,))
    row = cur.fetchone()
    if not row:
        print("Schedule not found in DB!")
        sys.exit(1)
        
    s_id, meta_opr = row
    if not meta_opr:
        print("schedules.metadata.operational_time_reports MISSING")
    else:
        print(f"schedules.metadata.operational_time_reports OK (Length: {len(meta_opr)})")

    # Check duty assignments
    cur.execute('SELECT count(*) FROM "duty_assignments" WHERE "scheduleId" = %s', (schedule_id,))
    total_duties = cur.fetchone()[0]

    cur.execute('SELECT count(*) FROM "duty_assignments" WHERE "scheduleId" = %s AND metadata->\'duty_time_segments\' IS NOT NULL', (schedule_id,))
    segments_duties = cur.fetchone()[0]
    
    cur.execute('SELECT count(*) FROM "duty_assignments" WHERE "scheduleId" = %s AND metadata->\'operational_time_report\' IS NOT NULL', (schedule_id,))
    report_duties = cur.fetchone()[0]

    print(f"Total Duties: {total_duties}")
    print(f"Duties with duty_time_segments: {segments_duties}")
    print(f"Duties with operational_time_report: {report_duties}")
    
    if total_duties == segments_duties and total_duties == report_duties and total_duties > 0:
        print("Database Validation: SUCCESS")
    else:
        print("Database Validation: FAILED")

main()
