"""
Одноразовый скрипт миграции пользователей из ids_yme.txt в bot.db.
Запускать вручную на проде ДО первого старта бота (или при остановленном боте).

    python3 migrate.py
"""

import sqlite3
from config import DB_FILE, IDS_FILE

with open(IDS_FILE, 'r', encoding='utf-8') as f:
    ids = {line.strip() for line in f if line.strip()}

con = sqlite3.connect(DB_FILE)
inserted = skipped = invalid = 0

for uid in ids:
    try:
        chat_id = int(uid)
    except ValueError:
        print(f"  [skip] невалидная строка: {uid!r}")
        invalid += 1
        continue

    cur = con.execute("INSERT OR IGNORE INTO users (chat_id) VALUES (?)", (chat_id,))
    if cur.rowcount:
        inserted += 1
    else:
        skipped += 1

con.commit()
con.close()

print(f"Готово. Добавлено: {inserted}, уже были в БД: {skipped}, невалидных строк: {invalid}")
