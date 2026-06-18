import sqlite3
import pandas as pd

conn = sqlite3.connect("activities.db")

df = pd.read_sql_query("""
SELECT
    athlete,
    COUNT(*) as total
FROM activities
GROUP BY athlete
ORDER BY total DESC
""", conn)

df.to_csv(
    "athlete_count.csv",
    index=False,
    encoding="utf-8-sig"
)

print(df.head(20))

conn.close()