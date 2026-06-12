import TestQuestions
import os
import shutil
import random

def run_targeted_test():
    results_dir = "Run_Results_Debug2"
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)

    # The specific problematic seeds you identified
    target_seeds = [820582, 986135]
    
    print("--- Part 1: Debugging Targeted Seeds ---")
    
    for seed in target_seeds:
        print(f"\nTargeting Problematic Map (Seed: {seed})...")
        try:
            # Run the setup
            TestQuestions.randomSetup(seed)
            
            # Look for the outputs
            found = False
            for mode in ["color", "bw"]:
                temp_name = f"Attempt1_{mode}.png"
                if os.path.exists(temp_name):
                    new_name = os.path.join(results_dir, f"DEBUG_Seed_{seed}_{mode}.png")
                    shutil.move(temp_name, new_name)
                    print(f"  [!] Saved: {new_name}")
                    found = True
            
            if not found:
                print(f"  [?] Setup finished but no images were generated for {seed}.")

        except Exception as e:
            print(f"  [X] Failure during Seed {seed}: {e}")

    print("\n--- Part 2: Resuming Random Samples ---")
    # (Optional: keep the rest of your original logic here if you want to continue to 50)

if __name__ == "__main__":
    run_targeted_test()