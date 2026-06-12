import BuildRandomMap
import RandomQuestions
import os
import shutil
import random
import json

# counter to make sure we have a more balanced datset
usage_counts = {i: 0 for i in range(1, 30)} # IDs 1 through 29

def get_unique_dir(base_name):
    """
    Prevents overwriting by appending (1), (2), etc. to the directory name.
    """
    if not os.path.exists(base_name):
        return base_name
    
    counter = 1
    while True:
        new_name = f"{base_name}({counter})"
        if not os.path.exists(new_name):
            return new_name
        counter += 1

def get_problem_tiered_questions(res_map, usage_counts):
    problem_buckets = {
        "easy": [1, 8, 9, 13, 26, 27],
        "medium": [2, 3, 5, 6, 7, 10, 11, 14, 15, 16, 20, 23, 24, 25, 28],
        "hard": [4, 12, 17, 18, 19, 21, 22] 
    }
    
    RandomQuestions.map = res_map
    tiered_qa = {}

    for tier, keys in problem_buckets.items():
        # Sort keys based on how FEW times they've been used
        # This prioritizes under-used questions
        pool = sorted(keys, key=lambda x: usage_counts.get(x, 0))
        
        found = False
        for key in pool:
            question, answer_text = RandomQuestions.triesRandomQuestion(key)
            if question:
                tiered_qa[tier] = {
                    "question": question,
                    "answer": answer_text,
                    "question_id": key
                }
                found = True
                break # Move to next tier
    return tiered_qa

def run_pilot_generation(total_images=100):
    """
    Main pipeline: Generates geometric maps, saves Color/BW pairs, 
    and creates the master metadata JSON.
    """
    base_dir = "Pilot_100_Samples"
    results_dir = get_unique_dir(base_dir)
    os.makedirs(results_dir)
    
    # Create subdirectories for images
    os.makedirs(os.path.join(results_dir, "images_color"))
    os.makedirs(os.path.join(results_dir, "images_bw"))

    seeds_used = set()
    dataset_list = []

    print(f"🚀 Initializing generation: Target = {total_images} samples.")

    success_count = 0
    while success_count < total_images:
        seed = random.randint(1, 1000000)
        if seed in seeds_used: 
            continue
        
        # Randomly sample face counts to ensure structural diversity (3 to 12 faces)
        target_n = random.randint(3, 12)
        
        try:
            # Build the random geometric map
            res_map = BuildRandomMap.BuildRandomMap(target_n, 1, 1, seed)
            actual_faces = len([f for f in res_map.faces if f.bounded])
            
            # Validation: Ensure generated face count matches target
            if actual_faces == target_n:
                qa_dict = get_problem_tiered_questions(res_map)
                
                # Only save if all 3 tiers (Easy, Med, Hard) were successfully generated
                if len(qa_dict) == 3:
                    
                    base_name = f"img_{success_count:03d}_faces_{target_n}_seed_{seed}"
                    
                    color_filename = f"{base_name}_color.png"
                    bw_filename = f"{base_name}_bw.png"

                    if target_n <= 5:
                        diag_comp = "easy"
                    elif target_n <= 8:
                        diag_comp = "medium"
                    else:
                        diag_comp = "hard"
                    
                    for tier in qa_dict:
                        q_id = qa_dict[tier]["question_id"]
                        usage_counts[q_id] += 1
                    # Move generated temporary files to the organized folders
                    # Assuming BuildRandomMap outputs 'Attempt1_color.png' and 'Attempt1_bw.png'
                    shutil.move("Attempt1_color.png", os.path.join(results_dir, "images_color", color_filename))
                    shutil.move("Attempt1_bw.png", os.path.join(results_dir, "images_bw", bw_filename))

                    # Construct the Metadata Dictionary for this sample
                    row = {
                        "id": success_count,
                        "face_count": target_n,
                        "diagram_complexity": diag_comp,  # Added here
                        "image_path_color": os.path.join("images_color", color_filename),
                        "image_path_bw": os.path.join("images_bw", bw_filename),
                        "questions": qa_dict, 
                        "seed": seed
                    }
                    dataset_list.append(row)
                    
                    seeds_used.add(seed)
                    success_count += 1
                    if success_count % 10 == 0:
                        print(f"   [Log] {success_count}/{total_images} samples completed.")
        
        except Exception as e:
            # Silent catch for map generation failures (common in geometric edge cases)
            continue

    # Save to standard JSON (Prettified for human reading)
    json_path = os.path.join(results_dir, "dataset_pilot.json")
    with open(json_path, "w") as f:
        json.dump(dataset_list, f, indent=4)

    # Save to JSONL (Standard format for TACC/LLM training pipelines)
    jsonl_path = os.path.join(results_dir, "dataset_pilot.jsonl")
    with open(jsonl_path, "w") as f:
        for entry in dataset_list:
            f.write(json.dumps(entry) + "\n")

    print(f"\n✅ Pipeline Finished!")
    print(f"📂 Master Directory: {results_dir}")
    print(f"📊 Summary: {len(dataset_list)} images generated with {len(dataset_list)*3} total QAs.")

if __name__ == "__main__":
    run_pilot_generation(100)
