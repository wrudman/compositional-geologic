import BuildRandomMap
import RandomQuestions # Import your question engine
import os
import shutil
import random

def get_tiered_questions(res_map):
    """
    Uses RandomQuestions logic to pull 1 Easy, 1 Medium, and 1 Hard question.
    """
    # Define buckets based on your RandomQuestions.py keys
    buckets = {
        "Easy": [1, 8, 9, 13],
        "Medium": [3, 5, 6, 7, 10, 11, 14, 15, 18, 20, 23, 24],
        "Hard": [2, 4, 12, 16, 17, 18, 19, 21, 22] 
    }
    
    # Set the global map in RandomQuestions so the functions can see it
    RandomQuestions.map = res_map
    
    qa_results = []
    for tier_name, keys in buckets.items():
        pool = keys.copy()
        random.shuffle(pool)
        
        found = False
        while not found and len(pool) > 0:
            key = pool.pop()
            # Call your existing logic
            question, answer_text = RandomQuestions.triesRandomQuestion(key)
            if question: # If quality > 0 and question is not False
                qa_results.append((tier_name, question, answer_text))
                found = True
    return qa_results

def run_systematic_test():
    results_dir = "Run_Results_Balanced"
    if os.path.exists(results_dir):
        shutil.rmtree(results_dir)
    os.makedirs(results_dir)

    tiers = {
        "Easy": range(3, 7),     # 3, 4, 5, 6
        "Medium": range(7, 11),   # 7, 8, 9, 10
        "Hard": range(11, 16)     # 11, 12, 13, 14, 15
    }

    samples_per_face_count = 5
    seeds_used = set()

    print(f"\n--- Starting Generation with Tiered Questions ---")

    for tier_name, face_range in tiers.items():
        tier_path = os.path.join(results_dir, tier_name)
        os.makedirs(tier_path)

        for target_n in face_range:
            print(f"   Targeting {target_n} faces:")
            success_for_this_count = 0
            
            while success_for_this_count < samples_per_face_count:
                seed = random.randint(1, 1000000)
                if seed in seeds_used: continue
                
                try:
                    res_map = BuildRandomMap.BuildRandomMap(target_n, 1, 1, seed)
                    actual_faces = len([f for f in res_map.faces if f.bounded])
                    
                    if actual_faces == target_n:
                        # 1. Generate the Q&A pairs first
                        qa_set = get_tiered_questions(res_map)
                        
                        # Only proceed if we actually got all 3 question types
                        if len(qa_set) == 3:
                            base_filename = f"Faces_{target_n}_Seed_{seed}"
                            
                            # 2. Save Images
                            for mode in ["color", "bw"]:
                                temp_name = f"Attempt1_{mode}.png"
                                if os.path.exists(temp_name):
                                    shutil.move(temp_name, os.path.join(tier_path, f"{base_filename}_{mode}.png"))

                            # 3. Save Questions to Text File
                            with open(os.path.join(tier_path, f"{base_filename}_Questions.txt"), "w") as f:
                                for q_tier, q_text, a_text in qa_set:
                                    f.write(f"[{q_tier} Question]\nQ: {q_text}\nA: {a_text}\n\n")

                            seeds_used.add(seed)
                            success_for_this_count += 1
                            print(f"      [OK] Sample {success_for_this_count} (Seed {seed}) + 3 Questions")
                
                except Exception as e:
                    continue

    print(f"\n✅ All diagrams and Q&A pairs generated in '{results_dir}'")

if __name__ == "__main__":
    run_systematic_test()