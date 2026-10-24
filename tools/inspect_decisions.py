import json
from collections import Counter

path = '/root/workloadpilot/out/decisions.jsonl'
rows = [json.loads(l) for l in open(path)]
print('decisions:', len(rows))
counts = Counter((r['action'], bool(r['applied'])) for r in rows)
for (action, applied), n in sorted(counts.items()):
    print('  {:22s} applied={}: {}'.format(action, applied, n))
print()
print('all applied decisions:')
for r in rows:
    if r['applied']:
        print(' ', r['ts'], r['action'], r.get('target'), '->', r['detail'][:140])
print()
print('one refusal detail per (action, detail-prefix):')
seen = set()
for r in rows:
    if not r['applied'] and r['action'] != 'do_nothing':
        key = (r['action'], r['detail'][:80])
        if key not in seen:
            seen.add(key)
            print(' ', r['action'], '|', r['detail'][:140])
