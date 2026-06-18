import sqlite3
import pandas as pd

conn = sqlite3.connect(r"F:\strava\activities.db")

df = pd.read_sql_query("""
SELECT
    COUNT(*) as total_rows,
    COUNT(DISTINCT activity_id) as unique_rows
FROM activities
""", conn)

print(df)

conn.close()