"""Draft reference-procedure workload, NOT validated minimum program length.

Standard-library only. No model responses are read and dataset files are unchanged.
Every counted unit has weight 1, which is a proposal, not a calibrated cost model.
Inspect output components and assumptions before aggregating across question types.

Conventions:
* union of k regions: k-1 binary unions (William's example).
* count/test n candidate objects: n object visits/tests, NOT number in the answer.
* rank n objects: n(n-1)/2 pair comparisons (explicit all-pairs strategy, NOT minimum).
* find minimum among n measured values: max(0,n-1) comparisons.
* a described-point lookup or region-contact test is currently ONE MACRO operation;
  its internal geometry/perceptual work is NOT expanded. These need team agreement.
* exhaustive scans do not exploit early stopping, even for Yes/No tasks.
"""
import argparse
import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def corner_points(graph, label):
    """Direction-change corners, excluding collinear topology subdivisions."""
    vertices = {v['id']: (v['x'], v['y']) for v in graph['vertices']}
    ids = next(r['vertex_ids'] for r in graph['regions'] if r['label'] == label)
    points = [vertices[i] for i in ids]
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    result = []
    for i, b in enumerate(points):
        a, c = points[i-1], points[(i+1) % len(points)]
        ux, uy, vx, vy = b[0]-a[0], b[1]-a[1], c[0]-b[0], c[1]-b[1]
        scale = math.hypot(ux, uy)*math.hypot(vx, vy)
        if scale and abs(ux*vy-uy*vx) > 1e-10*scale:
            result.append(b)
    return result


def calculate(item, graph):
    q = item['question']; qid = q['question_id']
    evidence = item['reference_solution']['evidence']
    n = len(graph['regions'])
    components = {}
    assumptions = []
    def add(name, count):
        assert isinstance(count, int) and count >= 0, (qid, name, count)
        components[name] = count
    def lookup(count):
        add('described_vertex_lookup_macro', count)
        assumptions.append('Each described vertex lookup counts as one macro; selector search/angle comparisons are not expanded.')
    def rank(count):
        add('ordering_pair_comparison', count*(count-1)//2)
        assumptions.append('All-pairs ordering strategy; this comparison count is not a minimum.')
    def contact(count):
        add('vertex_only_contact_test_macro', count)
        assumptions.append('Each region-pair contact classification counts as one macro; boundary work is not expanded.')
    def union():
        add('binary_union', len(evidence['source_regions'])-1)
    def corners(label):
        return len(corner_points(graph, label))
    text = q['question_text']
    if qid == 'C-009':
        contact(n-1)
    elif qid == 'C-027':
        k = len(evidence['candidate_vertex_ids'])
        lookup(k+1); add('distance_measurement', k); rank(k)
    elif qid == 'C-030':
        k = len(evidence['vertex_ids']); lookup(k); rank(k)
    elif qid == 'C-031':
        union(); lookup(1); add('union_corner_membership_test', 1)
    elif qid == 'C-032':
        lookup(2); add('height_comparison', 1)
    elif qid == 'C-090':
        k = len(evidence['target_vertices'])
        lookup(2); add('distance_measurement', 2*k); add('distance_comparison', k)
        assumptions.append('Each successful comparison contributes to a running count; no extra increment cost.')
    elif qid == 'C-091':
        lookup(2)
        add('intermediate_vertex_count_visit', evidence['clockwise_intermediate']+evidence['counterclockwise_intermediate'])
        add('count_comparison', 1)
    elif qid in ('C-093', 'C-095'):
        labels = list(evidence['frame_vertex_counts'])
        add('corner_frame_test_and_count', sum(corners(label) for label in labels))
        if qid == 'C-093': rank(len(labels))
        else: add('count_comparison', 1)
        assumptions.append('Inspect every corner, including corners off frame; do not use the answer count as scan cost.')
    elif qid == 'C-094':
        union(); add('distinct_source_vertex_membership_test_and_count', evidence['source_distinct_vertex_count'])
        assumptions.append('Source-vertex deduplication and union-boundary construction are not separately expanded.')
    elif qid == 'C-097':
        k = len(evidence['contact_points'])
        lookup(1); contact(n-1)
        add('contact_point_lookup_macro', k); add('distance_measurement', k)
        add('minimum_distance_comparison', max(0,k-1))
    elif qid == 'C-098':
        target = re.search(r'boundary of region ([A-Z]+)', text).group(1)
        lookup(1)
        add('boundary_topology_point_visit', len(set(next(r['vertex_ids'] for r in graph['regions'] if r['label']==target))))
        contact(n-1)
        assumptions.append('Traverse each boundary topology point once, then classify candidate regions; same-point angular ordering is unexpanded. This may double-count work shared by a more efficient strategy.')
    elif qid == 'C-099':
        add('edge_lookup_macro', 1); add('line_extension', 1)
        contact(n-1)
        add('line_interior_crossing_test_macro', len(evidence['all_vertex_only_neighbors']))
        assumptions.append('Check line crossing only for vertex-only candidates; never substitute answer-region count. Edge lookup and line crossing are unexpanded macros.')
    elif qid == 'C-100':
        contact(n*(n-1)//2)
        add('contact_point_lookup_macro', len(evidence['ordered_pairs']))
        rank(len(evidence['ordered_pairs']))
        assumptions.append('Exhaustive unordered region-pair scan; a junction-based strategy could require fewer operations.')
    elif qid == 'C-101':
        union(); contact(n-len(evidence['source_regions']))
    elif qid == 'C-102':
        contact(2*(n-2))
        sets = list(evidence['neighbor_sets'].values())
        add('neighbor_set_membership_test', sum(map(len, sets)))
        assumptions.append('Check both neighbor sets exhaustively using unit-cost set membership, no early exit. Set construction costs are not expanded.')
    else:
        raise ValueError(f'No reviewed draft rule for {qid}')
    program = item['reference_solution'].get('program') or {}
    return {
        'item_id': item['item_id'], 'question_id': qid,
        'question_type': q['question_type'],
        'original_complexity_level': item['question_complexity']['level'],
        'original_complexity_parameter': item['question_complexity']['parameter'],
        'region_count': n,
        'draft_atomic_operation_count': sum(components.values()),
        'components': components,
        'status': 'draft_reference_procedure_not_validated_minimum',
        'cross_type_comparability': 'requires agreement on units and macro expansion',
        'reference_program_call_site_count': program.get('tool_call_site_count'),
        'assumptions': assumptions,
        'question_text': text,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=ROOT/'dataset/dataset.json')
    parser.add_argument('--output-dir', type=Path, default=ROOT/'analysis_atomic_operations')
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text())
    rows = [calculate(item, json.loads((args.dataset.parent/item['graph_path']).read_text())) for item in dataset['items']]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir/'atomic_operations_draft.json').write_text(json.dumps({
        'schema_version': 'draft_reference_workload_v1',
        'warning': 'Not validated minimum atomic operations; equal macro weights and reference strategies require agreement before cross-type aggregation.',
        'dataset_id': dataset['dataset_id'], 'items': rows}, ensure_ascii=False, indent=2)+'\n')
    flat = [{**r, 'components': json.dumps(r['components']), 'assumptions': ' | '.join(r['assumptions'])} for r in rows]
    with (args.output_dir/'atomic_operations_draft.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(flat[0]));writer.writeheader();writer.writerows(flat)
    groups = defaultdict(list)
    for r in rows: groups[r['question_id']].append(r)
    print(f'{len(rows)} items; {len(groups)} question types. DRAFT, not validated minimum counts.')
    for qid, group in sorted(groups.items()):
        values = [r['draft_atomic_operation_count'] for r in group]
        print(f'{qid}: {min(values)}–{max(values)}; first item {group[0]["components"]}')

if __name__ == '__main__':
    main()
