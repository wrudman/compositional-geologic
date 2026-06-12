import streamlit as st
st.set_page_config(layout="wide", page_title="Geologic Geometry Pad")

import streamlit.components.v1 as components
import json, pickle, os
from PIL import Image
from io import BytesIO
import base64

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

print("\n🚀 === [Python] Streamlit Render Loop Triggered ===")

DISPLAY_SIDE = 600
MATH_SCALE = 800.0
PERSIST_FILE = "/tmp/geo_session.pkl"

def load_or_create_session():
    if os.path.exists(PERSIST_FILE):
        try:
            with open(PERSIST_FILE, "rb") as f:
                data = pickle.load(f)
                print(f"💾 Loaded session from disk, actions={len(data['session'].actions)}")
                return data
        except Exception as e:
            print(f"⚠️ Failed to load session: {e}")

    print("🆕 INITIALIZING NEW SESSION")
    Graph.initialize()
    maxX, maxY = 1.0, 1.0
    res_map = BuildRandomMap.BuildRandomMap(8, maxX, maxY, seed=42)
    # res_map = BuildRandomMap.BuildRandomMap(8, maxX, maxY, seed=35)
    img_size = (int(200 + 800 * maxX), int(200 + 800 * maxY))
    return {
        "session": AnnotationSession(res_map, img_size),
        "union_buffer": [],
        "last_active_id": "none",
        "v_start": None,
        "v_start_id": "",
        "tool_mode": "Vertex",
    }

def save_session(data):
    try:
        with open(PERSIST_FILE, "wb") as f:
            pickle.dump(data, f)
        print(f"💾 Saved session to disk, actions={len(data['session'].actions)}")
    except Exception as e:
        print(f"⚠️ Failed to save session: {e}")

data = load_or_create_session()
sess = data["session"]

# --- BACKEND ROUTER ---
query_params = st.query_params

if "bridge_act" in query_params:
    act = query_params["bridge_act"]
    tgt_id = query_params.get("bridge_tgt", "none")

    print(f"🔥 [Bridge] Action: {act} | Target: {tgt_id}")

    hidden_edge_ids = sess.get_active_hidden_edges()
    target_v = None
    if tgt_id and tgt_id != "none":
        for v in sess.res_map.vertices:
            if str(getattr(v, "num", id(v))) == str(tgt_id):
                target_v = v
                data["last_active_id"] = str(tgt_id)
                break

    if target_v:
        is_obsolete = sess.is_marker_obsolete(tool_label_vertex, [target_v], hidden_edge_ids)
        if not is_obsolete:
            if act == "commit_vertex":
                sess.add_vertex_action(target_v, label=None, auto_enumerate=True)
                save_session(data)
                st.toast(f"✅ Vertex {tgt_id} Highlighted")

            elif act == "set_start_point":
                data["v_start"] = target_v
                data["v_start_id"] = str(tgt_id)
                save_session(data)
                st.toast(f"📍 Start Vertex Selected (Node {tgt_id})")

            elif act == "confirm_connection":
                v1 = data.get("v_start")
                if v1 and target_v.p != v1.p:
                    sess.add_auxiliary_line_action(tool_draw_points_line, v1.p, target_v.p, extend=False)
                    data["v_start"] = None
                    data["v_start_id"] = ""
                    save_session(data)
                    st.toast(f"🔗 Connection Created: {data.get('v_start_id','')} → {tgt_id}")

            elif act == "commit_axis_h":
                sess.add_auxiliary_line_action(tool_draw_axis_line, target_v.p, direction='H')
                save_session(data)
                st.toast("↔ Horizontal Line Drawn")

            elif act == "commit_axis_v":
                sess.add_auxiliary_line_action(tool_draw_axis_line, target_v.p, direction='V')
                save_session(data)
                st.toast("↕ Vertical Line Drawn")

            elif act == "commit_angle":
                face_idx = int(query_params.get("bridge_face", "-1"))
                target_face = None
                for face in sess.res_map.faces:
                    if hasattr(face, '_cache_idx') and face._cache_idx == face_idx:
                        target_face = face
                        break
                if target_face and target_v:
                    is_union = False
                    union_faces_list = None
                    for action_func, action_args, action_kwargs in sess.actions:
                        if "draw_union" in action_func.__name__.lower() and len(action_args) >= 3:
                            fa, fb = action_args[1], action_args[2]
                            if target_face == fa or target_face == fb:
                                is_union = True
                                union_faces_list = [fa, fb]
                                break
                    
                    if is_union and union_faces_list:
                        sess.add_combined_angle_action(union_faces_list, target_v, None)
                    else:
                        sess.add_angle_action((target_face, target_v), label=None, auto_enumerate=True)
                    save_session(data)
                    st.toast(f"✅ Angle marked in Region")

        else:
            st.warning(f"⚠️ Vertex {tgt_id} is obsolete.")

    if act == "commit_edge":
        face_side = query_params.get("bridge_side", "main")
        tail_id = int(query_params.get("bridge_tail", "-1"))
        head_id = int(query_params.get("bridge_head", "-1"))
        target_e = None
        for edge in sess.res_map.edges:
            t = int(getattr(edge.tail, "num", id(edge.tail)))
            h = int(getattr(edge.head, "num", id(edge.head)))
            if (t == tail_id and h == head_id) or (t == head_id and h == tail_id):
                target_e = edge
                break
        if target_e:
            f_main = target_e.leftFace
            f_oppo = target_e.reverse.leftFace if hasattr(target_e, 'reverse') else None

            # For frame edges, the bounded face is whichever side is bounded
            if face_side == "main":
                chosen_face = f_main if (f_main and f_main.bounded) else f_oppo
            else:
                chosen_face = f_oppo if (f_oppo and f_oppo.bounded) else f_main

            if chosen_face and chosen_face.bounded:
                target_root = getattr(target_e, "trueEdge", target_e)
                target_rev_root = getattr(target_e.reverse, "trueEdge", target_e.reverse) if hasattr(target_e, 'reverse') else None

                # Add union partner if chosen_face is part of a union
                faces_to_search = [chosen_face]
                for action_func, action_args, action_kwargs in sess.actions:
                    if "draw_union" in action_func.__name__.lower() and len(action_args) >= 3:
                        fa, fb = action_args[1], action_args[2]
                        if chosen_face == fa:
                            faces_to_search.append(fb)
                            break
                        elif chosen_face == fb:
                            faces_to_search.append(fa)
                            break

                face_segments = [
                    e for face in faces_to_search
                    for e in face.edges
                    if getattr(e, "trueEdge", e) == target_root or
                    (target_rev_root and getattr(e, "trueEdge", e) == target_rev_root)
                ]

                if face_segments:
                    print(f"face_side={face_side}, chosen_face={chosen_face.letter}, faces_to_search={[f.letter for f in faces_to_search]}, segments={len(face_segments)}")
                    sess.add_edge_action(face_segments, label=None, auto_enumerate=True)
                    save_session(data)
                    st.toast(f"✅ Edge marked")


    elif act == "extend_edge":
        tail_id = int(query_params.get("bridge_tail", "-1"))
        head_id = int(query_params.get("bridge_head", "-1"))
        target_e = None
        for edge in sess.res_map.edges:
            t = int(getattr(edge.tail, "num", id(edge.tail)))
            h = int(getattr(edge.head, "num", id(edge.head)))
            if (t == tail_id and h == head_id) or (t == head_id and h == tail_id):
                target_e = edge
                break
        if target_e:
            sess.add_auxiliary_line_action(tool_draw_extended_edge, target_e)
            save_session(data)
            st.toast("📏 Edge Extended")

    elif act == "commit_region":
        face_idx = int(query_params.get("bridge_face", "-1"))
        custom_label = query_params.get("custom_label", "").strip()
        target_face = None
        for face in sess.res_map.faces:
            if hasattr(face, '_cache_idx') and face._cache_idx == face_idx:
                target_face = face
                break
        if target_face:
            label_to_save = custom_label if custom_label != "" else None
            sess.add_region_action(target_face, label=label_to_save, color=None)
            save_session(data)
            st.toast(f"✅ Region {target_face.letter} Highlighted")

    elif act == "add_to_buffer":
        face_idx = int(query_params.get("bridge_face", "-1"))
        target_face = None
        for face in sess.res_map.faces:
            if hasattr(face, '_cache_idx') and face._cache_idx == face_idx:
                target_face = face
                break
        if target_face:
            buffer_faces = data.get("union_buffer", [])
            if len(buffer_faces) == 1:
                first_face = buffer_faces[0]
                shared_edges = get_shared_edges(first_face, target_face)
                if not shared_edges:
                    st.error(f"❌ Cannot merge! Region {target_face.letter} is not a neighbor of {first_face.letter}.")
                else:
                    buffer_faces.append(target_face)
                    data["union_buffer"] = buffer_faces
                    save_session(data)
                    st.toast(f"➕ Added neighbor {target_face.letter} to buffer")
            else:
                if target_face not in buffer_faces:
                    buffer_faces.append(target_face)
                    data["union_buffer"] = buffer_faces
                    save_session(data)
                    st.toast(f"➕ Added {target_face.letter} to buffer")

    elif act == "remove_from_buffer":
        face_idx = int(query_params.get("bridge_face", "-1"))
        buffer_faces = data.get("union_buffer", [])
        data["union_buffer"] = [f for f in buffer_faces if getattr(f, '_cache_idx', -1) != face_idx]
        save_session(data)
        st.toast("❌ Removed from buffer")

    elif act == "clear_buffer":
        data["union_buffer"] = []
        save_session(data)
        st.toast("🗑️ Buffer Cleared")

    elif act == "execute_union":
        buffer_faces = data.get("union_buffer", [])
        if len(buffer_faces) == 2:
            sess.add_union_action(buffer_faces[0], buffer_faces[1], maxX=1.0, maxY=1.0)
            data["union_buffer"] = []
            save_session(data)
            st.toast("🚀 Union Executed Successfully!")

    elif act == "commit_union_highlight":
        face_idx = int(query_params.get("bridge_face", "-1"))
        custom_label = query_params.get("custom_label", "").strip()
        target_face = None
        for face in sess.res_map.faces:
            if hasattr(face, '_cache_idx') and face._cache_idx == face_idx:
                target_face = face
                break
        if target_face and hasattr(sess, 'get_union_group'):
            union_group = sess.get_union_group(target_face)
            if union_group and hasattr(sess, 'add_union_highlight_action'):
                u_label = custom_label if custom_label != "" else None
                sess.add_union_highlight_action(union_group, label=u_label, color=(255, 255, 0, 100) )
                save_session(data)
                st.toast("✅ Merged Formation Highlighted")

    elif act == "cancel_connection":
        data["v_start"] = None
        data["v_start_id"] = ""
        data["last_active_id"] = "none"
        save_session(data)
        st.toast("❌ Cancel & Reset")

    st.query_params.clear()

# --- REFRESH STATE ---
sess = data["session"]
action_count = len(sess.actions)
last_active_id = data.get("last_active_id", "none")
has_start_point = data.get("v_start") is not None
start_point_id = data.get("v_start_id", "")

# --- FACE DATA ---
faces_data = []
for face in sess.res_map.faces:
    if not face.bounded:
        continue
    if hasattr(face, '_cache_idx') and face._cache_idx in sess.face_label_cache:
        lp, d = sess.face_label_cache[face._cache_idx]
        cx = lp.x * MATH_SCALE + 100
        cy = 900.0 - (lp.y * MATH_SCALE)
        pcx = cx / (sess.img_size[0] / DISPLAY_SIDE)
        pcy = cy / (sess.img_size[1] / DISPLAY_SIDE)
    else:
        continue

    face_display = face.letter
    for action_func, action_args, action_kwargs in sess.actions:
        if "draw_union" in action_func.__name__.lower() and len(action_args) >= 3:
            fa, fb = action_args[1], action_args[2]
            if face == fa or face == fb:
                face_display = "U"
                break

    face_vertices = []
    for edge in face.edges:
        v = edge.tail
        v_num = int(getattr(v, "num", id(v)))
        render_x = v.p.x * MATH_SCALE + 100
        render_y = 900.0 - (v.p.y * MATH_SCALE)
        pvx = render_x / (sess.img_size[0] / DISPLAY_SIDE)
        pvy = render_y / (sess.img_size[1] / DISPLAY_SIDE)
        face_vertices.append({"id": v_num, "x": pvx, "y": pvy})

    current_hidden = sess.get_active_hidden_edges()
    face_is_obsolete = bool(sess.is_marker_obsolete(tool_highlight_region, [face], current_hidden))

    union_partner_idx = None
    for action_func, action_args, action_kwargs in sess.actions:
        if "draw_union" in action_func.__name__.lower() and len(action_args) >= 3:
            fa, fb = action_args[1], action_args[2]
            if face == fa and hasattr(fb, '_cache_idx'):
                union_partner_idx = fb._cache_idx
                break
            elif face == fb and hasattr(fa, '_cache_idx'):
                union_partner_idx = fa._cache_idx
                break

    # Compute valid corner ids for angle hover filtering
    valid_corner_ids = []
    for edge in face.edges:
        v = edge.tail
        v_num = int(getattr(v, "num", id(v)))
        is_angle_obsolete = sess.is_marker_obsolete(
            tool_label_angle, [sess.res_map, (face, v)], current_hidden
        )
        if not is_angle_obsolete:
            valid_corner_ids.append(v_num)

    faces_data.append({
        "cache_idx": face._cache_idx,
        "letter": face.letter,
        "display": face_display,
        "cx": pcx,
        "cy": pcy,
        "vertices": face_vertices,
        "is_obsolete": face_is_obsolete,
        "union_partner_idx": union_partner_idx,
        "valid_corner_ids": valid_corner_ids,
    })

    # This is used later for not higlight obselete face.
    union_partner_idx = None
    for action_func, action_args, action_kwargs in sess.actions:
        if "draw_union" in action_func.__name__.lower() and len(action_args) >= 3:
            fa, fb = action_args[1], action_args[2]
            if face == fa and hasattr(fb, '_cache_idx'):
                union_partner_idx = fb._cache_idx
                break
            elif face == fb and hasattr(fa, '_cache_idx'):
                union_partner_idx = fa._cache_idx
                break

    faces_data.append({
        "cache_idx": face._cache_idx,
        "letter": face.letter,
        "display": face_display,
        "cx": pcx,
        "cy": pcy,
        "vertices": face_vertices,
        "is_obsolete": face_is_obsolete,
        "union_partner_idx": union_partner_idx, 
    })

# --- EDGE DATA ---
def get_face_display(face, valid):
    if not valid:
        return "Frame"
    for af, aa, ak in sess.actions:
        if "draw_union" in af.__name__.lower() and len(aa) >= 3:
            if face == aa[1] or face == aa[2]:
                return "U"
    return face.letter

edges_data = []
hidden_edge_ids = sess.get_active_hidden_edges()
seen_edge_pairs = set()

for edge in sess.res_map.edges:
    e_id = id(edge)
    e_rev_id = id(edge.reverse) if hasattr(edge, 'reverse') else None
    pair = tuple(sorted([e_id, e_rev_id or e_id]))
    if pair in seen_edge_pairs:
        continue
    seen_edge_pairs.add(pair)

    is_hidden = e_id in hidden_edge_ids or (e_rev_id and e_rev_id in hidden_edge_ids)
    f_main = edge.leftFace
    f_oppo = edge.reverse.leftFace if hasattr(edge, 'reverse') else None
    is_main_valid = bool(f_main and f_main.bounded)
    is_oppo_valid = bool(f_oppo and f_oppo.bounded)
    main_name = get_face_display(f_main, is_main_valid)
    oppo_name = get_face_display(f_oppo, is_oppo_valid)

    px1 = (edge.tail.p.x * MATH_SCALE + 100) / (sess.img_size[0] / DISPLAY_SIDE)
    py1 = (900.0 - edge.tail.p.y * MATH_SCALE) / (sess.img_size[1] / DISPLAY_SIDE)
    px2 = (edge.head.p.x * MATH_SCALE + 100) / (sess.img_size[0] / DISPLAY_SIDE)
    py2 = (900.0 - edge.head.p.y * MATH_SCALE) / (sess.img_size[1] / DISPLAY_SIDE)

    edge_is_obsolete = bool(is_hidden)

    # Build full segment list for hover highlight (same logic as commit_edge)
    target_root = getattr(edge, "trueEdge", edge)
    target_rev_root = getattr(edge.reverse, "trueEdge", edge.reverse) if hasattr(edge, 'reverse') else None

    # Find which faces to search (main + union partner if any)
    hover_faces = []
    for face in [f_main, f_oppo]:
        if not face or not face.bounded:
            continue
        if face not in hover_faces:
            hover_faces.append(face)
        for action_func, action_args, action_kwargs in sess.actions:
            if "draw_union" in action_func.__name__.lower() and len(action_args) >= 3:
                fa, fb = action_args[1], action_args[2]
                if face == fa and fb not in hover_faces:
                    hover_faces.append(fb)
                elif face == fb and fa not in hover_faces:
                    hover_faces.append(fa)

    all_segments = []
    seen_seg_pairs = set()
    for face in hover_faces:
        for e in face.edges:
            s_id = id(e)
            s_rev_id = id(e.reverse) if hasattr(e, 'reverse') else None
            seg_pair = tuple(sorted([s_id, s_rev_id or s_id]))
            if seg_pair in seen_seg_pairs:
                continue
            if getattr(e, "trueEdge", e) == target_root or \
               (target_rev_root and getattr(e, "trueEdge", e) == target_rev_root):
                seen_seg_pairs.add(seg_pair)
                sx1 = (e.tail.p.x * MATH_SCALE + 100) / (sess.img_size[0] / DISPLAY_SIDE)
                sy1 = (900.0 - e.tail.p.y * MATH_SCALE) / (sess.img_size[1] / DISPLAY_SIDE)
                sx2 = (e.head.p.x * MATH_SCALE + 100) / (sess.img_size[0] / DISPLAY_SIDE)
                sy2 = (900.0 - e.head.p.y * MATH_SCALE) / (sess.img_size[1] / DISPLAY_SIDE)
                all_segments.append({"x1": sx1, "y1": sy1, "x2": sx2, "y2": sy2})

    edges_data.append({
        "tail_id": int(getattr(edge.tail, "num", id(edge.tail))),
        "head_id": int(getattr(edge.head, "num", id(edge.head))),
        "x1": px1, "y1": py1, "x2": px2, "y2": py2,
        "segments": all_segments,  # NEW
        "is_hidden": bool(is_hidden),
        "is_obsolete": edge_is_obsolete,
        "main_name": main_name,
        "oppo_name": oppo_name,
        "main_valid": is_main_valid,
        "oppo_valid": is_oppo_valid,
    })
# --- VERTEX DATA ---
vertices_data = []
hidden_edge_ids_for_v = sess.get_active_hidden_edges()
for v in sess.res_map.vertices:
    render_x = v.p.x * MATH_SCALE + 100
    render_y = 900.0 - (v.p.y * MATH_SCALE)
    px = render_x / (sess.img_size[0] / DISPLAY_SIDE)
    py = render_y / (sess.img_size[1] / DISPLAY_SIDE)
    v_is_obsolete = bool(sess.is_marker_obsolete(tool_label_vertex, [v], hidden_edge_ids_for_v))

    # Collect neighboring region names for display
    neighbor_regions = []
    seen_face_ids = set()
    for e in v.outarcs:
        for face in [e.leftFace, e.reverse.leftFace if hasattr(e, 'reverse') else None]:
            if not face or not face.bounded:
                continue
            if id(face) in seen_face_ids:
                continue
            seen_face_ids.add(id(face))
            # Use union display name if applicable
            display = face.letter
            for af, aa, ak in sess.actions:
                if "draw_union" in af.__name__.lower() and len(aa) >= 3:
                    if face == aa[1] or face == aa[2]:
                        display = "U"
                        break
            if display not in neighbor_regions:
                neighbor_regions.append(display)

    vertices_data.append({
        "id": int(getattr(v, "num", id(v))),
        "x": px, "y": py,
        "label": getattr(v, "num", ""),
        "is_obsolete": v_is_obsolete,
        "neighbor_regions": neighbor_regions,
    })

# --- SIDEBAR ---
st.title("Geometry Pad ✏️")

with st.sidebar:
    st.header("Settings")
    saved_mode = data.get("tool_mode", "Vertex")
    mode_index = ["Vertex", "Angle", "Edge", "Region"].index(saved_mode)
    tool_mode = st.radio("Select Active Tool:", ["Vertex", "Angle", "Edge", "Region"], index=mode_index)
    if tool_mode != saved_mode:
        data["tool_mode"] = tool_mode
        save_session(data)
    st.divider()
    if st.button(f"↩ Undo Last Action ({action_count})", use_container_width=True, disabled=(action_count == 0)):
        sess.undo_action()
        data["union_buffer"] = []
        data["last_active_id"] = "none"
        data["v_start"] = None
        data["v_start_id"] = ""
        save_session(data)
        st.rerun()
    if st.button("🗑 Reset All", use_container_width=True):
        if os.path.exists(PERSIST_FILE):
            os.remove(PERSIST_FILE)
        st.rerun()

print(f"🎨 Rendering with {len(sess.actions)} actions")
bg_image = sess.render()
display_bg = bg_image.resize((DISPLAY_SIDE, DISPLAY_SIDE), Image.Resampling.LANCZOS)
buffered = BytesIO()
display_bg.save(buffered, format="PNG")
img_base64 = base64.b64encode(buffered.getvalue()).decode()

# --- EVALUATE UNION STATUS FOR JAVASCRIPT ---
has_existing_union = any("draw_union" in action_func.__name__.lower() for action_func, _, _ in sess.actions)
buffer_indices = [int(f._cache_idx) for f in data.get("union_buffer", []) if hasattr(f, '_cache_idx')]
buffer_letters = [str(f.letter) for f in data.get("union_buffer", []) if hasattr(f, 'letter')]

obsolete_faces_union_info = {}
if hasattr(sess, 'get_union_group'):
    for face in sess.res_map.faces:
        if not face.bounded: continue
        hidden_edge_ids = sess.get_active_hidden_edges()
        if sess.is_marker_obsolete(tool_highlight_region, [face], hidden_edge_ids):
            ug = sess.get_union_group(face)
            if ug:
                func, args, kwargs = ug
                faces_in_ug = args[1:] if "draw_union" in func.__name__.lower() else args
                names = ", ".join([f.letter for f in faces_in_ug if hasattr(f, "letter")])
                obsolete_faces_union_info[face._cache_idx] = names

html_code = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            margin: 0; padding: 10px;
            font-family: -apple-system, BlinkMacSystemFont, sans-serif;
            background: transparent; display: flex; gap: 25px;
        }}
        .pad-container {{ position: relative; width: {DISPLAY_SIDE}px; height: {DISPLAY_SIDE}px; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }}
        canvas {{ position: absolute; top: 0; left: 0; cursor: crosshair; }}
        .right-panel {{ width: 340px; height: {DISPLAY_SIDE}px; background: #ffffff; border-radius: 8px; border: 1px solid #EAEAEA; padding: 24px; box-sizing: border-box; display: flex; flex-direction: column; box-shadow: 0 4px 12px rgba(0,0,0,0.05); overflow-y: auto; }}
        .status-box {{ padding: 12px; background-color: #EDF7ED; border-left: 4px solid #4CAF50; color: #1E4620; margin-bottom: 20px; font-size: 14px; font-weight: 500; border-radius: 0 6px 6px 0; }}
        .angle-box {{ padding: 12px; background-color: #FFF8E1; border-left: 4px solid #FFA000; color: #5D4037; margin-bottom: 12px; font-size: 14px; font-weight: 500; border-radius: 0 6px 6px 0; }}
        .edge-box {{ padding: 12px; background-color: #FFF3E0; border-left: 4px solid #FF9800; color: #4E342E; margin-bottom: 12px; font-size: 14px; font-weight: 500; border-radius: 0 6px 6px 0; }}
        .region-box {{ padding: 12px; background-color: #FFF8E1; border-left: 4px solid #FFA000; color: #5D4037; margin-bottom: 12px; font-size: 14px; font-weight: 500; border-radius: 0 6px 6px 0; }}
        .info-box {{ padding: 12px; background-color: #E3F2FD; border-left: 4px solid #2196F3; color: #0D47A1; margin-bottom: 15px; font-size: 13px; border-radius: 0 6px 6px 0; }}
        .hidden {{ display: none !important; }}
        .action-btn {{ background: #FF4B4B; color: white; border: none; padding: 14px; border-radius: 6px; cursor: pointer; font-weight: bold; margin-top: 5px; width: 100%; font-size: 14px; transition: background 0.2s; }}
        .action-btn:hover {{ background: #E03E3E; }}
        .angle-btn {{ background: #FFA000; color: white; border: none; padding: 14px; border-radius: 6px; cursor: pointer; font-weight: bold; margin-top: 5px; width: 100%; font-size: 14px; transition: background 0.2s; }}
        .angle-btn:hover {{ background: #E65100; }}
        .edge-btn {{ background: #FF9800; color: white; border: none; padding: 14px; border-radius: 6px; cursor: pointer; font-weight: bold; margin-top: 5px; width: 100%; font-size: 14px; transition: background 0.2s; }}
        .edge-btn:hover {{ background: #E65100; }}
        .region-btn {{ background: #FFA000; color: white; border: none; padding: 14px; border-radius: 6px; cursor: pointer; font-weight: bold; margin-top: 5px; width: 100%; font-size: 14px; transition: background 0.2s; }}
        .region-btn:hover {{ background: #E65100; }}
        .sec-btn {{ background: #f5f5f5; color: #333; border: 1px solid #ccc; margin-top: 8px; width:100%; text-align:left; padding:8px; border-radius:4px; cursor:pointer; }}
        .sec-btn:hover {{ background: #e0e0e0; }}
        .cancel-btn {{ background: #6c757d; color: white; }}
    </style>
</head>
<body>
    <div class="pad-container">
        <canvas id="bgCanvas" width="{DISPLAY_SIDE}" height="{DISPLAY_SIDE}"></canvas>
        <canvas id="interactionCanvas" width="{DISPLAY_SIDE}" height="{DISPLAY_SIDE}"></canvas>
    </div>

    <div class="right-panel">
        <h3 id="panelHeader" style="margin-top:0; color:#111; font-size:18px; border-bottom:2px solid #F0F0F0; padding-bottom:10px;">Tool Panel: {tool_mode}</h3>

        <div id="placeholderText" style="color: #666; font-size: 14px; line-height: 1.6;">
            💡 <b>How to operate:</b><br>
            1. Hover over the geometric map.<br>
            2. <b>Click to lock/select</b> an element so your selection stays fixed.<br>
            3. Click it again to unlock, or use the operational controls.
        </div>

        <div id="vertexPanel" class="hidden">
            <div class="status-box">
                🎯 <b>Active Node ID:</b> <span id="v_id_span">-</span> <span id="v_lock_status" style="font-size:11px; font-weight:bold; color:#FF4B4B; margin-left:8px; display:none;">(LOCKED)</span>
            </div>
            <div id="connectionAlert" class="info-box hidden">
                ✅ <b>Start Vertex Selected</b>
            </div>
            <div id="normalForm">
                <button class="action-btn" id="submitBtn">Highlight Vertex</button>
                <div style="margin-top:20px; border-top:1px dashed #DDD; padding-top:15px;">
                    <span style="font-size:12px; font-weight:bold; color:#777;">Advanced Geometric Tools:</span>
                    <button class="sec-btn" id="startConnectBtn">🔗 Connect to another Vertex...</button>
                    <button class="sec-btn" id="axisHBtn">↔ Draw Horizontal Line</button>
                    <button class="sec-btn" id="axisVBtn">↕ Draw Vertical Line</button>
                </div>
            </div>
            <div id="connectionForm" class="hidden">
                <h3 style="font-size:14px; color:#333; margin-top:5px;">Select Target Vertex</h3>
                <button class="action-btn" id="confirmConnectBtn">Draw Connection</button>
                <button class="action-btn cancel-btn" id="cancelConnectBtn">❌ Cancel & Reset</button>
            </div>
        </div>

        <div id="anglePanel" class="hidden">
            <div class="angle-box">
                📐 <b>Corner:</b> <span id="angle_region_span">-</span> <span id="angle_lock_status" style="font-size:11px; font-weight:bold; color:#E65100; margin-left:8px; display:none;">(LOCKED)</span>
            </div>
            <p style="font-size:13px; color:#666; margin:0 0 12px;">Arc preview shown on map.</p>
            <button class="angle-btn" id="commitAngleBtn">✅ Mark Angle</button>
        </div>

        <div id="edgePanel" class="hidden">
            <div id="edgeHiddenWarning" class="info-box hidden">
                ⚠️ This edge is hidden by a union.
            </div>
            <div id="edgeActiveContent" class="hidden">
                <div class="edge-box">
                    📍 <b>Edge:</b> <span id="edge_label_span">-</span> <span id="edge_lock_status" style="font-size:11px; font-weight:bold; color:#E65100; margin-left:8px; display:none;">(LOCKED)</span>
                </div>
                <div style="font-size:12px; color:#777; margin-bottom:8px;">Which region's boundary?</div>
                <button class="edge-btn" id="edgeMainBtn">-</button>
                <button class="edge-btn" id="edgeOppoBtn" style="margin-top:8px;">-</button>
                <div style="margin-top:16px; border-top:1px dashed #DDD; padding-top:12px;">
                    <button class="sec-btn" id="extendEdgeBtn">📏 Extend this Edge</button>
                </div>
            </div>
        </div>

        <div id="regionPanel" class="hidden">
            <div id="mergedFormationAlert" class="status-box hidden" style="background-color: #E8F5E9; border-left-color: #2E7D32; color: #1B5E20;">
                📍 <b>Merged Formation Detected</b><br>
                <span style="font-size: 12px;" id="merged_includes_span">(Includes: -)</span>
            </div>
            
            <div id="normalRegionBox" class="region-box">
                🗺️ <b>Region:</b> <span id="region_label_span">-</span> <span id="region_lock_status" style="font-size:11px; font-weight:bold; color:#E65100; margin-left:8px; display:none;">(LOCKED)</span>
            </div>

            <button class="region-btn" id="commitRegionBtn">✅ Highlight Region</button>
            <button class="region-btn hidden" id="commitUnionHighlightBtn" style="background: #2E7D32;">✅ Highlight Combined Formation</button>

            <div id="unionConstructionSection" style="margin-top:20px; border-top:1px dashed #DDD; padding-top:15px;">
                <span style="font-size:12px; font-weight:bold; color:#777;">Union Construction:</span>
                <button class="sec-btn" id="addToBufferBtn" style="margin-top: 8px;">➕ Add to Union Buffer</button>
                <button class="sec-btn cancel-btn" id="removeFromBufferBtn" style="margin-top: 8px; background-color:#FFE0B2; color:#B66D00; border-color:#FFB74D; display:none;">❌ Remove from Buffer</button>
                <div id="bufferWarning" style="color: #D32F2F; font-size: 11px; margin-top: 5px; font-weight: 500;" class="hidden"></div>
            </div>

            <div id="globalBufferBox" style="margin-top: 15px; padding: 10px; background: #FFF3E0; border-radius: 6px; border: 1px solid #FFE0B2;" class="hidden">
                <span style="font-size: 12px; font-weight: bold; color: #E65100;">Current Buffer Status:</span>
                <p style="font-size: 13px; margin: 4px 0 10px; color: #E65100;">Regions staged for merging: <b id="staged_letters_span">-</b></p>
                <div style="display: flex; gap: 8px;">
                    <button id="execUnionBtn" style="flex: 1; background: #FF9800; color: white; border: none; padding: 8px; font-weight: bold; border-radius: 4px; cursor: pointer; font-size: 12px;">Execute Union</button>
                    <button id="clearBufferBtn" style="background: #F5F5F5; color: #333; border: 1px solid #ccc; padding: 8px; border-radius: 4px; cursor: pointer; font-size: 12px;">Clear Buffer</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        const toolMode = "{tool_mode}";
        const hasStartPoint = {str(has_start_point).lower()};
        const startPointId = "{start_point_id}";
        const lastActiveId = "{last_active_id}";
        
        const hasExistingUnion = {str(has_existing_union).lower()};
        const bufferIndices = {json.dumps(buffer_indices)};
        const bufferLetters = {json.dumps(buffer_letters)};
        const obsoleteFacesUnionInfo = {json.dumps(obsolete_faces_union_info)};

        const vertices = {json.dumps(vertices_data)};
        const facesData = {json.dumps(faces_data)};
        const edgesData = {json.dumps(edges_data)};

        const bgCanvas = document.getElementById('bgCanvas');
        const bgCtx = bgCanvas.getContext('2d');
        const interCanvas = document.getElementById('interactionCanvas');
        const interCtx = interCanvas.getContext('2d');

        const img = new Image();
        img.onload = () => bgCtx.drawImage(img, 0, 0);
        img.src = "data:image/png;base64,{img_base64}";

        let hoverV = null, hoverFace = null, hoverEdge = null;
        let selectedElement = null;
        let lockedV = null, lockedFace = null, lockedEdge = null;

        function isPointInPolygon(mx, my, polyVertices) {{
            let inside = false;
            for (let i = 0, j = polyVertices.length - 1; i < polyVertices.length; j = i++) {{
                const xi = polyVertices[i].x, yi = polyVertices[i].y;
                const xj = polyVertices[j].x, yj = polyVertices[j].y;
                const intersect = ((yi > my) !== (yj > my))
                    && (mx < (xj - xi) * (my - yi) / (yj - yi) + xi);
                if (intersect) inside = !inside;
            }}
            return inside;
        }}

        if (toolMode === "Vertex" && hasStartPoint) {{
            const found = vertices.find(v => String(v.id) === String(startPointId));
            if (found) {{
                lockedV = found;
                selectedElement = {{ type: "Vertex", data: found }};
                showVertexPanel(found);
            }}
        }}

        interCanvas.addEventListener('mousemove', function(e) {{
            if (selectedElement) return;

            const rect = interCanvas.getBoundingClientRect();
            const mx = e.clientX - rect.left;
            const my = e.clientY - rect.top;

            hoverV = null; hoverFace = null; hoverEdge = null;

            if (toolMode === "Vertex") {{
                for (let v of vertices) {{
                    if (v.is_obsolete) continue;
                    if (Math.sqrt((mx-v.x)**2 + (my-v.y)**2) < 20) {{
                        hoverV = v;
                        lockedV = v;
                        showVertexPanel(v);
                        break;
                    }}
                }}

            }} else if (toolMode === "Angle") {{
                let activeContainingFace = null;
                for (let f of facesData) {{
                    if (isPointInPolygon(mx, my, f.vertices)) {{
                        activeContainingFace = f;
                        break;
                    }}
                }}
                if (activeContainingFace) {{
                    let nearestFaceVertex = null;
                    let strictMinDist = 9999;
                    for (let v of activeContainingFace.vertices) {{
                        const fullVect = vertices.find(origV => origV.id === v.id);
                        if (!fullVect) continue;
                        // Skip if this vertex is not a valid corner
                        if (!activeContainingFace.valid_corner_ids.includes(v.id)) continue;
                        const d = Math.sqrt((mx - fullVect.x)**2 + (my - fullVect.y)**2);
                        if (d < strictMinDist) {{ strictMinDist = d; nearestFaceVertex = fullVect; }}
                    }}
                    if (nearestFaceVertex && strictMinDist < 35) {{
                        hoverV = nearestFaceVertex;
                        lockedV = nearestFaceVertex;
                        hoverFace = activeContainingFace;
                        lockedFace = activeContainingFace;
                        showAnglePanel(nearestFaceVertex, activeContainingFace);
                    }}
                }}

            }} else if (toolMode === "Edge") {{
                let bestEdge = null;
                let bestDist = 9999;
                for (let e of edgesData) {{
                    if (e.is_obsolete) continue;
                    const dx = e.x2 - e.x1;
                    const dy = e.y2 - e.y1;
                    const lenSq = dx*dx + dy*dy;
                    let t = lenSq > 0 ? ((mx-e.x1)*dx + (my-e.y1)*dy) / lenSq : 0;
                    t = Math.max(0, Math.min(1, t));
                    const nearX = e.x1 + t*dx;
                    const nearY = e.y1 + t*dy;
                    const dist = Math.sqrt((nearX-mx)**2 + (nearY-my)**2);
                    if (dist < bestDist) {{ bestDist = dist; bestEdge = e; }}
                }}
                if (bestEdge && bestDist < 18) {{
                    hoverEdge = bestEdge;
                    lockedEdge = bestEdge;
                    showEdgePanel(bestEdge);
                }}

            }} else if (toolMode === "Region") {{
                let targetFace = null;
                for (let f of facesData) {{
                    if (isPointInPolygon(mx, my, f.vertices)) {{
                        targetFace = f;
                        break;
                    }}
                }}
                if (!targetFace) {{
                    let minFaceDist = 9999;
                    for (let f of facesData) {{
                        const fd = Math.sqrt((mx - f.cx)**2 + (my - f.cy)**2);
                        if (fd < minFaceDist && fd < 60) {{ minFaceDist = fd; targetFace = f; }}
                    }}
                }}
                if (targetFace) {{
                    hoverFace = targetFace;
                    lockedFace = targetFace;
                    showRegionPanel(targetFace);
                }}
            }}

            redraw();
        }});

        interCanvas.addEventListener('click', function(e) {{
            if (selectedElement) {{
                selectedElement = null;
                document.getElementById('v_lock_status').style.display = "none";
                document.getElementById('angle_lock_status').style.display = "none";
                document.getElementById('edge_lock_status').style.display = "none";
                document.getElementById('region_lock_status').style.display = "none";
                document.getElementById('panelHeader').innerText = "Tool Panel: " + toolMode;
                stalePanels();
                redraw();
                return;
            }}
            if (toolMode === "Vertex" && lockedV && hoverV) {{
                selectedElement = {{ type: "Vertex", data: lockedV }};
                document.getElementById('v_lock_status').style.display = "inline";
            }} else if (toolMode === "Angle" && lockedV && lockedFace && hoverV) {{
                selectedElement = {{ type: "Angle", data: {{ v: lockedV, f: lockedFace }} }};
                document.getElementById('angle_lock_status').style.display = "inline";
            }} else if (toolMode === "Edge" && lockedEdge && hoverEdge) {{
                selectedElement = {{ type: "Edge", data: lockedEdge }};
                document.getElementById('edge_lock_status').style.display = "inline";
            }} else if (toolMode === "Region" && lockedFace && hoverFace) {{
                selectedElement = {{ type: "Region", data: lockedFace }};
                document.getElementById('region_lock_status').style.display = "inline";
            }}
            if (selectedElement) {{
                document.getElementById('panelHeader').innerText = "Tool Panel: " + toolMode + " (Selected)";
            }}
            redraw();
        }});

        function stalePanels() {{
            document.getElementById('placeholderText').classList.remove('hidden');
            document.getElementById('vertexPanel').classList.add('hidden');
            document.getElementById('anglePanel').classList.add('hidden');
            document.getElementById('edgePanel').classList.add('hidden');
            document.getElementById('regionPanel').classList.add('hidden');
            lockedV = null; lockedFace = null; lockedEdge = null;
        }}

        function showVertexPanel(v) {{
            document.getElementById('placeholderText').classList.add('hidden');
            document.getElementById('anglePanel').classList.add('hidden');
            document.getElementById('edgePanel').classList.add('hidden');
            document.getElementById('regionPanel').classList.add('hidden');
            document.getElementById('vertexPanel').classList.remove('hidden');

            const regionLabel = (v.neighbor_regions && v.neighbor_regions.length > 0)
                ? v.neighbor_regions.join(' / ')
                : String(v.id);
            document.getElementById('v_id_span').innerText = regionLabel;

            if (hasStartPoint) {{
                document.getElementById('connectionAlert').classList.remove('hidden');
                document.getElementById('normalForm').classList.add('hidden');
                document.getElementById('connectionForm').classList.remove('hidden');
                const btn = document.getElementById('confirmConnectBtn');
                btn.disabled = String(v.id) === String(startPointId);
                btn.style.opacity = btn.disabled ? 0.5 : 1.0;
            }} else {{
                document.getElementById('connectionAlert').classList.add('hidden');
                document.getElementById('normalForm').classList.remove('hidden');
                document.getElementById('connectionForm').classList.add('hidden');
            }}
        }}

        function showAnglePanel(v, face) {{
            document.getElementById('placeholderText').classList.add('hidden');
            document.getElementById('vertexPanel').classList.add('hidden');
            document.getElementById('edgePanel').classList.add('hidden');
            document.getElementById('regionPanel').classList.add('hidden');
            document.getElementById('anglePanel').classList.remove('hidden');
            document.getElementById('angle_region_span').innerText = "Vertex " + v.id + " in Region " + face.display;
        }}

        function showEdgePanel(e) {{
            document.getElementById('placeholderText').classList.add('hidden');
            document.getElementById('vertexPanel').classList.add('hidden');
            document.getElementById('anglePanel').classList.add('hidden');
            document.getElementById('regionPanel').classList.add('hidden');
            document.getElementById('edgePanel').classList.remove('hidden');
            if (e.is_hidden) {{
                document.getElementById('edgeHiddenWarning').classList.remove('hidden');
                document.getElementById('edgeActiveContent').classList.add('hidden');
            }} else {{
                document.getElementById('edgeHiddenWarning').classList.add('hidden');
                document.getElementById('edgeActiveContent').classList.remove('hidden');
                document.getElementById('edge_label_span').innerText = e.main_name + " | " + e.oppo_name;
                const mainBtn = document.getElementById('edgeMainBtn');
                const oppoBtn = document.getElementById('edgeOppoBtn');
                mainBtn.innerText = "Edge of " + e.main_name;
                mainBtn.style.display = e.main_valid ? 'block' : 'none';
                oppoBtn.innerText = "Edge of " + e.oppo_name;
                oppoBtn.style.display = e.oppo_valid ? 'block' : 'none';
            }}
        }}

        function showRegionPanel(face) {{
            document.getElementById('placeholderText').classList.add('hidden');
            document.getElementById('vertexPanel').classList.add('hidden');
            document.getElementById('anglePanel').classList.add('hidden');
            document.getElementById('edgePanel').classList.add('hidden');
            document.getElementById('regionPanel').classList.remove('hidden');

            const isObsolete = face.cache_idx in obsoleteFacesUnionInfo;
            const isInBuffer = bufferIndices.includes(face.cache_idx);
            const bufferIsFull = bufferIndices.length >= 2;

            if (isObsolete) {{
                document.getElementById('mergedFormationAlert').classList.remove('hidden');
                document.getElementById('merged_includes_span').innerHTML = "<b>Includes:</b> " + obsoleteFacesUnionInfo[face.cache_idx];
                document.getElementById('normalRegionBox').classList.add('hidden');
                document.getElementById('commitRegionBtn').classList.add('hidden');
                document.getElementById('commitUnionHighlightBtn').classList.remove('hidden');
            }} else {{
                document.getElementById('mergedFormationAlert').classList.add('hidden');
                document.getElementById('normalRegionBox').classList.remove('hidden');
                document.getElementById('region_label_span').innerText = "Region " + face.display;
                document.getElementById('commitRegionBtn').classList.remove('hidden');
                document.getElementById('commitUnionHighlightBtn').classList.add('hidden');
            }}

            const addBtn = document.getElementById('addToBufferBtn');
            const removeBtn = document.getElementById('removeFromBufferBtn');
            const bufWarn = document.getElementById('bufferWarning');

            if (isInBuffer) {{
                addBtn.style.display = 'none';
                removeBtn.style.display = 'block';
                bufWarn.classList.remove('hidden');
                bufWarn.innerText = "Region " + face.letter + " is inside your union buffer.";
            }} else {{
                addBtn.style.display = 'block';
                removeBtn.style.display = 'none';
                bufWarn.classList.add('hidden');
                if (hasExistingUnion || bufferIsFull || isObsolete) {{
                    addBtn.disabled = true;
                    addBtn.style.opacity = 0.5;
                    if (hasExistingUnion) {{
                        bufWarn.classList.remove('hidden');
                        bufWarn.innerText = "❌ An active union already exists.";
                    }} else if (bufferIsFull) {{
                        bufWarn.classList.remove('hidden');
                        bufWarn.innerText = "❌ Buffer is full (max 2 regions).";
                    }}
                }} else {{
                    addBtn.disabled = false;
                    addBtn.style.opacity = 1.0;
                }}
            }}

            const globalBox = document.getElementById('globalBufferBox');
            if (bufferLetters.length > 0) {{
                globalBox.classList.remove('hidden');
                document.getElementById('staged_letters_span').innerText = bufferLetters.join(', ');
                const execBtn = document.getElementById('execUnionBtn');
                const canExecute = bufferLetters.length === 2 && !hasExistingUnion;
                execBtn.disabled = !canExecute;
                execBtn.style.opacity = canExecute ? 1.0 : 0.5;
            }} else {{
                globalBox.classList.add('hidden');
            }}
        }}

        function redraw() {{
            interCtx.clearRect(0, 0, {DISPLAY_SIDE}, {DISPLAY_SIDE});

            const renderLock = selectedElement !== null;
            const targetV = renderLock ? lockedV : hoverV;
            const targetFace = renderLock ? lockedFace : hoverFace;
            const targetEdge = renderLock ? lockedEdge : hoverEdge;
            const primaryColor = renderLock ? '#FF4B4B' : '#00FFCC';
            const strokeWidth = renderLock ? 5 : 4;

            if (toolMode === "Vertex" && targetV && !targetV.is_obsolete) {{
                interCtx.beginPath();
                interCtx.arc(targetV.x, targetV.y, 15, 0, 2*Math.PI);
                interCtx.strokeStyle = primaryColor;
                interCtx.lineWidth = strokeWidth;
                interCtx.stroke();

            }} else if (toolMode === "Angle" && targetV && targetFace) {{
                const fverts = targetFace.vertices;
                const idx = fverts.findIndex(fv => fv.id === targetV.id);
                if (idx !== -1) {{
                    const n = fverts.length;
                    const prev = fverts[(idx - 1 + n) % n];
                    const next = fverts[(idx + 1) % n];
                    const ang1 = Math.atan2(prev.y - targetV.y, prev.x - targetV.x);
                    const ang2 = Math.atan2(next.y - targetV.y, next.x - targetV.x);

                    interCtx.beginPath();
                    interCtx.moveTo(targetV.x, targetV.y);
                    interCtx.lineTo(prev.x, prev.y);
                    interCtx.strokeStyle = renderLock ? 'rgba(255,75,75,0.8)' : 'rgba(255,160,0,0.7)';
                    interCtx.lineWidth = strokeWidth;
                    interCtx.stroke();

                    interCtx.beginPath();
                    interCtx.moveTo(targetV.x, targetV.y);
                    interCtx.lineTo(next.x, next.y);
                    interCtx.strokeStyle = renderLock ? 'rgba(255,75,75,0.8)' : 'rgba(255,160,0,0.7)';
                    interCtx.lineWidth = strokeWidth;
                    interCtx.stroke();

                    let diff = ang2 - ang1;
                    while (diff < 0) diff += 2 * Math.PI;
                    interCtx.beginPath();
                    if (diff > Math.PI) {{
                        interCtx.arc(targetV.x, targetV.y, 22, ang2, ang1, false);
                    }} else {{
                        interCtx.arc(targetV.x, targetV.y, 22, ang1, ang2, false);
                    }}
                    interCtx.strokeStyle = renderLock ? 'rgba(200,20,20,0.9)' : 'rgba(255,100,0,0.9)';
                    interCtx.lineWidth = 3;
                    interCtx.stroke();
                }}

            }}  else if (toolMode === "Edge" && targetEdge) {{
                    const segs = (targetEdge.segments && targetEdge.segments.length > 0)
                        ? targetEdge.segments
                        : [{{ x1: targetEdge.x1, y1: targetEdge.y1, x2: targetEdge.x2, y2: targetEdge.y2 }}];
                    const edgeColor = targetEdge.is_hidden
                        ? 'rgba(150,150,150,0.6)'
                        : (renderLock ? '#FF4B4B' : 'rgba(255,152,0,0.9)');
                    const edgeWidth = renderLock ? 7 : 6;
                    for (let seg of segs) {{
                        interCtx.beginPath();
                        interCtx.moveTo(seg.x1, seg.y1);
                        interCtx.lineTo(seg.x2, seg.y2);
                        interCtx.strokeStyle = edgeColor;
                        interCtx.lineWidth = edgeWidth;
                        interCtx.stroke();
                    }}


            }} else if (toolMode === "Region" && targetFace) {{
                let facesToDraw = [targetFace];
                if (targetFace.is_obsolete && targetFace.union_partner_idx !== null) {{
                    const partner = facesData.find(f => f.cache_idx === targetFace.union_partner_idx);
                    if (partner) facesToDraw.push(partner);
                }}

                const isObs = targetFace.is_obsolete;
                const fillColor = isObs
                    ? (renderLock ? 'rgba(46,125,50,0.3)' : 'rgba(46,125,50,0.15)')
                    : (renderLock ? 'rgba(255,75,75,0.25)' : 'rgba(33,150,243,0.2)');
                const strokeColor = isObs
                    ? (renderLock ? '#2E7D32' : 'rgba(46,125,50,0.7)')
                    : (renderLock ? '#FF4B4B' : 'rgba(21,101,192,0.8)');

                for (let f of facesToDraw) {{
                    const fverts = f.vertices;
                    if (fverts.length > 0) {{
                        interCtx.beginPath();
                        interCtx.moveTo(fverts[0].x, fverts[0].y);
                        for (let i = 1; i < fverts.length; i++) {{
                            interCtx.lineTo(fverts[i].x, fverts[i].y);
                        }}
                        interCtx.closePath();
                        interCtx.fillStyle = fillColor;
                        interCtx.fill();
                    }}
                }}

                if (facesToDraw.length === 1) {{
                    const fverts = facesToDraw[0].vertices;
                    if (fverts.length > 0) {{
                        interCtx.beginPath();
                        interCtx.moveTo(fverts[0].x, fverts[0].y);
                        for (let i = 1; i < fverts.length; i++) {{
                            interCtx.lineTo(fverts[i].x, fverts[i].y);
                        }}
                        interCtx.closePath();
                        interCtx.strokeStyle = strokeColor;
                        interCtx.lineWidth = strokeWidth;
                        interCtx.stroke();
                    }}
                }} else {{
                    const faceAVerts = new Set(facesToDraw[0].vertices.map(v => v.id));
                    const faceBVerts = new Set(facesToDraw[1].vertices.map(v => v.id));

                    for (let f of facesToDraw) {{
                        const fverts = f.vertices;
                        const n = fverts.length;
                        for (let i = 0; i < n; i++) {{
                            const v1 = fverts[i];
                            const v2 = fverts[(i + 1) % n];
                            const isShared = faceAVerts.has(v1.id) && faceAVerts.has(v2.id)
                                          && faceBVerts.has(v1.id) && faceBVerts.has(v2.id);
                            if (isShared) continue;

                            interCtx.beginPath();
                            interCtx.moveTo(v1.x, v1.y);
                            interCtx.lineTo(v2.x, v2.y);
                            interCtx.strokeStyle = strokeColor;
                            interCtx.lineWidth = strokeWidth;
                            interCtx.stroke();
                        }}
                    }}
                }}
            }}
        }}

        function dispatchAction(actionName, extraParams) {{
            if (!lockedV && !['cancel_connection','commit_edge','extend_edge','commit_region','add_to_buffer','remove_from_buffer','clear_buffer','execute_union','commit_union_highlight'].includes(actionName)) {{
                alert("Please click/select a vertex first!");
                return;
            }}
            const targetId = lockedV ? lockedV.id : "none";
            const parentBaseUrl = window.parent.location.origin + window.parent.location.pathname;
            const newParams = new URLSearchParams();
            newParams.set("bridge_act", actionName);
            newParams.set("bridge_tgt", targetId);
            if (extraParams) {{
                for (const [k, v] of Object.entries(extraParams)) {{
                    newParams.set(k, v);
                }}
            }}
            window.parent.location.replace(parentBaseUrl + "?" + newParams.toString());
        }}

        document.getElementById('submitBtn')?.addEventListener('click', () => dispatchAction('commit_vertex'));
        document.getElementById('startConnectBtn')?.addEventListener('click', () => dispatchAction('set_start_point'));
        document.getElementById('axisHBtn')?.addEventListener('click', () => dispatchAction('commit_axis_h'));
        document.getElementById('axisVBtn')?.addEventListener('click', () => dispatchAction('commit_axis_v'));
        document.getElementById('confirmConnectBtn')?.addEventListener('click', () => dispatchAction('confirm_connection'));
        document.getElementById('cancelConnectBtn')?.addEventListener('click', () => dispatchAction('cancel_connection'));

        document.getElementById('commitAngleBtn')?.addEventListener('click', () => {{
            if (!lockedV || !lockedFace) return;
            dispatchAction('commit_angle', {{ bridge_face: lockedFace.cache_idx }});
        }});

        document.getElementById('edgeMainBtn')?.addEventListener('click', () => {{
            if (!lockedEdge) return;
            dispatchAction('commit_edge', {{ bridge_side: 'main', bridge_tail: lockedEdge.tail_id, bridge_head: lockedEdge.head_id }});
        }});
        document.getElementById('edgeOppoBtn')?.addEventListener('click', () => {{
            if (!lockedEdge) return;
            dispatchAction('commit_edge', {{ bridge_side: 'oppo', bridge_tail: lockedEdge.tail_id, bridge_head: lockedEdge.head_id }});
        }});
        document.getElementById('extendEdgeBtn')?.addEventListener('click', () => {{
            if (!lockedEdge) return;
            dispatchAction('extend_edge', {{ bridge_tail: lockedEdge.tail_id, bridge_head: lockedEdge.head_id }});
        }});

        document.getElementById('commitRegionBtn')?.addEventListener('click', () => {{
            if (!lockedFace) return;
            dispatchAction('commit_region', {{ bridge_face: lockedFace.cache_idx }});
        }});
        document.getElementById('commitUnionHighlightBtn')?.addEventListener('click', () => {{
            if (!lockedFace) return;
            dispatchAction('commit_union_highlight', {{ bridge_face: lockedFace.cache_idx }});
        }});
        document.getElementById('addToBufferBtn')?.addEventListener('click', () => {{
            if (!lockedFace) return;
            dispatchAction('add_to_buffer', {{ bridge_face: lockedFace.cache_idx }});
        }});
        document.getElementById('removeFromBufferBtn')?.addEventListener('click', () => {{
            if (!lockedFace) return;
            dispatchAction('remove_from_buffer', {{ bridge_face: lockedFace.cache_idx }});
        }});
        document.getElementById('clearBufferBtn')?.addEventListener('click', () => dispatchAction('clear_buffer'));
        document.getElementById('execUnionBtn')?.addEventListener('click', () => dispatchAction('execute_union'));

        redraw();
    </script>
</body>
</html>
"""

components.html(html_code, height=DISPLAY_SIDE + 20, width=1000)
