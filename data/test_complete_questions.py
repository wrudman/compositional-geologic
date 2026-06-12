import BuildRandomMap
import RandomQuestions
import os
import shutil
import random
import json
import glob
from tqdm import tqdm

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

def get_all_questions(res_map):
    """
    Generates answers for ALL 28 geometry questions.
    Categorizes them into Easy, Medium, and Hard tiers.
    """
    # 你的题库分类逻辑
    problem_buckets = {
        "easy": [1, 8, 9, 13, 26, 27],
        "medium": [2, 3, 5, 6, 7, 10, 11, 14, 15, 16, 20, 23, 24, 25, 28],
        "hard": [4, 12, 17, 18, 19, 21, 22, 29] 
    }

    RandomQuestions.map = res_map
    qa_results = {}

    # 遍历所有 28 个问题
    for key in range(1, 30):
        try:
            result = RandomQuestions.triesRandomQuestion(key)
            
            if result and isinstance(result, (tuple, list)) and len(result) >= 2:
                question = result[0]
                answer_text = result[1]
                
                if question:
                    # 自动确定题目所属的 Question_Tier
                    q_tier = "unknown"
                    for tier_name, id_list in problem_buckets.items():
                        if key in id_list:
                            q_tier = tier_name
                            break

                    qa_results[f"Q{key}"] = {
                        "question": question,
                        "answer": answer_text,
                        "question_id": key,
                        "question_tier": q_tier
                    }
        except Exception as e:
            # 某些题目可能因为地图特征缺失而无法生成（例如没有共顶点的区域），这是正常的
            continue
    return qa_results

def run_full_pilot(total_images=5):
    """
    Main loop to generate complex maps and all 28 questions.
    """
    base_dir = "GeoLogic_Full_Quest_Pilot"
    results_dir = get_unique_dir(base_dir)
    
    os.makedirs(results_dir)
    os.makedirs(os.path.join(results_dir, "images_color"))
    os.makedirs(os.path.join(results_dir, "images_bw"))
    
    dataset_list = []
    success_count = 0
    
    print(f"🚀 Starting Full Pilot: Generating {total_images} complex maps with all 28 questions.")

    while success_count < total_images:
        seed = random.randint(1, 999999)
        target_n = random.randint(8, 12) 
        
        # Diagram_Complexity
        if target_n <= 5: diagram_comp = "easy"
        elif target_n <= 8: diagram_comp = "medium"
        else: diagram_comp = "hard"

        try:
            res_map = BuildRandomMap.BuildRandomMap(target_n, 1, 1, seed)
            
            color_src = "Attempt1_color.png" if os.path.exists("Attempt1_color.png") else "color.png"
            bw_src = "Attempt1_bw.png" if os.path.exists("Attempt1_bw.png") else "bw.png"

            qa_batch = get_all_questions(res_map)


            if len(qa_batch) < 10: 
                print(f" [Skip] Seed {seed} only produced {len(qa_batch)} questions. Retrying for more complexity...")
                continue

            img_base_name = f"complex_{success_count:02d}_faces_{target_n}_seed_{seed}"
            color_name = f"{img_base_name}_color.png"
            bw_name = f"{img_base_name}_bw.png"

            if os.path.exists(color_src):
                shutil.move(color_src, os.path.join(results_dir, "images_color", color_name))
            if os.path.exists(bw_src):
                shutil.move(bw_src, os.path.join(results_dir, "images_bw", bw_name))

            entry = {
                "id": success_count,
                "seed": seed,
                "face_count": target_n,
                "diagram_complexity": diagram_comp,
                "image_path_color": f"images_color/{color_name}",
                "image_path_bw": f"images_bw/{bw_name}",
                "questions": qa_batch
            }
            
            dataset_list.append(entry)
            success_count += 1
            print(f" [Success] Map {success_count}/{total_images} (Faces: {target_n}, Questions: {len(qa_batch)})")

        except Exception as e:
            print(f" [Error] Seed {seed} failed: {e}")
            continue

    output_path = os.path.join(results_dir, "dataset_pilot_full.json")
    with open(output_path, "w", encoding='utf-8') as f:
        json.dump(dataset_list, f, indent=4, ensure_ascii=False)
    
    print(f"\n✅ All set! Full report and images saved in: {results_dir}")

if __name__ == "__main__":
    run_full_pilot(total_images=5)