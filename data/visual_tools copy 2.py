import numpy as np
import random
import os
from PIL import Image, ImageDraw
import Graph
import BuildRandomMap 
import DrawGraph 
import Questions
import math

'''we use labelmanger to keep track of all the labels, for regions, vertices, interior angles etc
reserved_areas keep track of list of reserved areas by previous labels;
reserve is used to reserve a point and its associated area
is_overlapping checks if the new point overlaps with existing reserved area.
'''
class LabelManager:
    def __init__(self):
        self.reserved_areas = [] # List of (x1, y1, x2, y2)

    def reserve(self, x, y, width, height, padding=10):
        # Create a bounding box centered at (x, y)
        x1 = x - width/2 - padding
        y1 = y - height/2 - padding
        x2 = x + width/2 + padding
        y2 = y + height/2 + padding
        self.reserved_areas.append((x1, y1, x2, y2))

    def is_overlapping(self, x, y, width, height, padding=10):
        nx1, ny1 = x - width/2 - padding, y - height/2 - padding
        nx2, ny2 = x + width/2 + padding, y + height/2 + padding
        for (ex1, ey1, ex2, ey2) in self.reserved_areas:
            # AABB Collision Detection
            if not (nx2 < ex1 or nx1 > ex2 or ny2 < ey1 or ny1 > ey2):
                return True
        return False

def draw_leader_with_arrow(draw, start_pos, end_pos, color):
    """Draws a line with an arrowhead pointing at start_pos (the vertex)."""
    draw.line([start_pos, end_pos], fill=color, width=2)
    # Arrowhead logic
    angle = math.atan2(end_pos[1] - start_pos[1], end_pos[0] - start_pos[0])
    arrow_len = 20
    p1 = (start_pos[0] + arrow_len * math.cos(angle + 0.4), 
          start_pos[1] + arrow_len * math.sin(angle + 0.4))
    p2 = (start_pos[0] + arrow_len * math.cos(angle - 0.4), 
          start_pos[1] + arrow_len * math.sin(angle - 0.4))
    draw.polygon([start_pos, p1, p2], fill=color)



def label_vertices(res_map, vertex_list, manager, maxX, maxY, filename="tool_labeled_points.png"):
    img_w, img_h = int(200 + 800 * maxX), int(200 + 800 * maxY)
    img = Image.new("RGBA", (img_w, img_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # 1. Draw base faces and reserve their labels in the manager
    # NOTE: You'll need to update DrawAllFaces to call manager.reserve() 
    # for each region letter (A, B, C) it draws.
    DrawGraph.DrawAllFaces(res_map, draw, manager) 

    FRAME_MIN, FRAME_MAX = 100, 900
    RED, BLUE, WHITE, BLACK = (255, 0, 0, 255), (0, 0, 255, 255), (255, 255, 255, 255), (0, 0, 0, 255)
    font_labels = DrawGraph.GetSystemFont(35)
    
    # Approx size of "P1" text for collision checking
    text_w, text_h = 45, 30

    for i, v in enumerate(vertex_list):
        px, py = DrawGraph.V2P(v.p)
        label_text = f"P{i+1}"
        
        # Draw the vertex hotspot
        draw.ellipse([px-10, py-10, px+10, py+10], fill=RED, outline=BLACK, width=2)
        
        # --- SMART PLACEMENT ---
        offsets = [(15, -25), (15, 25), (-55, -25), (-55, 25)]
        best_pos = None
        
        for ox, oy in offsets:
            tx, ty = px + ox, py + oy
            # Check manager for ANY overlap (Regions or previous P labels)
            if not manager.is_overlapping(tx, ty, text_w, text_h):
                # Ensure it's inside the frame
                if FRAME_MIN < tx < FRAME_MAX and FRAME_MIN < ty < FRAME_MAX:
                    best_pos = (tx, ty)
                    break

        if best_pos:
            # OPTION A: Safe space found
            draw.text(best_pos, label_text, fill=BLUE, font=font_labels, 
                      stroke_width=2, stroke_fill=WHITE)
            manager.reserve(best_pos[0], best_pos[1], text_w, text_h)
        else:
            # OPTION B: finding space outside of the frame
            dists = {'L': px-FRAME_MIN, 'R': FRAME_MAX-px, 'T': py-FRAME_MIN, 'B': FRAME_MAX-py}
            edge = min(dists, key=dists.get)
            
            MIN_ARROW_LEN = 45 
            found_margin_spot = False
            
            # Make sure that there is no overlapping, and if there is, find a nearby position 
            search_offsets = [0, 40, -40, 80, -80, 120, -120]
            
            for s_off in search_offsets:
                if edge == 'L':
                    temp_x = min(FRAME_MIN - 75, px - MIN_ARROW_LEN - text_w)
                    temp_y = py - 15 + s_off # slide along Y
                elif edge == 'R':
                    temp_x = max(FRAME_MAX + 25, px + MIN_ARROW_LEN)
                    temp_y = py - 15 + s_off 
                elif edge == 'T':
                    temp_x = px - 20 + s_off # slide along X
                    temp_y = min(FRAME_MIN - 65, py - MIN_ARROW_LEN - text_h)
                else: # Bottom
                    temp_x = px - 20 + s_off 
                    temp_y = max(FRAME_MAX + 25, py + MIN_ARROW_LEN)

                if not manager.is_overlapping(temp_x + text_w/2, temp_y + text_h/2, text_w, text_h):
                    ext_x, ext_y = temp_x, temp_y
                    found_margin_spot = True
                    break
            
            if not found_margin_spot:
                ext_x, ext_y = temp_x, temp_y 

            if edge == 'L':   conn_x, conn_y = ext_x + text_w, ext_y + (text_h / 2)
            elif edge == 'R': conn_x, conn_y = ext_x, ext_y + (text_h / 2)
            elif edge == 'T': conn_x, conn_y = ext_x + (text_w / 2), ext_y + text_h
            else:             conn_x, conn_y = ext_x + (text_w / 2), ext_y

            # 2. Draw arrow pointing TO the vertex (px, py) 
            # starting FROM the connection point (conn_x, conn_y)
            draw_leader_with_arrow(draw, (px, py), (conn_x, conn_y), BLUE)
            draw.text((ext_x, ext_y), label_text, fill=BLUE, font=font_labels, 
                      stroke_width=2, stroke_fill=WHITE)
            manager.reserve(ext_x + text_w/2, ext_y + text_h/2, text_w, text_h)
    img.save(filename)


def label_interior_angles(res_map, angle_list, manager, maxX, maxY, filename="tool_labeled_angles.png"):
    # 1. Canvas Setup
    img_w, img_h = int(200 + 800 * maxX), int(200 + 800 * maxY)
    img = Image.new("RGBA", (img_w, img_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # Draw base map and reserve region labels (A, B, C...)
    # Note: Ensure DrawAllFaces uses your new width=6 for interior lines
    DrawGraph.DrawAllFaces(res_map, draw, manager) 

    FRAME_MIN, FRAME_MAX = 100, 900
    RED, BLUE, WHITE, BLACK = (255, 0, 0, 255), (0, 0, 255, 255), (255, 255, 255, 255), (0, 0, 0, 255)
    
    # Keeping font size 35 for the "α1", "α2" or "1", "2" labels
    font_labels = DrawGraph.GetSystemFont(35)
    
    # Bounding box for label collision (e.g., "a1")
    text_w, text_h = 45, 30

    for i, angle_data in enumerate(angle_list):
        # I assume angle_data has a point property '.p' representing the corner
        px, py = DrawGraph.V2P(angle_data.p)
        label_text = f"a{i+1}" # 'a' for angle
        
        # Draw a small indicator for the angle/corner
        draw.ellipse([px-8, py-8, px+8, py+8], fill=RED, outline=BLACK, width=2)
        
        # --- SMART PLACEMENT (Proximal) ---
        offsets = [(20, -30), (20, 30), (-60, -30), (-60, 30)]
        best_pos = None
        
        for ox, oy in offsets:
            tx, ty = px + ox, py + oy
            if not manager.is_overlapping(tx, ty, text_w, text_h):
                if FRAME_MIN < tx < FRAME_MAX and FRAME_MIN < ty < FRAME_MAX:
                    best_pos = (tx, ty)
                    break

        if best_pos:
            # OPTION A: Inside the map
            draw.text(best_pos, label_text, fill=BLUE, font=font_labels, 
                      stroke_width=2, stroke_fill=WHITE)
            manager.reserve(best_pos[0], best_pos[1], text_w, text_h)
        else:
            # OPTION B: Margin placement with leader line
            dists = {'L': px-FRAME_MIN, 'R': FRAME_MAX-px, 'T': py-FRAME_MIN, 'B': FRAME_MAX-py}
            edge = min(dists, key=dists.get)
            
            MIN_ARROW_LEN = 50 
            found_margin_spot = False
            search_offsets = [0, 45, -45, 90, -90, 135, -135] # Slightly larger step for angles
            
            for s_off in search_offsets:
                if edge == 'L':
                    temp_x = min(FRAME_MIN - 75, px - MIN_ARROW_LEN - text_w)
                    temp_y = py - 15 + s_off
                elif edge == 'R':
                    temp_x = max(FRAME_MAX + 25, px + MIN_ARROW_LEN)
                    temp_y = py - 15 + s_off 
                elif edge == 'T':
                    temp_x = px - 20 + s_off
                    temp_y = min(FRAME_MIN - 65, py - MIN_ARROW_LEN - text_h)
                else: # Bottom
                    temp_x = px - 20 + s_off 
                    temp_y = max(FRAME_MAX + 25, py + MIN_ARROW_LEN)

                if not manager.is_overlapping(temp_x + text_w/2, temp_y + text_h/2, text_w, text_h):
                    ext_x, ext_y = temp_x, temp_y
                    found_margin_spot = True
                    break
            
            if not found_margin_spot:
                ext_x, ext_y = temp_x, temp_y 

            # Calculate connection point on text box
            if edge == 'L':   conn_x, conn_y = ext_x + text_w, ext_y + (text_h / 2)
            elif edge == 'R': conn_x, conn_y = ext_x, ext_y + (text_h / 2)
            elif edge == 'T': conn_x, conn_y = ext_x + (text_w / 2), ext_y + text_h
            else:             conn_x, conn_y = ext_x + (text_w / 2), ext_y

            # Draw Bold Leader Line (Width 2 or 3 looks better here)
            draw_leader_with_arrow(draw, (px, py), (conn_x, conn_y), BLUE)
            draw.text((ext_x, ext_y), label_text, fill=BLUE, font=font_labels, 
                      stroke_width=2, stroke_fill=WHITE)
            manager.reserve(ext_x + text_w/2, ext_y + text_h/2, text_w, text_h)

    # 7. Heavy Outer Frame (STRICT: width = 4 as requested)
    p_bl = DrawGraph.V2P(Graph.Vector(0, 0))
    p_tr = DrawGraph.V2P(Graph.Vector(1.0, 1.0))
    # Note: Rectangle outline uses the requested width 4
    draw.rectangle([p_bl[0], p_tr[1], p_tr[0], p_bl[1]], outline=BLACK, width=4)
    
    img.save(filename)


def draw_union(res_map, fa, fb, manager, maxX, maxY, filename="union_result.png"):
    # 1. Canvas Setup (matching DrawGraph sizing)
    img_w, img_h = int(200 + 800 * maxX), int(200 + 800 * maxY)
    img = Image.new("RGBA", (img_w, img_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # Initialize color palette
    DrawGraph.InitColors(alpha=153)
    black = (0, 0, 0, 255)
    
    # 2. Font Styles (Strictly matching DrawGraph: 80/45)
    font_bold = DrawGraph.GetSystemFont(80)
    font_small = DrawGraph.GetSystemFont(45)
    
    # Identify edges to "dissolve"
    shared_edge_ids = get_shared_edges(fa, fb)
    
    # 3. Draw Polygons (Fill ONLY - No Outlines here!)
    for face in res_map.faces:
        if not face.bounded: 
            continue
        
        vvs = DrawGraph.FaceVertex2P(face)
        if face == fa or face == fb:
            fill_color = (147, 112, 219, 180) 
        else:
            fill_color = DrawGraph.colors[face.color]
            
        # REMOVED outline=black and width=4 from here
        draw.polygon(vvs, fill=fill_color)

    # 4. Draw Edges (This is where the actual borders are drawn)
    for edge in res_map.edges:
        # Check if the edge separates fa and fb
        if id(edge) in shared_edge_ids:
            continue
            
        p1 = DrawGraph.V2P(edge.tail.p)
        p2 = DrawGraph.V2P(edge.head.p)
        
        # We draw all other boundaries in black
        draw.line([p1, p2], fill=black, width=6)

    # 5. Label all other faces normally first
    for face in res_map.faces:
        if face.bounded and face != fa and face != fb:
            lp, d = Graph.LetterPointFace(face)
            coords = DrawGraph.V2P(lp)
            
            # Use DrawGraph threshold (0.06) and fonts (80/45)
            chosen_font = font_bold if d > 0.06 else font_small
            draw.text(coords, face.letter, fill=black, font=chosen_font, anchor="mm")
            
            if manager:
                manager.reserve(coords[0], coords[1], width=35, height=35)

    # 6. Label the Union "U" 
    best_p_a, dist_a = Graph.LetterPointFace(fa)
    best_p_b, dist_b = Graph.LetterPointFace(fb)
    
    # Pick the deeper point between the two original faces
    u_vector = best_p_a if dist_a > dist_b else best_p_b
    u_coords = DrawGraph.V2P(u_vector)
    
    # Draw 'U' using the bold font (80)
    draw.text(u_coords, "U", fill=black, font=font_bold, anchor="mm")
    if manager:
        manager.reserve(u_coords[0], u_coords[1], width=40, height=40)

    # 7. Draw the heavy Outer Frame (width = 8)
    p_bl = DrawGraph.V2P(Graph.Vector(0, 0))
    p_tr = DrawGraph.V2P(Graph.Vector(1.0, 1.0))
    draw.rectangle([p_bl[0], p_tr[1], p_tr[0], p_bl[1]], outline=black, width=4)

    img.save(filename)
    return img

def get_shared_edges(fa, fb):
    """
    Returns a set of edge IDs that are shared between fa and fb 
    using the 'edges' list provided in the Face class.
    """
    shared = set()
    
    # Iterate through the list of edges stored inside fa
    for edge in fa.edges:
        # Check the face on the other side of this edge.
        # Most implementations use edge.reverse.leftFace 
        # or edge.rightFace to identify the neighbor.
        if edge.reverse.leftFace == fb:
            shared.add(id(edge))
            shared.add(id(edge.reverse))
            
    return shared

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
    #initialize labelling
    label_man = LabelManager()
    
# 2. Call the function with the manager included
    label_vertices(
        res_map=res_map,
        vertex_list=selected_vertices,
        manager=label_man,  # <--- Add this line!
        maxX=maxX,
        maxY=maxY,
        filename="demo_labeled_points.png"
    )
    
    # --- TOOL 2: LAGEL INTERIOR ANGLES ---
    all_possible_angles = []

    for face in res_map.faces:
        if face.bounded:
            # Each face has a list of vertices. 
            # We skip the last vertex if it's a duplicate of the first.
            face_verts = face.vertices[:-1] if face.vertices[0] == face.vertices[-1] else face.vertices
            
            for v in face_verts:
                # We store the vertex point as the 'angle' location
                # We wrap it in a simple object with a '.p' attribute 
                # to match the label_interior_angles logic.
                angle_item = type('Angle', (object,), {'p': v.p, 'parent_face': face})
                all_possible_angles.append(angle_item)

    # Pick 3 to 6 random angles from the map
    num_angles = min(len(all_possible_angles), random.randint(3, 6))
    selected_angles = random.sample(all_possible_angles, num_angles)

    print(f"Labeling {num_angles} interior angles...")

    # --- CALL THE NEW TOOL ---
    label_interior_angles(
        res_map=res_map,
        angle_list=selected_angles,
        manager=label_man,
        maxX=maxX,
        maxY=maxY,
        filename="demo_labeled_angles.png"
    )

    # --- TOOL 3: LABELING UNION ---
    # We iterate through edges to find two adjacent faces
    potential_pairs = []
    for e in res_map.edges:
        fa = e.leftFace
        fb = e.reverse.leftFace
        
        # Ensure both are bounded faces and not the same face
        if fa.bounded and fb.bounded and fa != fb:
            # Sort to avoid duplicates like (A,B) and (B,A)
            pair = tuple(sorted([id(fa), id(fb)]))
            potential_pairs.append((fa, fb, pair))

    # Remove duplicates
    unique_pairs = {p[2]: (p[0], p[1]) for p in potential_pairs}
    pair_list = list(unique_pairs.values())

    if not pair_list:
        print("No adjacent faces found to union.")
        return

    # 3. Pick a random pair and verify with your FaceUnion logic
    random.shuffle(pair_list)
    selected_union = None
    
    for fa, fb in pair_list:
        # Using your existing logic to verify the geometric path exists
        pf = Questions.FaceUnion(fa, fb)
        if pf:
            selected_union = (fa, fb, pf) 
            print(f"Valid Union found: Face {fa.letter} and Face {fb.letter}")
            break

    # 4. Draw the Union Map if found
    if selected_union:
        fa, fb, pf = selected_union
        print(fa,fb)
        # We pass the manager to keep track of the new 'U' and other labels
        draw_union(
            res_map=res_map, 
            fa=fa, 
            fb=fb, 
            manager=label_man, 
            maxX=maxX, 
            maxY=maxY, 
            filename="union_result.png"
        )
    else:
        print("No pairs passed the FaceUnion geometric check.")
    print(f"Point labeling demo saved to: demo_labeled_points.png")


if __name__ == "__main__":
    main()



