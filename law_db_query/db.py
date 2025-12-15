import psycopg2
import os
from dotenv import load_dotenv
load_dotenv(override=True)
DATABASE_URL = os.getenv("DATABASE_URL")

def query_article_from_db(law_names, article):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    sql = """
    SELECT law_name, law_year, chapter, section, article, text
    FROM law_articles
    WHERE law_name = %s AND article = %s
    ORDER BY law_year DESC
    LIMIT 1;
    """

    for ln in law_names:
        cur.execute(sql, (ln, article))
        row = cur.fetchone()
        if row:
            cur.close()
            conn.close()
            return row

    cur.close()
    conn.close()
    return None
