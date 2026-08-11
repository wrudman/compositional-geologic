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
            # Before a union/merge there are no obsolete vertices: every
            # vertex drawn by the map is a valid selectable geometric object.
            # The checks below exist only to suppress junctions that disappear
            # when shared edges are hidden by a merge.  Applying them to the
            # original map incorrectly makes some visible frame or collinear
            # vertices impossible to select and highlight.
            if not hidden_edge_ids:
                return False

            # Capture ALL raw edges from the data structure
            incident_edges = list(vertex.outarcs)
            
            visible_internal_edges = []
            frame_boundary_edges = []
            
            for i, e in enumerate(incident_edges):
                # 1. Hidden Status
                is_hidden = (id(e) in hidden_edge_ids) or (id(e.reverse) in hidden_edge_ids)
                
                # 2. Frame Status
                e_left_bounded = e.leftFace.bounded if e.leftFace else False
                e_rev_left_bounded = e.reverse.leftFace.bounded if e.reverse.leftFace else False
                is_frame = not (e_left_bounded and e_rev_left_bounded)
                
                # Populate our logic lists
                if not is_hidden:
                    if not is_frame:
                        visible_internal_edges.append(e)
                    else:
                        frame_boundary_edges.append(e)

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
                            return True
                    except Exception:
                        pass
                return False

            # 2. Frame Corner Check
            if len(frame_boundary_edges) >= 2:
                e1 = frame_boundary_edges[0]
                e2 = frame_boundary_edges[1]
                
                angle_diff = abs(Graph.signedAngle(e1.head.p, vertex.p, e2.head.p))
                is_straight = abs(angle_diff - np.pi) < 0.05
                
                if not is_straight:
                    return False

            # All remaining cases are straight frame junctions or vertices
            # whose incident boundaries disappeared in the union.
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
                return True

            # RULE 2: Flat surface rejection (180 degrees)
            if len(visible_local_edges) == 2:
                e1, e2 = visible_local_edges[0], visible_local_edges[1]
                p1 = e1.head.p if Graph.vecDist(e1.tail.p, v_p) < 1e-5 else e1.tail.p
                p2 = e2.head.p if Graph.vecDist(e2.tail.p, v_p) < 1e-5 else e2.tail.p
                
                try:
                    angle_diff = abs(Graph.signedAngle(p1, v_p, p2))
                    if abs(angle_diff - np.pi) < 0.05:
                        return True
                except Exception:
                    return True

            return False
        
        elif "label_edge" in func_name or "label_edge_list" in func_name:
            data = args[1] if len(args) > 1 else args[0]
            edges = data if isinstance(data, list) else [data]

            hidden_count = sum(
                1 for e in edges
                if (id(e) in hidden_edge_ids) or (id(e.reverse) in hidden_edge_ids)
            )

            # An edge marker is obsolete only when none of its segments remain
            # visible.  A union can hide one old constituent segment while
            # other segments of the same trueEdge remain on U's boundary.
            # Endpoint simplification must not erase that visible boundary.
            return bool(edges) and hidden_count == len(edges)

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
            elif category == "vertex" and "labeled_vertex_segment" in name:
                for label_text in (args[1] if len(args) > 1 else None, args[3] if len(args) > 3 else None):
                    if label_text and str(label_text).startswith(prefix):
                        active_used.add(str(label_text))
            elif category == "angle" and ("label_angle" in name or "combined_angle" in name):
                label_index = 3 if "combined_angle" in name else 2
                label_text = args[label_index] if len(args) > label_index else None
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
    def add_edge_action(self, edge_list, label=None, auto_enumerate=False, color=(0, 255, 255, 235)):
        """Handles the segment list passed from the UI."""
        if not isinstance(edge_list, list):
            edge_list = [edge_list]

        # Handle enumeration labels
        final_label = label
        if auto_enumerate:
            final_label = self._generate_label("edge", "e")

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

    # Intersect the ray with the frame rectangle.  A candidate obtained from
    # an x-boundary is valid only when its y-coordinate is also inside the
    # frame (and vice versa).  Choosing the smallest positive t without this
    # check can put both endpoints outside the canvas, so the action is logged
    # successfully while no extended line is visible.
    eps = 1e-9
    candidates = []
    if abs(dx) > eps:
        for boundary_x in (f_min, f_max):
            t = (boundary_x - x1) / dx
            candidate_y = y1 + t * dy
            if t > eps and f_min - eps <= candidate_y <= f_max + eps:
                candidates.append(t)
    if abs(dy) > eps:
        for boundary_y in (f_min, f_max):
            t = (boundary_y - y1) / dy
            candidate_x = x1 + t * dx
            if t > eps and f_min - eps <= candidate_x <= f_max + eps:
                candidates.append(t)

    if not candidates:
        return p2

    t = min(candidates)
    return (x1 + t * dx, y1 + t * dy)

BLUE = (0, 0, 255, 255)

def draw_line_label(draw, manager, start_pos, end_pos, label_text, color=(0, 0, 255, 255)):
    if not label_text:
        return
    font = DrawGraph.GetSystemFont(35)
    mx = (start_pos[0] + end_pos[0]) / 2
    my = (start_pos[1] + end_pos[1]) / 2
    dx = end_pos[0] - start_pos[0]
    dy = end_pos[1] - start_pos[1]
    length = math.hypot(dx, dy) or 1.0
    offset = 18
    tx = mx - (dy / length) * offset
    ty = my + (dx / length) * offset
    bbox = draw.textbbox((tx, ty), str(label_text), font=font, anchor="mm")
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    draw.text(
        (tx, ty),
        str(label_text),
        fill=color,
        font=font,
        anchor="mm",
        stroke_width=3,
        stroke_fill=(255, 255, 255, 255),
    )
    manager.reserve(tx, ty, text_w, text_h)

def tool_draw_extended_edge(draw, img, manager, edge, color=(0, 0, 255, 255), width=6, label=None):
    """Extends an existing map edge to the frame boundaries."""
    p1 = DrawGraph.V2P(edge.tail.p)
    p2 = DrawGraph.V2P(edge.head.p)
    ext_start = get_extended_point(p2, p1)
    ext_end = get_extended_point(p1, p2)
    draw.line([ext_start, ext_end], fill=color, width=width)
    draw_line_label(draw, manager, ext_start, ext_end, label, color)

def tool_draw_points_line(draw, img, manager, v1_p, v2_p, extend=False, color=(0, 0, 255, 255), width=6, label=None):
    """Draws a line between two arbitrary points (e.g., a diagonal)."""
    p1 = DrawGraph.V2P(v1_p)
    p2 = DrawGraph.V2P(v2_p)
    if extend:
        # Compute both extensions from the original endpoints. Mutating p1
        # before calculating p2 changes the direction and can produce a line
        # that no longer follows the selected segment.
        original_p1, original_p2 = p1, p2
        p1 = get_extended_point(original_p2, original_p1)
        p2 = get_extended_point(original_p1, original_p2)
    draw.line([p1, p2], fill=color, width=width)
    draw_line_label(draw, manager, p1, p2, label, color)


def tool_draw_labeled_vertex_segment(draw, img, manager, v1, v1_label, v2, v2_label, line_label):
    """Render two labeled input vertices and their segment as one undoable action."""
    tool_label_vertex(draw, img, manager, v1, v1_label)
    tool_label_vertex(draw, img, manager, v2, v2_label)
    tool_draw_points_line(draw, img, manager, v1.p, v2.p, extend=False, label=line_label)

def tool_draw_axis_line(draw, img, manager, vertex_p, direction='H', color=(0, 0, 255, 255), width=6, label=None):
    """Draws a horizontal or vertical reference line through a point."""
    f_min, f_max = 100, 900
    px, py = DrawGraph.V2P(vertex_p)
    if direction.upper() == 'H':
        start_pos, end_pos = (f_min, py), (f_max, py)
    else:
        start_pos, end_pos = (px, f_min), (px, f_max)
    draw.line([start_pos, end_pos], fill=color, width=width)
    draw_line_label(draw, manager, start_pos, end_pos, label, color)

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
    """Draw a committed vertex annotation in the compositional-survey style."""
    px, py = DrawGraph.V2P(vertex.p)
    draw.ellipse(
        [px-12, py-12, px+12, py+12],
        fill=(255, 215, 0, 230),
        outline=(184, 134, 11, 255),
        width=4,
    )
    
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
    radius = 25 / 800.0
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

def tool_label_combined_angle(draw, img, manager, res_map, boundary_vertices, target_v, label):
    """Draw the actual interior angle of a merged region's outer boundary."""
    # Backward compatibility for sessions saved before union angles stored the
    # ordered outer boundary. Old actions contained the two constituent faces.
    if boundary_vertices and not hasattr(boundary_vertices[0], "p"):
        drawn_count = 0
        for face in boundary_vertices:
            if target_v in [edge.tail for edge in face.edges]:
                tool_label_angle(
                    draw, img, manager, res_map, (face, target_v),
                    label if drawn_count == 0 else None,
                )
                drawn_count += 1
        return

    if len(boundary_vertices) < 3:
        return
    target_id = str(getattr(target_v, "num", id(target_v)))
    index = next(
        (i for i, vertex in enumerate(boundary_vertices)
         if str(getattr(vertex, "num", id(vertex))) == target_id),
        -1,
    )
    if index < 0:
        return

    previous = boundary_vertices[(index - 1) % len(boundary_vertices)]
    following = boundary_vertices[(index + 1) % len(boundary_vertices)]
    area_twice = sum(
        vertex.p.x * boundary_vertices[(i + 1) % len(boundary_vertices)].p.y
        - boundary_vertices[(i + 1) % len(boundary_vertices)].p.x * vertex.p.y
        for i, vertex in enumerate(boundary_vertices)
    )
    prev_angle = math.atan2(previous.p.y - target_v.p.y, previous.p.x - target_v.p.x)
    next_angle = math.atan2(following.p.y - target_v.p.y, following.p.x - target_v.p.x)
    if area_twice > 0:
        start_angle = next_angle
        sweep = (prev_angle - next_angle) % (2 * math.pi)
    else:
        start_angle = prev_angle
        sweep = (next_angle - prev_angle) % (2 * math.pi)

    # Geometry is normalized to 0..1; 25 display pixels equals 25/800 here.
    radius = 25 / 800.0
    sample_count = max(18, int(math.degrees(sweep) / 4))
    arc_points = []
    for sample_index in range(sample_count + 1):
        angle = start_angle + sweep * sample_index / sample_count
        point = Graph.Vector(
            target_v.p.x + radius * math.cos(angle),
            target_v.p.y + radius * math.sin(angle),
        )
        arc_points.append(DrawGraph.V2P(point))
    draw.line(arc_points, fill=(203, 32, 107, 255), width=4, joint="curve")

    if label:
        mid_angle = start_angle + sweep / 2
        label_distance = radius + 22 / 800.0
        label_point = Graph.Vector(
            target_v.p.x + label_distance * math.cos(mid_angle),
            target_v.p.y + label_distance * math.sin(mid_angle),
        )
        lx, ly = DrawGraph.V2P(label_point)
        font = DrawGraph.GetSystemFont(30)
        draw.text(
            (lx, ly), str(label), fill=(0, 100, 180, 255), font=font,
            anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255, 255),
        )
        manager.reserve(lx, ly, 32, 22, padding=5)
            

def tool_label_edge(draw, img, manager, edge, label_text=None, color=(0, 255, 255, 235)):
    """
    1. Highlights an edge with the compositional survey's cyan marker.
    2. If label_text is provided, places it at the midpoint.
    3. Uses a two-sided collision check to prevent overlapping labels.
    """
    p1 = DrawGraph.V2P(edge.tail.p)
    p2 = DrawGraph.V2P(edge.head.p)

    draw.line([p1, p2], fill=color, width=14)
    for px, py in (p1, p2):
        draw.ellipse([px-7, py-7, px+7, py+7], fill=color)

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
        draw.text((final_tx, final_ty), str(label_text), fill=(0, 100, 130, 255), font=font,
                  anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255, 255))
        
        manager.reserve(final_tx, final_ty, text_w, text_h, padding=5)

def tool_label_edge_list(draw, img, manager, res_map, edge_list, label, color, **kwargs):
    """
    Highlights EVERY segment provided in edge_list to form a continuous line.
    """
    if not edge_list:
        return
        
    # 1. DRAW HIGHLIGHTS FOR ALL SEGMENTS
    for edge in edge_list:
        p1 = DrawGraph.V2P(edge.tail.p)
        p2 = DrawGraph.V2P(edge.head.p)
        draw.line([p1, p2], fill=color, width=14)
        for px, py in (p1, p2):
            draw.ellipse([px-7, py-7, px+7, py+7], fill=color)
        
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
    
    dir_in = math.atan2(e_in.tail.p.y - v_p.y, e_in.tail.p.x - v_p.x)
    dir_out = math.atan2(e_out.head.p.y - v_p.y, e_out.head.p.x - v_p.x)
    forward_sweep = (dir_out - dir_in) % (2 * math.pi)

    def point_in_face(px, py):
        polygon = [(item.p.x, item.p.y) for item in face.vertices]
        inside = False
        j = len(polygon) - 1
        for i in range(len(polygon)):
            xi, yi = polygon[i]
            xj, yj = polygon[j]
            if ((yi > py) != (yj > py)) and (
                px < (xj - xi) * (py - yi) / ((yj - yi) or 1e-12) + xi
            ):
                inside = not inside
            j = i
        return inside

    forward_bisector = dir_in + forward_sweep / 2
    probe_distance = 0.02
    if point_in_face(
        v_p.x + math.cos(forward_bisector) * probe_distance,
        v_p.y + math.sin(forward_bisector) * probe_distance,
    ):
        bisector_dir = forward_bisector
    else:
        bisector_dir = dir_out + ((2 * math.pi - forward_sweep) / 2)
    
    # 4. Create the offset vector (Scaling distance to math space)
    # Assuming 800 is your coordinate scale factor
    offset_x = math.cos(bisector_dir) * (distance / 800)
    offset_y = math.sin(bisector_dir) * (distance / 800)
    
    return Graph.Vector(v_p.x + offset_x, v_p.y + offset_y)


USED_ANGLE_LABELS = set()

def tool_draw_interior_arc(draw, img, manager, res_map, angle_data, radius=45, color=(0, 150, 0, 255)):
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

    def point_in_polygon(px, py, polygon):
        inside = False
        j = len(polygon) - 1
        for i in range(len(polygon)):
            xi, yi = polygon[i]
            xj, yj = polygon[j]
            if ((yi > py) != (yj > py)) and (
                px < (xj - xi) * (py - yi) / ((yj - yi) or 1e-12) + xi
            ):
                inside = not inside
            j = i
        return inside

    # There are two arcs between the boundary rays. Choose the one whose
    # midpoint lies inside the selected face. This avoids relying on polygon
    # winding after mathematical coordinates are flipped into screen pixels.
    face_polygon = [DrawGraph.V2P(face_vertex.p) for face_vertex in face.vertices]
    forward_sweep = (ang_next - ang_prev) % 360
    forward_mid = math.radians(ang_prev + forward_sweep / 2)
    probe_radius = max(8, radius * 0.55)
    probe_x = cx + math.cos(forward_mid) * probe_radius
    probe_y = cy + math.sin(forward_mid) * probe_radius
    if point_in_polygon(probe_x, probe_y, face_polygon):
        start, end = ang_prev, ang_prev + forward_sweep
    else:
        reverse_sweep = 360 - forward_sweep
        start, end = ang_next, ang_next + reverse_sweep
    
    # Avoid drawing if it's a straight line (collinear edges)
    if abs((end - start) - 180.0) < 0.1:
        return

    bbox = [cx - radius, cy - radius, cx + radius, cy + radius]

    draw.arc(bbox, start=start, end=end, fill=color, width=5)


import math
def tool_label_angle(draw, img, manager, res_map, angle_data, label_text=None, color=(0, 150, 0, 255)):
    face, vertex = angle_data
    arc_radius = 45
    text_w, text_h = 30, 20
    
    # Draw the interior arc
    tool_draw_interior_arc(draw, img, manager, res_map, angle_data, radius=arc_radius, color=color)
    if label_text:
        v_p = vertex.p
        px, py = DrawGraph.V2P(v_p)
        arc_target_p = calculate_angle_center_point(angle_data, distance=arc_radius)
        tpx, tpy = DrawGraph.V2P(arc_target_p)
        
        # Keep the label inside the marked angle.  Putting it on the opposite
        # side of the corner makes it collide with vertex labels selected at
        # the same point (for example a1 and v1 in the practice diagram).
        inner_p = calculate_angle_center_point(angle_data, distance=45)

        dx = inner_p.x - v_p.x
        dy = inner_p.y - v_p.y
        
        final_lx, final_ly = None, None
        needs_arrow = False
        
        search_rings = [(1.0, False), (1.35, False), (1.7, True)]
        
        for dist_mult, use_arrow in search_rings:
            for offset_angle in [0, 0.4, -0.4, 0.8, -0.8]:
                cos_a, sin_a = math.cos(offset_angle), math.sin(offset_angle)
                rx = (dx * cos_a - dy * sin_a) * dist_mult
                ry = (dx * sin_a + dy * cos_a) * dist_mult
                
                lx, ly = DrawGraph.V2P(Graph.Vector(v_p.x + rx, v_p.y + ry))
                
                if not manager.is_overlapping(lx, ly, text_w, text_h, padding=2):
                    final_lx, final_ly = lx, ly
                    needs_arrow = use_arrow
                    break
            if final_lx is not None: break

        # Fall back to the interior bisector.
        if final_lx is None:
            flx, fly = DrawGraph.V2P(Graph.Vector(v_p.x + dx, v_p.y + dy))
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

    # --- STEP 3: Draw Special Label 'U' for the merged region ---
    # We only need to draw the 'U' at the position of the first face (fa)
    if hasattr(fa, '_cache_idx') and fa._cache_idx in label_cache:
        lp, d = label_cache[fa._cache_idx]
        coords = DrawGraph.V2P(lp)
        draw.text(coords, "U", fill=(0, 0, 0, 255), font=font_bold, 
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

    if hasattr(fa, '_cache_idx') and fa._cache_idx in label_cache:
        lp, d = label_cache[fa._cache_idx]
        coords = DrawGraph.V2P(lp)
        mask_r = 45 if d > 0.06 else 25
        draw.ellipse([coords[0]-mask_r, coords[1]-mask_r, coords[0]+mask_r, coords[1]+mask_r], fill=color)
        draw.text(coords, "U", fill=(0, 0, 0, 255), font=font_bold,
                  anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255, 255))
        manager.reserve(coords[0], coords[1], 40, 40)



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
