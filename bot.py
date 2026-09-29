#!/usr/bin/env python3
"""Hourly Unity/Keitaro report. Python 3.11+, standard library only."""
import base64
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
SUB_ID = '7742'
GEO_ALIASES = {
    'GERMANY': 'DE', 'DEUTSCHLAND': 'DE', 'SPAIN': 'ES', 'ITALY': 'IT',
    'HUNGARY': 'HU', 'ROMANIA': 'RO', 'POLAND': 'PL',
    'UK': 'GB', 'UNITED KINGDOM': 'GB', 'GREAT BRITAIN': 'GB',
    'IRELAND': 'IE', 'DENMARK': 'DK', 'NORWAY': 'NO',
    'FINLAND': 'FI', 'ICELAND': 'IS',
    'ГЕРМАНИЯ': 'DE', 'ИСПАНИЯ': 'ES', 'ИТАЛИЯ': 'IT',
    'ВЕНГРИЯ': 'HU', 'РУМЫНИЯ': 'RO', 'ПОЛЬША': 'PL',
    'ВЕЛИКОБРИТАНИЯ': 'GB', 'АНГЛИЯ': 'GB', 'ИРЛАНДИЯ': 'IE',
    'ДАНИЯ': 'DK', 'НОРВЕГИЯ': 'NO', 'ФИНЛЯНДИЯ': 'FI',
    'ИСЛАНДИЯ': 'IS',
}

def need(name):
    value = os.environ.get(name, '').strip()
    if not value: raise ValueError(f'Missing {name}')
    return value

def request(url, *, headers=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {}, method='POST' if data else 'GET')
    with urllib.request.urlopen(req, timeout=45) as response:
        if response.status == 204: return {'data': []}
        return json.load(response)

def money(value):
    return Decimal(str(value or '0'))

def unity(start, end):
    key = base64.b64encode(f"{need('UNITY_KEY_ID')}:{need('UNITY_SECRET_KEY')}".encode()).decode()
    url = f"https://services.api.unity.com/advertise/stats/v2/organizations/{urllib.parse.quote(need('UNITY_ORG_CORE_ID'))}/reports/acquisitions"
    args = {'start': start.astimezone(dt.timezone.utc).isoformat().replace('+00:00','Z'),
            'end': end.astimezone(dt.timezone.utc).isoformat().replace('+00:00','Z'),
            'scale': 'hour', 'metrics': 'spend', 'breakdowns': 'campaign', 'format': 'json'}
    result = request(url + '?' + urllib.parse.urlencode(args), headers={'Authorization': 'Basic ' + key})
    if not isinstance(result, dict) or not isinstance(result.get('data'), list):
        raise ValueError('Unexpected Unity response')
    rows = {}
    for item in result['data']:
        name = item['campaignName']
        if not re.search(r'(?<!\d)7742(?!\d)', name): continue
        campaign_id = str(item['campaignId'])
        record = rows.setdefault(campaign_id, {'name': name, 'spend': Decimal(0)})
        record['spend'] += money(item['spend'])
    return rows

def keitaro(start, end):
    body = {
        'range': {
            'interval': 'custom_date_range',
            'timezone': os.getenv('REPORT_TIMEZONE', 'Europe/Moscow'),
            'from': start.strftime('%Y-%m-%d %H:%M'),
            'to': end.strftime('%Y-%m-%d %H:%M'),
        },
        'grouping': ['country', 'campaign', 'sub_id_16'],
        'metrics': ['campaign_unique_clicks', 'conversions', 'sales'],
        'filters': [],
        'columns': [],
        'sort': [{'name': 'sales', 'order': 'desc'}],
        'extended': True,
        'summary': False,
        'limit': 100,
        'offset': 0,
    }
    # The UI's campaign_id filter is deliberately omitted. Unity defines scope.
    # The UI's sub_id_2 filter is omitted; sub_id_16 is checked on every row.
    url = need('KEITARO_URL').rstrip('/') + '/admin_api/v1/report/build'
    headers = {'Api-Key': need('KEITARO_API_KEY'), 'Content-Type': 'application/json'}
    rows = []
    while True:
        result = request(url, body=body, headers=headers)
        if not isinstance(result, dict) or not isinstance(result.get('rows'), list) or not isinstance(result.get('total'), int):
            raise ValueError('Unexpected Keitaro response: expected rows and total')
        batch = result['rows']
        rows.extend(batch)
        if len(rows) >= result['total']:
            return rows
        if not batch or len(batch) > body['limit']:
            raise ValueError('Incomplete or invalid Keitaro pagination')
        body['offset'] += len(batch)
        if body['offset'] > 100000:
            raise ValueError('Keitaro report exceeds pagination safety limit')

def combine(unity_rows, keitaro_rows, mapping, payouts):
    by_name = {}
    for campaign_id, rec in unity_rows.items():
        by_name.setdefault(rec['name'].strip().casefold(), []).append(campaign_id)
    for row in keitaro_rows:
        sub_id_16 = str(row[mapping['sub_id_16']]).strip()
        if not re.search(r'(?<!\d)7742(?!\d)', sub_id_16):
            continue
        # The tracker campaign label is shared by several Unity campaign names;
        # sub_id_16 is the per-ad-campaign naming value in this export.
        campaign = str(row[mapping['campaign']]).strip()
        candidates = ([sub_id_16] if sub_id_16 in unity_rows else
                      by_name.get(sub_id_16.casefold(), []))
        if not candidates:
            # Keitaro records late conversions for campaigns outside today's
            # Unity report. The Unity campaign list defines report scope.
            continue
        if len(candidates) != 1:
            raise ValueError(f'Keitaro Sub ID 16 has ambiguous Unity match: {sub_id_16!r} ({campaign})')
        campaign_id = candidates[0]
        rec = unity_rows[campaign_id]
        geo = str(row[mapping['geo']]).strip().upper()
        geo = GEO_ALIASES.get(geo, geo)
        purchases = int(row[mapping['purchases']])
        if purchases and geo not in payouts:
            raise ValueError(f'No payout for geo {geo!r} in {campaign!r}')
        for key in ('installs', 'registrations', 'purchases'):
            rec[key] = rec.get(key, 0) + int(row[mapping[key]])
        rec['income'] = rec.get('income', Decimal(0)) + purchases * money(payouts.get(geo, 0))
    return unity_rows

def report(rows, start, end):
    lines = [f"📊 7742 | {start:%d.%m.%Y} | на {end:%H:%M} ({end.tzname()})"]
    for rec in sorted(rows.values(), key=lambda x: x['name']):
        lines.append(f"\n{rec['name']}\nСпенд: ${rec['spend']:.2f} | Инкам: ${rec.get('income', 0):.2f}\nИнсталлы: {rec.get('installs', 0)} | Реги: {rec.get('registrations', 0)} | Депозиты: {rec.get('purchases', 0)}")
    if not rows: lines.append('Кампаний с 7742 нет.')
    return '\n'.join(lines)

def send(message):
    url = 'https://api.telegram.org/bot' + need('TELEGRAM_BOT_TOKEN') + '/sendMessage'
    while message:
        chunk, message = message[:3900], message[3900:]
        response = request(url, body={'chat_id': need('TELEGRAM_CHAT_ID'), 'text': chunk}, headers={'Content-Type': 'application/json'})
        if response.get('ok') is not True: raise ValueError('Telegram send failed')

def main():
    end = dt.datetime.now(ZoneInfo(os.getenv('REPORT_TIMEZONE', 'UTC')))
    start = end.replace(hour=0, minute=0, second=0, microsecond=0)
    mapping = json.loads((ROOT / 'keitaro_columns.json').read_text())
    payouts = json.loads((ROOT / 'payouts.json').read_text())
    if not payouts: raise ValueError('Fill payouts.json first')
    rows = unity(start, end)
    data = keitaro(start, end)
    text = report(combine(rows, data, mapping, payouts), start, end)
    if '--dry-run' in sys.argv: print(text)
    else: send(text)

if __name__ == '__main__':
    try: main()
    except Exception as exc:
        print(f'Report failed: {exc}', file=sys.stderr)
        sys.exit(1)
