#!/usr/bin/env python3
"""Build dataset-v2 from a runs dir: featurize + labeler per run, then split by run."""
import argparse
import subprocess
import sys
from pathlib import Path

DSV2 = Path('/root/workloadpilot/dsv2')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runs-dir', required=True)
    parser.add_argument('--out-dir', required=True)
    args = parser.parse_args()

    runs_dir = Path(args.runs_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ok = 0
    fail = 0
    for run in sorted(runs_dir.glob('run-*')):
        if not (run / 'telemetry.jsonl').exists() or not (run / 'decisions.jsonl').exists():
            print('skip {}: missing telemetry/decisions'.format(run.name))
            continue
        try:
            step1 = subprocess.run([sys.executable, str(DSV2 / 'featurize.py'), '--run-dir', str(run)],
                                   capture_output=True, text=True, timeout=120)
            if step1.returncode != 0:
                raise RuntimeError('featurize: ' + step1.stderr[-400:])
            step2 = subprocess.run([sys.executable, str(DSV2 / 'labeler.py'), '--run-dir', str(run)],
                                   capture_output=True, text=True, timeout=120)
            if step2.returncode != 0:
                raise RuntimeError('labeler: ' + step2.stderr[-400:])
            ok += 1
            note = step2.stdout.strip().splitlines()[-1] if step2.stdout.strip() else ''
            print('ok {}: {}'.format(run.name, note))
        except Exception as exc:  # noqa: BLE001 - keep going through a batch
            fail += 1
            print('FAIL {}: {}'.format(run.name, exc))

    split = subprocess.run([sys.executable, str(DSV2 / 'split_by_run.py'),
                            '--runs-dir', str(runs_dir), '--out-dir', str(out_dir)], text=True)
    print('build done: ok={} fail={} split_rc={}'.format(ok, fail, split.returncode))
    print('dataset dir: {}'.format(out_dir))


if __name__ == '__main__':
    main()
