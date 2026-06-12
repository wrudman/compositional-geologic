import streamlit as st
import numpy as np
from streamlit_drawable_canvas import st_canvas
from PIL import Image
import base64
from io import BytesIO

# --- 1. MODULE IMPORTS ---
# Consolidating imports at the top prevents circular dependency errors
import Graph
import BuildRandomMap
import DrawGraph
from visual_tools import (
    AnnotationSession, 
    tool_draw_points_line, 
    tool_highlight_region, 
    draw_union, 
    get_shared_edges
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

def get_nearest_vertex(px, py, session, threshold_px=25):
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
    if st.button("Undo Last Action", use_container_width=True):
        st.session_state.session.undo_action()
        st.rerun()

# --- 6. CANVAS AREA (COL 1) ---
# --- 6. CANVAS AREA (COL 1) ---
with col1:
    canvas_key = f"canvas_v{len(st.session_state.session.actions)}"
    bg_image = st.session_state.session.render()
    
    # Logic to determine the mode:
    # "line" for the Line tool
    # "point" for others (captures clicks without selection boxes)
    current_drawing_mode = "line" if tool_mode == "Line" else "point"

    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.3)",
        stroke_width=3,
        stroke_color="#FF0000",
        background_image=bg_image,
        update_streamlit=True,
        height=DISPLAY_SIDE,
        width=DISPLAY_SIDE,
        drawing_mode=current_drawing_mode,
        point_display_radius=0, # Keeps the "point" click invisible
        display_toolbar=False,
        key=canvas_key,
    )
# --- 7. LOGIC & INTERACTION (COL 2) ---
with col2:
    st.subheader(f"Tool: {tool_mode}")
    sess = st.session_state.session
    found_something = False

    if canvas_result.json_data and canvas_result.json_data["objects"]:
        last_obj = canvas_result.json_data["objects"][-1]
        raw_x, raw_y = last_obj.get("left", 0), last_obj.get("top", 0)

        # TOOL: POINT
        if tool_mode == "Point":
            target_v = get_nearest_vertex(raw_x, raw_y, sess, threshold_px=40)
            if target_v:
                found_something = True
                st.markdown(f"✅ **Selected Vertex {target_v.num}**")
                if st.button(f"Label v{target_v.num}", type="primary", use_container_width=True):
                    sess.add_vertex_action(target_v, auto_enumerate=True)
                    st.rerun()

        # TOOL: ANGLE
        elif tool_mode == "Angle":
            target_v = get_nearest_vertex(raw_x, raw_y, sess, threshold_px=40)
            target_f = get_clicked_face(raw_x, raw_y, sess)
            if target_f and target_v:
                # Membership check
                if any(e.tail == target_v for e in target_f.edges):
                    found_something = True
                    st.markdown(f"✅ **Angle at v{target_v.num} in Region {target_f.letter}**")
                    if st.button("Label Angle", type="primary", use_container_width=True):
                        sess.add_angle_action((target_f, target_v), auto_enumerate=True)
                        st.rerun()
# TOOL: EDGE
        elif tool_mode == "Edge":
            target_e = get_clicked_edge(raw_x, raw_y, sess, threshold_px=35)
    
            if target_e:
                hidden_edge_ids = sess.get_active_hidden_edges()
                is_hidden = id(target_e) in hidden_edge_ids
                
                if not is_hidden:
                    # Identify the long line (trueEdge) and the adjacent faces
                    root_obj = getattr(target_e, 'trueEdge', target_e)
                    f_main = target_e.leftFace
                    f_oppo = target_e.reverse.leftFace
                    
                    name_main = f_main.letter if (f_main and f_main.bounded) else "Outside"
                    name_oppo = f_oppo.letter if (f_oppo and f_oppo.bounded) else "Outside"
                    
                    st.markdown(f"### 🛣️ Edge: {name_main} | {name_oppo}")
                    st.write("Which region's edge are you labeling?")

                    # Unique ID for button keys
                    edge_id_str = f"{target_e.tail.num}_{target_e.head.num}"

                    # --- Label Input ---
                    custom_edge_label = st.text_input(
                        "Label text (e.g., 'm'):", 
                        key=f"input_{edge_id_str}",
                        placeholder="Highlight only if empty..."
                    )
                    label_val = custom_edge_label.strip() if custom_edge_label.strip() != "" else None

                    # --- Action Buttons (One per Region) ---
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if st.button(f"Label for {name_main}", use_container_width=True, type="primary"):
                            if f_main and f_main.bounded:
                                # Apply to all segments of this root line for f_main
                                for e in f_main.edges:
                                    if getattr(e, 'trueEdge', e) == root_obj:
                                        sess.add_edge_action(e, label=label_val)
                                st.rerun()

                    with col2:
                        if f_oppo and f_oppo.bounded:
                            if st.button(f"Label for {name_oppo}", use_container_width=True, type="primary"):
                                # Apply to all segments of this root line for f_oppo
                                for e in f_oppo.edges:
                                    if getattr(e, 'trueEdge', e) == root_obj:
                                        sess.add_edge_action(e, label=label_val)
                                st.rerun()

                    st.divider()
                    
                    # --- ACTION 2: EXTENDING (Always uses the root geometric line) ---
                    st.write("**Geometric Tool:**")
                    if st.button("Extend this Line (Infinite)", use_container_width=True):
                        sess.add_auxiliary_line_action(tool_draw_extended_edge, target_e)
                        st.rerun()
                    
                else:
                    st.info("📍 **Click near a line** to label it for a specific region or extend it.")
            else:
                st.info("📍 **Click near a line** to label it for a specific region or extend it.")

        elif tool_mode == "Line":
            if last_obj.get("type") == "line":
                x1, y1 = last_obj.get("x1"), last_obj.get("y1")
                x2, y2 = last_obj.get("x2"), last_obj.get("y2")
                v_start = get_nearest_vertex(x1, y1, sess, threshold_px=60)
                v_end = get_nearest_vertex(x2, y2, sess, threshold_px=60)
                
                if v_start and v_end and v_start != v_end:
                    found_something = True
                    st.success(f"✅ **Line: v{v_start.num} to v{v_end.num}**")
                    if st.button("Confirm Auxiliary Line", type="primary", use_container_width=True):
                        sess.add_action(tool_draw_points_line, v_start.p, v_end.p, extend=True)
                        st.rerun()

        # TOOL: REGION
        elif tool_mode == "Region":
            target_f = get_clicked_face(raw_x, raw_y, sess)
            if target_f:
                found_something = True
                st.markdown(f"✅ **Selected Region {target_f.letter}**")
                c1, c2 = st.columns(2)
                if c1.button("Highlight", type="primary", use_container_width=True):
                    sess.add_region_action(target_f)
                    st.rerun()
                if c2.button("Queue Merge", use_container_width=True):
                    if target_f not in st.session_state.union_buffer:
                        st.session_state.union_buffer.append(target_f)
                        st.rerun()

    # If the user clicked but missed a target, or hasn't clicked yet:
    if not found_something:
        st.info(f"Please click (or drag for Line) to select a **{tool_mode}** target.")

# --- 2. GLOBAL UNION MANAGEMENT (Moved to Right Sidebar) ---
    st.markdown("---")
    
    # Check for existing Union
    union_idx = next((i for i, a in enumerate(sess.actions) if "union" in a[0].__name__.lower()), -1)
    
    if union_idx != -1:
        with st.container(border=True):
            st.write("💠 **Current Union (U) is active**")
            if st.button("Reset Union", use_container_width=True):
                sess.actions.pop(union_idx)
                st.rerun()

    # --- 3. MERGE QUEUE LOGIC ---
    if st.session_state.union_buffer:
        st.write("📂 **Merge Queue:**", " + ".join([f.letter for f in st.session_state.union_buffer]))
        m1, m2 = st.columns(2)
        
        if union_idx != -1:
            st.warning("Only one Union allowed.")
        else:
            if len(st.session_state.union_buffer) >= 2:
                f1, f2 = st.session_state.union_buffer[0], st.session_state.union_buffer[1]
                if len(get_shared_edges(f1, f2)) == 0:
                    st.error(f"❌ {f1.letter} & {f2.letter} don't touch. Resetting...")
                    st.session_state.union_buffer = []
                else:
                    if m1.button("Confirm Merge", type="primary", use_container_width=True):
                        # CLEANUP: Remove old highlights of f1 and f2
                        # Comparing the function object directly is safer
                        sess.actions = [
                            a for a in sess.actions 
                            if not (a[0] == tool_highlight_region and a[1] in [f1, f2])
                        ]
                        sess.add_action(draw_union, f1, f2)
                        st.session_state.union_buffer = []
                        st.rerun()
        
        if m2.button("Clear Queue", use_container_width=True):
            st.session_state.union_buffer = []
            st.rerun()