import json

rows = [json.loads(l) for l in open('/root/workloadpilot/out/telemetry.jsonl')]
print('ts (19:51-19:54) | n_psi_io_avg10 | n_wbytes_mb | delta_mb_per_2s')
prev_w = None
for r in rows:
    ts = r['ts']
    win = ts[11:19]
    if not ('19:51:00' <= win <= '19:54:00'):
        continue
    n = r['cgroups'].get('wlp-neighbor')
    if not n:
        print(ts, '| null')
        continue
    w = (n.get('io_stat') or {}).get('wbytes')
    wm = None if w is None else round(w / 1048576, 1)
    dw = None
    if w is not None and prev_w is not None:
        dw = round((w - prev_w) / 1048576, 2)
    if w is not None:
        prev_w = w
    psi = (n.get('psi_io_some') or {}).get('avg10')
    print(ts, '|', psi, '|', wm, '|', dw)
