# Variable inputs and batch Measure

The current survey entry point is `compositional_survey.py`. Its sorting modes
already accept variable-length selections. Measure now accepts multiple angles
or regions in one RUN, with labeled results and one recorded, undoable tool call.

## Survey

- **Union:** select two or more edge-connected regions. Existing unions can be
  expanded. The existing single-union-per-diagram rule still applies; holes and
  pinched boundaries are rejected.
- **Angle / area / position sorting:** select any number of the appropriate
  objects (at least two), then Sort.
- **Distance sorting:** select the reference vertex first, then the candidate
  vertices (at least two candidates; three selected vertices are required).
- **Measure angle:** select one or more angles, then Measure → angle.
- **Measure area / edge count:** select one or more regions, then Measure →
  area / edge count.
- **Measure distance:** select the reference first, then one or more targets.
  All objects must be vertices, or all must be regions. This measures reference
  to each target, not every pair. The panel identifies the reference before RUN.
- **Cycle orientation:** exactly three vertices, as before.
- **Intersect:** a line against the diagram or one other line, as before.

The question bank keeps angle comparisons within one region. No new cross-region
angle question type is introduced.

The annotation edition (`app_2.py`) also supports one or more selected angles,
one or more region areas, and distances from the first-selected vertex to each
other selected vertex. A batch produces labeled results in one action/tool-call
record. Highlight and Draw retain their existing input requirements. Annotation
Measure retains its existing three modes: distance, angle, and area.

All sorting modes display equal ranks using `=`, for example
`v1 = v3, v2`. Position ties compare only the selected axis; distance ties compare
distance to the reference, and angle/area ties compare their respective values.
Values are compared before display rounding, with a small floating-point
tolerance. Survey records retain the flat `items` list and additionally store
`tie_groups` and `has_ties`. Python callers can request tied groups using
`tools.sort(items, by=..., reference=..., grouped=True)`; the default still
returns a flat list.

## Generate questions with configurable N

Both `generate_dataset_survey.py` and `generate_structure_complexity_test.py`
accept these arguments:

| Argument | Meaning | Existing default |
| --- | --- | --- |
| `--union-inputs N` | Constituent regions in U, for Q14/15/16/30/33 | 2 |
| `--angle-inputs N` | All N interior angles of one region, for Q11 | 4 |
| `--distance-inputs N` | Candidate points excluding the reference, for Q10 | 3 |
| `--position-inputs N` | Points to order, for Q20 | 3 |
| `--area-inputs N` | Comparison objects including U, for Q16 | Legacy policy |

For example, from this directory:

```sh
python3 generate_structure_complexity_test.py --total-items 24 --hard-only \
  --output-dir Variable_Inputs_24 --union-inputs 3 --angle-inputs 5 \
  --distance-inputs 4 --position-inputs 5 --area-inputs 4
```

The same configuration is available to Python callers:

```python
import RandomQuestions
RandomQuestions.set_input_counts(union=3, angle=5, distance=4, position=5, area=4)
```

N is configurable, not automatically randomized. Region angles require N >= 3;
other configurable counts require N >= 2. Geometry and visual separation checks
still apply, so not every N is feasible on every map. Existing dataset JSON files
and previously collected responses are not rewritten.

## Python measurement API

```python
tools.measure([A, B, C], what="area")
tools.measure([A, B, C], what="edge_count")
tools.measure([angle1, angle2, angle3], what="angle")
tools.measure([(vertex1, A), (vertex2, A)], what="angle")
tools.measure([p, q, r], what="distance", reference=origin)
```

Batch calls return a list of numeric values in input order. Scalar calls retain
their existing return type. The survey shows the object labels beside those
values and records a structured `measurements` result.

## Reference programs and behavioral records

New reference programs use `geo_reference_program_v2`, variable-length labels
(including multi-digit subscripts), and batch measurements for repeated region
measurements. The new list operations `all_equal`, `filter_by_values`, and
`argmax_by_values` associate measured values with objects by input position.
`let` binds a computed candidate collection once before it is measured.

New tool calls carry `tool_version=2026-10-02-batch-measure`. Batch Measure calls
also include `batch`, `input_count`, and an output `measurement_count`. A distance
batch's input count includes the reference; its measurement count excludes it.
Undo marks the one batch call as undone and restores the original selection.

Historical reference programs remain versioned as originally saved. Analyses
must match the reference/tool version to the trial. `tool_call_site_count` remains
the static number of call sites, not the executed count for loops, and is not a
proof that a program is the unique shortest strategy.

## Validation

```sh
MPLCONFIGDIR=/tmp/geologic-mpl python3 -m unittest \
  test_variable_inputs test_merge_multiple_regions test_annotation_measurements -q
```

Tests cover scalar compatibility, batch values, invalid selections, N-input
questions, multi-digit labels, all 24 existing reference parsers, real-map
generation, single-call logging, Undo, and existing multi-region Union cases.
Annotation tests also check batch output, call conversion, atomic rejection of
invalid or mixed selections, and frontend button logic. Set `NODE_BINARY` to a
Node.js executable to run the frontend checks when `node` is not on PATH.
