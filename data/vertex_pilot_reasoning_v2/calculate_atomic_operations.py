"""Draft proposal for calculating the number of atomic operations.

Counting rules are provisional and need review before comparing across question types.

Reuses the existing generator corner logic (requires NumPy).
No model responses are read and dataset files are unchanged.
Every counted unit has weight 1.
Inspect output components and assumptions before aggregating across question types.

Conventions:
* union of k regions: k-1 binary unions (William's example).
* count/test n candidate objects: n object visits/tests, NOT number in the answer.
* rank n objects: n(n-1)/2 comparisons (insertion sort worst-case count).
* find minimum among n measured values: max(0,n-1) comparisons.
* a described-point lookup counts as one atomic operation.
* a region-contact test currently counts as one macro operation; its internal
  geometry/perceptual work is not expanded and needs team agreement.
* these calculations do not account for early stopping. For example, when
  checking whether two regions have the same neighbor set, one mismatch is
  enough to answer "No", but we still count the full scan. Another example is
  ordering distances d1, ..., dk: we use insertion sort's worst-case count,
  k(k-1)/2, although fewer comparisons may suffice (e.g., d1 < d2 < d3
  establishes the order without comparing d1 with d3). This is an upper bound
  for the chosen sorting procedure, not the minimum required by every method.
"""
import argparse
import csv
import json
import sys
import re
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'generator'))
import Graph
import FinalizeFaces

for module in (Graph, FinalizeFaces):
    if Path(module.__file__).resolve().parent != (ROOT / 'generator').resolve():
        raise ImportError(f"{module.__name__} was loaded from another source; run this script in a fresh Python process.")


def corner_points(graph, label):
    """Read JSON coordinates and reuse the generator's trueVertices logic.

    Build only the ordered edge view required by SetTrueVertices; do not
    regenerate the random map or implement a second corner predicate.
    """
    vertices = {
        v['id']: SimpleNamespace(p=Graph.Vector(v['x'], v['y']))
        for v in graph['vertices']
    }
    ids = list(next(r['vertex_ids'] for r in graph['regions'] if r['label'] == label))
    if len(ids) > 1 and ids[0] == ids[-1]:
        ids.pop()
    edges = []
    for i, vertex_id in enumerate(ids):
        tail, head = vertices[vertex_id], vertices[ids[(i + 1) % len(ids)]]
        edges.append(SimpleNamespace(
            tail=tail, head=head, direction=Graph.PointDirection(tail.p, head.p)))
    face = SimpleNamespace(edges=edges)
    face.trueVertices = FinalizeFaces.SetTrueVertices(face)
    # SetTrueVertices closes the list by repeating the first corner.
    return [(v.p.x, v.p.y) for v in face.trueVertices[:-1]]


def local_contact_candidates(graph, target_label):
    """Labeled regions sharing any boundary point with the target, excluding itself.

    Saved topology includes shared boundary incidence points, even when a point
    is not a corner of both regions. Outside is not in graph['regions'].
    Candidate discovery is treated as given, not separately counted.
    """
    target = next(r for r in graph['regions'] if r['label'] == target_label)
    target_ids = set(target['vertex_ids'])
    return sorted(r['label'] for r in graph['regions']
                  if r['label'] != target_label and target_ids.intersection(r['vertex_ids']))


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
        assumptions.append('Each described vertex lookup counts as one atomic operation; its internal search is not expanded.')
    def rank(count):
        add('ordering_pair_comparison', count*(count-1)//2)
        assumptions.append('Insertion sort worst-case comparison count n(n-1)/2; actual comparisons may be fewer. This is not an optimal worst-case bound across all sorting algorithms.')
    def contact(count):
        add('vertex_only_contact_test_macro', count)
        assumptions.append('Each region-pair contact classification counts as one macro; boundary work is not expanded.')
    def union():
        add('binary_union', len(evidence['source_regions'])-1)
    def corners(label):
        return len(corner_points(graph, label))
    text = q['question_text']
    if qid == 'C-009':
        target = re.search(r'touch region ([A-Z]+) only at a vertex', text).group(1)
        candidates = local_contact_candidates(graph, target)
        contact(len(candidates))
        assumptions.append('C-009 checks only regions sharing any boundary point with the target, including edge neighbors. Identifying this candidate set is not separately counted; no full-map scan is charged.')
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
        lookup(2)
        add('distance_measurement', 2*k)
        add('distance_comparison', k)
        assumptions.append('C-090 reference procedure: find the two reference vertices, then measure two distances and compare for each candidate (2 + 3k). Identifying the target region\'s candidate vertices is included in per-item processing; no separate set lookup is charged. This is not an assumption that humans/models actually follow these steps.')
        assumptions.append('Each successful comparison contributes to a running count; no extra increment cost.')
    elif qid == 'C-091':
        lookup(2)
        add('intermediate_vertex_count_visit', evidence['clockwise_intermediate']+evidence['counterclockwise_intermediate'])
        add('count_comparison', 1)
    elif qid == 'C-093':
        counts = evidence['frame_vertex_counts']
        if len(counts) != 3:
            raise ValueError('C-093 assumes exactly three regions.')
        add('frame_vertex_count_visit', sum(counts.values()))
        rank(3)
        assumptions.append('C-093 reference procedure: count frame vertices region by region, then rank the three counts (k + 3, where k is their sum). Identifying frame vertices is included in counting; recording counts is not charged separately. Off-frame corner checks are not separately counted. This is a counting convention, not a claim about actual human/model strategy or perceptual effort.')
    elif qid == 'C-095':
        counts = evidence['frame_vertex_counts']
        if len(counts) != 2:
            raise ValueError('C-095 assumes exactly two regions.')
        add('frame_vertex_count_visit', sum(counts.values()))
        add('count_comparison', 1)
        assumptions.append('C-095 reference procedure: count frame vertices in each of two regions, then compare the counts (k + 1, where k is their sum). Identifying frame vertices is included in counting; recording counts is not charged separately. Off-frame corner checks are not separately counted. This is a counting convention, not a claim about actual human/model strategy or perceptual effort.')
    elif qid == 'C-094':
        union(); add('distinct_source_vertex_membership_test_and_count', evidence['source_distinct_vertex_count'])
        assumptions.append('Source-vertex deduplication and union-boundary construction are not separately expanded.')
    elif qid == 'C-097':
        candidates = local_contact_candidates(graph, evidence['target_region'])
        k = len(evidence['contact_points'])
        if k < 2:
            raise ValueError('C-097 assumes at least two vertex-only candidates.')
        lookup(1)
        contact(len(candidates))
        add('contact_point_lookup_macro', k)
        add('distance_measurement', k)
        add('minimum_distance_comparison', k-1)
        assumptions.append('C-097 uses c local boundary-contact neighbors, including edge neighbors, and k vertex-only candidates. Count one reference-vertex lookup, c contact classifications, k contact-point lookups, k distances and k-1 minimum comparisons (c + 3k). Contact classification and locating the point for measurement are separate operations. Candidate-neighborhood discovery is not separately charged. This is a reference procedure, not a claim about actual human/model strategy.')
    elif qid == 'C-098':
        target = re.search(r'boundary of region ([A-Z]+)', text).group(1)
        candidates = local_contact_candidates(graph, target)
        lookup(1)
        contact(len(candidates))
        assumptions.append('C-098 reference procedure: find the starting vertex, then scan local boundary-contact neighbors in the specified traversal order, screening each distinct labeled neighbor once (1 + c). Edge neighbors are screened too; Outside is excluded. Record qualifying regions as encountered; no separate sorting, contact-point lookup or recording cost is charged.')
        assumptions.append('Direction cost is pending review: the current total excludes a separate clockwise/counterclockwise orientation step; adding one would give 2 + c.')
        assumptions.append('This coarse count does not separately quantify boundary tracking, maintaining order while filtering, or ordering multiple regions at the same contact point. It is not a complete measure of cognitive difficulty or a claim that all operations require equal effort.')
    elif qid == 'C-099':
        add('edge_lookup_macro', 1); add('line_extension', 1)
        candidates = local_contact_candidates(graph, evidence['target_region'])
        contact(len(candidates))
        add('line_interior_crossing_test_macro', len(evidence['all_vertex_only_neighbors']))
        assumptions.append('C-099: 2 + c + k. Find the defining edge, extend it, classify c local boundary-contact neighbors (including edge neighbors, excluding Outside), and test interior crossing for each of k vertex-only neighbors. Candidate discovery is uncharged. Never substitute answer-region count for k. Generation safeguards remove grazing ambiguity, not crossing tests; task wording is unchanged pending review by William.')
    elif qid == 'C-100':
        contact(n*(n-1)//2)
        add('contact_point_lookup_macro', len(evidence['ordered_pairs']))
        rank(len(evidence['ordered_pairs']))
        assumptions.append('C-100 reference procedure: exhaustively classify all n(n-1)/2 unordered region pairs, locate the contact point for each of k qualifying pairs, then rank them using k(k-1)/2 worst-case comparisons. This task includes whole-map search, not only local workload. Ask William whether to retain this exhaustive-search question; other search strategies may require fewer operations.')
    elif qid == 'C-101':
        union()
        source_regions = set(evidence['source_regions'])
        source_vertex_ids = set().union(*(set(r['vertex_ids']) for r in graph['regions'] if r['label'] in source_regions))
        candidates = sorted(r['label'] for r in graph['regions']
                            if r['label'] not in source_regions and source_vertex_ids.intersection(r['vertex_ids']))
        contact(len(candidates))
        assumptions.append('C-101: (k-1)+c. Form the union of k source regions, then classify c distinct other labeled regions sharing any boundary point with the union. Include edge neighbors, exclude source regions and Outside. Candidate discovery is uncharged, consistent with C-009. Any shared edge with the union disqualifies a vertex-only neighbor.')
    elif qid == 'C-102':
        targets = list(evidence['neighbor_sets'])
        candidate_sets = {target: [label for label in local_contact_candidates(graph, target) if label not in targets] for target in targets}
        contact(sum(map(len, candidate_sets.values())))
        sets = list(evidence['neighbor_sets'].values())
        add('neighbor_set_membership_test', sum(map(len, sets)))
        assumptions.append('C-102: c1+c2+k1+k2. Classify each target region’s local contact neighbors, excluding both compared regions and Outside, then check membership in both directions. Shared neighbors are classified separately for each target. Candidate discovery is uncharged; no early exit or preliminary size comparison is used.')
    else:
        raise ValueError(f'No reviewed draft rule for {qid}')
    program = item['reference_solution'].get('program') or {}
    return {
        'item_id': item['item_id'], 'question_id': qid,
        'question_type': q['question_type'],
        'original_complexity_level': item['question_complexity']['level'],
        'original_complexity_parameter': item['question_complexity']['parameter'],
        'region_count': n,
        'local_contact_candidates': candidates if qid in ('C-009', 'C-097', 'C-098', 'C-099', 'C-101') else None,
        'draft_atomic_operation_count': sum(components.values()),
        'components': components,
        'direction_cost_pending': qid == 'C-098',
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
