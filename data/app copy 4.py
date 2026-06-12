import streamlit as st
import numpy as np
from streamlit_drawable_canvas import st_canvas
from PIL import Image
import base64
from io import BytesIO

# --- 1. MODULE IMPORTS ---
# Consolidating imports at the top prevents circular dependency e rrors
import Graph
import BuildRandomMap
import DrawGraph
from visual_tools import (
    AnnotationSession, 
    tool_draw_points_line, 
    tool_highlight_region, 
    draw_union, 
    get_shared_edges,
    tool_label_vertex,
    tool_label_angle,
    highlight_edge,
    tool_draw_axis_line,
    tool_draw_extended_edge,
)

# --- 2. GLOBAL CONFIG & CONSTANTS ---
DISPLAY_SIDE = 600 
MATH_SCALE = 800.0  # The internal coordinate system size

# --- 3. SESSION INITIALIZATION ---
if "session" not in st.session_state:
    Graph.initialize()
    maxX, maxY = 1.0, 1.0
    res_map = BuildRandomMap.BuildRandomMap(8, maxX, maxY, seed=42)
    
    # Original high-res size for rendering (1000x1000 for maxX=1)
    img_size = (int(200 + 800 * maxX), int(200 + 800 * maxY))
    
    st.session_state.session = AnnotationSession(res_map, img_size)
    st.session_state.union_buffer = []
    st.session_state.active_tool = "line"

# --- 4. HELPER FUNCTIONS ---

def get_math_coords(px, py, session):
    """Universal mapper from Canvas Pixels to Graph Math Space."""
    img_w, img_h = session.img_size
    actual_scale_x = img_w / DISPLAY_SIDE
    actual_scale_y = img_h / DISPLAY_SIDE
    
    render_x = px * actual_scale_x
    render_y = py * actual_scale_y
    
    # Invert V2P: Math = (Pixel - Offset) / Scale
    math_x = (render_x - 100) / MATH_SCALE
    math_y = (900.0 - render_y) / MATH_SCALE
    return Graph.Vector(math_x, math_y)

def get_nearest_vertex(px, py, session, threshold_px=45):
    click_point = get_math_coords(px, py, session)
    best_v, min_dist = None, float('inf')
    math_threshold = threshold_px / MATH_SCALE

    for v in session.res_map.vertices:
        dist = Graph.vecDist(click_point, v.p)
        if dist < min_dist and dist < math_threshold:
            min_dist, best_v = dist, v
    return best_v

def get_clicked_face(px, py, session):
    click_point = get_math_coords(px, py, session)
    for face in session.res_map.faces:
        if face.bounded and Graph.pointInsideFace(click_point, face):
            return face
    return None

def get_clicked_edge(px, py, session, threshold_px=20):
    click_point = get_math_coords(px, py, session)
    best_edge, min_dist = None, float('inf')
    math_threshold = threshold_px / MATH_SCALE

    for edge in session.res_map.edges:
        d = Graph.distPointFromEdge(click_point, edge.tail.p, edge.head.p)
        if d < min_dist and d < math_threshold:
            min_dist, best_edge = d, edge
    return best_edge

# --- 5. UI LAYOUT ---
st.set_page_config(layout="wide", page_title="Geologic Geometry Pad")
st.title("Geologic Geometry Pad ✏️")

col1, col2 = st.columns([3, 1])

with st.sidebar:
    st.header("Settings")
    tool_mode = st.radio(
        "Select Active Tool:",
        ["Point", "Angle", "Edge", "Region", "Line"],
        index=0
    )

# --- 6. CANVAS AREA ---
with col1:
    # We add tool_mode to the key so switching tools clears the canvas drawing
    canvas_key = f"canvas_{tool_mode}_{len(st.session_state.session.actions)}"
    
    bg_image = st.session_state.session.render()
    
    # Logic: Only 'Point' mode shows the red dot. 
    # Others use radius 0 to stay invisible but still clickable.
    # current_radius = 5 if tool_mode == "Point" else 0
    current_radius = 0

    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.3)",
        stroke_width=0,
        stroke_color="#FF0000",
        background_image=bg_image,
        update_streamlit=True,
        height=DISPLAY_SIDE,
        width=DISPLAY_SIDE,
        drawing_mode="point" if tool_mode != "Line" else "line",
        point_display_radius=current_radius, 
        display_toolbar=False,
        key=canvas_key,
    )

with col2:
    st.subheader(f"Tool: {tool_mode}")
    
    if "union_buffer" not in st.session_state:
        st.session_state.union_buffer = []

    if canvas_result.json_data and canvas_result.json_data["objects"]:
        last_obj = canvas_result.json_data["objects"][-1]
        raw_x, raw_y = last_obj.get("left", 0), last_obj.get("top", 0)
        sess = st.session_state.session

# 🎯 POINT TOOL: Label junctions with custom text or just highlight
        if tool_mode == "Point":
            target_v = get_nearest_vertex(raw_x, raw_y, sess, threshold_px=40)
            
            if target_v:
                hidden_edge_ids = sess.get_active_hidden_edges()
                is_obsolete = sess.is_marker_obsolete(tool_label_vertex, [target_v], hidden_edge_ids)
                
                if not is_obsolete:
                    st.markdown("### 📍 Label Vertex")
                    
                    # Custom Label Input
                    # Use a unique key to prevent state clashing
                    custom_label = st.text_input(
                        "Enter Label (leave empty for highlight only):", 
                        key=f"label_input_{target_v.num}"
                    )
                    
                    if st.button("Confirm Point", use_container_width=True, type="primary"):
                        # If the user typed nothing, we pass None or an empty string
                        # depending on how your add_vertex_action handles the 'label' param
                        label_to_save = custom_label if custom_label.strip() != "" else None
                        
                        # Note: auto_enumerate=True might override your custom label 
                        # depending on your Graph module logic. 
                        # Usually, if label_to_save is provided, auto_enumerate should be False.
                        sess.add_vertex_action(
                            target_v, 
                            label=label_to_save, 
                            auto_enumerate=(label_to_save is None)
                        )
                        st.rerun()
                else:
                    st.warning("This junction is no longer part of the active map.")
            else:
                st.info("Click near a junction to label a vertex.")
# 📐 ANGLE TOOL: Strictly for interior angles
        elif tool_mode == "Angle":
            target_v = get_nearest_vertex(raw_x, raw_y, sess, threshold_px=45)
            target_f = get_clicked_face(raw_x, raw_y, sess)
            
            if target_f and target_v:
                # 1. Get current hidden edges from unions
                hidden_edge_ids = sess.get_active_hidden_edges()
                
                # 2. Check if this specific corner is obsolete (merged boundary)
                is_obsolete = sess.is_marker_obsolete(tool_label_angle, [(target_f, target_v)], hidden_edge_ids)
                
                # 3. Verify the vertex actually belongs to the clicked face
                face_vertices = [e.tail for e in target_f.edges]
                
                if target_v in face_vertices and not is_obsolete:
                    # Semantic labeling for the user
                    st.markdown(f"### 📐 Angle in Region {target_f.letter}")
                    st.write("Mark this specific corner within the region.")

                    # Custom Label Input
                    # Unique key based on face letter and vertex ID to prevent state clashing
                    custom_angle_label = st.text_input(
                        "Enter Label (leave empty for highlight only):", 
                        key=f"angle_label_{target_f.letter}_{target_v.num}"
                    )
                    
                    if st.button(f"Confirm Angle in {target_f.letter}", use_container_width=True, type="primary"):
                        label_to_save = custom_angle_label if custom_angle_label.strip() != "" else None
                        
                        # Add the action: 
                        # If label_to_save is None, auto_enumerate handles it (e.g., θ1, θ2)
                        # If you want NO text at all when empty, ensure add_angle_action handles label=None
                        sess.add_angle_action(
                            (target_f, target_v), 
                            label=label_to_save, 
                            auto_enumerate=(label_to_save is None)
                        )
                        st.rerun()
                else:
                    st.info(f"📍 To label an angle, click inside a region near one of its corners.")
            else:
                st.info("📍 Click inside a region near a corner to label the interior angle.")

# 🛣️ EDGE TOOL: Highlight or label specific boundaries
        elif tool_mode == "Edge":
            target_e = get_clicked_edge(raw_x, raw_y, sess, threshold_px=25)
            
            if target_e:
                hidden_edge_ids = sess.get_active_hidden_edges()
                is_hidden = id(target_e) in hidden_edge_ids
                
                if not is_hidden:
                    # Identify the regions this edge separates
                    f1 = target_e.leftFace.letter if (target_e.leftFace and target_e.leftFace.bounded) else "Frame"
                    f2 = target_e.reverse.leftFace.letter if (target_e.reverse.leftFace and target_e.reverse.leftFace.bounded) else "Frame"
                    
                    st.markdown(f"### 🛣️ Boundary: {f1} | {f2}")
                    st.write(f"This is the shared edge between Region {f1} and Region {f2}.")

                    # Custom Label Input
                    # Unique key based on the sorted face letters to identify the unique boundary
                    boundary_id = "-".join(sorted([f1, f2]))
                    custom_edge_label = st.text_input(
                        "Enter Label (leave empty for highlight only):", 
                        key=f"edge_label_{boundary_id}"
                    )
                    
                    if st.button(f"Highlight Boundary {f1}-{f2}", use_container_width=True, type="primary"):
                        label_to_save = custom_edge_label if custom_edge_label.strip() != "" else None
                        
                        # Add the action:
                        # label=label_to_save allows for custom names like "m" from Q12
                        sess.add_edge_action(
                            target_e, 
                            label=label_to_save, 
                            auto_enumerate=(label_to_save is None and False) # Usually False for edges unless you want e1, e2...
                        )
                        st.rerun()
                else:
                    st.warning("This boundary no longer exists because the adjacent regions were merged.")
            else:
                st.info("📍 Click near a line on the map to highlight or label that boundary.")

        # 💎 REGION TOOL: Highlight or Merge
 # 💎 REGION TOOL: Highlight, Label, or Merge
        elif tool_mode == "Region":
            target_f = get_clicked_face(raw_x, raw_y, sess)
            
            if target_f:
                st.markdown(f"### 💎 Region {target_f.letter}")
                
                # --- 1. Label/Highlight Section ---
                st.write("Label this specific area or just highlight it.")
                
                # Custom label input
                custom_region_label = st.text_input(
                    "Enter Label (e.g., 'Target', 'U'):", 
                    key=f"region_label_{target_f.letter}"
                )
                
                if st.button(f"Highlight Region {target_f.letter}", use_container_width=True, type="primary"):
                    label_to_save = custom_region_label if custom_region_label.strip() != "" else None
                    # Passing label to the action
                    sess.add_region_action(target_f, label=label_to_save, color=(255, 255, 0, 100))
                    st.rerun()

                st.markdown("---")
                
                # --- 2. Merge/Union Section ---
                st.write("**Region Union Construction**")
                st.caption("Add regions to the buffer to merge them into a single shape.")
                
                if st.button(f"Add Region {target_f.letter} to Union Buffer", use_container_width=True):
                    if target_f not in st.session_state.union_buffer:
                        st.session_state.union_buffer.append(target_f)
                        st.toast(f"Added {target_f.letter} to buffer")
                        st.rerun()
                    else:
                        st.warning(f"Region {target_f.letter} is already in the buffer.")
            
            else:
                st.info("📍 Click inside a bounded region to highlight it or add it to a union.")

            # --- 3. Buffer Display & Execution ---
            # We show the buffer status regardless of whether a face is currently clicked
            if st.session_state.union_buffer:
                st.markdown("---")
                st.subheader("🛠️ Current Union Buffer")
                
                buffer_letters = [f.letter for f in st.session_state.union_buffer]
                st.info(f"Regions to merge: **{', '.join(buffer_letters)}**")
                
                col_exec, col_clear = st.columns(2)
                
                if col_exec.button("🔥 Execute Union", use_container_width=True, type="primary"):
                    # Record the union action in the session
                    sess.add_union_action(list(st.session_state.union_buffer))
                    # Clear buffer after successful execution
                    st.session_state.union_buffer = [] 
                    st.rerun()
                
                if col_clear.button("Clear Buffer", use_container_width=True):
                    st.session_state.union_buffer = []
                    st.rerun()
        elif tool_mode == "Line":
            # Get the current hidden state once for efficiency
            hidden_edge_ids = sess.get_active_hidden_edges()
            
            # --- SUB-MODE SELECTION ---
            # # We add a callback to clear the buffer if the mode changes
            def clear_line_buffer():
                if "v_start" in st.session_state:
                    del st.session_state.v_start

            sub_mode = st.selectbox(
                "Construction Type", 
                ["Connect 2 Vertices", "Extend Edge", "Horizontal/Vertical Ray"],
                on_change=clear_line_buffer
            )

            # --- CASE A: Connect 2 Vertices ---
            if sub_mode == "Connect 2 Vertices":
                target_v = get_nearest_vertex(raw_x, raw_y, sess, threshold_px=45)
                
                if "v_start" not in st.session_state:
                    if target_v and not sess.is_marker_obsolete(tool_label_vertex, [target_v], hidden_edge_ids):
                        st.markdown("### 1️⃣ First Point")
                        if st.button("Set as Start", use_container_width=True, type="primary"):
                            st.session_state.v_start = target_v
                            st.rerun()
                    else:
                        st.info("📍 Click a junction to select the **start** point.")
                else:
                    v1 = st.session_state.v_start
                    st.success("✅ **Start Point Set.**")
                    
                    if target_v and not sess.is_marker_obsolete(tool_label_vertex, [target_v], hidden_edge_ids):
                        if target_v.p != v1.p:
                            st.markdown("### 2️⃣ Second Point")
                            if st.button("Draw Connector Line", use_container_width=True, type="primary"):
                                sess.add_auxiliary_line_action(tool_draw_points_line, v1.p, target_v.p, extend=False)
                                del st.session_state.v_start
                                st.rerun()
                    
                    if st.button("Cancel & Reset", use_container_width=True):
                        del st.session_state.v_start
                        st.rerun()

            # --- CASE B: Extend Edge (Q12) ---
            elif sub_mode == "Extend Edge":
                target_e = get_clicked_edge(raw_x, raw_y, sess, threshold_px=45)
                
                if target_e and (id(target_e) not in hidden_edge_ids):
                    f1 = target_e.leftFace.letter if (target_e.leftFace and target_e.leftFace.bounded) else "Frame"
                    f2 = target_e.reverse.leftFace.letter if (target_e.reverse.leftFace and target_e.reverse.leftFace.bounded) else "Frame"
                    
                    st.markdown(f"### 🛣️ Boundary: {f1} | {f2}")
                    if st.button("Extend this Boundary", use_container_width=True, type="primary"):
                        sess.add_auxiliary_line_action(tool_draw_extended_edge, target_e)
                        st.rerun()
                else:
                    st.info("📍 Click near a visible line to extend it.")

            # --- CASE C: Axis Lines ---
            elif sub_mode == "Horizontal/Vertical Ray":
                target_v = get_nearest_vertex(raw_x, raw_y, sess, threshold_px=45)
                
                if target_v and not sess.is_marker_obsolete(tool_label_vertex, [target_v], hidden_edge_ids):
                    st.markdown("### 🎯 Selected Junction")
                    c1, c2 = st.columns(2)
                    if c1.button("Horizontal", use_container_width=True):
                        sess.add_auxiliary_line_action(tool_draw_axis_line, target_v.p, direction='H')
                        st.rerun()
                    if c2.button("Vertical", use_container_width=True):
                        sess.add_auxiliary_line_action(tool_draw_axis_line, target_v.p, direction='V')
                        st.rerun()
                else:
                    st.info("Click a junction to draw a reference axis.")
# --- 2. MULTI-STEP ACTIONS (MERGE) ---
# In your main app/logic:
    def perform_union(sess, face_a, face_b):
        """
        Adds the union task to the action stack.
        Note: The 'res_map' is already available in 'sess', but 
        draw_union expects it as the first argument.
        """
        # Arguments passed here start AFTER (draw, img, manager) 
        # which are automatically injected by sess.render()
        sess.add_action(
            draw_union,            
            sess.res_map,          # res_map
            face_a,                # fa
            face_b,                # fb
            sess.face_label_cache, # label_cache
            1.0,                   # maxX
            1.0                    # maxY
  
        )
    if st.session_state.union_buffer and tool_mode == "Region":
        st.markdown("---")
        st.write("**Merge Queue**")
        st.caption(" + ".join([f.letter for f in st.session_state.union_buffer]))
        m1, m2 = st.columns(2)
        
        if m1.button("Confirm Merge", type="primary", use_container_width=True, key="btn_confirm_merge"):
            if len(st.session_state.union_buffer) >= 2:
                fa = st.session_state.union_buffer[0]
                fb = st.session_state.union_buffer[1]
                perform_union(st.session_state.session, fa, fb)
                st.session_state.union_buffer = []
                st.rerun()
                
        if m2.button("Clear", use_container_width=True, key="btn_clear_buffer"):
            st.session_state.union_buffer = []
            st.rerun()

    # --- 3. GLOBAL UNDO ---
    st.markdown("---")
    # Added a unique key here
    if st.button("Undo Last Action", use_container_width=True, key="undo_bottom_main"):
        st.session_state.session.undo_action()
        st.rerun()



