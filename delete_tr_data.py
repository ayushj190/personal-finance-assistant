import sqlite3
import os
import sys

# add parent directory to path to import config
sys.path.append(r"c:\Users\ayush\Documents\Repos\personal-finance-assistant")
from config import DB_PATH

conn = sqlite3.connect(DB_PATH)
acc = conn.execute("SELECT id FROM accounts WHERE external_id = 'tr_cash_eur'").fetchone()
if acc:
    acc_id = acc[0]
    conn.execute("DELETE FROM account_snapshots WHERE account_id = ?", (acc_id,))
    conn.execute("DELETE FROM holdings WHERE account_id = ?", (acc_id,))
    conn.execute("DELETE FROM transactions WHERE account_id = ?", (acc_id,))
    conn.execute("DELETE FROM accounts WHERE id = ?", (acc_id,))
    conn.commit()
    print("Deleted trade republic account and its data.")
else:
    print("trade republic account not found.")
conn.close()
