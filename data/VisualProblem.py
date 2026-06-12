import RandomQuestions 
class VisualProblem:
    def __init__(self, key, map_obj):
        self.key = key
        self.map = map_obj
        # Generate the text and internal answer data
        self.question_text, self.answer_text, self.raw_data, self.quality =  RandomQuestions.tryrandomQuestion(key)
        # Define the 'Expert Trace' (Ground Truth Tools)
        self.expert_visual_trace = self._get_expert_tools(key)

    def _get_expert_tools(self, key):
        # Maps question keys to necessary visual operations
        tool_map = {
            14: ["highlight_region(fa)", "highlight_region(fb)", "draw_union"],
            18: ["label_vertex(p)", "label_vertex(q)", "draw_line", "get_faces_along_line"],
            11: ["label_angle(v1)", "label_angle(v2)", "compare_angles"]
        }
        return tool_map.get(key, [])


# def run_composite_test(session):
#     # --- SCENARIO 1: Union + Corresponding Points & Angles ---
#     # Goal: Merge two regions and label only the vertices on the new outer boundary
#     path_c = ensure_dir("04_composite_tools")
#     session.reset_actions()
    
#     fa, fb = find_adjacent_faces(session.res_map)
#     if fa and fb:
#         # Find vertices that are NOT shared (the exterior boundary)
#         shared_v_ids = {v.id for v in set(fa.trueVertices) & set(fb.trueVertices)}
#         external_vs = [v for v in set(fa.trueVertices) | set(fb.trueVertices) 
#                        if v.id not in shared_v_ids]
        
#         # Label 3 random exterior vertices and their angles
#         for i, v in enumerate(random.sample(external_vs, min(3, len(external_vs)))):
#             session.add_vertex_action(v, label=f"P{i+1}")
#             session.add_angle_action(Angle(v.p, fa), label=str(i+1))
            
#         # Note: We use the draw_union_with_annotations helper discussed earlier
#         img_union = draw_union_with_annotations(
#             session.res_map, fa, fb, LabelManager(), 
#             session.face_label_cache, session.actions, 1.0, 1.0
#         )
#         img_union.save(os.path.join(path_c, "composite_union_annotated.png"))

    # # --- SCENARIO 2: Line + Highlight Intersected Regions ---
    # # Goal: Draw a line and automatically highlight all faces it passes through
    # session.reset_actions()
    # p1, p2 = Graph.Vector(0.1, 0.1), Graph.Vector(0.9, 0.8)
    
    # # Using your existing tool to get intersected regions
    # intersected_faces = session.res_map.get_faces_along_line(p1, p2)
    # for face in intersected_faces:
    #     session.add_region_action(face, color=(255, 255, 0, 80)) # Translucent yellow
        
    # session.add_action(tool_draw_points_line, p1, p2, color=(255, 0, 0, 255))
    # session.render().save(os.path.join(path_c, "composite_intersection.png"))

    # # --- SCENARIO 3: Multi-Region Edge Count ---
    # # Goal: Select 3 regions and label them with their edge count
    # session.reset_actions()
    # target_faces = random.sample([f for f in session.res_map.faces if f.bounded], 3)
    # for face in target_faces:
    #     count = len(face.edges)
    #     session.add_region_action(face, label=f"{count} sides", color=(100, 200, 255, 100))
    # session.render().save(os.path.join(path_c, "composite_edge_counting.png"))

    # # --- SCENARIO 4: Double Simultaneous Lines ---
    # session.reset_actions()
    # session.add_action(tool_draw_points_line, Graph.Vector(0, 0.5), Graph.Vector(1, 0.5), color=(0, 0, 255, 255))
    # session.add_action(tool_draw_points_line, Graph.Vector(0.5, 0), Graph.Vector(0.5, 1), color=(0, 255, 0, 255))
    # session.render().save(os.path.join(path_c, "composite_double_lines.png"))