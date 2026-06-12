import numpy as np
import random
import os
from PIL import Image, ImageDraw
import Graph
import BuildRandomMap 
import DrawGraph 

import math

def label_vertices(res_map, vertex_list, maxX, maxY, filename="tool_labeled_points.png"):
    """
    Highlights vertices. Uses proximity labels by default, but switches to 
    external callouts (leader lines) if region labels (A, B, C) cause collisions.
    """
    # 1. Setup Canvas
    img_w, img_h = int(200 + 800 * maxX), int(200 + 800 * maxY)
    img = Image.new("RGBA", (img_w, img_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # Define internal frame boundaries
    FRAME_MIN, FRAME_MAX = 100, 900
    
    # 2. Draw base graph and get region label positions
    region_label_positions = DrawGraph.DrawAllFaces(res_map, draw) 

    # 3. Setup Fonts
    font_labels = DrawGraph.GetSystemFont(35)
    print(font_labels)
    
    for i, v in enumerate(vertex_list):
        px, py = DrawGraph.V2P(v.p)
        label_text = f"P{i+1}"
        
        # Draw the red "Hotspot" circle at the vertex
        r = 10
        draw.ellipse([px-r, py-r, px+r, py+r], fill=(255, 0, 0, 255), outline=(0,0,0), width=2)
        
        # --- COLLISION & PLACEMENT LOGIC ---
        
        # Try different quadrants around the vertex to find a non-overlapping spot
        offsets = [(25, -45), (25, 45), (-65, -45), (-65, 45)]
        best_offset = None
        
        for ox, oy in offsets:
            target_pos = (px + ox, py + oy)
            
            # Check if this target is safe from all region labels
            is_safe = True
            for face_letter, region_pos in region_label_positions.items():
                # Corrected distance calculation logic
                dx = target_pos[0] - region_pos[0]
                dy = target_pos[1] - region_pos[1]
                dist = math.sqrt((target_pos[0] - region_pos[0])**2 + (target_pos[1] - region_pos[1])**2)
                
                if dist < 60: # Threshold to prevent overlap with letters
                    is_safe = False
                    break
            
            # Also ensure the proximal label doesn't go outside the frame
            if not (FRAME_MIN < target_pos[0] < FRAME_MAX and FRAME_MIN < target_pos[1] < FRAME_MAX):
                is_safe = False

            if is_safe:
                best_offset = (ox, oy)
                break

        # --- FINAL RENDERING ---
        
        if best_offset:
            # OPTION A: Proximal Label (Clean area found)
            final_x, final_y = px + best_offset[0], py + best_offset[1]
            draw.text((final_x, final_y), label_text, fill=(255, 0, 0, 255), 
                      font=font_labels, stroke_width=2, stroke_fill=(255, 255, 255))
        # else:
        #     # OPTION B: Leader Line (Area too crowded)
        #     dists = {
        #         'L': px - FRAME_MIN,
        #         'R': FRAME_MAX - px,
        #         'T': py - FRAME_MIN,
        #         'B': FRAME_MAX - py
        #     }
        #     closest_edge = min(dists, key=dists.get)
            
        #     if closest_edge == 'L':   ext_pos = (FRAME_MIN - 70, py - 20)
        #     elif closest_edge == 'R': ext_pos = (FRAME_MAX + 20, py - 20)
        #     elif closest_edge == 'T': ext_pos = (px - 20, FRAME_MIN - 60)
        #     else:                     ext_pos = (px - 20, FRAME_MAX + 20)
            
        #     # Draw Leader Line from vertex to label
        #     draw.line([(px, py), (ext_pos[0] + 15, ext_pos[1] + 15)], fill=(255, 0, 0, 255), width=2)
            
        #     # Draw External Label with white stroke for legibility
        #     draw.text(ext_pos, label_text, fill=(255, 0, 0, 255), 
        #               font=font_labels, stroke_width=2, stroke_fill=(255, 255, 255))

    img.save(filename)
    print(f"Vertex labeling completed successfully: {filename}")

def main():
    # Initialize the geometry engine
    Graph.initialize()
    
    # Map configuration
    maxX, maxY = 1.0, 1.0
    n_faces = 8 
    seed = random.randint(0, 9999)
    
    print(f"Building map with seed {seed}...")
    res_map = BuildRandomMap.BuildRandomMap(n_faces, maxX, maxY, seed)
    
    # --- TOOL 1: POINT LABELING DEMO ---
    
    # Corrected Logic: 
    # In your Vertex class, the connected edges are stored in 'outarcs'
    # We look for junctions where more than 2 edges meet
    vertex_pool = [v for v in res_map.vertices if len(v.outarcs) > 2]
    
    # Fallback if no high-degree junctions exist
    if not vertex_pool:
        vertex_pool = res_map.vertices

    # Pick 3 to 5 random vertices to label
    num_to_label = min(5, len(vertex_pool))
    selected_vertices = random.sample(vertex_pool, num_to_label)
    
    print(f"Labeling {num_to_label} vertices...")
    
    # Call the labeling tool
    label_vertices(
        res_map=res_map, 
        vertex_list=selected_vertices, 
        maxX=maxX, 
        maxY=maxY, 
        filename="demo_labeled_points.png"
    )
    
    print(f"Point labeling demo saved to: demo_labeled_points.png")

if __name__ == "__main__":
    main()





# #                           QUESTION 11

# def Question11(fa,codes):  
#     global smallAng
#     vvs = fa.trueVertices[1:]
#     n = len(vvs)
#     angles = []
#     for v in vvs:
#         angles += [Graph.angleAtFace(v,fa)]
#     angles, indices = parallelSort(angles,list(range(len(vvs))))
#     quality = Q11Quality(angles,n)
#     if quality == 0:
#         return failureOutput  
#     question = "Region " + fa.letter + " has " + str(n) + " vertices, numbered as follows:\n "
#     for i in range(n):
#         vName = identifyVertexForQ11(vvs[i],fa,codes[i])
#         if vName == "":
#             return failureOutput
#         question = question + "(" + str(i+1) + ") " + vName
#         if i==n-1:
#             question += ".\n"
#         else:
#             question += ";\n"
#     question += "Sort these in increasing order by the size of the interior angle at each corner.\n"+int_angle_def
#     answerList = []
#     for i in range(n):
#         answerList += [vvs[indices[i]]]
#         indices[i] += 1
#     return question, str(indices), answerList, quality
   
# def Q11Quality(angles,n):
#     quality = 7
#     for i in range(n-1):
#          diff = angles[i+1] - (angles[i] + (10*np.pi/180))
#          if diff < 0:    
#              return 0
#          else:
#             if diff < quality:
#                quality = diff
#     return quality


# #Line Extension

# def Question29(fe, fb, map, samples=400):
#     """
#     Question 25-29 Style: Find max intermediate regions.
#     Rejects the question if the result depends on 'scraping' (dist < 0.05).
#     """
#     if fe == fb or not fe.bounded or not fb.bounded:
#         return failureOutput

#     max_robust_count = 0
#     # The 'Human-Visible' Threshold
#     VISUAL_THRESHOLD = 0.03
#     # The 'Absolute Truth' Threshold
#     EPSILON_THRESHOLD = 0.0005 

#     for _ in range(samples):
#         pa = Graph.randomPointInFace(fe, True)
#         pb = Graph.randomPointInFace(fb, True)

#         # 1. Calculate the 'Perfect' Ground Truth
#         true_path = TraceSegment(pa, pb, map, min_dist=EPSILON_THRESHOLD)
#         true_set = {f.letter for f in true_path if f != fe and f != fb}
#         true_count = len(true_set)

#         # 2. Calculate the 'Visually Clear' Path
#         robust_path = TraceSegment(pa, pb, map, min_dist=VISUAL_THRESHOLD)
#         robust_set = {f.letter for f in robust_path if f != fe and f != fb}
#         robust_count = len(robust_set)

#         # HARD REJECTION: If the 'Truth' and 'Visuals' differ, 
#         # this specific two regions are too ambiguous/scraped. Skip it.
#         if true_count != robust_count:
#             return failureOutput

#         # If they match, it's a high-quality, clear path.
#         if robust_count > max_robust_count:
#             max_robust_count = robust_count

#     # If no visually clear path exists at all, reject the whole question for this map
#     if max_robust_count == 0:
#         return None

#     # Final Question Formulation
#     question = (f"Consider all possible straight line segments connecting a point in the interior of region {fe.letter} "
#                 f"to a point in the interior of region {fb.letter}. "
#                 f"What is the maximum number of distinct regions, excluding regions {fe.letter} and {fb.letter}, "
#                 f"that such a line segment can pass through? \n")
#     question += pass_interior_def

#     # Return: question, answer, numeric answer, quality score
#     return question, str(max_robust_count), max_robust_count, 1.0 + (max_robust_count * 0.5)


# def TraceSegment(pa, pb, map, min_dist=0.05):
#     """
#     Traces the sequence of regions passed by the segment from pa to pb.
#     Only includes regions where the segment travels a distance > min_dist.
#     """
#     intersections = []
#     # Always include the start and end of the segment
#     intersections.append({'p': pa, 't': 0.0})
#     intersections.append({'p': pb, 't': 1.0})
    
#     for edge in map.edges:
#         if Graph.crossLines(pa, pb, edge.tail.p, edge.head.p):
#             p_cross = Graph.lineIntersect(pa, pb, edge.tail.p, edge.head.p)
            
#             # Parametric position 't' (0 to 1) along the segment to sort them
#             if abs(pb.x - pa.x) > 0.00001:
#                 t = (p_cross.x - pa.x) / (pb.x - pa.x)
#             else:
#                 t = (p_cross.y - pa.y) / (pb.y - pa.y)
            
#             # Only count intersections strictly between the endpoints
#             if 0.0001 < t < 0.9999:
#                 intersections.append({'p': p_cross, 't': t})

#     # Sort intersections from pa to pb
#     intersections.sort(key=lambda x: x['t'])
    
#     # Clean up duplicate points (e.g., hitting a vertex)
#     unique_pts = [intersections[0]['p']]
#     for i in range(1, len(intersections)):
#         if Graph.pointDist(intersections[i]['p'], unique_pts[-1]) > 0.0001:
#             unique_pts.append(intersections[i]['p'])

#     path_sequence = []
#     for i in range(len(unique_pts) - 1):
#         p1 = unique_pts[i]
#         p2 = unique_pts[i+1]
        
#         # Determine if this segment is long enough to be "visible"
#         segment_len = Graph.pointDist(p1, p2)
#         if segment_len < min_dist:
#             continue
            
#         # Use midpoint to identify which face this segment is inside
#         mid = Graph.midpoint(p1, p2)
#         for face in map.faces:
#             if face.bounded and Graph.pointInsideFace(mid, face):
#                 path_sequence.append(face)
#                 break 
                
#     return path_sequence





# #Union of Regions
# def Question14(fa,fb):
#     fu = FaceUnion(fa,fb)
#     if fu==False:
#         return failureOutput
#     question = UnionText(fa,fb,'U')
#     question += "How many edges does U have? \n"
#     question += union_def
#     return question, str(fu.numSides), fu.numSides, fu.numSides + len(fu.edges) 
# def UnionText(fa,fb,uname):
#     return "Let " + uname + " be the union of regions " + fa.letter + " and " + fb.letter + ". " 
