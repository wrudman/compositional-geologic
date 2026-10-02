import BuildRandomMap
import RandomQuestions
import argparse
import json
import os
import random
import re
import shutil
from datetime import datetime
from reference_programs import (
    ACTIVE_QUESTION_IDS as REFERENCE_PROGRAM_QUESTION_IDS,
    build_reference_program,
)


REGION_COUNTS = list(range(3, 13))
MEDIUM_REGION_COUNTS = {6, 7, 8, 9}
DEFAULT_TOTAL_PAIRS = 24
DATASET_ROLE = "internal_demo"

# The final 24-type design removes Q24, Q25, Q27, and Q28 from the previous
# 28-type hard-mode set while retaining compositional questions Q30-Q33.
ALL_QUESTION_IDS = [
    1, 2, 4, 5, 8, 9, 10, 11, 12, 13, 14, 15,
    16, 18, 19, 20, 21, 22, 23, 26, 30, 31, 32, 33,
]
TWO_CHOICE_OPTIONS_BY_QUESTION_ID = {
    2: ["Yes", "No"],
    21: ["Clockwise", "Counterclockwise"],
    22: ["Yes", "No"],
    25: ["Yes", "No"],
    28: ["Above", "Below"],
    33: ["Yes", "No"],
}
REGION_CHOICE_QUESTION_IDS = {24}

if len(ALL_QUESTION_IDS) != 24:
    raise ValueError(
        f"Expected exactly 24 active question ids, found {len(ALL_QUESTION_IDS)}."
    )
if tuple(ALL_QUESTION_IDS) != REFERENCE_PROGRAM_QUESTION_IDS:
    raise ValueError(
        "Active dataset questions and reference-program coverage are out of sync."
    )


def get_unique_dir(base_name):
    if not os.path.exists(base_name):
        return base_name
    counter = 1
    while True:
        candidate = f"{base_name}({counter})"
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def target_quota_by_region_count(total_pairs):
    """
    Supported balanced designs:
    - 20 pairs: 2 diagrams for each region count from 3 through 12.
    - 24 pairs: the 20-pair design plus one extra diagram for 6, 7, 8 and 9.
    """
    if total_pairs not in {20, 24}:
        raise ValueError("total_pairs must be either 20 or 24.")
    return {
        region_count: (
            3
            if total_pairs == 24 and region_count in MEDIUM_REGION_COUNTS
            else 2
        )
        for region_count in REGION_COUNTS
    }


def diagram_complexity(region_count):
    if region_count <= 5:
        return "easy"
    if region_count <= 9:
        return "medium"
    return "hard"


def _answer_matches_choices(answer_text, choices):
    answer_lower = str(answer_text).strip().lower()
    return answer_lower in {str(choice).strip().lower() for choice in choices}


def get_region_choice_options(question_id, question_text, answer_text):
    if question_id not in REGION_CHOICE_QUESTION_IDS:
        return None

    match = re.search(r":\s*([A-Z])\s+or\s+([A-Z])\?", question_text)
    if not match:
        return None

    choices = [match.group(1), match.group(2)]
    return choices if _answer_matches_choices(answer_text, choices) else None


def infer_two_choice_options(question_text, answer_text):
    question_lower = question_text.lower()
    answer_lower = str(answer_text).strip().lower()

    yes_no_question = re.match(
        r"^\s*(do|does|did|is|are|was|were|can|could|will|would|has|have)\b",
        question_lower,
    )
    if yes_no_question and answer_lower in {"yes", "no"}:
        return ["Yes", "No"]

    if (
        re.search(r"\bclockwise\s+or\s+counterclockwise\b", question_lower)
        or re.search(r"\bcounterclockwise\s+or\s+clockwise\b", question_lower)
        or re.search(r"\bcounter-clockwise\s+or\s+clockwise\b", question_lower)
        or re.search(r"\bclockwise\s+or\s+counter-clockwise\b", question_lower)
    ) and answer_lower in {"clockwise", "counterclockwise", "counter-clockwise"}:
        return ["Clockwise", "Counterclockwise"]

    if (
        re.search(r"\babove\s+or\s+below\b", question_lower)
        or re.search(r"\bbelow\s+or\s+above\b", question_lower)
    ) and answer_lower in {"above", "below"}:
        return ["Above", "Below"]

    return None


def build_question_metadata(
    question_id, question_text, answer_text, reference_program=None
):
    choices = None
    if question_id in TWO_CHOICE_OPTIONS_BY_QUESTION_ID:
        candidate_choices = TWO_CHOICE_OPTIONS_BY_QUESTION_ID[question_id]
        if _answer_matches_choices(answer_text, candidate_choices):
            choices = candidate_choices
    if choices is None:
        choices = get_region_choice_options(question_id, question_text, answer_text)
    if choices is None:
        choices = infer_two_choice_options(question_text, answer_text)
    metadata = {
        "question_id": question_id,
        "question_text": question_text,
        "answer": answer_text,
        "answer_type": "two_choice" if choices else "fill_in_the_blank",
        "reference_program": (
            reference_program
            if reference_program is not None
            else build_reference_program(question_id, question_text)
        ),
    }
    if choices:
        metadata["choices"] = choices
    # Store actual arities from the generated program, not global defaults.
    def calls(value):
        if isinstance(value, dict):
            if value.get("node") == "call":
                yield value
            for child in value.values():
                yield from calls(child)
        elif isinstance(value, list):
            for child in value:
                yield from calls(child)
    metadata["operation_input_counts"] = [
        {"tool": node["function"],
         "count": len(node["args"][0]) if node["function"] == "sort" else len(node["args"]),
         "reference_count": int("reference" in node.get("kwargs", {}))}
        for node in calls(metadata["reference_program"])
        if node["function"] in ("sort", "merge")
    ]
    return metadata


def choose_question_for_map(res_map, remaining_question_ids):
    """
    Returns one randomly selected question for this diagram.
    Each active question id is used at most once across the full dataset.
    """
    RandomQuestions.map = res_map
    candidate_ids = list(remaining_question_ids)
    random.shuffle(candidate_ids)

    for question_id in candidate_ids:
        question, answer_text, reference_program = (
            RandomQuestions.triesRandomQuestion(
                question_id, include_reference=True
            )
        )
        if question:
            remaining_question_ids.remove(question_id)
            return build_question_metadata(
                question_id, question, answer_text, reference_program
            )

    return None


def move_generated_images(results_dir, base_name):
    color_src = "Attempt1_color.png"
    color_filename = f"{base_name}_color.png"

    if os.path.exists(color_src):
        shutil.move(color_src, os.path.join(results_dir, "images_color", color_filename))
    else:
        color_filename = ""

    return os.path.join("images_color", color_filename) if color_filename else ""


def generate_balanced_dataset(
    total_pairs=DEFAULT_TOTAL_PAIRS,
    output_dir=None,
    max_attempts=20000,
    master_seed=None,
):
    if output_dir is None:
        output_dir = f"Balanced_{total_pairs}_Diagram_Question_Pairs"
    if master_seed is not None:
        random.seed(master_seed)

    results_dir = get_unique_dir(output_dir)
    os.makedirs(os.path.join(results_dir, "images_color"), exist_ok=True)

    quotas = target_quota_by_region_count(total_pairs)
    completed_by_region_count = {region_count: 0 for region_count in REGION_COUNTS}
    remaining_question_ids = set(ALL_QUESTION_IDS)
    seeds_used = set()
    dataset = []

    attempts = 0
    pair_index = 0
    print(f"Starting balanced generation in {results_dir}")
    print(f"Target quotas: {quotas}")

    while (
        sum(completed_by_region_count.values()) < total_pairs
        and attempts < max_attempts
    ):
        attempts += 1

        remaining_counts = [
            region_count
            for region_count in REGION_COUNTS
            if completed_by_region_count[region_count] < quotas[region_count]
        ]
        if not remaining_counts:
            break

        # Pick the most under-filled region count first, with random tie-breaking.
        min_progress = min(
            completed_by_region_count[count] / quotas[count]
            for count in remaining_counts
        )
        most_underfilled = [
            count
            for count in remaining_counts
            if completed_by_region_count[count] / quotas[count] == min_progress
        ]
        target_region_count = random.choice(most_underfilled)

        seed = random.randint(1, 1_000_000_000)
        if seed in seeds_used:
            continue

        try:
            res_map = BuildRandomMap.BuildRandomMap(target_region_count, 1, 1, seed)
            actual_region_count = len([face for face in res_map.faces if face.bounded])
            if actual_region_count != target_region_count:
                continue

            question = choose_question_for_map(res_map, remaining_question_ids)
            if not question:
                continue

            base_name = (
                f"pair_{pair_index:03d}"
                f"_regions_{target_region_count}"
                f"_seed_{seed}"
            )
            color_path = move_generated_images(results_dir, base_name)

            dataset.append({
                "pair_id": f"pair_{pair_index:03d}",
                "region_count": target_region_count,
                "diagram_complexity": diagram_complexity(target_region_count),
                "seed": seed,
                "image_path": color_path,
                "question": question,
            })

            seeds_used.add(seed)
            completed_by_region_count[target_region_count] += 1
            pair_index += 1

            print(
                f"[{pair_index:02d}/{total_pairs}] regions={target_region_count}, "
                f"seed={seed}, question_id={question['question_id']}"
            )

        except Exception:
            continue

    if len(dataset) != total_pairs:
        raise RuntimeError(
            f"Only generated {len(dataset)} pairs after {attempts} attempts. "
            "Increase max_attempts or inspect map/question generation failures."
        )

    used_question_ids = [item["question"]["question_id"] for item in dataset]
    if (
        len(set(used_question_ids)) != total_pairs
        or not set(used_question_ids).issubset(ALL_QUESTION_IDS)
    ):
        raise RuntimeError(
            "Question uniqueness validation failed. "
            f"Used ids: {sorted(used_question_ids)}"
        )

    random.shuffle(dataset)
    metadata = {
        "dataset_version": f"demo_{total_pairs}_v1",
        "dataset_role": DATASET_ROLE,
        "master_seed": master_seed,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_pairs": len(dataset),
        "region_count_quota": quotas,
        "medium_region_counts_with_extra_diagram": sorted(MEDIUM_REGION_COUNTS),
        "excluded_question_ids": [3, 6, 7, 17],
        "active_question_ids": sorted(ALL_QUESTION_IDS),
        "items": dataset,
    }

    json_path = os.path.join(
        results_dir, f"dataset_{total_pairs}_balanced.json"
    )
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    jsonl_path = os.path.join(
        results_dir, f"dataset_{total_pairs}_balanced.jsonl"
    )
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for item in dataset:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print("\nFinished.")
    print(f"Directory: {results_dir}")
    print(f"JSON: {json_path}")
    print(f"JSONL: {jsonl_path}")
    print(f"Region count summary: {completed_by_region_count}")
    print(f"Unused active question ids: {sorted(remaining_question_ids)}")
    return metadata


def generate_balanced_24_dataset(
    output_dir="Balanced_24_Diagram_Question_Pairs",
    max_attempts=20000,
):
    """Backward-compatible entry point for existing callers."""
    return generate_balanced_dataset(
        total_pairs=24,
        output_dir=output_dir,
        max_attempts=max_attempts,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate a balanced survey dataset."
    )
    parser.add_argument(
        "--total-pairs",
        type=int,
        choices=(20, 24),
        default=DEFAULT_TOTAL_PAIRS,
    )
    parser.add_argument("--output-dir")
    parser.add_argument("--max-attempts", type=int, default=20000)
    parser.add_argument("--seed", type=int)
    RandomQuestions.add_input_count_arguments(parser)
    args = parser.parse_args()
    RandomQuestions.configure_input_count_arguments(args)
    generate_balanced_dataset(
        total_pairs=args.total_pairs,
        output_dir=args.output_dir,
        max_attempts=args.max_attempts,
        master_seed=args.seed,
    )
