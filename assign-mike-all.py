#!/usr/bin/env python3
"""Assign all contacts to Mike in both GHL sub-accounts"""
import urllib.request, json, time

ACCOUNTS = [
    {
        'name': 'Master',
        'location': '1OOZ4AKIgxO8QKKMnIcK',
        'token': 'pit-8e3c20cd-0d7f-43a3-be9d-c087e925b3e7',
        'mike_id': 'Lc2bBJfpmmCueklVfR1B',
    },
    {
        'name': 'Call Center',
        'location': '7hTDBClatcBgmUv36bZX',
        'token': 'pit-48465a41-26c9-4115-8195-b0a557dbdb6d',
        'mike_id': '2MxKFbJMQiF0kBxXq5w5',
    },
]

BASE = 'https://services.leadconnectorhq.com'
HEADERS_BASE = {'Version': '2021-07-28', 'Content-Type': 'application/json'}

def api(method, path, token, body=None):
    h = {**HEADERS_BASE, 'Authorization': f'Bearer {token}'}
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(f'{BASE}{path}', data=data, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

for acct in ACCOUNTS:
    print(f"\n=== {acct['name']} ===")
    contacts = []
    # Paginate
    url = f"/contacts/?locationId={acct['location']}&limit=100"
    while url:
        data = api('GET', url, acct['token'])
        batch = data.get('contacts', [])
        contacts.extend(batch)
        meta = data.get('meta', {})
        next_url = meta.get('nextPageUrl', '')
        if next_url and 'startAfterId=' in next_url:
            after_id = next_url.split('startAfterId=')[1].split('&')[0]
            url = f"/contacts/?locationId={acct['location']}&limit=100&startAfterId={after_id}"
        elif meta.get('startAfterId'):
            url = f"/contacts/?locationId={acct['location']}&limit=100&startAfterId={meta['startAfterId']}"
        else:
            url = None

    print(f"  Total contacts: {len(contacts)}")
    already = 0
    updated = 0
    errors = 0
    for c in contacts:
        cid = c.get('id', '')
        assigned = c.get('assignedTo', '')
        if assigned == acct['mike_id']:
            already += 1
            continue
        try:
            api('PUT', f'/contacts/{cid}', acct['token'], {'assignedTo': acct['mike_id']})
            updated += 1
            if updated % 20 == 0:
                print(f"    ... {updated} updated")
            time.sleep(0.15)
        except Exception as e:
            errors += 1
            print(f"    ERR {cid}: {e}")

    print(f"  Already Mike: {already}")
    print(f"  Newly assigned: {updated}")
    print(f"  Errors: {errors}")

print("\nDone")
