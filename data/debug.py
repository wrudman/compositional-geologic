import BuildRandomMap
import Questions
import RandomQuestions
import os
import shutil
import random
import json

# --- SETTINGS ---
num_test_maps = 20  # Test across 20 different random seeds
tries_per_map = 10  # Try picking different faces within the same map

def run_diagnostic():
    print("=== STARTING DIAGNOSTIC FOR Q2 AND Q17 ===\n")
    
    q17_stats = {"Yes": 0, "No": 0, "Fail": 0}
    q2_results = []
    
    for seed in range(num_test_maps):
        # 1. Setup the map
        RandomQuestions.randomSetup(seed)
        current_map = RandomQuestions.map
        print(f"--- Testing Map Seed: {seed} ({len(current_map.faces)-1} regions) ---")
        
        # 2. Test Question 17 (Convex Union Yes/No)
        # Since Q17 now has internal balancing, we call it directly
        for _ in range(3): # Try a few times per map
            q, ans_text, ans_obj, quality = Questions.Question17(current_map)
            if quality > 0:
                q17_stats[ans_text] += 1
                if _ == 0: # Only print the first one to save space
                    print(f"[Q17 Sample] {q}")
                    print(f"      Answer: {ans_text} | Quality: {quality}")
            else:
                q17_stats["Fail"] += 1

        # 3. Test Question 2 (Max Regions Count)
        # We need to pick two faces for the randomQuestion2 wrapper
        success_q2 = 0
        attempts = 0
        while success_q2 < 2 and attempts < 20:
            attempts += 1
            # Picking two random bounded faces
            faces = [f for f in current_map.faces if f.bounded]
            if len(faces) < 2: break
            fa, fb = random.sample(faces, 2)
            
            if fa.convex and fb.convex:
                q, ans_text, ans_val, quality = Questions.Question2(fa, fb, current_map)
                if quality > 0:
                    q2_results.append(ans_val)
                    success_q2 += 1
                    if success_q2 == 1:
                        print(f"[Q2 Sample] {q}")
                        print(f"     Max Regions: {ans_text} | Quality: {quality:.2f}")

        print("-" * 30)

    # --- FINAL SUMMARY ---
    print("\n=== FINAL STATS SUMMARY ===")
    
    print(f"\nQuestion 17 (Convex Union) Distribution:")
    total_q17 = q17_stats["Yes"] + q17_stats["No"]
    if total_q17 > 0:
        print(f"  - YES: {q17_stats['Yes']} ({q17_stats['Yes']/total_q17*100:.1f}%)")
        print(f"  - NO:  {q17_stats['No']} ({q17_stats['No']/total_q17*100:.1f}%)")
    print(f"  - Failed to generate: {q17_stats['Fail']}")

    print(f"\nQuestion 2 (Path Counting) Stats:")
    if q2_results:
        print(f"  - Min Regions Found: {min(q2_results)}")
        print(f"  - Max Regions Found: {max(q2_results)}")
        print(f"  - Avg Regions Found: {sum(q2_results)/len(q2_results):.2f}")
    else:
        print("  - No Q2 samples successfully generated.")

if __name__ == "__main__":
    run_diagnostic()