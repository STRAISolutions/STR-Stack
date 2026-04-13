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

def api_get(path, token):
    req = urllib.request.Request(
        f'{BASE}{path}',
        headers={'Authorization': f'Bearer {token}', 'Version': '2021-07-28', 'Accept': 'application/json', 'User-Agent': 'STR-Stack/1.0'}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def api_put(path, token, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f'{BASE}{path}', data=data, method='PUT',
        headers={'Authorization': f'Bearer {token}', 'Version': '2021-07-28', 'Content-Type': 'application/json', 'User-Agent': 'STR-Stack/1.0'}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

for acct in ACCOUNTS:
    print(f"\n=== {acct['name']} ===")
    contacts = []
    page_url = f"/contacts/?locationId={acct['location']}&limit=100"

    while page_url:
        data = api_get(page_url, acct['token'])
        batch = data.get('contacts', [])
        contacts.extend(batch)
        meta = data.get('meta', {})
        sa = meta.get('startAfter')
        said = meta.get('startAfterId')
        if sa and said:
            page_url = f"/contacts/?locationId={acct['location']}&limit=100&startAfter={sa}&startAfterId={said}"
        else:
            page_url = None

    print(f"  Total contacts: {len(contacts)}")
    already = 0
    updated = 0
    errors = 0

    for c in contacts:
        cid = c.get('id', '')
        assigned = c.get('assignedTo') or ''
        if assigned == acct['mike_id']:
            already += 1
            continue
        try:
            api_put(f'/contacts/{cid}', acct['token'], {'assignedTo': acct['mike_id']})
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
