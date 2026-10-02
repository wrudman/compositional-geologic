import argparse
import json
import math
import os
import random
import shutil
from collections import Counter
from datetime import datetime

import BuildRandomMap
import RandomQuestions
from generate_dataset_survey import ALL_QUESTION_IDS, build_question_metadata
from reference_programs import EXPERIMENTAL_QUESTION_IDS


def get_unique_dir(base_name):
    if not os.path.exists(base_name):
        return base_name
    counter = 1
    while os.path.exists(f"{base_name}({counter})"):
        counter += 1
    return f"{base_name}({counter})"


def raw_structure_metrics(res_map, max_x=1, max_y=1):
    bounded_faces = [face for face in res_map.faces if face.bounded]
    vertices = list(res_map.vertices)
    tolerance = 1e-8

    def is_on_frame(vertex):
        return (
            abs(vertex.p.x) <= tolerance
            or abs(vertex.p.x - max_x) <= tolerance
            or abs(vertex.p.y) <= tolerance
            or abs(vertex.p.y - max_y) <= tolerance
        )

    face_vertex_counts = [len(face.vertices) for face in bounded_faces]
    return {
        "region_count": len(bounded_faces),
        "total_vertex_count": int(len(vertices)),
        "interior_vertex_count": int(sum(not is_on_frame(v) for v in vertices)),
        "frame_vertex_count": int(sum(is_on_frame(v) for v in vertices)),
        "undirected_edge_count": int(len(res_map.edges) // 2),
        "nonconvex_region_count": int(
            sum(not face.convex for face in bounded_faces)
        ),
        "face_vertex_counts": face_vertex_counts,
        "mean_vertices_per_region": (
            float(sum(face_vertex_counts) / len(face_vertex_counts))
            if face_vertex_counts
            else 0
        ),
        "max_vertices_in_region": int(max(face_vertex_counts, default=0)),
    }


def successful_split_metrics(res_map):
    trace = list(getattr(res_map, "generation_trace", []))
    path_splits = [entry for entry in trace if entry["is_path_split"]]
    path_bend_count = sum(
        entry["internal_bend_count"] for entry in path_splits
    )
    return {
        "successful_split_count": len(trace),
        "successful_path_split_count": len(path_splits),
        "successful_linear_split_count": len(trace) - len(path_splits),
        "successful_path_split_ratio": (
            len(path_splits) / len(trace) if trace else 0.0
        ),
        "successful_path_bend_count": path_bend_count,
        "successful_split_trace": trace,
    }


def passes_high_complexity_quota(region_count, split_metrics):
    expected_split_count = region_count - 1
    minimum_path_splits = math.ceil(expected_split_count * 0.40)
    minimum_path_bends = minimum_path_splits * 2
    passed = (
        split_metrics["successful_split_count"] == expected_split_count
        and split_metrics["successful_path_split_count"] >= minimum_path_splits
        and split_metrics["successful_path_bend_count"] >= minimum_path_bends
    )
    return passed, {
        "minimum_successful_path_splits": minimum_path_splits,
        "minimum_successful_path_bends": minimum_path_bends,
    }


def choose_balanced_question(
    res_map,
    usage_counts,
    line_path_counts,
    question22_counts,
    question_ids=None,
    line_path_long_probability=0.65,
    hard_only=False,
):
    RandomQuestions.map = res_map
    question_ids = list(question_ids or ALL_QUESTION_IDS)
    candidate_ids = [
        question_id for question_id in question_ids
        if not hard_only or usage_counts[question_id] == 0
    ]
    random.shuffle(candidate_ids)
    candidate_ids.sort(key=lambda question_id: usage_counts[question_id])

    for question_id in candidate_ids:
        line_path_band = None
        q10_ratio_band = None
        q4_length_band = None
        q13_length_band = None
        q22_target_answer = None
        if question_id == 1:
            RandomQuestions.set_question1_complex_neighbor_filter(True)
        if question_id == 5:
            RandomQuestions.set_question5_complex_pair_filter(True)
        if question_id == 24:
            RandomQuestions.set_question24_distance_difficulty_filter(True)
        if question_id == 2:
            RandomQuestions.set_question2_high_edge_count_filter(True)
        if question_id == 4:
            q4_length_band = (
                (4, 6)
                if hard_only or random.random() < 0.65
                else (1, 3)
            )
            RandomQuestions.set_question4_answer_length_band(*q4_length_band)
        if question_id == 10:
            q10_ratio_band = (
                (1.3, 1.6)
                if hard_only or random.random() < 0.65
                else (1.6, None)
            )
            RandomQuestions.set_question10_distance_ratio_band(*q10_ratio_band)
        if question_id == 11:
            RandomQuestions.set_question11_visual_difficulty_filter(True)
        if question_id == 13:
            # High mode excludes the visually obvious three-region junctions.
            q13_length_band = (4, None)
            RandomQuestions.set_question13_answer_length_band(*q13_length_band)
        if question_id == 15:
            RandomQuestions.set_question15_complex_union_neighbor_filter(True)
        if question_id == 16:
            RandomQuestions.set_question16_balanced_union_area_filter(True)
        if question_id == 27:
            RandomQuestions.set_question27_largest_area_ratio_filter(True)
        if question_id == 22:
            next_total = question22_counts["total"] + 1
            desired_yes_total = math.ceil(0.5 * next_total)
            q22_target_answer = question22_counts["yes"] < desired_yes_total
            RandomQuestions.set_question22_visual_difficulty_filter(
                True, q22_target_answer
            )
        if question_id in {12, 18, 19}:
            # Enforce, rather than merely prefer, the selected difficulty band.
            # Choose the band from accepted-item counts, not independently on
            # every attempt. Otherwise difficult candidates fail more often and
            # the final dataset becomes strongly biased toward short answers.
            next_total = line_path_counts["total"] + 1
            desired_long_total = round(
                line_path_long_probability * next_total
            )
            needs_long = (
                hard_only
                or line_path_counts["long"] < desired_long_total
            )
            line_path_band = (
                (4, None)
                if needs_long
                else (1, 3)
            )
            RandomQuestions.set_line_path_length_band(
                question_id, *line_path_band
            )
        try:
            question, answer_text, reference_program = RandomQuestions.triesRandomQuestion(
                question_id, include_reference=True
            )
        finally:
            if question_id == 1:
                RandomQuestions.set_question1_complex_neighbor_filter(False)
            if question_id == 5:
                RandomQuestions.set_question5_complex_pair_filter(False)
            if question_id == 24:
                RandomQuestions.set_question24_distance_difficulty_filter(False)
            if question_id == 2:
                RandomQuestions.set_question2_high_edge_count_filter(False)
            if question_id == 4:
                RandomQuestions.set_question4_answer_length_band()
            if question_id == 10:
                RandomQuestions.set_question10_distance_ratio_band()
            if question_id == 11:
                RandomQuestions.set_question11_visual_difficulty_filter(False)
            if question_id == 13:
                RandomQuestions.set_question13_answer_length_band()
            if question_id == 15:
                RandomQuestions.set_question15_complex_union_neighbor_filter(False)
            if question_id == 16:
                RandomQuestions.set_question16_balanced_union_area_filter(False)
            if question_id == 27:
                RandomQuestions.set_question27_largest_area_ratio_filter(False)
            if question_id == 22:
                RandomQuestions.set_question22_visual_difficulty_filter(False)
            if question_id in {12, 18, 19}:
                RandomQuestions.set_line_path_length_band(question_id)
        if question:
            usage_counts[question_id] += 1
            if question_id == 22:
                question22_counts["total"] += 1
                question22_counts[
                    "yes" if answer_text.strip().lower() == "yes" else "no"
                ] += 1
            if line_path_band is not None:
                line_path_counts["total"] += 1
                line_path_counts[
                    "long" if line_path_band[0] == 4 else "short_medium"
                ] += 1
            metadata = build_question_metadata(
                question_id,
                question,
                answer_text,
                reference_program,
            )
            if line_path_band is not None:
                metadata["path_length_band"] = (
                    "long_4_plus"
                    if line_path_band[0] == 4
                    else "short_medium_1_to_3"
                )
                answer_regions = {
                    part.strip()
                    for part in answer_text.strip("{}[]").split(",")
                    if part.strip()
                }
                metadata["answer_distinct_region_count"] = len(answer_regions)
            if question_id == 2:
                metadata["edge_count_comparison_policy"] = {
                    "minimum_edges_per_region": 5,
                    "allowed_edge_count_differences": [0, 1, 2],
                    "target_yes_probability_when_both_available": 0.5,
                }
            if question_id == 1:
                metadata["edge_neighbor_policy"] = {
                    "minimum_diagram_regions": 6,
                    "minimum_target_region_edges": 6,
                    "answer_length_range": [4, 6],
                    "requires_vertex_only_distractor": True,
                }
            if question_id == 5:
                metadata["vertex_only_pair_policy"] = {
                    "minimum_diagram_regions": 6,
                    "answer_pair_count_range": [2, 4],
                    "minimum_edge_sharing_distractor_pairs": 2,
                    "minimum_noncontact_distractor_pairs": 2,
                    "requires_internal_answer_contact": True,
                }
            if q4_length_band is not None:
                answer_entries = [
                    part.strip()
                    for part in answer_text.strip("[]").split(",")
                    if part.strip()
                ]
                metadata["boundary_trace_band"] = (
                    "hard_4_to_6"
                    if q4_length_band[0] == 4
                    else "simple_medium_1_to_3"
                )
                metadata["answer_sequence_length"] = len(answer_entries)
                metadata["has_repeated_region"] = (
                    len(answer_entries) > len(set(answer_entries))
                )
            if q10_ratio_band is not None:
                metadata["distance_ratio_band"] = (
                    "moderate_1.3_to_1.6"
                    if q10_ratio_band[1] == 1.6
                    else "simple_1.6_plus"
                )
            if q13_length_band is not None:
                answer_entries = [
                    part.strip()
                    for part in answer_text.strip("{}").split(",")
                    if part.strip()
                ]
                metadata["meeting_regions_band"] = (
                    "hard_4_plus"
                    if q13_length_band[0] == 4
                    else "simple_medium_exactly_3"
                )
                metadata["answer_region_count"] = len(answer_entries)
            if question_id == 11:
                metadata["angle_sort_count"] = RandomQuestions.INPUT_COUNTS["angle"]
                metadata["angle_gap_policy_degrees"] = {
                    "minimum_adjacent_sorted_gap": 12,
                    "maximum_adjacent_sorted_gap": 60,
                }
            if question_id == 15:
                metadata["union_neighbor_policy"] = {
                    "minimum_diagram_regions": 5,
                    "minimum_edge_neighbors": 3,
                    "maximum_edge_neighbors": 5,
                    "minimum_union_edges": 5,
                    "requires_vertex_only_distractor": True,
                }
            if question_id == 16:
                metadata["union_area_ratio_policy"] = {
                    "comparison_count": RandomQuestions.INPUT_COUNTS["area"] or 3,
                    "union_rank": "unrestricted",
                    "minimum_adjacent_sorted_ratio": 1.3,
                    "maximum_adjacent_sorted_ratio": 1.6,
                }
            if question_id == 27:
                metadata["largest_area_ratio_policy"] = {
                    "minimum_largest_to_second_ratio": 1.3,
                    "maximum_largest_to_second_ratio": 1.5,
                }
            if question_id == 22:
                metadata["segment_intersection_policy"] = {
                    "minimum_segment_length_fraction_of_frame_diagonal": 0.30,
                    "minimum_bounding_box_overlap_fraction_per_axis": 0.03,
                    "target_answer": "Yes" if q22_target_answer else "No",
                    "yes_intersection_parameter_range": [0.15, 0.85],
                    "no_case": "finite-segment near miss with intersecting infinite lines",
                }
            if question_id == 24:
                metadata["region_distance_policy"] = {
                    "minimum_far_to_close_ratio": 1.3,
                    "maximum_far_to_close_ratio": 1.6,
                    "minimum_close_distance_fraction_of_frame_diagonal": 0.05,
                }
            return metadata
    return None


def generate_test_dataset(
    total_items=30,
    output_dir="Structure_Complexity_High_30_Test",
    master_seed=20260820,
    max_attempts=30000,
    hard_only=False,
):
    if total_items not in {24, 28, 30}:
        raise ValueError("This generator supports 24-, 28-, or 30-item test designs.")

    question_ids = (
        list(ALL_QUESTION_IDS) + list(EXPERIMENTAL_QUESTION_IDS)
        if total_items == 28
        else list(ALL_QUESTION_IDS)
    )

    random.seed(master_seed)
    results_dir = get_unique_dir(output_dir)
    image_dir = os.path.join(results_dir, "images_color")
    os.makedirs(image_dir, exist_ok=True)

    if total_items in {24, 28}:
        # Keep every all-hard item out of trivially small diagrams while
        # distributing the 24 enabled question types across sizes 6–12.
        targets = (
            [region_count for region_count in range(6, 9) for _ in range(4)]
            + [region_count for region_count in range(9, 13) for _ in range(3)]
        )
        if total_items == 28:
            targets += [8, 9, 10, 11]
    else:
        targets = [region_count for region_count in range(3, 13) for _ in range(3)]
    random.shuffle(targets)
    usage_counts = Counter({question_id: 0 for question_id in question_ids})
    line_path_counts = Counter({"total": 0, "long": 0, "short_medium": 0})
    question22_counts = Counter({"total": 0, "yes": 0, "no": 0})
    failed_question_attempts = Counter()
    seeds_used = set()
    items = []
    attempts = 0

    while targets and attempts < max_attempts:
        attempts += 1
        target_region_count = targets[0]
        seed = random.randint(1, 1_000_000_000)
        if seed in seeds_used:
            continue

        try:
            res_map = BuildRandomMap.BuildRandomMap(
                target_region_count,
                1,
                1,
                seed,
                structure_complexity="high",
            )
            metrics = raw_structure_metrics(res_map)
            if metrics["region_count"] != target_region_count:
                continue

            split_metrics = successful_split_metrics(res_map)
            passes_quota, quota = passes_high_complexity_quota(
                target_region_count, split_metrics
            )
            if not passes_quota:
                continue

            before = usage_counts.copy()
            question = choose_balanced_question(
                res_map,
                usage_counts,
                line_path_counts,
                question22_counts,
                question_ids=question_ids,
                hard_only=hard_only,
            )
            if not question:
                for question_id in question_ids:
                    failed_question_attempts[question_id] += 1
                continue
            question["targeting_policy"] = "complex_local_targets"

            for question_id in question_ids:
                if usage_counts[question_id] == before[question_id]:
                    failed_question_attempts[question_id] += 1

            item_index = len(items)
            base_name = (
                f"item_{item_index:03d}_regions_{target_region_count}_seed_{seed}"
            )
            image_filename = f"{base_name}_color.png"
            shutil.move(
                "Attempt1_color.png",
                os.path.join(image_dir, image_filename),
            )
            if os.path.exists("Attempt1_bw.png"):
                os.remove("Attempt1_bw.png")

            items.append({
                "item_id": f"item_{item_index:03d}",
                "generator_mode": "high_internal_test",
                "seed": seed,
                "image_path": os.path.join("images_color", image_filename),
                "structure_metrics": metrics,
                "successful_split_metrics": split_metrics,
                "complexity_acceptance_quota": quota,
                "question": question,
            })
            seeds_used.add(seed)
            targets.pop(0)
            print(
                f"[{len(items):02d}/{total_items}] regions={target_region_count}, "
                f"vertices={metrics['total_vertex_count']}, "
                f"interior={metrics['interior_vertex_count']}, "
                f"paths={split_metrics['successful_path_split_count']}/"
                f"{split_metrics['successful_split_count']}, "
                f"bends={split_metrics['successful_path_bend_count']}, "
                f"question_id={question['question_id']}"
            )
        except Exception:
            continue

    if targets:
        raise RuntimeError(
            f"Generated only {len(items)} items after {attempts} attempts."
        )
    if hard_only:
        missing_or_repeated = {
            question_id: usage_counts[question_id]
            for question_id in question_ids
            if usage_counts[question_id] != 1
        }
        if missing_or_repeated:
            raise RuntimeError(
                f"All-hard {total_items}-item design must contain each enabled question "
                f"type exactly once: {missing_or_repeated}"
            )

    metadata = {
        "dataset_version": (
            f"structure_complexity_all_hard_{total_items}_v1"
            if hard_only
            else "structure_complexity_high_local_targets_test_v2"
        ),
        "dataset_role": "internal_test",
        "generator_mode": "high",
        "hard_only": bool(hard_only),
        "question_targeting_policy": "complex_local_targets",
        "line_path_question_policy": {
            "question_ids": [12, 18, 19],
            "counting_rule": "distinct_regions",
            "target_long_4_plus_proportion": 1.0 if hard_only else 0.65,
            "accepted_item_counts": dict(line_path_counts),
            "actual_long_4_plus_proportion": (
                line_path_counts["long"] / line_path_counts["total"]
                if line_path_counts["total"]
                else None
            ),
            "selection_rule": "hard_filter",
            "quota_rule": "deterministic_from_accepted_items",
        },
        "question2_edge_count_policy": {
            "minimum_edges_per_region": 5,
            "allowed_edge_count_differences": [0, 1, 2],
            "target_yes_probability_when_both_available": 0.5,
            "selection_rule": "hard_filter",
        },
        "question1_edge_neighbor_policy": {
            "minimum_diagram_regions": 6,
            "minimum_target_region_edges": 6,
            "answer_length_range": [4, 6],
            "requires_vertex_only_distractor": True,
            "selection_rule": "hard_filter",
        },
        "question5_vertex_only_pair_policy": {
            "minimum_diagram_regions": 6,
            "answer_pair_count_range": [2, 4],
            "minimum_edge_sharing_distractor_pairs": 2,
            "minimum_noncontact_distractor_pairs": 2,
            "requires_internal_answer_contact": True,
            "selection_rule": "hard_filter",
        },
        "line_path_visual_clearance_policy": {
            "question_ids": [12, 18, 19],
            "minimum_clearance_fraction_of_frame_diagonal": 0.012,
            "interior_sample_fractions": [0.25, 0.5, 0.75],
            "purpose": "reject near-boundary paths that are mathematically but not visually unambiguous",
            "selection_rule": "hard_filter",
        },
        "question4_boundary_trace_policy": {
            "hard_probability": 1.0 if hard_only else 0.65,
            "hard_answer_sequence_range": [4, 6],
            "simple_medium_probability": 0.0 if hard_only else 0.35,
            "simple_medium_answer_sequence_range": [1, 3],
            "prefer_repeated_region_in_hard_band": True,
            "selection_rule": "hard_filter",
        },
        "question13_meeting_regions_policy": {
            "hard_probability": 1.0,
            "hard_answer_length_minimum": 4,
            "simple_medium_probability": 0.0,
            "standard_mode_note": "Three-region junctions remain available outside high mode.",
            "selection_rule": "hard_filter",
        },
        "question22_segment_intersection_policy": {
            "minimum_segment_length_fraction_of_frame_diagonal": 0.30,
            "minimum_bounding_box_overlap_fraction_per_axis": 0.03,
            "target_yes_probability": 0.5,
            "yes_intersection_parameter_range": [0.15, 0.85],
            "no_case": "finite-segment near miss with intersecting infinite lines",
            "accepted_item_counts": dict(question22_counts),
            "selection_rule": "hard_filter",
        },
        "question24_region_distance_policy": {
            "minimum_far_to_close_ratio": 1.3,
            "maximum_far_to_close_ratio": 1.6,
            "minimum_close_distance_fraction_of_frame_diagonal": 0.05,
            "selection_rule": "hard_filter",
        },
        "question10_distance_sort_policy": {
            "comparison_count": 3,
            "moderate_probability": 1.0 if hard_only else 0.65,
            "moderate_adjacent_ratio_range": [1.3, 1.6],
            "simple_probability": 0.0 if hard_only else 0.35,
            "simple_minimum_adjacent_ratio": 1.6,
            "minimum_distance_fraction_of_frame_diagonal": 0.08,
            "selection_rule": "hard_filter",
        },
        "question11_angle_sort_policy": {
            "angle_count": 4,
            "minimum_adjacent_sorted_gap_degrees": 12,
            "maximum_adjacent_sorted_gap_degrees": 60,
            "purpose": "challenging but visually answerable without measurement tools",
            "selection_rule": "hard_filter",
        },
        "question15_union_neighbor_policy": {
            "minimum_diagram_regions": 5,
            "minimum_edge_neighbors": 3,
            "maximum_edge_neighbors": 5,
            "minimum_union_edges": 5,
            "requires_vertex_only_distractor": True,
            "selection_rule": "hard_filter",
        },
        "question16_union_area_policy": {
            "comparison_count": 3,
            "union_rank": "unrestricted",
            "minimum_adjacent_sorted_ratio": 1.3,
            "maximum_adjacent_sorted_ratio": 1.6,
            "selection_rule": "hard_filter",
        },
        "question27_largest_area_policy": {
            "minimum_largest_to_second_ratio": 1.3,
            "maximum_largest_to_second_ratio": 1.5,
            "selection_rule": "hard_filter",
        },
        "classification_note": (
            "The high label is a generation setting only. Use structure_metrics "
            "as raw data for later classification."
        ),
        "acceptance_rule": (
            "Every accepted diagram has at least ceil((region_count - 1) * 0.40) "
            "successful Path splits and at least two successful Path bends per "
            "required Path split."
        ),
        "master_seed": master_seed,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_items": len(items),
        "region_count_design": (
            "4 items for counts 6-8 and 3 items for counts 9-12"
            if total_items == 24
            else (
                "24-item 6-12 design plus one additional item for counts 8-12"
                if total_items == 28
                else "3 items for every count from 3 through 12"
            )
        ),
        "question_usage": dict(sorted(usage_counts.items())),
        "question_nonselection_counts": dict(sorted(failed_question_attempts.items())),
        "items": items,
    }

    json_filename = (
        f"dataset_{total_items}_all_hard.json"
        if hard_only else "dataset_30_high_test.json"
    )
    json_path = os.path.join(results_dir, json_filename)
    with open(json_path, "w", encoding="utf-8") as output_file:
        json.dump(metadata, output_file, indent=2, ensure_ascii=False)

    jsonl_filename = (
        f"dataset_{total_items}_all_hard.jsonl"
        if hard_only else "dataset_30_high_test.jsonl"
    )
    jsonl_path = os.path.join(results_dir, jsonl_filename)
    with open(jsonl_path, "w", encoding="utf-8") as output_file:
        for item in items:
            output_file.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"Finished: {results_dir}")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="Structure_Complexity_High_30_Test")
    parser.add_argument("--seed", type=int, default=20260820)
    parser.add_argument("--max-attempts", type=int, default=30000)
    parser.add_argument("--total-items", type=int, choices=[24, 28, 30], default=30)
    parser.add_argument("--hard-only", action="store_true")
    RandomQuestions.add_input_count_arguments(parser)
    args = parser.parse_args()
    RandomQuestions.configure_input_count_arguments(args)
    generate_test_dataset(
        total_items=args.total_items,
        output_dir=args.output_dir,
        master_seed=args.seed,
        max_attempts=args.max_attempts,
        hard_only=args.hard_only,
    )
