import streamlit as st
import numpy as np
from streamlit_drawable_canvas import st_canvas
from PIL import Image
import Graph

# --- 0. UNIVERSAL PATCH (Must be at the top) ---
import streamlit.elements.image as st_image
import Graph, BuildRandomMap, DrawGraph
from visual_tools import tool_draw_points_line, tool_highlight_region, draw_union, get_shared_edges

if "session" not in st.session_state:
    Graph.initialize()
    maxX, maxY = 1.0, 1.0
    res_map = BuildRandomMap.BuildRandomMap(8, maxX, maxY, seed=42)
    # Original high-res size for rendering
    img_size = (int(200 + 800 * maxX), int(200 + 800 * maxY))
    
    from visual_tools import AnnotationSession 
    st.session_state.session = AnnotationSession(res_map, img_size)
    st.session_state.points_buffer = []
    st.session_state.active_tool = "line"

# --- 2. HELPER FUNCTIONS ---
#if the click is very close to a vertex, select that vertex
import Graph # Assuming this is your provided code
def get_nearest_vertex(px, py, session, threshold_px=25):
    # Standardize scale logic
    img_w, _ = session.img_size
    actual_scale = img_w / DISPLAY_SIDE
    
    render_x, render_y = px * actual_scale, py * actual_scale
    
    # Map to 0.0-1.0 space
    math_x = (render_x - 100) / 800.0
    math_y = (900.0 - render_y) / 800.0
    click_point = Graph.Vector(math_x, math_y)
    
    best_v, min_dist = None, float('inf')
    math_threshold = threshold_px / 800.0

    for v in session.res_map.vertices:
        dist = Graph.vecDist(click_point, v.p)
        if dist < min_dist and dist < math_threshold:
            min_dist, best_v = dist, v
    return best_v


def get_clicked_face(px, py, session):
    """
    Precisely maps canvas clicks to the 0.0-1.0 math space.
    """
    # 1. Get the real dimensions of the high-res background image
    # For maxX=1, maxY=1, this is 1000x1000
    img_w, img_h = session.img_size 
    
    # 2. Calculate the true scale based on the 1000px image size
    # If display is 600, actual_scale is 1.666...
    actual_scale_x = img_w / DISPLAY_SIDE
    actual_scale_y = img_h / DISPLAY_SIDE
    
    # 3. Convert mouse pixels to high-res render pixels
    render_x = px * actual_scale_x
    render_y = py * actual_scale_y
    
    # 4. Invert the V2P formula:
    # Pixel X = 100 + 800 * Math X  => Math X = (Pixel X - 100) / 800
    # Pixel Y = 900 - 800 * Math Y  => Math Y = (900 - Pixel Y) / 800
    math_x = (render_x - 100) / 800.0
    math_y = (900.0 - render_y) / 800.0
    
    # Create the Vector for Graph.py
    click_point = Graph.Vector(math_x, math_y)
    
    # LOGGING for your verification
    print(f"--- Coordinate Analysis ---")
    print(f"Mouse on Screen: ({px}, {py})")
    print(f"Point in Math:   ({math_x:.4f}, {math_y:.4f})")
    
    # 5. Hit Test
    for face in session.res_map.faces:
        if not face.bounded:
            continue
            
        # This uses your Winding Number (Angle Sum) logic in Graph.py
        if Graph.pointInsideFace(click_point, face):
            print(f"MATCH: Face {face.letter}")
            return face
            
    print("MISSED: Click was outside all bounded regions.")
    return None

def get_clicked_edge(px, py, session, threshold_px=20):
    """
    Finds the nearest edge by converting the click into the 0.0-1.0 math space
    used by the Graph model.
    """
    # 1. Map display pixels to high-res render pixels (1000x1000)
    img_w, img_h = session.img_size 
    actual_scale_x = img_w / DISPLAY_SIDE
    actual_scale_y = img_h / DISPLAY_SIDE
    
    render_x = px * actual_scale_x
    render_y = py * actual_scale_y
    
    # 2. Convert to Math Space (0.0 to 1.0) to match the model's coordinates
    # This must be the EXACT inverse of your V2P function
    math_x = (render_x - 100) / 800.0
    math_y = (900.0 - render_y) / 800.0
    
    click_point = Graph.Vector(math_x, math_y)
    
    best_edge = None
    min_dist = float('inf')

    # 3. Iterate through edges using math-space distance
    # Graph.distPointFromEdge calculates distance in 0.0-1.0 units
    for edge in session.res_map.edges:
        pa = edge.tail.p
        pb = edge.head.p
        
        # Use the built-in distance function from your Graph.py
        # It handles the projection math correctly
        d = Graph.distPointFromEdge(click_point, pa, pb)
        
        # We convert our pixel threshold (e.g. 20px) to math units (0-1)
        # 20 pixels / 800 total pixels = 0.025 math units
        math_threshold = threshold_px / 800.0
        
        if d < min_dist and d < math_threshold:
            min_dist = d
            best_edge = edge
                
    if best_edge:
        print(f"EDGE MATCH: {best_edge.tail.num}-{best_edge.head.num} at distance {min_dist:.4f}")
    
    return best_edge


# --- 3. UI LAYOUT ---
st.set_page_config(layout="wide")
st.title("Geologic Geometry Pad ✏️")

col1, col2 = st.columns([3, 1])

# Sidebar Controls
tool_mode = st.sidebar.radio(
    "Select Active Tool:",
    ["Point", "Angle", "Edge", "Region", "Line"],
    index=0
)
if st.sidebar.button("Undo Last Action"):
    if st.session_state.session.actions:
        st.session_state.session.actions.pop()
        st.rerun()

import base64
from io import BytesIO


def PIL_to_base64(img):
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

import base64
from io import BytesIO

def PIL_to_base64(img):
    """Converts the PIL image to a string that the browser can read directly."""
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

# --- 2. DISPLAY SETTINGS ---
# Adjust this value to make the diagram smaller or larger on your screen
DISPLAY_SIDE = 600 
# Scaling factor to map canvas clicks back to the 800x800 render coordinates
SCALE = 800 / DISPLAY_SIDE 


with col1:
    bg_image = st.session_state.session.render()
    
    canvas_key = f"canvas_v{len(st.session_state.session.actions)}"
    
    # We set display_height/width to DISPLAY_SIDE (600)
    # The background_image will automatically be scaled by the component to fit
    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.3)",
        stroke_width=3,
        stroke_color="#FF0000",
        background_image=bg_image,
        update_streamlit=True,
        height=DISPLAY_SIDE,
        width=DISPLAY_SIDE,
        drawing_mode=tool_mode,
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

        # --- 1. TOOL-SPECIFIC DETECTION & UI ---

        # 🎯 POINT TOOL: Only label/place points
        if tool_mode == "Point":
            target_v = get_nearest_vertex(raw_x, raw_y, sess, threshold_px=40)
            if target_v:
                st.markdown("### 📍 Label Vertex")
                if st.button(f"Confirm v{target_v.num}", use_container_width=True, type="primary"):
                    sess.add_vertex_action(target_v, auto_enumerate=True)
                    st.rerun()
            else:
                st.info("Click near a junction to label a vertex.")

        # 📐 ANGLE TOOL: Strictly for interior angles
        elif tool_mode == "Angle":
            target_v = get_nearest_vertex(raw_x, raw_y, sess, threshold_px=40)
            target_f = get_clicked_face(raw_x, raw_y, sess)
            
            if target_f and target_v:
                face_vertices = [e.tail for e in target_f.edges]
                if target_v in face_vertices:
                    st.markdown(f"### 📐 Angle in {target_f.letter}")
                    if st.button(f"Label Angle at v{target_v.num}", use_container_width=True, type="primary"):
                        sess.add_angle_action((target_f, target_v), auto_enumerate=True)
                        st.rerun()
                else:
                    st.warning("Click a corner inside the region.")
            else:
                st.info("Select a corner of a region to label the angle.")

        # 🛣️ EDGE TOOL: Strictly for edge highlights
        elif tool_mode == "Edge":
            target_e = get_clicked_edge(raw_x, raw_y, sess, threshold_px=25)
            if target_e:
                st.markdown("### 🛣️ Highlight Edge")
                if st.button(f"Highlight {target_e.tail.num}-{target_e.head.num}", use_container_width=True, type="primary"):
                    sess.add_edge_action(target_e, label=None, auto_enumerate=False)
                    st.rerun()
            else:
                st.info("Click near a line to highlight it.")

        # 💎 REGION TOOL: Highlight or Merge
        elif tool_mode == "Region":
            target_f = get_clicked_face(raw_x, raw_y, sess)
            if target_f:
                st.markdown(f"### 💎 Region {target_f.letter}")
                c1, c2 = st.columns(2)
                if c1.button("Highlight", use_container_width=True, type="primary"):
                    sess.add_region_action(target_f, color=(255, 255, 0, 100))
                    st.rerun()
                
                if c2.button("Buffer Merge", use_container_width=True):
                    if target_f not in st.session_state.union_buffer:
                        st.session_state.union_buffer.append(target_f)
                        st.toast(f"Buffered {target_f.letter}")
                        st.rerun()
            else:
                st.info("Click inside a bounded area.")

        # ✏️ LINE TOOL: Drawing auxiliary lines
        elif tool_mode == "Line":
            st.markdown("### ✏️ Auxiliary Line")
            st.info("Line drawing logic (e.g. Points-to-Line) goes here.")
            # Example: sess.add_action(tool_draw_points_line, ...)

    # --- 2. MULTI-STEP ACTIONS (MERGE) ---
    if st.session_state.union_buffer and tool_mode == "Region":
        st.markdown("---")
        st.write("**Merge Queue**")
        st.caption(" + ".join([f.letter for f in st.session_state.union_buffer]))
        m1, m2 = st.columns(2)
        if m1.button("Confirm Merge", type="primary", use_container_width=True):
            if len(st.session_state.union_buffer) >= 2:
                fa, fb = st.session_state.union_buffer[0], st.session_state.union_buffer[1]
                sess.add_action(draw_union, fa, fb)
                st.session_state.union_buffer = []
                st.rerun()
        if m2.button("Clear", use_container_width=True):
            st.session_state.union_buffer = []
            st.rerun()

    # --- 3. GLOBAL UNDO ---
    st.markdown("---")
    if st.button("Undo Last Action", use_container_width=True):
        st.session_state.session.undo_action()
        st.rerun()