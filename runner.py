import datetime
import time
import traceback

import bot

while True:
    try:
        bot.main()
        print("Отчёт отправлен", flush=True)
    except Exception:
        traceback.print_exc()

    now = datetime.datetime.now(datetime.timezone.utc)
    next_hour = (
        now.replace(minute=0, second=0, microsecond=0)
        + datetime.timedelta(hours=1)
    )
    time.sleep(max(1, (next_hour - now).total_seconds()))
