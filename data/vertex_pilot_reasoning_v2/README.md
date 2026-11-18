# Vertex pilot: VLM agent and dataset

Self-contained code snapshot for GeoLogic map experiments: **74 question–diagram pairs, 16 Vertex question types**. Run Qwen3.5-9B with optional compositional tools or no tools. Model execution and offline evaluation are separate.

## Main files

| File | Purpose |
| --- | --- |
| `run_vertex_pilot.py` | Starts vLLM, verifies reasoning capture, runs/resumes episodes |
| `agent/geo_agent.py` | System prompts, tool schemas, dispatch, model loop and response logging |
| `agent/geo_env.py` | Compositional environment |
| `runner_compat.py` | Diagram reconstruction and geometry checks |
| `calculate_atomic_operations.py` | Draft per-item operation counts with explicit assumptions; not validated minimum counts |
| `audit_tool_calling.py` | Offline consistency checks across saved responses, traces and message history |
| `evaluate_results.py` | Standalone format-aware scoring, no model calls |
| `geo_agent_tutorial_vertex_pilot_v1.ipynb` | Configuration and shared runner definitions; legacy filename |
| `dataset/dataset.json` | Questions, gold answers, complexity metadata and generation settings |
| `dataset/graphs/` | Saved diagram geometry for reconstruction checks |
| `generator/`, `tools/` | Frozen map generation and geometry-tool implementations |

Annotation modules remain because the inherited tutorial imports them; the batch runner only offers compositional and no-tools setups. This is a runnable snapshot, not yet a general multi-provider API runner.

## Environment

Use an existing compatible GPU/vLLM environment. `requirements.txt` lists the lightweight runner dependencies; it is **not a complete CUDA/PyTorch/vLLM lockfile**. `runtime_versions.json` records the local reconstruction-validation environment, not a complete GPU serving environment. Do not blindly upgrade an existing working serving stack.

The tested Vista serving environment used Python 3.11, PyTorch 2.13.0+cu130, vLLM `0.26.1rc1.dev1208+g80771bbbd`, and Triton 3.7.1 on ARM/Grace Hopper. A specific wheel/platform configuration may be required. Model weights are not included.

## Configure and run

From this directory, inside an allocated GPU node and activated Python environment:

```bash
export MODEL_PATH=/path/to/local/Qwen3.5-9B
export HF_HOME=/path/to/huggingface-cache
# Optional: export VLLM_PORT=8000

# First verify actual reasoning TEXT is returned and saved.
python -u run_vertex_pilot.py --capture-check-only --run-dir runs/capture_check

# New experiment; session budget includes model startup.
python -u run_vertex_pilot.py \
  --run-dir runs/raw_32768_v2 \
  --setups compositional no_tools \
  --session-minutes 110
```

The runner launches its own vLLM server; do not start another server on the same port. Configure allocation length separately through your scheduler. A session budget does not extend an allocation.

Use the **same code and run directory** on the next node to resume. A manifest checks source/config consistency, and a lock prevents concurrent writers. Saved episodes, including token-limit outcomes and recorded runtime errors, are skipped. An interrupted episode without a final JSON is attempted again. Per-request response files may contain fragments from interrupted attempts; inspect request numbering before treating them as one uninterrupted trace.

## Current experiment settings

Thinking **on**, output cap **32,768 tokens per request**, temperature 0.6, top_p 0.95, top_k 20, min_p 0, presence_penalty 0, repetition_penalty 1. Up to 10 normal requests plus one tool-disabled final-answer request when exhausted. Compositional uses `auto`; no-tools receives no tool schema. These settings live in the notebook's configuration cells. **Thinking-off has not been implemented/tested as a separate experiment in this snapshot.** Its settings and capture check must be adapted before running it.

## Output and evaluation

Runtime saves unscored episode JSON, initial/final images, model messages, prompts/tool schemas, tool traces, finish reasons, token usage and generation status. Full SDK responses and returned reasoning fields are flushed per request to `responses/*.jsonl`; tool outputs are also logged incrementally. Reasoning is not replayed into model messages. `completed` describes generation, not correctness. Gold answers remain in the dataset and are not sent to the model.

```bash
python evaluate_results.py --run-dir runs/raw_32768_v2
```

Evaluation is written separately under `evaluation/format_type_aware_v1/`. Adjusting scoring does not require rerunning the model. Ranking/traversal order is preserved; set order is ignored only for set-valued tasks. Dynamic vertex aliases may require manual review.

## Dataset and limitations

Region vertices are boundary direction changes; vertex-only contact can occur at a point that is not a corner of both regions. Reconstruction requires exact labeled topology, with a 1e-12 absolute coordinate tolerance for cross-platform floating-point differences.

Each question type × complexity level has one pair; diagrams can be reused. Current `question_complexity` records the generator's question-specific parameter, **not a fully standardized atomic-operation count**. Historical runs included repeated “No vertex found” responses. The November 17 lookup changes below address identified selection restrictions; their model-level impact has not yet been tested. “No vertex found” is a normal tool response, so it is not counted as a tool execution error. Strategy efficiency has not yet been evaluated against validated reference programs.

This upload excludes model weights, environments, credentials, execution results, reasoning datasets, reports, caches, ZIP archives and internal taxonomy spreadsheets. Original local files are unchanged. The generator modules support replay of the packaged maps; the ad-hoc dataset-search scripts are not included.

## Changes relative to William's original agent

The local comparison baseline is `data/geo_agent/` (the retained October 20 source snapshot), not a verified upstream Git commit. This package changes more than experiment parameters; it does not replace the original agent architecture.

- **Configuration:** dataset/source paths, optional compositional and no-tools conditions, 10 normal requests, recommended thinking-mode VL sampling parameters, and a 32,768-token output cap per request for the reasoning run.
- **Response recording:** save full SDK responses, returned reasoning fields, finish reasons, per-request and aggregate token usage, incremental tool traces, and generation completion/incompletion status. Returned reasoning is recorded but is not added to subsequent model messages.
- **Final-answer behavior:** after exhausting the normal request budget, send one additional request with tools disabled. Earlier responses without tool calls still end the episode, as in the original loop. This is an execution-logic change, not only logging.
- **Batch execution:** add server startup/health checks, a reasoning-text capture preflight, per-episode persistence, resumable execution, run-directory locking, and source/configuration manifests. Reconstruction checks use exact labeled topology and a 1e-12 absolute coordinate tolerance across platforms.
- **Evaluation:** keep model execution and format-aware offline scoring separate; changing scoring rules does not require a new model run.
- **Vertex selection fix (November 17, after the saved run):** Many valid vertex selections returned no result because the lookup required all regions meeting at the point to be specified. Two regions now suffice if they identify a unique shared point. `on_frame` is optional: both frame and interior points are searched unless the model explicitly specifies a filter.

The original system-prompt definitions and normal request/tool-dispatch feedback loop are largely retained. `agent/visual_tools.py` matches the local baseline; shared vertex lookup changes are in `tools/map_helpers.py` and `tools/tools_human.py`. This comparison does not establish that the full serving configuration matches William's earlier successful run, or rule out a request/parser integration issue.

**Version distinction:** the existing 32,768-token results predate the November 17 vertex fixes and are unchanged. Use a new run directory with modified source. This document describes local code; it does not confirm upload to GitHub or TACC. Human-survey checkbox changes are in the parent workspace's survey files, not this agent-only package. The atomic-operation script is a draft reference-procedure count; macro costs and sorting/search strategies need agreement before cross-type aggregation.

### Provisional line-crossing generation constraint

Future C-099 generation rejects point-only contact and boundary overlap for relevant candidate regions. Every crossed region must have at least 5% of its area on each side of the line (provisional threshold). The defining edge’s necessary overlap with its extended line is exempt. The area safeguard also applies to legacy extended-edge questions 12 and 31, alongside their existing crossing checks. Existing dataset items and answers are unchanged; use a fresh generation output/cache.
