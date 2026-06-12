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

# --- SESSION INITIALIZATION ---
# 每次都从磁盘恢复，这样 location.replace 刷新页面也不怕
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
    img_size = (int(200 + 800 * maxX), int(200 + 800 * maxY))
    return {
        "session": AnnotationSession(res_map, img_size),
        "union_buffer": [],
        "last_active_id": "none",
        "v_start": None,
        "v_start_id": "",
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
                print(f"✅ actions count = {len(sess.actions)}")
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
                    st.toast(f"🔗 Connection: {data.get('v_start_id','')} → {tgt_id}")

            elif act == "commit_axis_h":
                sess.add_auxiliary_line_action(tool_draw_axis_line, target_v.p, direction='H')
                save_session(data)
                st.toast("↔ Horizontal Line Drawn")

            elif act == "commit_axis_v":
                sess.add_auxiliary_line_action(tool_draw_axis_line, target_v.p, direction='V')
                save_session(data)
                st.toast("↕ Vertical Line Drawn")
        else:
            st.warning(f"⚠️ Vertex {tgt_id} is obsolete.")

    if act == "cancel_connection":
        data["v_start"] = None
        data["v_start_id"] = ""
        data["last_active_id"] = "none"
        save_session(data)
        st.toast("❌ Cancel & Reset")

    st.query_params.clear()

# 每次渲染都从 data 读最新状态
sess = data["session"]
action_count = len(sess.actions)
last_active_id = data.get("last_active_id", "none")
has_start_point = data.get("v_start") is not None
start_point_id = data.get("v_start_id", "")

# --- VERTEX DATA ---
vertices_data = []
for v in sess.res_map.vertices:
    render_x = v.p.x * MATH_SCALE + 100
    render_y = 900.0 - (v.p.y * MATH_SCALE)
    px = render_x / (sess.img_size[0] / DISPLAY_SIDE)
    py = render_y / (sess.img_size[1] / DISPLAY_SIDE)
    vertices_data.append({
        "id": int(getattr(v, "num", id(v))),
        "x": px,
        "y": py,
        "label": getattr(v, "num", "")
    })

# --- SIDEBAR ---
st.title("Geologic Geometry Pad ✏️")

with st.sidebar:
    st.header("Settings")
    tool_mode = st.radio("Select Active Tool:", ["Vertex", "Angle", "Edge", "Region"], index=0)
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

# --- FRONTEND (unchanged) ---
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
        .right-panel {{ width: 340px; height: {DISPLAY_SIDE}px; background: #ffffff; border-radius: 8px; border: 1px solid #EAEAEA; padding: 24px; box-sizing: border-box; display: flex; flex-direction: column; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }}
        .status-box {{ padding: 12px; background-color: #EDF7ED; border-left: 4px solid #4CAF50; color: #1E4620; margin-bottom: 20px; font-size: 14px; font-weight: 500; border-radius: 0 6px 6px 0; }}
        .info-box {{ padding: 12px; background-color: #E3F2FD; border-left: 4px solid #2196F3; color: #0D47A1; margin-bottom: 15px; font-size: 13px; border-radius: 0 6px 6px 0; }}
        .hidden {{ display: none !important; }}
        .action-btn {{ background: #FF4B4B; color: white; border: none; padding: 14px; border-radius: 6px; cursor: pointer; font-weight: bold; margin-top: 5px; width: 100%; font-size: 14px; transition: background 0.2s; }}
        .action-btn:hover {{ background: #E03E3E; }}
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
        <h3 style="margin-top:0; color:#111; font-size:18px; border-bottom:2px solid #F0F0F0; padding-bottom:10px;">Tool Panel: {tool_mode}</h3>
        <div id="placeholderText" style="color: #666; font-size: 14px; line-height: 1.6;">
            💡 <b>How to operate:</b><br>
            1. Hover over a vertex node in the left pad.<br>
            2. Click the quick buttons to perform actions live.
        </div>
        <div id="dynamicContent" class="hidden">
            <div id="targetNodeBox" class="status-box">
                🎯 <b>Active Node ID:</b> <span id="v_id_span">-</span>
            </div>
            <div id="connectionAlert" class="info-box hidden">
                ✅ <b>Start Vertex Selected</b>
            </div>
            <div id="vertexModeControls">
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
        </div>
    </div>

    <script>
        const vertices = {json.dumps(vertices_data)};
        const toolMode = "{tool_mode}";
        const hasStartPoint = {str(has_start_point).lower()};
        const startPointId = "{start_point_id}";
        const lastActiveId = "{last_active_id}";

        const bgCanvas = document.getElementById('bgCanvas');
        const bgCtx = bgCanvas.getContext('2d');
        const interCanvas = document.getElementById('interactionCanvas');
        const interCtx = interCanvas.getContext('2d');

        const img = new Image();
        img.onload = () => bgCtx.drawImage(img, 0, 0);
        img.src = "data:image/png;base64,{img_base64}";

        let lockedV = null;

        if (hasStartPoint) {{
            const found = vertices.find(v => String(v.id) === String(startPointId));
            if (found) {{ lockedV = found; updateRightPanel(found); }}
        }} else if (lastActiveId && lastActiveId !== "none") {{
            const found = vertices.find(v => String(v.id) === String(lastActiveId));
            if (found) {{ lockedV = found; updateRightPanel(found); }}
        }}

        interCanvas.addEventListener('mousemove', function(e) {{
            const rect = interCanvas.getBoundingClientRect();
            const mx = e.clientX - rect.left;
            const my = e.clientY - rect.top;
            for (let v of vertices) {{
                if (Math.sqrt((mx-v.x)**2 + (my-v.y)**2) < 20) {{
                    lockedV = v;
                    updateRightPanel(v);
                    break;
                }}
            }}
            redraw();
        }});

        function updateRightPanel(v) {{
            document.getElementById('placeholderText').classList.add('hidden');
            document.getElementById('dynamicContent').classList.remove('hidden');
            document.getElementById('v_id_span').innerText = v.id;
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

        function redraw() {{
            interCtx.clearRect(0, 0, {DISPLAY_SIDE}, {DISPLAY_SIDE});
            if (lockedV) {{
                interCtx.beginPath();
                interCtx.arc(lockedV.x, lockedV.y, 15, 0, 2*Math.PI);
                interCtx.strokeStyle = '#00FFCC';
                interCtx.lineWidth = 4;
                interCtx.stroke();
            }}
        }}

        function dispatchAction(actionName) {{
            if (!lockedV && actionName !== "cancel_connection") {{
                alert("Please hover over a vertex first!");
                return;
            }}
            const targetId = actionName === "cancel_connection" ? "none" : lockedV.id;
            const parentBaseUrl = window.parent.location.origin + window.parent.location.pathname;
            const newParams = new URLSearchParams();
            newParams.set("bridge_act", actionName);
            newParams.set("bridge_tgt", targetId);
            window.parent.location.replace(parentBaseUrl + "?" + newParams.toString());
        }}

        document.getElementById('submitBtn')?.addEventListener('click', () => dispatchAction('commit_vertex'));
        document.getElementById('startConnectBtn')?.addEventListener('click', () => dispatchAction('set_start_point'));
        document.getElementById('axisHBtn')?.addEventListener('click', () => dispatchAction('commit_axis_h'));
        document.getElementById('axisVBtn')?.addEventListener('click', () => dispatchAction('commit_axis_v'));
        document.getElementById('confirmConnectBtn')?.addEventListener('click', () => dispatchAction('confirm_connection'));
        document.getElementById('cancelConnectBtn')?.addEventListener('click', () => dispatchAction('cancel_connection'));

        redraw();
    </script>
</body>
</html>
"""

components.html(html_code, height=DISPLAY_SIDE + 20, width=1000)
