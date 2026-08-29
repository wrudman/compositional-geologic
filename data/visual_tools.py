import numpy as np
import random
import os
import math
from PIL import Image, ImageDraw
from collections import namedtuple
import RandomQuestions 
import Graph
import BuildRandomMap 
import DrawGraph 
import Questions
import map_helpers

# Data structure for angles
Angle = namedtuple('Angle', ['p', 'parent_face'])

"""
LabelManager handles collision avoidance for map annotations.
Maintains a registry of 'reserved' rectangular areas to ensure labels for 
vertices, regions, and angles remain legible without overlapping.
"""
import numpy as np
import random
import os
import math
from PIL import Image, ImageDraw
from collections import namedtuple
import RandomQuestions 
import Graph
import BuildRandomMap 
import DrawGraph 
import Questions

# Data structure for angles
Angle = namedtuple('Angle', ['p', 'parent_face'])

"""
LabelManager handles collision avoidance for map annotations.
Maintains a registry of 'reserved' rectangular areas to ensure labels for 
vertices, regions, and angles remain legible without overlapping.
"""
class LabelManager:
    def __init__(self):
        self.reserved_areas = []

    def reserve(self, x, y, width, height, padding=10):
        x1, y1 = x - width/2 - padding, y - height/2 - padding
        x2, y2 = x + width/2 + padding, y + height/2 + padding
        self.reserved_areas.append((x1, y1, x2, y2))

    def is_overlapping(self, x, y, width, height, padding=10):
        nx1, ny1 = x - width/2 - padding, y - height/2 - padding
        nx2, ny2 = x + width/2 + padding, y + height/2 + padding
        for (ex1, ey1, ex2, ey2) in self.reserved_areas:
            if not (nx2 < ex1 or nx1 > ex2 or ny2 < ey1 or ny1 > ey2):
                return True
        return False
    

# Action: we record a list of actions, and allow users to undo actions
class Action:
    """Stores a function and its arguments to be replayed later."""
    def __init__(self, func, *args, **kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def execute(self, draw, img, manager):
        """Runs the stored command on the provided canvas/image."""
        return self.func(draw, img, manager, *self.args, **self.kwargs)
    


class AnnotationSession:
    def __init__(self, res_map, img_size):
        self.res_map = res_map
        self.img_size = img_size
        self.actions = []
        self.temp_selection = None

        for i, face in enumerate(self.res_map.faces):
            face._cache_idx = i

        self.face_label_cache = {}
        for face in self.res_map.faces:
            if face.bounded:
                lp, d = Graph.LetterPointFace(face)
                self.face_label_cache[face._cache_idx] = (lp, d)

        self.counters = {"vertex": 1, "angle": 1, "edge": 1}
        self.used_labels = {"vertex": set(), "angle": set(), "edge": set()}

    
    def get_active_hidden_edges(self):
        """
        Scans current actions to find all edges that should be hidden 
        due to 'union' operations currently in the action stack.
        """
        hidden_edge_ids = set()
        for func, args, kwargs in self.actions:
            if "draw_union" in func.__name__.lower():
                # FIX: args[0] is res_map, so the actual merging faces 
                # are at index 1 and index 2
                if len(args) >= 3:
                    fa, fb = args[1], args[2]
                    shared = get_shared_edges(fa, fb)
                    hidden_edge_ids.update(shared)
        return hidden_edge_ids
    
    def get_union_group(self, face):
        """
        Finds the union action that contains the given face.
        Returns the action tuple (func, args, kwargs) if found, else None.
        """
        if face is None:
            return None
            
        face_id = id(face)
        for action in self.actions:
            func, args, kwargs = action
            # Check if this is a union action
            if "draw_union" in func.__name__.lower():
                # In draw_union(draw, img, manager, face1, face2, ...), 
                # faces start from args[0] in the stored action list
                # (Note: render injects draw/img/mgr, but the stored args are just the faces)
                if any(id(f) == face_id for f in args):
                    return action
        return None

    def is_marker_obsolete(self, func, args, hidden_edge_ids):
        """
        Determines if a marker should be ignored.
        Now ignores vertices if all their remaining visible edges are on the Frame.
        """
        func_name = func.__name__.lower()

        if "label_vertex" in func_name:
            vertex = args[0]
            # Capture ALL raw edges from the data structure
            incident_edges = list(vertex.outarcs)
            
            visible_internal_edges = []
            frame_boundary_edges = []
            
            # --- COMPREHENSIVE DEBUG START ---
            v_id = getattr(vertex, 'num', 'unknown')
            print(f"\n--- 🔍 Full Diagnostics: Vertex {v_id} ---")
            print(f"Total Raw Edges (outarcs): {len(incident_edges)}")
            
            for i, e in enumerate(incident_edges):
                # 1. Hidden Status
                is_hidden = (id(e) in hidden_edge_ids) or (id(e.reverse) in hidden_edge_ids)
                
                # 2. Frame Status
                e_left_bounded = e.leftFace.bounded if e.leftFace else False
                e_rev_left_bounded = e.reverse.leftFace.bounded if e.reverse.leftFace else False
                is_frame = not (e_left_bounded and e_rev_left_bounded)
                
                # Print individual edge status
                status_str = "HIDDEN" if is_hidden else "VISIBLE"
                type_str = "FRAME" if is_frame else "INTERNAL"
                print(f"  Edge {i}: [{status_str}] | Type: [{type_str}] | Target: Vertex {getattr(e.head, 'num', '??')}")

                # Populate our logic lists
                if not is_hidden:
                    if not is_frame:
                        visible_internal_edges.append(e)
                    else:
                        frame_boundary_edges.append(e)

            print(f"--- 📊 Final Logic Counts ---")
            print(f"  Visible Internal: {len(visible_internal_edges)}")
            print(f"  Visible Frame:    {len(frame_boundary_edges)}")
            # --- COMPREHENSIVE DEBUG END ---

            # --- DECISION LOGIC ---
            # 1. Visible Internal Check
            if len(visible_internal_edges) > 0:
                if len(visible_internal_edges) == 2:
                    e1, e2 = visible_internal_edges[0], visible_internal_edges[1]
                    p1 = e1.head.p
                    p2 = e2.head.p
                    try:
                        angle_diff = abs(Graph.signedAngle(p1, vertex.p, p2))
                        is_straight = abs(angle_diff - np.pi) < 0.01
                        if is_straight:
                            print(f"  >>> RESULT: HIDE (Straight line through junction)")
                            return True
                    except Exception:
                        pass
                print(f"  >>> RESULT: KEEP (Has visible geologic line)")
                return False

            # 2. Frame Corner Check
            if len(frame_boundary_edges) >= 2:
                e1 = frame_boundary_edges[0]
                e2 = frame_boundary_edges[1]
                
                angle_diff = abs(Graph.signedAngle(e1.head.p, vertex.p, e2.head.p))
                is_straight = abs(angle_diff - np.pi) < 0.05
                
                print(f"  >>> Angle Check: {angle_diff:.4f} rad (Straight={is_straight})")
                
                if not is_straight:
                    print("  >>> RESULT: KEEP (Map Corner)")
                    return False
                else:
                    print("  >>> RESULT: HIDE (Straight line on frame)")

            # Default
            if len(visible_internal_edges) == 0 and len(frame_boundary_edges) < 2:
                 print("  >>> RESULT: HIDE (Isolated or hidden junction)")
            
            return True

        elif "label_angle" in func_name:
            # Safe unpack: Handles mock UI arrays [None, data] and real render parameters [res_map, data]
            angle_data = args[1] if len(args) > 1 else args[0]
            face, vertex_obj = angle_data
            v_p = vertex_obj.p if hasattr(vertex_obj, 'p') else vertex_obj
            
            # --- 💡 NEW: CHRONOLOGICAL UNION CHECK ---
            # Find the position of the CURRENT action in the global execution stack
            # --- CHRONOLOGICAL UNION CHECK ---
            current_action_idx = -1
            for idx, act in enumerate(self.actions):
                # Safe index access to avoid tuple length crashes
                act_func = act[0]
                act_args = act[1]
                act_kwargs = act[2] if len(act) > 3 else {} # Safer fallback
                
                # Check match using function object identity and underlying arguments memory address
                if act_func == func and id(act_args) == id(args):
                    current_action_idx = idx
                    break
            
            # Find if there is an active union containing this face
            face_id = id(face)
            union_action_idx = -1
            for idx, act in enumerate(self.actions):
                f_act, a_act, _ = act
                if "draw_union" in f_act.__name__.lower():
                    # Check if our face is part of this union's arguments
                    if any(id(f) == face_id for f in a_act if hasattr(f, 'edges')):
                        union_action_idx = idx
                        break

            # 🚀 CORE LOGIC CHANGE: If this angle action was placed AFTER the union execution,
            # it is explicitly meant to be a Combined Angle! Do not run structural obsolescence on it.
            if union_action_idx != -1 and current_action_idx > union_action_idx:
                print(f">>> RESULT: KEEP (New Combined Angle drawn after Union)")
                return False

            # --- PREVIOUS FIXED LOCAL BOUNDARY LOGIC (For old angles) ---
            # Look ONLY at the edges that belong structurally to the old parent face
            face_boundary_edges = list(face.edges) if hasattr(face, 'edges') else []
            
            # Filter edges that are incident to this specific vertex
            local_incident_edges = [
                e for e in face_boundary_edges 
                if Graph.vecDist(e.tail.p, v_p) < 1e-5 or Graph.vecDist(e.head.p, v_p) < 1e-5
            ]
            
            # Check which of these face-specific edges are still VISIBLE globally
            visible_local_edges = [
                e for e in local_incident_edges
                if (id(e) not in hidden_edge_ids) and (id(e.reverse) not in hidden_edge_ids)
            ]

            # RULE 1: If an old angle lost its surrounding structural lines, dissolve it
            if len(visible_local_edges) < 2:
                print(">>> RESULT: HIDE (Old angle edges dissolved by union)")
                return True

            # RULE 2: Flat surface rejection (180 degrees)
            if len(visible_local_edges) == 2:
                e1, e2 = visible_local_edges[0], visible_local_edges[1]
                p1 = e1.head.p if Graph.vecDist(e1.tail.p, v_p) < 1e-5 else e1.tail.p
                p2 = e2.head.p if Graph.vecDist(e2.tail.p, v_p) < 1e-5 else e2.tail.p
                
                try:
                    angle_diff = abs(Graph.signedAngle(p1, v_p, p2))
                    if abs(angle_diff - np.pi) < 0.05:
                        print(">>> RESULT: HIDE (Old angle flattened into straight line)")
                        return True
                except Exception:
                    return True

            print(">>> RESULT: KEEP (Old angle remains fully intact)")
            return False
        
        elif "label_edge" in func_name or "label_edge_list" in func_name:
            data = args[1] if len(args) > 1 else args[0]
            edges = data if isinstance(data, list) else [data]

            hidden_count = sum(
                1 for e in edges
                if (id(e) in hidden_edge_ids) or (id(e.reverse) in hidden_edge_ids)
            )

            if hidden_count > 0:
                return True

            for e in edges:
                for vertex in [e.tail, e.head]:
                    # Only check internal vertices, skip frame vertices
                    incident = list(vertex.outarcs)
                    is_frame_vertex = any(
                        not (inc.leftFace and inc.leftFace.bounded and
                            inc.reverse.leftFace and inc.reverse.leftFace.bounded)
                        for inc in incident
                    )
                    if is_frame_vertex:
                        continue

                    is_v_obsolete = self.is_marker_obsolete(
                        tool_label_vertex, [vertex], hidden_edge_ids
                    )
                    if is_v_obsolete:
                        return True

            return False

        # elif "label_edge" in func_name or "label_edge_list" in func_name:
        #     data = args[1] if len(args) > 1 else args[0]
        #     edges = data if isinstance(data, list) else [data]

        #     hidden_count = sum(
        #         1 for e in edges
        #         if (id(e) in hidden_edge_ids) or (id(e.reverse) in hidden_edge_ids)
        #     )

        #     if hidden_count > 0:
        #         return True

        #     for e in edges:
        #         for vertex in [e.tail, e.head]:
        #             is_v_obsolete = self.is_marker_obsolete(
        #                 tool_label_vertex, [vertex], hidden_edge_ids
        #             )
        #             if is_v_obsolete:
        #                 return True

        #     return False
        # elif "label_edge" in func_name or "label_edge_list" in func_name:
        #     # 1. Unpack edge data safely
        #     data = args[1] if len(args) > 1 else args[0]
        #     edges = data if isinstance(data, list) else [data]

        #     # print(f"🔍 Edge obsolete check: {len(edges)} segments")
        #     # for e in edges:
        #     #     is_hid = (id(e) in hidden_edge_ids) or (id(e.reverse) in hidden_edge_ids)
        #     #     print(f"  edge {id(e)}: hidden={is_hid}")
            
        #     # if all(((id(e) in hidden_edge_ids) or (id(e.reverse) in hidden_edge_ids)) for e in edges):
        #     #     print(">>> RESULT: HIDE (all hidden)")
        #     #     return True
            
        #     # 2. Base Condition: If all segments inside this action are hidden inside the union, hide it
        #     if all(((id(e) in hidden_edge_ids) or (id(e.reverse) in hidden_edge_ids)) for e in edges):
        #         return True
                
        #     # 3. Track how many segments in this action have actually degraded/flattened
        #     degraded_segments_count = 0

        #     for e in edges:
        #         # If this specific segment is hidden, it's automatically degraded
        #         if (id(e) in hidden_edge_ids) or (id(e.reverse) in hidden_edge_ids):
        #             degraded_segments_count += 1
        #             continue

        #         segment_flattened = False
        #         # Check both endpoints of this specific segment
        #         for vertex in [e.tail, e.head]:
        #             incident_edges = list(vertex.outarcs)
                    
        #             visible_internal_edges = []
        #             frame_boundary_edges = []
                    
        #             for incident_e in incident_edges:
        #                 is_hidden = (id(incident_e) in hidden_edge_ids) or (id(incident_e.reverse) in hidden_edge_ids)
                        
        #                 if not is_hidden:
        #                     e_left_bounded = incident_e.leftFace.bounded if incident_e.leftFace else False
        #                     e_rev_left_bounded = incident_e.reverse.leftFace.bounded if incident_e.reverse.leftFace else False
        #                     is_frame = not (e_left_bounded and e_rev_left_bounded)
                            
        #                     if not is_frame:
        #                         visible_internal_edges.append(incident_e)
        #                     else:
        #                         frame_boundary_edges.append(incident_e)

        #             total_visible_lines = len(visible_internal_edges) + len(frame_boundary_edges)
                    
        #             # If exactly 2 visible lines meet here, check if it became a straight line
        #             if total_visible_lines == 2:
        #                 all_visible = visible_internal_edges + frame_boundary_edges
        #                 e1, e2 = all_visible[0], all_visible[1]
                        
        #                 p1 = e1.head.p if Graph.vecDist(e1.tail.p, vertex.p) < 1e-5 else e1.tail.p
        #                 p2 = e2.head.p if Graph.vecDist(e2.tail.p, vertex.p) < 1e-5 else e2.tail.p
                        
        #                 try:
        #                     angle_diff = abs(Graph.signedAngle(p1, vertex.p, p2))
        #                     if abs(angle_diff - np.pi) < 0.05:
        #                         segment_flattened = True
        #                         break # No need to check the other vertex for this segment
        #                 except Exception:
        #                     pass
                            
        #         if segment_flattened:
        #             degraded_segments_count += 1

        #     # 💡 THE FIX: Only return True (obsolete) if EVERY segment in this action was broken down.
        #     # If any segment remains perfectly intact as a standalone edge, return False to KEEP it.
        #     return degraded_segments_count == len(edges)
                    

        elif "highlight_region" in func_name:
            # In tool_highlight_region(draw, img, manager, face, ...), 
            # args[0] is the face object
            face = args[0]
            
            # A face is obsolete if its boundary edges have been "hidden" 
            # (meaning the boundary between two regions was removed)
            if face.edges:
                # If ANY boundary edge of this face is hidden, the original 
                # face is now part of a larger union.
                return any(id(e) in hidden_edge_ids for e in face.edges)
    
    def add_action(self, func, *args, **kwargs):
        """
        The missing method: Stores a function and its arguments 
        to be executed later during render().
        """
        self.actions.append((func, args, kwargs))

    def _generate_label(self, category, prefix):
        #we make sure that we don't use labels for geomtric constructions that are obselete
        hidden_edge_ids = self.get_active_hidden_edges()
        
        active_used = set()
        for func, args, kwargs in self.actions:
            name = func.__name__.lower()
            if self.is_marker_obsolete(func, args, hidden_edge_ids):
                continue
            if category == "vertex" and "label_vertex" in name:
                label_text = args[1] if len(args) > 1 else None
                if label_text and str(label_text).startswith(prefix):
                    active_used.add(str(label_text))
            elif category == "angle" and "label_angle" in name:
                label_text = args[2] if len(args) > 2 else None
                if label_text and str(label_text).startswith(prefix):
                    active_used.add(str(label_text))
            elif category == "edge" and "label_edge" in name:
                label_text = args[2] if len(args) > 2 else None
                if label_text and str(label_text).startswith(prefix):
                    active_used.add(str(label_text))

        counter = 1
        while f"{prefix}{counter}" in active_used:
            counter += 1
        
        new_label = f"{prefix}{counter}"
        return new_label

    def add_vertex_action(self, vertex, label=None, auto_enumerate=False):
        """High-level method to add a vertex labeling task."""
        final_label = label
        if auto_enumerate:
            final_label = self._generate_label("vertex", "v")
        # elif label:
        #     self.used_labels["vertex"].add(str(label))
            
        # Now self.add_action will work!
        self.add_action(tool_label_vertex, vertex, final_label)


    def add_angle_action(self, angle_data, label=None, auto_enumerate=False):
            """High-level method to add an angle labeling task."""
            final_label = label
            if auto_enumerate:
                final_label = self._generate_label("angle", "a")
            # elif label:
            #     self.used_labels["angle"].add(str(label))
                

            self.add_action(
                tool_label_angle, 
                self.res_map,   
                angle_data,     
                final_label     
            )    
    # --- NEW METHOD FOR EDGES ---
# Inside class AnnotationSession:

    def add_combined_angle_action(self, union_faces, target_v, label):
        """Pushes a single combined angle transaction onto the action stack."""
        # We store the function and raw parameters. 
        # When session.render() iterates, it calls action.execute(draw, img, manager)
        self.actions.append((
            tool_label_combined_angle, 
            (self.res_map, union_faces, target_v, label), 
            {}
        ))
    def add_edge_action(self, edge_list, label=None, auto_enumerate=False, color=(147, 112, 219, 255)):
        """Handles the segment list passed from the UI."""
        if not isinstance(edge_list, list):
            edge_list = [edge_list]

        # Handle enumeration labels
        final_label = label
        if auto_enumerate:
            final_label = self._generate_label("edge", "e")

        print(f"DEBUG: Adding edge action with {len(edge_list)} segments.")

        self.add_action(
            tool_label_edge_list,
            self.res_map,
            edge_list,
            final_label,
            color
        )

    
    def add_region_action(self, face, label=None, color=(147, 112, 219, 100)):
            """
            High-level method to highlight a specific region. 
            Explicitly sets the default soft purple color to ensure consistency.
            """
            self.add_action(
                AnnotationSession.tool_highlight_region, 
                face, 
                label, 
                color, # Pass the default or custom color explicitly
                label_cache=self.face_label_cache  
            )

    def add_union_action(self, fa, fb, maxX=1.0, maxY=1.0):
        # This was missing res_map and shifting the arguments!
        self.add_action(
            draw_union, 
            self.res_map,          # 1st: res_map
            fa,                    # 2nd: fa
            fb,                    # 3rd: fb
            self.face_label_cache, # 4th: label_cache
            maxX,                  # 5th: maxX
            maxY                   # 6th: maxY
        )

    @staticmethod
    def tool_highlight_region(draw, img, manager, face, label=None, color=None, label_cache=None):
        faces = face if isinstance(face, (list, tuple)) else [face]
        valid_faces = [f for f in faces if f and f.bounded]
        if not valid_faces: 
            return
            
        fill_color = color if color else (255, 255, 0, 100) # Soft yellow

        # 1. Draw the underlying polygon fills for all faces in the group
        for f in valid_faces:
            draw.polygon(DrawGraph.FaceVertex2P(f), fill=fill_color)

        # 2. Highlight the outer boundaries
        group_face_ids = {id(f) for f in valid_faces}
        for f in valid_faces:
            for edge in f.edges:
                other_face = edge.reverse.leftFace if hasattr(edge, 'reverse') else None
                is_internal_contact = id(other_face) in group_face_ids if other_face else False
                if not is_internal_contact:
                    p1 = DrawGraph.V2P(edge.tail.p)
                    p2 = DrawGraph.V2P(edge.head.p)
                    draw.line([p1, p2], fill=fill_color, width=6)

        # 3. Label Text Masking & Overwrite
        primary_face = valid_faces[0]
        if label_cache and hasattr(primary_face, '_cache_idx') and primary_face._cache_idx in label_cache:
            lp, d = label_cache[primary_face._cache_idx]
        else:
            lp, d = Graph.LetterPointFace(primary_face)
            
        cx, cy = DrawGraph.V2P(lp)
        
        is_large = d > 0.06
        font_main = DrawGraph.GetSystemFont(80 if is_large else 45)
        
        # Check if we have an overriding Union designation label (like 'U')
        display_letter = label if (label and str(label).strip() != "") else primary_face.letter

        if display_letter != primary_face.letter:
            # 💡 SOLUTION: Draw a clean white background circle over the old "C" 
            # so the text layers do not clash or overlap on the canvas
            mask_r = 45 if is_large else 25
            draw.ellipse(
                [cx - mask_r, cy - mask_r, cx + mask_r, cy + mask_r], 
                fill=(255, 255, 255, 255)
            )
            # Re-apply a clean layer of your fill color over the mask patch
            draw.ellipse(
                [cx - mask_r, cy - mask_r, cx + mask_r, cy + mask_r], 
                fill=fill_color
            )

        # 4. Render the official primary designation text in big bold lettering
        draw.text(
            (cx, cy), 
            str(display_letter), 
            fill=(0, 0, 0, 255), 
            font=font_main, 
            anchor="mm", 
            stroke_width=2, 
            stroke_fill=(255, 255, 255, 255)
        )
        
        manager.reserve(cx, cy, 50, 80)

    def add_union_highlight_action(self, union_action, color=(255, 255, 0, 180), **kwargs):
        func, args, original_kwargs = union_action
        if len(args) >= 3:
            res_map, fa, fb = args[0], args[1], args[2]
            maxX = args[4] if len(args) > 4 else 1.0
            maxY = args[5] if len(args) > 5 else 1.0
            final_color = kwargs.get('color', color)

            self.add_action(
                run_highlight_union_fill,
                res_map,
                fa,
                fb,
                self.face_label_cache,
                maxX,
                maxY,
                final_color  # 作为位置参数传入，不用 closure
            )
            print(f"Registered clean union highlight action. Color: {final_color}")
    
    # --- ADD NEW LINES ---
    def add_auxiliary_line_action(self, line_type, *args, **kwargs):
        """
        Generic method to add auxiliary lines.
        line_type: tool_draw_extended_edge, tool_draw_points_line, or tool_draw_axis_line
        """
        self.add_action(line_type, *args, **kwargs)
    
    def undo_action(self):
        if self.actions:
            last_action = self.actions.pop()
            func = last_action[0]
            print(f"Undid action: {func.__name__}")

            # # Rebuild used_labels and counters from scratch based on remaining actions
            # self.used_labels = {"vertex": set(), "angle": set(), "edge": set()}
            # self.counters = {"vertex": 1, "angle": 1, "edge": 1}

            for action_func, action_args, action_kwargs in self.actions:
                name = action_func.__name__.lower()
                if "label_vertex" in name:
                    # label is the second arg: (vertex, label_text)
                    label_text = action_args[1] if len(action_args) > 1 else None
                    if label_text and str(label_text).startswith("v"):
                        self.used_labels["vertex"].add(str(label_text))
                        try:
                            num = int(str(label_text)[1:])
                            self.counters["vertex"] = max(self.counters["vertex"], num + 1)
                        except ValueError:
                            pass
                elif "label_angle" in name:
                    label_text = action_args[2] if len(action_args) > 2 else None
                    if label_text and str(label_text).startswith("a"):
                        self.used_labels["angle"].add(str(label_text))
                        try:
                            num = int(str(label_text)[1:])
                            self.counters["angle"] = max(self.counters["angle"], num + 1)
                        except ValueError:
                            pass
                elif "label_edge" in name:
                    label_text = action_args[2] if len(action_args) > 2 else None
                    if label_text and str(label_text).startswith("e"):
                        self.used_labels["edge"].add(str(label_text))
                        try:
                            num = int(str(label_text)[1:])
                            self.counters["edge"] = max(self.counters["edge"], num + 1)
                        except ValueError:
                            pass
        else:
            print("No actions to undo.")

    def render(self):
        img = Image.new("RGBA", self.img_size, (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)
        manager = LabelManager()

        # 1. Gather all topologically active hidden edges globally
        shared_edge_ids = self.get_active_hidden_edges()

        # FIXED PASS 1: Always draw the entire base map completely.
        # No more filtering out faces, which prevents random white holes on undo.
        DrawGraph.DrawAllFaces(self.res_map, draw, manager, label_cache=self.face_label_cache)

        # PASS 2: Structural Polygons & Color Highlights (Fills Only)
        # Gather faces that have active custom fills to skip duplicate default fills
        highlighted_face_ids = set()
        for action in self.actions:
            func, args, kwargs = action
            name = func.__name__.lower()
            if "run_highlight_union_fill" in name:  # 只针对 union highlight
                if len(args) >= 3:
                    if args[1]: highlighted_face_ids.add(id(args[1]))  # fa
                    if args[2]: highlighted_face_ids.add(id(args[2]))  # fb

        for action in self.actions:
            func, args, kwargs = action
            name = func.__name__.lower()
            
            if "union" in name or "region" in name or "fill" in name:
                if name == "draw_union" and len(args) >= 3:
                    fa, fb = args[1], args[2]
                    if id(fa) in highlighted_face_ids or id(fb) in highlighted_face_ids:
                        continue
                        
                func(draw, img, manager, *args, **kwargs)

        # PASS 3: Clean Geologic Boundary Lines (Base Grid)
        for edge in self.res_map.edges:
            if id(edge) in shared_edge_ids: 
                continue
            p1 = DrawGraph.V2P(edge.tail.p)
            p2 = DrawGraph.V2P(edge.head.p)
            draw.line([p1, p2], fill=(0, 0, 0, 255), width=3)

        # PASS 4: Active Annotation Overlay & Text Labels
        for action in self.actions:
            func, args, kwargs = action
            name = func.__name__.lower()
            
            # Skip base structural fills/unions
            if "union" in name or "region" in name or "fill" in name: 
                continue 
            
            is_obs = self.is_marker_obsolete(func, args, shared_edge_ids)
            print(f"🎨 PASS4 action={func.__name__}, obsolete={is_obs}")  
            # Rely strictly on topology checks to hide markers that actually vanished
            if self.is_marker_obsolete(func, args, shared_edge_ids): 
                continue 
            
            # Execute and draw the annotation
            func(draw, img, manager, *args, **kwargs)
                
        return img
                
          
    
def find_label_position(manager, target_px, target_py, text_w, text_h, frame_bounds, canvas_size=None):
    """
    Finds label position with three tiers of search:
    1. Tight Internal (Right next to point)
    2. Mid-Range Internal (Double distance, still inside frame)
    3. External (Outside frame with leader line)
    """
    f_min, f_max = frame_bounds
    c_w, c_h = canvas_size if canvas_size else (1000, 1000)
    
    SAFE_MARGIN = 2 
    COLLISION_PADDING = 2 # Reduced for tighter packing

    # --- 1. INTERNAL PLACEMENT (Tier 1: Tight & Tier 2: Mid-Range) ---
    search_tiers = [
        [(15, -22), (15, 12), (-45, -22), (-45, 12)], # Tier 1: Tight
        [(35, -45), (35, 30), (-75, -45), (-75, 30)]  # Tier 2: Mid-Range
    ]

    for offsets in search_tiers:
        for ox, oy in offsets:
            tx, ty = target_px + ox, target_py + oy
            # Ensure it stays inside the frame bounds
            if f_min < tx < f_max - text_w and f_min < ty < f_max - text_h:
                if not manager.is_overlapping(tx + text_w/2, ty + text_h/2, text_w, text_h, padding=COLLISION_PADDING):
                    return (tx, ty), False, None

    # --- 2. EXTERNAL PLACEMENT (Tier 3: Outside Frame) ---
    dists = {'L': target_px - f_min, 'R': f_max - target_px, 'T': target_py - f_min, 'B': f_max - target_py}
    edge = min(dists, key=dists.get)
    
    for depth in [0, 30, 60]: # Gradually move further out if needed
        for s_off in [0, 35, -35, 70, -70]:
            if edge == 'L':
                tx = min(f_min - 25 - depth - text_w, target_px - 50 - text_w)
                ty = target_py - (text_h / 2) + s_off
            elif edge == 'R':
                tx = max(f_max + 15 + depth, target_px + 50)
                ty = target_py - (text_h / 2) + s_off
            elif edge == 'T':
                tx = target_px - (text_w / 2) + s_off
                ty = min(f_min - 25 - depth - text_h, target_py - 50 - text_h)
            else: # Bottom
                tx = target_px - (text_w / 2) + s_off
                ty = max(f_max + 15 + depth, target_py + 50)
                
            if 0 <= tx <= c_w - text_w and 0 <= ty <= c_h - text_h:
                if not manager.is_overlapping(tx + text_w/2, ty + text_h/2, text_w, text_h, padding=COLLISION_PADDING):
                    return (tx, ty), True, edge
                    
    # Ultimate fallback if completely constrained
    return (target_px + 15, target_py - 22), False, None


def get_connection_point(tx, ty, text_w, text_h, edge_side):
    """
    Computes the anchor vertex on the bounding box of the text label 
    to neatly hook a leader line to, depending on which side it fell.
    """
    if edge_side == 'L':
        return tx + text_w, ty + text_h / 2
    elif edge_side == 'R':
        return tx, ty + text_h / 2
    elif edge_side == 'T':
        return tx + text_w / 2, ty + text_h
    elif edge_side == 'B':
        return tx + text_w / 2, ty
    return tx, ty

def get_extended_point(p1, p2, frame_bounds=(100, 900)):
    f_min, f_max = frame_bounds
    x1, y1 = p1
    x2, y2 = p2
    
    dx = x2 - x1
    dy = y2 - y1
    
    t_values = []
    if dx != 0:
        t_values.append((f_min - x1) / dx)
        t_values.append((f_max - x1) / dx)
    if dy != 0:
        t_values.append((f_min - y1) / dy)
        t_values.append((f_max - y1) / dy)
    
    valid_t = [t for t in t_values if t > 0]
    if not valid_t: return p2
    
    t = min(valid_t)
    return (x1 + t * dx, y1 + t * dy)

BLUE = (0, 0, 255, 255)

def tool_draw_extended_edge(draw, img, manager, edge, color=(0, 0, 255, 255), width=8):
    """Extends an existing map edge to the frame boundaries."""
    p1 = DrawGraph.V2P(edge.tail.p)
    p2 = DrawGraph.V2P(edge.head.p)
    ext_start = get_extended_point(p2, p1)
    ext_end = get_extended_point(p1, p2)
    draw.line([ext_start, ext_end], fill=color, width=width)

def tool_draw_points_line(draw, img, manager, v1_p, v2_p, extend=False, color=(0, 0, 255, 255), width=8):
    """Draws a line between two arbitrary points (e.g., a diagonal)."""
    p1 = DrawGraph.V2P(v1_p)
    p2 = DrawGraph.V2P(v2_p)
    if extend:
        p1 = get_extended_point(p2, p1)
        p2 = get_extended_point(p1, p2)
    draw.line([p1, p2], fill=color, width=width)

def tool_draw_axis_line(draw, img, manager, vertex_p, direction='H', color=(0, 0, 255, 255), width=8):
    """Draws a horizontal or vertical reference line through a point."""
    f_min, f_max = 100, 900
    px, py = DrawGraph.V2P(vertex_p)
    if direction.upper() == 'H':
        draw.line([(f_min, py), (f_max, py)], fill=color, width=width)
    else:
        draw.line([(px, f_min), (px, f_max)], fill=color, width=width)

def highlight_vertex(draw, vertex_p, color=(255, 215, 0, 200)):
    px, py = DrawGraph.V2P(vertex_p)
    r = 12  
    
    # Increased halo size to +5 for "PPT-level" visibility
    draw.ellipse(
        [px - (r + 2), py - (r + 2), px + (r + 2), py + (r + 2)], 
        fill=(255, 255, 255, 255)
    )
    
    # Original Golden Dot
    draw.ellipse(
        [px - r, py - r, px + r, py + r], 
        fill=color, 
        outline=(184, 134, 11, 255),
        width=4
    )

def highlight_edge(draw, edge, color=(0, 255, 255, 120)):
    p1 = DrawGraph.V2P(edge.tail.p)
    p2 = DrawGraph.V2P(edge.head.p)
    draw.line([p1, p2], fill=color, width=10)


def tool_highlight_region(draw, img, manager, face, label=None, color=None, label_cache=None):
    """
    Highlights a single region or a union of multiple regions by tracing 
    their collective outer edges, skipping hidden internal boundaries.
    """
    # 1. Handle single face vs multiple faces gracefully
    faces = face if isinstance(face, (list, tuple)) else [face]
    valid_faces = [f for f in faces if f and f.bounded]
    if not valid_faces: 
        return
        
    fill_color = color if color else (147, 112, 219, 100) # Soft purple

    # 2. Draw the underlying polygon fills for all faces in the group
    for f in valid_faces:
        draw.polygon(DrawGraph.FaceVertex2P(f), fill=fill_color)

    # 3. HIGHLIGHT THE ENTIRE OUTER BOUNDARY
    # Collect all boundary IDs within this group
    group_face_ids = {id(f) for f in valid_faces}
    
    for f in valid_faces:
        for edge in f.edges:
            # Determine if this edge is an internal contact line between the merging faces
            other_face = edge.reverse.leftFace if hasattr(edge, 'reverse') else None
            is_internal_contact = id(other_face) in group_face_ids if other_face else False
            
            # ONLY highlight if it faces the outside of the unified group U
            if not is_internal_contact:
                p1 = DrawGraph.V2P(edge.tail.p)
                p2 = DrawGraph.V2P(edge.head.p)
                # Draw a prominent glowing line along the true outer perimeter
                draw.line([p1, p2], fill=fill_color, width=6)

    # 4. Label Text Sync (Anchored to the primary representative face)
    primary_face = valid_faces[0]
    face_id = id(primary_face)
    
    if label_cache and face_id in label_cache:
        lp, d = label_cache[face_id]
    else:
        lp, d = Graph.LetterPointFace(primary_face)
        
    cx, cy = DrawGraph.V2P(lp)
    
    is_large = d > 0.06
    font_main = DrawGraph.GetSystemFont(80 if is_large else 45)
    font_sub = DrawGraph.GetSystemFont(35 if is_large else 22)
    
    # Redraw original region letter
    draw.text((cx, cy), primary_face.letter, fill=(0, 0, 0, 255), font=font_main, 
              anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255, 255))
    
    # Render tracking sub-label safely on top
    if label:
        vertical_offset = 45 if is_large else 28
        draw.text((cx, cy + vertical_offset), str(label), fill=(200, 0, 0, 255), 
                  font=font_sub, anchor="mm", stroke_width=1, 
                  stroke_fill=(255, 255, 255, 255))
    
    manager.reserve(cx, cy, 50, 80)

def draw_leader_with_arrow(draw, start_pos, end_pos, color):
    draw.line([start_pos, end_pos], fill=color, width=2)
    angle = math.atan2(end_pos[1] - start_pos[1], end_pos[0] - start_pos[0])
    arrow_len, spread = 20, 0.4
    p1 = (start_pos[0] + arrow_len * math.cos(angle + spread), start_pos[1] + arrow_len * math.sin(angle + spread))
    p2 = (start_pos[0] + arrow_len * math.cos(angle - spread), start_pos[1] + arrow_len * math.sin(angle - spread))
    draw.polygon([start_pos, p1, p2], fill=color)

def draw_labeled_feature(draw, img, manager, point, label_text, font, color, frame_bounds=(100, 900)):
    """Standard tool for labeling with improved leader line length."""
    px, py = DrawGraph.V2P(point)
    # Estimate text dimensions
    text_w, text_h = 45, 30 
    
    canvas_size = (img.width, img.height)
    pos_data, needs_leader, edge = find_label_position(
        manager, px, py, text_w, text_h, frame_bounds, canvas_size
    )
    
    if pos_data:
        tx, ty = pos_data
        if needs_leader:
            # 1. Get the specific point on the text box  start the line
            conn_p = get_connection_point(tx, ty, text_w, text_h, edge)
            
            # 2. Draw a line from the label connection point to the vertex
            # This ensures the line is as long as the distance requires
            draw.line([conn_p, (px, py)], fill=color, width=2)
            
            # 3. Draw the arrowhead specifically at the vertex (px, py)
            # This points exactly at the feature being labeled
            draw_arrow_head(draw, conn_p, (px, py), color)
            
        # Draw the label text
        draw.text((tx, ty), label_text, fill=color, font=font, 
                  stroke_width=2, stroke_fill=(255,255,255,255))
        
        # Reserve the area in the manager
        manager.reserve(tx + text_w/2, ty + text_h/2, text_w, text_h)

def draw_arrow_head(draw, start_pos, end_pos, color):
    """Draws an arrowhead at end_pos, pointing away from start_pos."""
    # Calculate angle of the line
    angle = math.atan2(end_pos[1] - start_pos[1], end_pos[0] - start_pos[0])
    
    arrow_len = 15
    spread = 0.5 # Radians
    
    # Calculate the two 'fins' of the arrowhead
    p1 = (end_pos[0] - arrow_len * math.cos(angle - spread), 
          end_pos[1] - arrow_len * math.sin(angle - spread))
    p2 = (end_pos[0] - arrow_len * math.cos(angle + spread), 
          end_pos[1] - arrow_len * math.sin(angle + spread))
    
    draw.polygon([end_pos, p1, p2], fill=color)

def get_shared_edges(fa, fb):
    """
    Identifies edges shared exclusively between two valid, bounded geological faces.
    Protects the outer frame boundaries from being hidden.
    """
    shared = set()
    
    # Safety Check: Ensure both items exist and have the 'bounded' attribute
    if not fa or not fb:
        return shared
    if not hasattr(fa, 'bounded') or not hasattr(fb, 'bounded'):
        return shared
    if not fa.bounded or not fb.bounded:
        return shared

    # Gather object IDs from Face B for strict lookup
    fb_edge_ids = {id(e) for e in fb.edges}
    fb_reverse_ids = {id(e.reverse) for e in fb.edges if hasattr(e, 'reverse')}

    for edge in fa.edges:
        e_id = id(edge)
        e_rev_id = id(edge.reverse) if hasattr(edge, 'reverse') else None
        
        # Check if the edge or its twin is structurally part of Face B
        is_shared = (e_id in fb_edge_ids) or (e_id in fb_reverse_ids) or \
                    (e_rev_id in fb_edge_ids) if e_rev_id else False

        if is_shared:
            # Shield Check: Ensure it is a internal geologic contact line, NOT the map frame
            e_left_bounded = edge.leftFace.bounded if edge.leftFace else False
            e_rev_left_bounded = edge.reverse.leftFace.bounded if edge.reverse.leftFace else False
            
            if e_left_bounded and e_rev_left_bounded:
                shared.add(e_id)
                if e_rev_id:
                    shared.add(e_rev_id)
                    
    return shared

def reset_label_session():
    global USED_LABELS
    USED_LABELS['vertex'].clear()
    USED_LABELS['angle'].clear()
    USED_LABELS['edges'].clear()

def tool_label_vertex(draw, img, manager, vertex, label_text=None, color=(0, 0, 255, 255)):
    # 1. Draw a significantly larger white "Base"
    px, py = DrawGraph.V2P(vertex.p)
    
    # Large white halo (Radius 12)
    draw.ellipse([px-12, py-12, px+12, py+12], fill=(255, 255, 255, 255))
    
    # # Core Red Dot (Radius 10)
    draw.ellipse([px-10, py-10, px+10, py+10], fill=(255, 0, 0, 255))
    
    # 2. Draw the Text
    if label_text is not None:
        font_labels = DrawGraph.GetSystemFont(35)
        # Note: If your draw_labeled_feature doesn't have white stroke, 
        # you might need to check that function too!
        draw_labeled_feature(draw, img, manager, vertex.p, str(label_text), font_labels, color)

def tool_label_angle(draw, img, manager, *args, **kwargs):
    """
    Draws an angular arc marker and text label at a corner.
    Traces union boundaries by physically hopping across hidden edges
    into adjacent faces until a real visible boundary is reached.
    """
    if len(args) >= 2:
        res_map = args[0]
        face, vertex = args[1]
    else:
        face, vertex = args[0]
        
    v_p = vertex.p
    session = kwargs.get('session', None)
    hidden_edge_ids = session.get_active_hidden_edges() if session else set()

    # --- TRACKING EDGE 1 (Leaving the vertex) ---
    # Find the edge belonging to the clicked face that starts at this vertex
    edge1 = None
    for e in face.edges:
        if e.tail == vertex or math.hypot(e.tail.p.x - v_p.x, e.tail.p.y - v_p.y) < 1e-5:
            edge1 = e
            break

    if not edge1:
        return

    # Trace Edge 1: Hop across hidden seams into neighboring faces
    visited_edges1 = {id(edge1)}
    while id(edge1) in hidden_edge_ids or (hasattr(edge1, 'reverse') and id(edge1.reverse) in hidden_edge_ids):
        if hasattr(edge1, 'reverse') and edge1.reverse and edge1.reverse.leftFace:
            neighbor_face = edge1.reverse.leftFace
            next_candidate = None
            # Find the edge in the new face leaving this vertex that isn't our old line
            for ne in neighbor_face.edges:
                if (ne.tail == vertex or math.hypot(ne.tail.p.x - v_p.x, ne.tail.p.y - v_p.y) < 1e-5) and id(ne) not in visited_edges1:
                    next_candidate = ne
                    break
            
            if next_candidate:
                edge1 = next_candidate
                visited_edges1.add(id(edge1))
            else:
                break
        else:
            break

    # --- TRACKING EDGE 2 (Entering the vertex) ---
    # Find the edge belonging to the clicked face that ends at this vertex
    edge2 = None
    for e in face.edges:
        if e.head == vertex or math.hypot(e.head.p.x - v_p.x, e.head.p.y - v_p.y) < 1e-5:
            edge2 = e
            break

    if not edge2:
        return

    # Trace Edge 2: Hop across hidden seams into neighboring faces backwards
    visited_edges2 = {id(edge2)}
    while id(edge2) in hidden_edge_ids or (hasattr(edge2, 'reverse') and id(edge2.reverse) in hidden_edge_ids):
        if hasattr(edge2, 'reverse') and edge2.reverse and edge2.reverse.leftFace:
            # When an incoming edge is hidden, its reverse is an outgoing edge for the neighbor face
            neighbor_face = edge2.reverse.leftFace
            next_candidate = None
            # Find the edge in the new face that comes INTO this vertex
            for ne in neighbor_face.edges:
                if (ne.head == vertex or math.hypot(ne.head.p.x - v_p.x, ne.head.p.y - v_p.y) < 1e-5) and id(ne) not in visited_edges2:
                    next_candidate = ne
                    break
            
            if next_candidate:
                edge2 = next_candidate
                visited_edges2.add(id(edge2))
            else:
                break
        else:
            break

    # --- GEOMETRIC ARC CALCULATIONS ---
    # edge1 points OUT from vertex; edge2 points IN to vertex.
    # Get the points far away from the vertex to calculate vectors.
    p1_far = edge1.head.p if math.hypot(edge1.tail.p.x - v_p.x, edge1.tail.p.y - v_p.y) < 1e-5 else edge1.tail.p
    p2_far = edge2.tail.p if math.hypot(edge2.head.p.x - v_p.x, edge2.head.p.y - v_p.y) < 1e-5 else edge2.head.p

    ang1 = math.atan2(p1_far.y - v_p.y, p1_far.x - v_p.x)
    ang2 = math.atan2(p2_far.y - v_p.y, p2_far.x - v_p.x)

    start_deg = math.degrees(ang1) % 360
    end_deg = math.degrees(ang2) % 360

    # Ensure the arc sweeps the interior space of the union group
    if (end_deg - start_deg) % 360 > 180:
        start_deg, end_deg = end_deg, start_deg

    # --- RENDERING ---
    radius = 25
    class PointMock:
        def __init__(self, x, y):
            self.x = x
            self.y = y

    p_min = DrawGraph.V2P(PointMock(v_p.x - radius, v_p.y - radius))
    p_max = DrawGraph.V2P(PointMock(v_p.x + radius, v_p.y + radius))
    p_bbox = [p_min[0], p_min[1], p_max[0], p_max[1]]
    
    # Draw the boundary-to-boundary continuous arc
    draw.arc(p_bbox, start=start_deg, end=end_deg, fill=(255, 69, 0, 255), width=3)

    # Place text along the true geometric bisector
    label_text = kwargs.get('label', None) or (args[2] if len(args) > 2 else None)
    if label_text:
        diff = (end_deg - start_deg) % 360
        mid_deg = (start_deg + diff / 2.0) % 360
            
        mid_rad = math.radians(mid_deg)
        text_dist = radius + 15
        
        tx_g = v_p.x + text_dist * math.cos(mid_rad)
        ty_g = v_p.y + text_dist * math.sin(mid_rad)
        tx_p, ty_p = DrawGraph.V2P(PointMock(tx_g, ty_g))
        
        manager.add_label(label_text, tx_p, ty_p, draw, fill_color=(0, 0, 0, 255))

def tool_label_combined_angle(draw, img, manager, res_map, union_faces, target_v, label):
    """
    Draws multiple sub-angles belonging to a union region as a single atomic action.
    This allows a single Undo command to revert the entire combined angle decoration.
    """
    drawn_count = 0
    for f in union_faces:
        f_vertices = [e.tail for e in f.edges]
        if target_v in f_vertices:
            # Assign the visual text label only to the first sub-angle to avoid text overlap
            current_label = label if drawn_count == 0 else None
            
            # Directly invoke the underlying atomic drawing routine 
            tool_label_angle(draw, img, manager, res_map, (f, target_v), current_label)
            drawn_count += 1
            
    print(f"[Action Executed] Combined angle drawn across {drawn_count} sub-faces.")

def tool_label_edge(draw, img, manager, edge, label_text=None, color=(200, 0, 255, 255)):
    """
    1. Highlights edge with a 'Bright Purple' glow.
    2. If label_text is provided, places it at the midpoint.
    3. Uses a two-sided collision check to prevent overlapping labels.
    """
    p1 = DrawGraph.V2P(edge.tail.p)
    p2 = DrawGraph.V2P(edge.head.p)

    # 1. BRIGHT PURPLE HIGHLIGHT
    # White background stroke for contrast
    draw.line([p1, p2], fill=(255, 255, 255, 255), width=14) 
    # Core Purple line
    draw.line([p1, p2], fill=color, width=10) 

# 2. OPTIONAL LABELING
    if label_text:
        mid_x = (p1[0] + p2[0]) / 2
        mid_y = (p1[1] + p2[1]) / 2
        
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        length = math.sqrt(dx**2 + dy**2)
        if length == 0: return
        
        # Unit normal vector
        nx, ny = -dy / length, dx / length
        
        text_w, text_h = 32, 22
        font = DrawGraph.GetSystemFont(28)
        
        # IMPROVED: Flip Logic based on Odd/Even parity
        # This prevents adjacent short edges (like 5 and 6) from crowding the same side.
        try:
            val = int(label_text)
            if val % 2 == 0:
                # Even numbers prefer Side B (Inside)
                search_offsets = [-30, 30, -55, 55]
            else:
                # Odd numbers prefer Side A (Outside)
                search_offsets = [30, -30, 55, -55]
        except ValueError:
            search_offsets = [30, -30, 50, -50]

        final_tx, final_ty = None, None
        
        # Check positions with increased padding (5 instead of 2) for better spacing
        for dist in search_offsets:
            tx, ty = mid_x + nx * dist, mid_y + ny * dist
            if not manager.is_overlapping(tx, ty, text_w, text_h, padding=5):
                final_tx, final_ty = tx, ty
                break
        
        # Fallback
        if final_tx is None:
            final_tx, final_ty = mid_x + nx * 60, mid_y + ny * 60

        # Draw the text with white stroke for maximum pop
        draw.text((final_tx, final_ty), str(label_text), fill=color, font=font, 
                  anchor="mm", stroke_width=3, stroke_fill=(255, 255, 255, 255))
        
        manager.reserve(final_tx, final_ty, text_w, text_h, padding=5)

def tool_label_edge_list(draw, img, manager, res_map, edge_list, label, color, **kwargs):
    """
    Highlights EVERY segment provided in edge_list to form a continuous line.
    """
    print(f"DEBUG tool_label_edge_list: {len(edge_list)} edges, color={color}")
    if not edge_list:
        return
        
    # 1. DRAW HIGHLIGHTS FOR ALL SEGMENTS
    for edge in edge_list:
        p1 = DrawGraph.V2P(edge.tail.p)
        p2 = DrawGraph.V2P(edge.head.p)
        # White backing (makes the purple pop)
        draw.line([p1, p2], fill=(255, 255, 255, 255), width=14) 
        # Colored glow
        draw.line([p1, p2], fill=color, width=10) 
        
    # 2. DRAW TEXT LABEL ONCE
    if label:
        # Place label at the midpoint of the middle segment in the list
        mid_idx = len(edge_list) // 2
        
        # FIXED: Removed res_map from this function call
        tool_label_edge(draw, img, manager, edge_list[mid_idx], label, color)

def calculate_angle_center_point(angle_data, distance=60):
    """
    Finds a point along the angle bisector inside the face.
    angle_data: namedtuple(p, parent_face)
    """
    # --- FIX: Unpack the tuple ---
    face, vertex = angle_data
    v_p = vertex.p 
    
    # Manually find edges to avoid the 'int' return error from ArcsAtVertexInFace
    e_in = next((e for e in face.edges if e.head.p == v_p), None)
    e_out = next((e for e in face.edges if e.tail.p == v_p), None)
    
    if not e_in or not e_out:
        # Fallback: if edges aren't found, return original point
        return v_p
    
    # 2. Get directions (in radians)
    # Direction of the edge leaving V
    dir_out = e_out.direction 
    # Direction of the edge coming into V (reverse it to get direction away from V)
    dir_in = e_in.reverse.direction 
    
    # 3. Calculate the interior sweep
    diff = dir_out - dir_in
    while diff < 0:
        diff += 2 * np.pi
    while diff >= 2 * np.pi:
        diff -= 2 * np.pi
    
    # The bisector direction is the start direction + half the interior sweep
    bisector_dir = dir_in + (diff / 2)
    
    # 4. Create the offset vector (Scaling distance to math space)
    # Assuming 800 is your coordinate scale factor
    offset_x = math.cos(bisector_dir) * (distance / 800)
    offset_y = math.sin(bisector_dir) * (distance / 800)
    
    return Graph.Vector(v_p.x + offset_x, v_p.y + offset_y)


USED_ANGLE_LABELS = set()

def tool_draw_interior_arc(draw, img, manager, res_map, angle_data, radius=40, color=(255, 0, 0, 255)):
    """
    Draws the interior arc for a face at a specific vertex.
    Updated to include res_map for parameter alignment in the action stack.
    """
    # --- UNPACK THE TUPLE ---
    # angle_data is args[1] in the session action stack
    face, vertex = angle_data
    
    # Use the vertex's math position .p
    p_center_math = vertex.p 
    p_center_pixel = DrawGraph.V2P(p_center_math)
    
    # Finding the incoming and outgoing edges for the specific face
    e_in = next((e for e in face.edges if e.head.p == p_center_math), None)
    e_out = next((e for e in face.edges if e.tail.p == p_center_math), None)
    
    if not e_in or not e_out:
        return

    cx, cy = p_center_pixel
    px_prev, py_prev = DrawGraph.V2P(e_in.tail.p)
    px_next, py_next = DrawGraph.V2P(e_out.head.p)

    # Calculate vectors relative to the vertex
    v_prev = (px_prev - cx, py_prev - cy)
    v_next = (px_next - cx, py_next - cy)

    # Calculate angles for the arc
    ang_prev = math.degrees(math.atan2(v_prev[1], v_prev[0]))
    ang_next = math.degrees(math.atan2(v_next[1], v_next[0]))

    start, end = ang_prev, ang_next
    while end < start:
        end += 360
    
    # Avoid drawing if it's a straight line (collinear edges)
    if abs((end - start) - 180.0) < 0.1:
        return

    bbox = [cx - radius, cy - radius, cx + radius, cy + radius]

    # 1. THE HALO: Draw a thicker white arc first for contrast
    draw.arc(bbox, start=start, end=end, fill=(255, 255, 255, 255), width=7)

    # 2. THE CORE: Draw the primary colored arc
    draw.arc(bbox, start=start, end=end, fill=color, width=5)


import math
def tool_label_angle(draw, img, manager, res_map, angle_data, label_text=None, color=(0, 128, 0, 255)):
    face, vertex = angle_data
    arc_radius = 40
    text_w, text_h = 30, 20
    
    # Draw the interior arc
    tool_draw_interior_arc(draw, img, manager, res_map, angle_data, radius=arc_radius, color=color)
    if label_text:
        v_p = vertex.p
        px, py = DrawGraph.V2P(v_p)
        arc_target_p = calculate_angle_center_point(angle_data, distance=arc_radius)
        tpx, tpy = DrawGraph.V2P(arc_target_p)
        
        # This point is INSIDE the angle
        inner_p = calculate_angle_center_point(angle_data, distance=45)
        
        # --- FLIP DIRECTION: Negate dx and dy to move OUTSIDE ---
        dx = -(inner_p.x - v_p.x)
        dy = -(inner_p.y - v_p.y)
        
        final_lx, final_ly = None, None
        needs_arrow = False
        
        # We start searching slightly further out (1.5x) because the 
        # label is now "outside" and might hit the vertex or nearby edges
        search_rings = [(1.5, False), (2.2, True), (3.0, True)]
        
        for dist_mult, use_arrow in search_rings:
            for offset_angle in [0, 0.4, -0.4, 0.8, -0.8]:
                cos_a, sin_a = math.cos(offset_angle), math.sin(offset_angle)
                # Apply the inverted vector
                rx = (dx * cos_a - dy * sin_a) * dist_mult
                ry = (dx * sin_a + dy * cos_a) * dist_mult
                
                lx, ly = DrawGraph.V2P(Graph.Vector(v_p.x + rx, v_p.y + ry))
                
                if not manager.is_overlapping(lx, ly, text_w, text_h, padding=2):
                    final_lx, final_ly = lx, ly
                    needs_arrow = use_arrow
                    break
            if final_lx is not None: break

        # Fallback using the inverted vector
        if final_lx is None:
            flx, fly = DrawGraph.V2P(Graph.Vector(v_p.x + dx * 1.5, v_p.y + dy * 1.5))
            final_lx, final_ly = flx, fly
            needs_arrow = False

        # 2. Draw leader line if needed
        if needs_arrow:
            # We connect to the vertex (px, py) or the arc center (tpx, tpy)
            # Connecting to the vertex usually looks better for 'outside' labels
            draw.line([(final_lx, final_ly), (px, py)], fill=color, width=1)
            draw_arrow_head(draw, (final_lx, final_ly), (px, py), color)

        # 3. Final Text Render
        font = DrawGraph.GetSystemFont(30)
        draw.text((final_lx, final_ly), str(label_text), fill=color, font=font, 
                  anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255, 255))
        
        manager.reserve(final_lx, final_ly, text_w, text_h, padding=2)

   


def draw_union(draw, img, manager, res_map, fa, fb, label_cache, maxX, maxY, **kwargs):
    """
    Note: 'draw' and 'img' are passed in by AnnotationSession.render; 
    do not re-initialize them here!
    """
    # 1. Ensure shared_edge_ids exists (calculate manually if not passed from render)
    shared_edge_ids = get_shared_edges(fa, fb)
    
    DrawGraph.InitColors(alpha=153)
    font_bold = DrawGraph.GetSystemFont(80)
    font_small = DrawGraph.GetSystemFont(45)
    
    # --- STEP 1: Draw Face Fills ---
    for face in res_map.faces:
        if not face.bounded: continue
        
        # Only apply purple fill to the faces participating in the union;
        # others remain as they are or transparent.
        if face == fa or face == fb:
            fill_color = (147, 112, 219, 180) 
            draw.polygon(DrawGraph.FaceVertex2P(face), fill=fill_color)
        # Note: No need to draw other faces here, as DrawAllFaces has already handled them.

    # --- STEP 2: Draw Black Borders (Skipping shared internal edges) ---
    for edge in res_map.edges:
        if id(edge) in shared_edge_ids:
            continue
            
        p1 = DrawGraph.V2P(edge.tail.p)
        p2 = DrawGraph.V2P(edge.head.p)
        
        draw.line([p1, p2], fill=(255, 255, 255, 255), width=8) # White outline for contrast
        draw.line([p1, p2], fill=(0, 0, 0, 255), width=6)       # Main black line

    # --- STEP 3: Draw Special Label 'U' inside the complete merged polygon ---
    lp, d = _union_label_lp_d(fa, fb, label_cache)
    coords = DrawGraph.V2P(lp)
    union_font = font_bold if d > 0.06 else font_small
    draw.text(coords, "U", fill=(0, 0, 0, 255), font=union_font,
              anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255, 255))
    manager.reserve(coords[0], coords[1], 40, 40)
    
    # No return statement needed, as modifications are made directly to the passed 'draw' object



def run_highlight_union_fill(draw, img, manager, res_map, fa, fb, label_cache, maxX, maxY, color=(255, 255, 0, 180), **inner_kwargs):
    shared_edge_ids = get_shared_edges(fa, fb)
    font_bold = DrawGraph.GetSystemFont(80)
    
    if fa and fa.bounded:
        draw.polygon(DrawGraph.FaceVertex2P(fa), fill=color)
    if fb and fb.bounded:
        draw.polygon(DrawGraph.FaceVertex2P(fb), fill=color)

    for edge in list(fa.edges) + list(fb.edges):
        if id(edge) in shared_edge_ids or (hasattr(edge, 'reverse') and id(edge.reverse) in shared_edge_ids):
            continue
        p1 = DrawGraph.V2P(edge.tail.p)
        p2 = DrawGraph.V2P(edge.head.p)
        draw.line([p1, p2], fill=(255, 255, 255, 255), width=8)
        draw.line([p1, p2], fill=(0, 0, 0, 255), width=6)

    lp, d = _union_label_lp_d(fa, fb, label_cache)
    coords = DrawGraph.V2P(lp)
    mask_r = 45 if d > 0.06 else 25
    draw.ellipse([coords[0]-mask_r, coords[1]-mask_r, coords[0]+mask_r, coords[1]+mask_r], fill=color)
    union_font = font_bold if d > 0.06 else DrawGraph.GetSystemFont(45)
    draw.text(coords, "U", fill=(0, 0, 0, 255), font=union_font,
              anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255, 255))
    manager.reserve(coords[0], coords[1], 40, 40)


def _union_label_lp_d(fa, fb, label_cache):
    """Return a spacious point inside the actual union, with a safe fallback."""
    try:
        union_face = map_helpers._face_union(fa, fb)
        if union_face is False:
            raise ValueError("regions do not form a connected union")
        return Graph.LetterPointFace(union_face)
    except Exception:
        candidates = []
        for face in (fa, fb):
            idx = getattr(face, '_cache_idx', None)
            if idx is not None and idx in label_cache:
                candidates.append(label_cache[idx])
            else:
                candidates.append(Graph.LetterPointFace(face))
        return max(candidates, key=lambda item: item[1])



def get_shared_edges(fa, fb):
    shared = set()
    
    # Safety check: Ensure both faces actually exist and are valid bounded regions
    if not fa or not fb or not fa.bounded or not fb.bounded:
        return shared

    # Gather all unique object IDs belonging to Face B's boundary for fast lookup
    fb_edge_ids = {id(e) for e in fb.edges}
    fb_reverse_ids = {id(e.reverse) for e in fb.edges if hasattr(e, 'reverse')}

    for edge in fa.edges:
        # Get the ID of this edge and its twin
        e_id = id(edge)
        e_rev_id = id(edge.reverse) if hasattr(edge, 'reverse') else None
        
        # Explicit Definition of a Shared Edge:
        # The edge from Face A must physically exist in Face B's edge list 
        # (either as itself or as its reverse twin)
        is_shared = (e_id in fb_edge_ids) or (e_id in fb_reverse_ids) or \
                    (e_rev_id in fb_edge_ids) if e_rev_id else False

        if is_shared:
            # Double-check that it is an internal geologic line, NOT the map frame
            e_left_bounded = edge.leftFace.bounded if edge.leftFace else False
            e_rev_left_bounded = edge.reverse.leftFace.bounded if edge.reverse.leftFace else False
            
            if e_left_bounded and e_rev_left_bounded:
                shared.add(e_id)
                if e_rev_id:
                    shared.add(e_rev_id)
                    
    return shared

# def get_shared_edges(fa, fb):
#     shared = set()
#     for edge in fa.edges:
#         if edge.reverse.leftFace == fb:
#             shared.update([id(edge), id(edge.reverse)])
#     return shared



import random

def main():
    maxX, maxY = 1.0, 1.0
    seed = random.randint(0, 9999)
    Graph.initialize()
    res_map = BuildRandomMap.BuildRandomMap(8, maxX, maxY, seed)
    
    img_size = (int(200 + 800 * maxX), int(200 + 800 * maxY))
    purple = (200, 0, 255, 255)

    bounded_faces = [f for f in res_map.faces if f.bounded]
    if not bounded_faces: return
    target_face = random.choice(bounded_faces)

    # --- IMAGE 1: edge_highlight.png ---
    # Pure highlight, no text
    session_h = AnnotationSession(res_map, img_size)
    session_h.add_edge_action(target_face.edges[0], label=None, color=purple)
    
    session_h.render().save("edge_highlight.png")
    print("Saved: edge_highlight.png")

# --- IMAGE 2: edge_labeled.png ---
    session_l = AnnotationSession(res_map, img_size)

    processed_true_edges = set()
    edge_counter = 1
    
    for edge in target_face.edges:
        t_edge = getattr(edge, 'trueEdge', edge) 
        t_id = id(t_edge)
        
        if t_id not in processed_true_edges:
            session_l.add_edge_action(edge, label=str(edge_counter), color=purple)
            processed_true_edges.add(t_id)
            edge_counter += 1
        else:
            session_l.add_edge_action(edge, label=None, color=purple)
    
    session_l.render().save("edge_labeled.png")
    print("Saved: edge_labeled.png")

if __name__ == "__main__":
    main() 
