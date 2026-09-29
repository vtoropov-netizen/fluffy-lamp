# Почасовой отчёт 7742

Проект подготовлен для Unity Advertising Statistics API v2, Keitaro Admin API и Telegram Bot API. Формат отчёта Keitaro настроен по показанному запросу `reports.build` и ответу `rows`/`total`. Перед запуском проверьте его с вашим Admin API key.

## Данные для настройки

- Unity: Organization core ID и ключ сервисного аккаунта с ролью **Advertise Stats API Viewer** (Key ID + Secret key).
- Keitaro: URL трекера и Admin API key с доступом к отчётам.
- Telegram: токен бота от @BotFather и chat ID чата после отправки боту `/start`.
- На выгрузках от 29.09.2026 подтверждено, что `Sub ID 16` совпадает с `campaignName` в Unity для трёх кампаний. Скриншот Admin API показал поля `rows`, `total`, `campaign_unique_clicks`, `conversions`, `sales`, `country`, `campaign`, `sub_id_16`.

Код формирует запрос `/admin_api/v1/report/build` с сегодняшним диапазоном `Europe/Moscow`, группировками `country`, `campaign`, `sub_id_16` и метриками `campaign_unique_clicks`, `conversions`, `sales`. Все страницы ответа загружаются по `limit`/`offset` до значения `total`. Фильтр интерфейса по `campaign_id` не копируется: код сам отбирает строки, у которых `sub_id_16` содержит отдельное число `7742`, и сопоставляет полное значение с названием кампании Unity. Строки Keitaro без совпадения в сегодняшнем отчёте Unity игнорируются: они могут относиться к долётам старых кампаний. При неоднозначном совпадении отчёт не отправляется. Проверьте, что учёт повторных покупок соответствует вашим правилам.

Текущая область отчёта — кампании, которые Unity возвращает за сегодня, в том числе с нулевым spend, если они присутствуют в ответе. Это не проверка переключателя состояния «включена» в Unity. Для буквального фильтра активного статуса потребуется дополнительно подключить Unity Advertising Management API и проверить доступ к нему.

В `payouts.json` уже внесены указанные ставки по 12 гео (ISO-коды стран). Инкам = число продаж × ставка по гео. Ставки, как вы описали, исходно в евро; знак `$` в сообщении используется как условное отображение числа **без пересчёта валюты**. Если нужен фактический USD, потребуется отдельное правило обменного курса. Названия и кодировки гео в Keitaro нужно сверить с примером ответа.

## Установка на Ubuntu VPS

```bash
sudo apt update
sudo apt install -y python3
sudo useradd --system --home /opt/unity-keitaro-bot --shell /usr/sbin/nologin reportbot
sudo mkdir -p /opt/unity-keitaro-bot
sudo cp bot.py keitaro_columns.json payouts.json /opt/unity-keitaro-bot/
sudo cp env.example /etc/unity-keitaro-bot.env
sudo nano /etc/unity-keitaro-bot.env
sudo chmod 600 /etc/unity-keitaro-bot.env
sudo chown root:root /etc/unity-keitaro-bot.env
sudo chown -R reportbot:reportbot /opt/unity-keitaro-bot
sudo cp report.service report.timer /etc/systemd/system/
sudo systemctl daemon-reload
```

Проверка после заполнения настроек:

```bash
sudo systemctl start report.service
sudo journalctl -u report.service -n 50 --no-pager
sudo systemctl enable --now report.timer
sudo systemctl list-timers report.timer
```

Для проверки без отправки в Telegram временно добавьте `--dry-run` в `ExecStart` файла service, выполните `sudo systemctl daemon-reload` и `sudo systemctl start report.service`, затем посмотрите вывод в `journalctl`. Перед включением таймера удалите `--dry-run` и снова выполните `daemon-reload`.

Таймер запускается по часу системного времени VPS; интервал «сегодня» определяется `REPORT_TIMEZONE`. Unity обновляет данные примерно раз в час с задержкой, поэтому текущий spend может отставать. Ошибки API прерывают отправку, чтобы не прислать отчёт с ложными нулями. Никакие пароли от панелей не нужны.
