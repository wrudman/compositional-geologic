"""Batch entry point: reuse only configuration/runner cells, never tutorial demos."""
import json
import os
import time
import argparse
import hashlib
import fcntl
import signal
from pathlib import Path
import requests

root = Path(__file__).resolve().parent
os.chdir(root)
notebook = json.loads((root / 'geo_agent_tutorial_vertex_pilot_v1.ipynb').read_text())
namespace = {'__name__': '__main__'}

def run_cell(index):
    source = ''.join(notebook['cells'][index]['source'])
    if index == 5:
        source = source.replace('stdout=open(LOG,', 'start_new_session=True, stdout=open(LOG,', 1)
    exec(compile(source, f'tutorial_cell_{index}', 'exec'), namespace)

def atomic_json(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, default=str))
    temporary.replace(path)


def run_resumable(output, setups, time_budget):
    import pandas as pd
    namespace['RUN_ROOT'] = output
    expected = set()
    for setup in ('compositional', 'no_tools'):
        tag = 'compositional_auto' if setup == 'compositional' else 'no_tools'
        for item in namespace['ITEMS']:
            run_id = f"{namespace['DATASET_ID']}_c{item['structure_complexity']}_{tag}_{item['item_id']}"
            expected.add((setup, item['item_id'], run_id))

    def summarize():
        records = []
        for setup, item_id, run_id in sorted(expected):
            tag = 'compositional_auto' if setup == 'compositional' else 'no_tools'
            path = output / tag / (run_id + '.json')
            if path.exists():
                record = json.loads(path.read_text())
                if record['item_id'] != item_id or record['setup'] != setup:
                    raise RuntimeError(f'Checkpoint identity mismatch: {path}')
                records.append(record)
        atomic_json(output / 'all_runs.json', records)
        temp = output / 'summary.csv.tmp'
        pd.DataFrame(records).drop(columns=['messages', 'trace', 'env_tool_calls'], errors='ignore').to_csv(temp, index=False)
        temp.replace(output / 'summary.csv')
        print(f"Saved episodes: {len(records)}/148; runtime errors: {sum(bool(x.get('run_error')) for x in records)}", flush=True)
        return records

    summarize()
    for setup in setups:
        tag = 'compositional_auto' if setup == 'compositional' else 'no_tools'
        for item in namespace['ITEMS']:
            run_id = f"{namespace['DATASET_ID']}_c{item['structure_complexity']}_{tag}_{item['item_id']}"
            path = output / tag / (run_id + '.json')
            if path.exists():
                print(f"SKIP saved {setup}: {item['item_id']}", flush=True)
                continue
            if time.monotonic() >= time_budget:
                print('Session time budget reached; resume with the same --run-dir.', flush=True)
                return
            record, _ = namespace['run_item'](setup, item, tool_mode='auto', max_turns=10, verbose=0)
            print(f"{setup} {item['item_id']}: answer={record.get('answer')!r}, status={record.get('status')}, seconds={record.get('elapsed_s')}", flush=True)
            summarize()
            if record.get('run_error'):
                raise RuntimeError(record['run_error'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', default='runs/reasoning_32768_v1')
    parser.add_argument('--setups', nargs='+', choices=['compositional', 'no_tools'], default=['compositional', 'no_tools'])
    parser.add_argument('--capture-check-only', action='store_true', help='Verify reasoning capture and exit without dataset evaluation')
    parser.add_argument('--session-minutes', type=float, default=330)
    args = parser.parse_args()
    output = Path(args.run_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Prevent batch and interactive jobs writing the same checkpoints concurrently.
    lock = (output / '.run.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('Another runner is using this run directory; refusing duplicate execution')
    manifest = {
        'dataset_sha256': hashlib.sha256((root/'dataset/dataset.json').read_bytes()).hexdigest(),
        'source_sha256': hashlib.sha256((root/'source_fingerprints.json').read_bytes()).hexdigest(),
        'notebook_sha256': hashlib.sha256((root/'geo_agent_tutorial_vertex_pilot_v1.ipynb').read_bytes()).hexdigest(),
        'runner_compat_sha256': hashlib.sha256((root/'runner_compat.py').read_bytes()).hexdigest(),
        'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    manifest_path = output/'manifest.json'
    if manifest_path.exists():
        if json.loads(manifest_path.read_text()) != manifest:
            raise SystemExit('Code/dataset/config changed: choose a new run directory')
    else:
        atomic_json(manifest_path, manifest)
    time_budget = time.monotonic() + args.session_minutes * 60
    namespace['RUN_ROOT'] = output
    run_cell(3)
    try:
        requests.get(f'http://127.0.0.1:{namespace.get("PORT", 8000)}/health', timeout=2).raise_for_status()
    except requests.RequestException:
        pass
    else:
        raise RuntimeError('Configured port already has a service; refusing to reuse it silently')
    def stop_on_signal(signum, frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, stop_on_signal)
    server = None
    try:
        run_cell(5)
        server = namespace['server']
        deadline = time.monotonic() + 2700
        while True:
            if server.poll() is not None:
                raise RuntimeError('vLLM exited; inspect /tmp/vllm.log')
            try:
                if requests.get(f'http://127.0.0.1:{namespace.get("PORT", 8000)}/health', timeout=2).status_code == 200:
                    break
            except requests.RequestException:
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError('vLLM did not become healthy within 45 minutes')
            time.sleep(5)
        for index in (8, 10, 11):
            run_cell(index)
        assert namespace['MAX_TURNS'] == 10 and namespace['THINKING'] is True
        # A separate diagnostic request; never counted as an evaluation episode.
        from openai import OpenAI
        agent = namespace['geo_agent']
        probe = OpenAI().chat.completions.create(
            model=agent.MODEL,
            messages=[{'role': 'user', 'content': 'What is 17 times 19? Explain briefly and give the answer.'}],
            **{**agent.SAMPLING, 'max_tokens': 2048}, extra_body=agent.EXTRA_BODY)
        capture = agent._request_record(probe, 0, 'capture_preflight', output/'capture_preflight.jsonl')
        if capture['reasoning_capture_status'] != 'captured':
            raise RuntimeError('Reasoning TEXT was not returned/captured. Full preflight response saved; stopping before dataset evaluation. Inspect parser/API fields first.')
        print('Reasoning TEXT capture preflight PASSED', flush=True)
        if not args.capture_check_only:
            run_resumable(output, args.setups, time_budget)
    finally:
        if server is not None:
            # The API server and its engine workers share a dedicated group.
            # Clean the group even if the API parent has already exited.
            try:
                os.killpg(server.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                server.wait(timeout=20)
            except Exception:
                pass
            time.sleep(2)
            try:
                os.killpg(server.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            server.wait()
            import shutil
            if Path('/tmp/vllm.log').exists():
                stamp = time.strftime('%Y%m%d_%H%M%S')
                shutil.copy2('/tmp/vllm.log', output / f'vllm_{stamp}.log')
