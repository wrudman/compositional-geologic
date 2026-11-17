# Vertex pilot: VLM agent and dataset

Self-contained code snapshot for GeoLogic map experiments: **74 question–diagram pairs, 16 Vertex question types**. Run Qwen3.5-9B with optional compositional tools or no tools. Model execution and offline evaluation are separate.

## Main files

| File | Purpose |
| --- | --- |
| `run_vertex_pilot.py` | Starts vLLM, verifies reasoning capture, runs/resumes episodes |
| `agent/geo_agent.py` | System prompts, tool schemas, dispatch, model loop and response logging |
| `agent/geo_env.py` | Compositional environment |
| `runner_compat.py` | Diagram reconstruction and geometry checks |
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

Each question type × complexity level has one pair; diagrams can be reused. Current `question_complexity` records the generator's question-specific parameter, **not a fully standardized atomic-operation count**. The vertex-finding tool repeatedly returned “No vertex found.” We should investigate why these selections failed. “No vertex found” is a normal tool response, so it is not counted as a tool execution error. Strategy efficiency has not yet been evaluated against validated reference programs.

This upload excludes model weights, environments, credentials, execution results, reasoning datasets, reports, caches, ZIP archives and internal taxonomy spreadsheets. Original local files are unchanged. The generator modules support replay of the packaged maps; the ad-hoc dataset-search scripts are not included.
