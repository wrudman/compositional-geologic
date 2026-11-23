"""Geometry primitives for native-map taxonomy review examples."""
import math,itertools
import Graph,Questions as Q,map_helpers as mh

EPS=1e-8
def xy(v):return (float(v.p.x),float(v.p.y))
def cross(a,b):return a[0]*b[1]-a[1]*b[0]
def sub(a,b):return(a[0]-b[0],a[1]-b[1])
def add(a,b):return(a[0]+b[0],a[1]+b[1])
def scale(a,k):return(a[0]*k,a[1]*k)
def labels(items):return ', '.join(str(x) for x in items) or 'None'
def poly_area(points):return abs(sum(cross(a,b) for a,b in zip(points,points[1:]+points[:1])))/2
def centroid(points):
    sums=[cross(a,b) for a,b in zip(points,points[1:]+points[:1])];area2=sum(sums)
    return tuple(sum((a[k]+b[k])*s for a,b,s in zip(points,points[1:]+points[:1],sums))/(3*area2) for k in [0,1])
def inside(p,points):
    x,y=p;hit=False
    for a,b in zip(points,points[1:]+points[:1]):
        if abs(cross(sub(p,a),sub(b,a)))<EPS and min(a[0],b[0])-EPS<=x<=max(a[0],b[0])+EPS and min(a[1],b[1])-EPS<=y<=max(a[1],b[1])+EPS:return False
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:hit=not hit
    return hit
def point_segment(p,a,b):
    d=sub(b,a);t=max(0,min(1,sum(x*y for x,y in zip(sub(p,a),d))/sum(x*x for x in d)))
    return math.dist(p,add(a,scale(d,t)))
def angle(f,v):
    boundary=list(dict.fromkeys(f.vertices));i=boundary.index(v);a,b,c=xy(boundary[i-1]),xy(v),xy(boundary[(i+1)%len(boundary)])
    incoming=math.atan2(b[1]-a[1],b[0]-a[0]);outgoing=math.atan2(c[1]-b[1],c[0]-b[0])
    turn=math.atan2(math.sin(outgoing-incoming),math.cos(outgoing-incoming));result=math.pi-turn
    assert abs(result-Graph.angleAtFace(v,f))<1e-6
    return result
def clip(points,a,b,positive):
    result=[];direction=sub(b,a)
    for u,v in zip(points,points[1:]+points[:1]):
        du=cross(direction,sub(u,a))*(1 if positive else -1);dv=cross(direction,sub(v,a))*(1 if positive else -1)
        if du>=-EPS:result.append(u)
        if (du>EPS and dv<-EPS) or (du<-EPS and dv>EPS):result.append(add(u,scale(sub(v,u),du/(du-dv))))
    return result
def sector_angle(f,v):
    boundary=list(dict.fromkeys(f.vertices));i=boundary.index(v);p=xy(v);out=sub(xy(boundary[(i+1)%len(boundary)]),p)
    return (math.atan2(out[1],out[0])+angle(f,v)/2)%(2*math.pi)

class MapView:
    def __init__(self,m):
        self.m=m;self.fs=[f for f in m.faces if f.bounded];self.by={f.letter:f for f in self.fs};mh.use_map(m)
        self.bound={f:list(dict.fromkeys(f.vertices)) for f in self.fs};self.cv={f:list(dict.fromkeys(f.trueVertices)) for f in self.fs}
        self.points={f:[xy(v) for v in self.bound[f]] for f in self.fs}
        self.centers={f:centroid(self.points[f]) for f in self.fs};self.areas={f:poly_area(self.points[f]) for f in self.fs}
        for f in self.fs:assert abs(self.areas[f]-mh.area(f))<1e-7
        self.edge_ns={f:{e.reverse.leftFace for e in f.edges if e.reverse.leftFace.bounded} for f in self.fs}
        self.point_ns={f:Q._vp_neighbors(f,self.fs) for f in self.fs};self.all_ns={f:self.edge_ns[f]|self.point_ns[f] for f in self.fs}
        self.edges={f:self.geometric_edges(f) for f in self.fs};self.describe={v:Q.identifyVertex(v,0) for v in m.vertices}
        self.count={f:len(self.cv[f]) for f in self.fs};self.frame={f:sum(Q._vp_on_frame(v) for v in self.cv[f]) for f in self.fs}
    def geometric_edges(self,f):
        corners=list(dict.fromkeys(f.trueVertices));result=[]
        boundary=list(dict.fromkeys(f.vertices));idx={v:i for i,v in enumerate(boundary)}
        for i,a in enumerate(corners):
            b=corners[(i+1)%len(corners)];lo,hi=idx[a],idx[b]
            segments=f.edges[lo:hi] if lo<hi else f.edges[lo:]+f.edges[:hi]
            result.append({'a':a,'b':b,'owner':f.letter,'length':math.dist(xy(a),xy(b)),'midpoint':scale(add(xy(a),xy(b)),.5),
                           'segments':segments,'meets':{s.reverse.leftFace for s in segments}})
        return result
    def unique_edges(self,f):
        edges=self.edges[f]
        return [e for e in edges if len(e['meets'])==1 and sum(x['meets']==e['meets'] for x in edges)==1]
    def edge_text(self,f,e):
        other=next(iter(e['meets']));return f'the edge of {f.letter} that borders '+('Outside' if not other.bounded else f'region {other.letter}')
    def line(self,a,b,lo=-1e6,hi=1e6):
        d=sub(b,a);events=[lo,hi]
        for e in self.m.edges:
            u,v=xy(e.tail),xy(e.head);ev=sub(v,u);den=cross(d,ev)
            if abs(den)<1e-10:continue
            t=cross(sub(u,a),ev)/den;s=cross(sub(u,a),d)/den
            if lo+EPS<t<hi-EPS and -EPS<=s<=1+EPS:events.append(t)
        events=sorted(set(round(t,10) for t in events));sequence=[];intervals=[]
        for l,r in zip(events,events[1:]):
            if r-l<1e-8:continue
            p=add(a,scale(d,(l+r)/2));hits=[f for f in self.fs if inside(p,self.points[f])]
            if len(hits)!=1:continue
            f=hits[0]
            if sequence and sequence[-1] is f and abs(intervals[-1][1]-l)<1e-7:intervals[-1]=(intervals[-1][0],r,f)
            else:sequence.append(f);intervals.append((l,r,f))
        return sequence,intervals
    def ray_to_frame(self,p,d):
        ahead=add(p,scale(d,1e-7))
        if any(x<-EPS or x>1+EPS for x in ahead):return 0
        ts=[(side-p[k])/d[k] for k in [0,1] if abs(d[k])>EPS for side in [0,1] if (side-p[k])/d[k]>EPS]
        return min(ts) if ts else 0
    def boundary_order(self,f,start,point_contacts=False):
        boundary=self.bound[f];i=boundary.index(start);ordered=f.edges[i:]+f.edges[:i];result=[]
        for e in ordered:
            if point_contacts:
                arcs=sorted(e.tail.outarcs,key=lambda a:math.atan2(a.head.p.y-e.tail.p.y,a.head.p.x-e.tail.p.x))
                incoming=next(x for x in f.edges if x.head is e.tail);cursor=arcs.index(incoming.reverse);stop=arcs.index(e)
                for _ in range(len(arcs)):
                    if cursor==stop:break
                    other=arcs[cursor].leftFace
                    if other is not f:
                        name=other.letter if other.bounded else 'Outside'
                        if not result or result[-1]!=name:result.append(name)
                    cursor=(cursor+1)%len(arcs)
            other=e.reverse.leftFace;name=other.letter if other.bounded else 'Outside'
            if not result or result[-1]!=name:result.append(name)
        if len(result)>1 and result[0]==result[-1]:result.pop()
        return result

def spaced_subset(values,n,minimum=0.0,ratio=None):
    # Try every starting position greedily; do not enumerate n-subsets.
    values=sorted(values,key=lambda pair:pair[1])
    for first in range(len(values)):
        picked=[]
        for obj,value in values[first:]:
            if picked and (value-picked[-1][1]<minimum or ratio is not None and value<ratio*picked[-1][1]):continue
            picked.append((obj,value))
            if len(picked)==n:return picked
    return None
