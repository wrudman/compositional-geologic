"""Exercise annotation measurement handlers without starting or saving a survey."""
import ast
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from test_merge_multiple_regions import grid

SOURCE = Path(__file__).with_name("app_2.py").read_text()


class AnnotationMeasurements(unittest.TestCase):
    def setUp(self):
        faces = grid(4, 1)
        for index, face in enumerate(faces):
            face._cache_idx = index
        vertices = list(dict.fromkeys(v for f in faces for v in f.vertices))
        session = SimpleNamespace(res_map=SimpleNamespace(faces=faces, vertices=vertices), actions=[])
        self.data = {"session": session, "selected_region_indices": [], "selected_vertex_ids": [],
                     "selected_angles": [], "selected_edges": [], "action_log": []}
        self.ns = {"math": math, "re": re, "save_session": Mock(),
                   "sync_vertex_selection_labels": Mock(),
                   "vertex_display_name": lambda sess, v: f"v{v.num}",
                   "union_boundary_vertices": lambda sess, face: []}
        names = {"run_selected_measurements", "find_vertex_by_id", "find_face_by_cache_idx",
                 "polygon_area_for_face", "distance_between_points", "interior_angle_degrees",
                 "measured_angle_degrees", "faces_for_region_measure", "measure_region",
                 "set_last_measurement", "_action_geometry_context", "format_measurement_display",
                 "participant_output_for_action", "compositional_tool_call_from_action"}
        tree = ast.parse(SOURCE)
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        exec(compile(ast.Module(body=functions, type_ignores=[]), "annotation_handlers", "exec"), self.ns)
        self.ns["log_action"] = Mock(side_effect=lambda data, action, detail: data["action_log"].append(
            {"action": action, "detail": detail, "event_id": "event_1"}))

    def run_measure(self, action):
        self.assertTrue(self.ns["run_selected_measurements"](self.data, action))
        self.ns["log_action"].assert_called_once()
        self.ns["save_session"].assert_called_once()
        call = self.ns["compositional_tool_call_from_action"](self.data["action_log"][0], 1)
        self.assertEqual(call["tool"], "measure")
        return self.data["last_measurement"], call

    def test_batch_areas_output_and_trace(self):
        self.data["selected_region_indices"] = [0, 1, 2]
        result, call = self.run_measure("measure_region")
        self.assertEqual([item["area"] for item in result["items"]], [1., 1., 1.])
        self.assertEqual(call["input_count"], 3)
        self.assertEqual(call["output"]["measurement_count"], 3)
        self.assertTrue(call["batch"])
        self.assertEqual(self.data["selected_region_indices"], [])
        for item in result["items"]:
            self.assertIn(item["label"], call["display_text"])
            self.assertIn("face", item["geometry"])

    def test_multiple_angles_keep_distinct_labels(self):
        face = self.data["session"].res_map.faces[0]
        self.data["selected_angles"] = [
            {"vertex_id": str(v.num), "face_idx": 0, "marker_label": f"a{i}"}
            for i, v in enumerate(face.vertices[1:4], 1)]
        result, call = self.run_measure("measure_angle")
        self.assertEqual([x["degrees"] for x in result["items"]], [90., 90., 90.])
        self.assertIn("a1", call["display_text"])
        self.assertIn("a3", call["display_text"])
        self.assertEqual(self.data["selected_angles"], [])

    def test_reference_to_many_distances(self):
        faces = self.data["session"].res_map.faces
        vertices = [face.vertices[0] for face in faces]
        self.data["selected_vertex_ids"] = [str(v.num) for v in vertices]
        result, call = self.run_measure("measure_distance")
        self.assertEqual([x["length"] for x in result["items"]], [1., 2., 3.])
        self.assertEqual(call["input_count"], 4)
        self.assertEqual(call["output"]["measurement_count"], 3)
        self.assertIn("reference=", call["input"])
        self.assertEqual(self.data["selected_vertex_ids"], [])

    def test_single_measurement_retains_scalar_schema(self):
        self.data["selected_region_indices"] = [0]
        result, call = self.run_measure("measure_region")
        self.assertEqual(result["kind"], "region")
        self.assertEqual(call["output"]["type"], "number")
        self.assertEqual(call["output"]["value"], 1.)
        self.assertFalse(call["batch"])

    def test_invalid_or_mixed_selection_is_atomic(self):
        self.data["selected_region_indices"] = [0, 999]
        self.assertFalse(self.ns["run_selected_measurements"](self.data, "measure_region"))
        self.assertEqual(self.data["selected_region_indices"], [0, 999])
        self.data["selected_vertex_ids"] = ["0", "1"]
        self.assertFalse(self.ns["run_selected_measurements"](self.data, "measure_distance"))
        self.ns["log_action"].assert_not_called()
        self.ns["save_session"].assert_not_called()

    def test_frontend_batch_enablement_and_dispatch(self):
        node = os.environ.get("NODE_BINARY") or shutil.which("node")
        if not node:
            self.skipTest("Set NODE_BINARY to run JavaScript control checks")
        start = SOURCE.index("        function updateRunButtonStates()")
        end = SOURCE.index("        document.querySelectorAll('.tool-choice')", start)
        js = SOURCE[start:end].replace("{{", "{").replace("}}", "}")
        start = SOURCE.index("        function runMeasureAngle()")
        end = SOURCE.index("        document.querySelectorAll('input[name=", start)
        js += SOURCE[start:end].replace("{{", "{").replace("}}", "}")
        prelude = """
        const assert = require('node:assert/strict');
        let selectedVertexIds=[], selectedRegionIndices=[], selectedAngles=[], selectedEdges=[];
        let activeCategory='measure', toolMode='Angle', measureKind='angle', hasExistingUnion=false;
        const document={querySelector:()=>null, getElementById:()=>({style:{}})};
        const states={}; const setRunDisabled=(id,disabled)=>states[id]=disabled;
        const selectedAngleData=()=>({}); const selectedEdgeData=()=>({});
        const totalSelectedInputs=()=>selectedVertexIds.length+selectedRegionIndices.length+selectedAngles.length+selectedEdges.length;
        const actions=[]; const dispatchAction=(a)=>actions.push(a); const alert=()=>{};
        """
        checks = """
        selectedAngles=[1,2,3]; updateRunButtonStates();
        assert.equal(states.measureAngleBtn,false); assert.equal(states.commitAngleBtn,true);
        runMeasureAngle(); assert.deepEqual(actions,['measure_angle']);
        selectedVertexIds=[1]; updateRunButtonStates();
        assert.equal(states.measureAngleBtn,true); runMeasureAngle(); assert.equal(actions.length,1);
        selectedAngles=[]; selectedVertexIds=[1,2,3,4]; measureKind='distance'; updateRunButtonStates();
        assert.equal(states.measureDistanceBtn,false); assert.equal(states.confirmConnectBtn,true);
        selectedVertexIds=[]; selectedRegionIndices=[1,2,3]; measureKind='area'; updateRunButtonStates();
        assert.equal(states.measureRegionBtn,false); assert.equal(states.commitRegionBtn,true);
        """
        subprocess.run([node, "-e", prelude + js + checks], check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
