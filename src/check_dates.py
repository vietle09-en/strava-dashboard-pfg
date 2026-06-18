import sqlite3
import pandas as pd

conn = sqlite3.connect(r"F:\strava\activities.db")

df = pd.read_sql_query("""
SELECT
    MIN(vietnam_time) as min_time,
    MAX(vietnam_time) as max_time,
    COUNT(*) as total
FROM activities
""", conn)

print(df)

df2 = pd.read_sql_query("""
SELECT vietnam_time, athlete, type, distance
FROM activities
ORDER BY vietnam_time DESC
LIMIT 10
""", conn)

print(df2)

conn.close()