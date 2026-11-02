import sqlite3
import pandas as pd
import glob
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(BASE_DIR, "database.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

LOAD_ORDER = ["categories", "customers", "products", "orders", "order_items", "promotions"]

def table_name(path):
    file_name = os.path.splitext(os.path.basename(path))[0]
    return file_name.split(" - ")[-1].strip()

if __name__ == "__main__":
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH) 

    csv_files = {table_name(p): p for p in glob.glob(os.path.join(DATA_DIR, "*.csv"))}

    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        con.executescript(f.read())

    for table in LOAD_ORDER:
        df = pd.read_csv(csv_files[table])
        df.to_sql(table, con, if_exists="append", index=False)
        print(f"{table}: {len(df)} linhas")

    con.commit()
    con.close()


