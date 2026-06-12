import json
import os
import html

# --- Configuration ---
# Ensure this matches the output filename from your previous script
JSON_INPUT = "GeoLogic_Full_Quest_Pilot_4/dataset_pilot_full.json"
# The directory created by your previous script
BASE_DIR = "GeoLogic_Full_Quest_Pilot_4"
OUTPUT_HTML = os.path.join(BASE_DIR, "Pilot_Visualizer.html")

def generate_html():
    if not os.path.exists(JSON_INPUT):
        print(f"Error: {JSON_INPUT} not found. Run the generation script first.")
        return

    with open(JSON_INPUT, 'r', encoding='utf-8') as f:
        data = json.load(f)

    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>GeoLogic Full Pilot Visualizer</title>
        <style>
            body { font-family: 'Inter', sans-serif; background-color: #f4f7f9; color: #333; margin: 0; padding: 20px; }
            .container { max-width: 1400px; margin: auto; }
            header { text-align: center; padding: 20px; background: #2c3e50; color: white; border-radius: 10px; margin-bottom: 30px; }
            
            /* Card Layout */
            .diagram-card { background: white; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 50px; overflow: hidden; border: 1px solid #d1d9e0; }
            .card-header { background: #ecf0f1; padding: 15px 25px; border-bottom: 1px solid #d1d9e0; display: flex; justify-content: space-between; align-items: center; }
            
            /* Image Section */
            .image-section { display: flex; gap: 20px; padding: 20px; background: #fafafa; justify-content: center; border-bottom: 1px solid #eee; }
            .img-container { text-align: center; flex: 1; max-width: 450px; }
            .img-container img { width: 100%; border-radius: 8px; border: 1px solid #ccc; background: white; }
            .img-label { font-weight: bold; margin-top: 10px; color: #7f8c8d; text-transform: uppercase; font-size: 12px; }

            /* Question Grid */
            .question-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 15px; padding: 25px; background: white; }
            .q-item { border: 1px solid #e1e4e8; border-radius: 8px; padding: 15px; display: flex; flex-direction: column; transition: transform 0.2s; }
            .q-item:hover { border-color: #3498db; background: #fcfdfe; }
            
            /* Tags */
            .tag { font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 4px; text-transform: uppercase; margin-right: 5px; }
            .easy { background: #d4edda; color: #155724; }
            .medium { background: #fff3cd; color: #856404; }
            .hard { background: #f8d7da; color: #721c24; }
            .diag-tag { background: #34495e; color: white; padding: 5px 12px; border-radius: 20px; }

            .q-id { font-weight: bold; color: #2980b9; margin-bottom: 8px; border-bottom: 1px solid #eee; padding-bottom: 4px; }
            .q-text { font-size: 14px; margin-bottom: 10px; flex-grow: 1; line-height: 1.4; }
            .q-ans { background: #f8f9fa; padding: 8px; border-radius: 5px; font-family: monospace; font-size: 13px; color: #2c3e50; border-left: 3px solid #3498db; }
            
            .meta-info { font-size: 13px; color: #666; }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>GeoLogic: Multi-Tier Question Visualizer</h1>
                <p>Comprehensive testing of Questions 1-29 across varying Diagram Complexities</p>
            </header>
    """

    for item in data:
        f_count = item['face_count']
        d_comp = item['diagram_complexity']
        seed = item['seed']
        
        html_content += f"""
        <div class="diagram-card">
            <div class="card-header">
                <div class="meta-info">
                    <strong>ID: {item['id']}</strong> | Seed: {seed} | Faces: {f_count}
                </div>
                <div class="diag-tag">Diagram Complexity: {d_comp.upper()}</div>
            </div>
            
            <div class="image-section">
                <div class="img-container">
                    <img src="{item['image_path_color']}" alt="Color Map">
                    <div class="img-label">Color Mode</div>
                </div>
                <div class="img-container">
                    <img src="{item['image_path_bw']}" alt="B&W Map">
                    <div class="img-label">Black & White Mode</div>
                </div>
            </div>

            <div class="question-grid">
        """

        # Sort questions by ID so Q1, Q2... Q28 are in order
        sorted_qs = sorted(item['questions'].items(), key=lambda x: int(x[0][1:]))
        
        for q_key, q_val in sorted_qs:
            q_tier = q_val.get('question_tier', 'unknown')
            q_id = q_val.get('question_id', 'N/A')
            
            html_content += f"""
                <div class="q-item">
                    <div class="q-id">
                        <span class="tag {q_tier}">{q_tier}</span> Question {q_id}
                    </div>
                    <div class="q-text">{html.escape(q_val['question'])}</div>
                    <div class="q-ans"><strong>GT:</strong> {html.escape(str(q_val['answer']))}</div>
                </div>
            """
        
        html_content += """
            </div>
        </div>
        """

    html_content += """
        </div>
    </body>
    </html>
    """

    with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✅ HTML Visualization ready: {OUTPUT_HTML}")

if __name__ == "__main__":
    generate_html()