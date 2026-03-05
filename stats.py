import json
from datetime import datetime, timedelta
from config import EXPORT_LOG


def load_export_log():
    try:
        with open(EXPORT_LOG, 'r') as f:
            return json.load(f)
    except Exception:
        return []


def record_export():
    timestamps = load_export_log()
    timestamps.append(datetime.now().isoformat())
    with open(EXPORT_LOG, 'w') as f:
        json.dump(timestamps, f)


def get_stats():
    timestamps = [datetime.fromisoformat(t) for t in load_export_log()]
    now = datetime.now()

    def rate(count, seconds):
        return round(count / (seconds / 60), 2) if seconds > 0 else 0.0

    def count_since(dt):
        return sum(1 for t in timestamps if t >= dt)

    hour_ago = now - timedelta(hours=1)
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    rows = [
        ("⏱ Последний час",  count_since(hour_ago),   3600),
        ("📅 Сегодня",        count_since(day_start),  (now - day_start).total_seconds()),
        ("📅 Эта неделя",     count_since(week_start), (now - week_start).total_seconds()),
        ("📆 Этот месяц",     count_since(month_start),(now - month_start).total_seconds()),
        ("📅 Этот год",       count_since(year_start), (now - year_start).total_seconds()),
    ]

    lines = []
    for label, count, secs in rows:
        lines.append(f"┌ <b>{label}</b>")
        lines.append(f"╰─ {count} пл.  ·  {rate(count, secs)} пл./мин\n")
    lines.append("┌ <b>🔢 Все время</b>")
    lines.append(f"╰─ {len(timestamps)} пл.")
    return "\n".join(lines)
