import json

base = '/root/workloadpilot/out'
print('phase starts:')
for line in open(base + '/phases.log'):
    ts, name = line.strip().split()
    print(' ', ts, name)

rows = [json.loads(l) for l in open(base + '/telemetry.jsonl')]
print('rows:', len(rows))
print()
print('ts                     | neighbor_mem_mb | wbytes_mb | throttled_us | mem_high_ev')
for i, row in enumerate(rows):
    if i % 8 != 0:
        continue
    n = row['cgroups'].get('wlp-neighbor')
    if not n:
        print('{} | null (no neighbor)'.format(row['ts']))
        continue
    io = n.get('io_stat') or {}
    cs = n.get('cpu_stat') or {}
    ev = n.get('memory_events') or {}
    wb = io.get('wbytes')
    print('{} | {:>14} | {:>9} | {:>12} | {}'.format(
        row['ts'],
        n.get('memory_current_mb'),
        None if wb is None else round(wb / 1048576, 1),
        cs.get('throttled_usec'),
        ev.get('high'),
    ))
