"""Geometry-order regressions: answers must not depend on region names."""
import contextlib
import io
import math
import os
from pathlib import Path
import tempfile
import unittest

import BuildRandomMap
import FinalizeFaces
import Graph
import GraphCheck
import Questions


def fan_fixture():
    Graph.initialize()
    coordinates = [(0,0),(1,0),(1,1),(0,1),(0,.5),(1,.5),(.5,.5),(.25,1),(.5,1),(.75,1)]
    vertices = [Graph.Vertex(Graph.Vector(*p)) for p in coordinates]
    edges = {}
    def edge(a,b):
        if (a,b) not in edges:
            e = Graph.Edge(vertices[a],vertices[b],True)
            edges[a,b],edges[b,a] = e,e.reverse
        return edges[a,b]
    polygons = {'M':[0,1,5,6,4], 'B':[6,7,3,4], 'N':[6,8,7],
                'D':[6,9,8], 'S':[6,5,2,9]}
    faces = {}
    for name,indices in polygons.items():
        es = [edge(a,b) for a,b in zip(indices,indices[1:]+indices[:1])]
        f = Graph.Face(es,True)
        faces[name] = f
        for e in es:e.leftFace = f
    boundary = [e for e in edges.values() if e.leftFace is None]
    outgoing = {e.tail:e for e in boundary}
    ordered = [boundary[0]]
    while ordered[-1].head is not ordered[0].tail:
        ordered.append(outgoing[ordered[-1].head])
    outside = Graph.Face(ordered,False)
    for e in ordered:e.leftFace = outside
    all_faces = [outside]+list(faces.values())
    FinalizeFaces.FinalizeFaces(vertices,list(edges.values()),all_faces)
    for name,f in faces.items():f.letter = name
    outside.letter = 'Outside'
    assert GraphCheck.GraphCheck(vertices,list(edges.values()),all_faces)
    return faces,vertices


class VertexBoundaryOrderTests(unittest.TestCase):
    def test_ccw_and_cw_have_opposite_fan_orders(self):
        faces,vertices = fan_fixture()
        ccw,_,groups = Questions.VertexOnlyBoundaryOrder(faces['M'],vertices[0],True)
        cw,_,_ = Questions.VertexOnlyBoundaryOrder(faces['M'],vertices[0],False)
        self.assertEqual(ccw,[faces['D'],faces['N']])
        self.assertEqual(cw,list(reversed(ccw)))
        self.assertEqual(groups[0]['exterior_sector_order'],['S','D','N','B'])
        self.assertNotIn('Outside',[f.letter for f in ccw])

    def test_labels_do_not_control_order(self):
        faces,vertices = fan_fixture()
        faces['D'].letter,faces['N'].letter = 'Z','A'
        ccw,_,_ = Questions.VertexOnlyBoundaryOrder(faces['M'],vertices[0],True)
        self.assertEqual([f.letter for f in ccw],['Z','A'])

    def test_start_contact_is_processed_first_and_reversed_locally(self):
        faces,vertices = fan_fixture()
        ccw,records,_ = Questions.VertexOnlyBoundaryOrder(faces['M'],vertices[6],True)
        cw,_,_ = Questions.VertexOnlyBoundaryOrder(faces['M'],vertices[6],False)
        self.assertEqual([r['boundary_index'] for r in records],[0,0])
        self.assertEqual(cw,list(reversed(ccw)))

    def test_native_six_candidate_example_against_polygon_angle_oracle(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory(prefix='native_boundary_order_test_') as temp:
            os.chdir(temp)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    m = BuildRandomMap.BuildRandomMap(20,1,1,5108,structure_complexity='high')
            finally:
                os.chdir(previous)
        f = next(f for f in m.faces if f.letter=='M')
        start = next(v for v in f.vertices if Questions.identifyVertex(v,0)=='the vertex of M with the widest angle')
        ccw,_,groups = Questions.VertexOnlyBoundaryOrder(f,start,True)
        cw,_,_ = Questions.VertexOnlyBoundaryOrder(f,start,False)
        self.assertEqual([g.letter for g in ccw],['I','E','F','O','D','N'])
        self.assertEqual(cw,list(reversed(ccw)))
        # Independent oracle: mid-angles of candidate polygon interior sectors,
        # measured from the ray to the previous target-boundary vertex.
        boundary = list(dict.fromkeys(f.vertices))
        index = boundary.index(start)
        walk = boundary[index:]+boundary[:index]
        ranking = []
        for candidate in ccw:
            v, = set(boundary)&set(candidate.vertices)
            poly = list(dict.fromkeys(candidate.vertices))
            i = poly.index(v)
            angle = lambda point:math.atan2(point.p.y-v.p.y,point.p.x-v.p.x)
            lo,hi = angle(poly[(i+1)%len(poly)]),angle(poly[i-1])
            midpoint = lo+((hi-lo)%(2*math.pi))/2
            j = boundary.index(v)
            arrival = angle(boundary[j-1])
            ranking.append(((walk.index(v),(midpoint-arrival)%(2*math.pi)),candidate))
        self.assertEqual([g for _,g in sorted(ranking,key=lambda x:x[0])],ccw)
        self.assertEqual([x['regions'] for x in groups if len(x['regions'])>1],[['F','O'],['D','N']])


if __name__=='__main__':
    unittest.main()
