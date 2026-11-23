"""Shared direction convention for question generation and extension display."""
import math
import re


def preferred_extension_axis(a, b, explicit_direction=None):
    """Honor specified wording; otherwise use the edge's dominant coordinate.

    A 45-degree tie uses left/right consistently. Coordinates are mathematical,
    so increasing y means up.
    """
    if explicit_direction in ('left','right'):return 'x'
    if explicit_direction in ('up','down','top','bottom'):return 'y'
    def xy(p):return (p.x,p.y) if hasattr(p,'x') else p
    a,b=xy(a),xy(b)
    return 'x' if abs(b[0]-a[0])>=abs(b[1]-a[1]) else 'y'


def question_extension_direction(a, b, text, graph):
    """Use question wording only when its described shared edge matches."""
    target=re.search(r'edge of (?:region )?([A-Z]) that (?:borders|meets) (?:region )?([A-Z])',text)
    direction=re.search(r'\bExtend\b[^.?!]{0,100}?\b(right|left|up|down|top|bottom)\b',text,re.I)
    if not target or not direction or graph is None:return None
    pair=set(target.groups());points=[]
    for edge in graph.edges:
        other=getattr(edge,'reverse',None)
        faces=[getattr(edge,'leftFace',None),getattr(other,'leftFace',None)]
        if {getattr(face,'letter',None) for face in faces}==pair:
            points.extend((edge.tail.p,edge.head.p))
    if not points:return None
    u,v=max(((u,v) for u in points for v in points),key=lambda p:math.hypot(p[0].x-p[1].x,p[0].y-p[1].y))
    near=lambda u,v:math.hypot(u.x-v.x,u.y-v.y)<1e-8
    if (near(a,u) and near(b,v)) or (near(a,v) and near(b,u)):
        return direction.group(1).lower()
    return None
