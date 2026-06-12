import BuildRandomMap
import RandomQuestions
import os
import shutil
import random
import json
import glob

def get_unique_dir(base_name):
    """Creates a unique directory name to avoid overwriting previous runs."""
    if not os.path.exists(base_name):
        return base_name
    counter = 1
    while True:
        new_name = f"{base_name}_{counter}"
        if not os.path.exists(new_name):
            return new_name
        counter += 1

problem_id = 22
def get_specific_questions(res_map):
    """
    Attempts to generate answers for specific geometry questions.
    Now includes Question 17 and handles variable return lengths safely.
    """
    target_keys = [22]
    RandomQuestions.map = res_map
    qa_results = {}

    for key in target_keys:
        try:
            result = RandomQuestions.triesRandomQuestion(key)
            
            # Check if result exists and is a sequence (tuple or list)
            if result and isinstance(result, (tuple, list)) and len(result) >= 2:
                # Flexible unpacking: captures first two regardless of total length
                question = result[0]
                answer_text = result[1]
                
                # Capture extra metadata if the function returns 4 values
                metadata = result[2:] if len(result) > 2 else None

                if question:
                    qa_results[f"Q{key}"] = {
                        "question": question,
                        "answer": answer_text,
                    }
                    # Optionally store metadata in the JSON if it exists
                    if metadata:
                        qa_results[f"Q{key}"]["metadata"] = metadata
                        
        except Exception as e:
            print(f"      [QA Error] Question {key} failed: {e}")
            continue
            
    return qa_results

def run_mini_pilot(total_images=10):
    """
    Main loop to generate a set of maps and their corresponding QA pairs.
    """
    base_dir = "New_Questions_problem_"+str(problem_id)
    results_dir = get_unique_dir(base_dir)
    os.makedirs(results_dir)
    os.makedirs(os.path.join(results_dir, "images"))

    dataset_list = []
    success_count = 0
    
    print(f"🚀 Starting Pilot: Target is {total_images} maps.")

    while success_count < total_images:
        seed = random.randint(1, 100000)
        # 5-10 faces provide enough complexity for the questions
        target_n = random.randint(5, 10) 
        
        try:
            # 1. Generate the map geometry
            res_map = BuildRandomMap.BuildRandomMap(target_n, 1, 1, seed)
            
            # 2. Find the generated image file immediately
            source_candidates = ["Attempt1_color.png", "color.png"]
            found_source = None
            for cand in source_candidates:
                if os.path.exists(cand):
                    found_source = cand
                    break
            
            # 3. Generate questions for this map
            qa_batch = get_specific_questions(res_map)
            
            # 4. Save if we have at least 1 valid question
            if len(qa_batch) >= 1: 
                img_name = f"pilot_{success_count:02d}_seed_{seed}.png"
                dest_path = os.path.join(results_dir, "images", img_name)
                
                if found_source:
                    shutil.move(found_source, dest_path)
                    # Clean up the black and white version if it exists
                    if os.path.exists("Attempt1_bw.png"):
                        os.remove("Attempt1_bw.png")
                else:
                    print(f"   [Warning] Geometry success but no image file found in root!")

                entry = {
                    "id": success_count,
                    "seed": seed,
                    "face_count": target_n,
                    "image": img_name,
                    "qa_pairs": qa_batch
                }
                dataset_list.append(entry)
                success_count += 1
                print(f"   [Success] Map {success_count}/{total_images} saved (Seed: {seed})")
            else:
                print(f"   [Skip] Seed {seed} produced 0 valid questions.")
                
        except Exception as e:
            print(f"   [Runtime Error] Skipping seed {seed} due to: {e}")
            continue

    # Finalize metadata
    metadata_path = os.path.join(results_dir, "pilot_metadata.json")
    with open(metadata_path, "w") as f:
        json.dump(dataset_list, f, indent=4)

    print(f"\n✅ Pilot Complete! Results saved in: {results_dir}")

if __name__ == "__main__":
    run_mini_pilot(total_images=10)