"""Item-aware tutorial environment creation; no model calls."""
from pathlib import Path
import hashlib, importlib, json, sys, math

ROOT=Path(__file__).resolve().parent

def verify_loaded_sources():
    fingerprints=json.loads((ROOT/'source_fingerprints.json').read_text())
    for relative,expected in fingerprints.items():
        if relative.startswith('generation_source/'):continue
        path=ROOT/relative
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise RuntimeError(f'Frozen source checksum mismatch: {relative}')
        name=path.stem
        # Model-client modules are not needed for local reconstruction checks.
        # Still check their source files, and their origin if already loaded.
        if name in ('geo_agent','geo_agent_annotation') and name not in sys.modules:
            continue
        module=importlib.import_module(name)
        if Path(module.__file__).resolve()!=path.resolve():
            raise RuntimeError(f'{name} was imported from {module.__file__}; restart kernel and load this package first')

def geometry_sha256(m):
    graph={'bounds':[float(v) for v in m.bounds],
           'vertices':[{'id':v.num,'x':float(v.p.x),'y':float(v.p.y)} for v in m.vertices],
           'regions':[{'label':f.letter,'vertex_ids':list(dict.fromkeys(v.num for v in f.vertices))} for f in m.faces if f.bounded]}
    return hashlib.sha256(json.dumps(graph,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def make_verified_env(setup,item,addressing='descriptor'):
    settings=item.get('generator_settings',{})
    kwargs=dict(num_regions=item['region_count'],seed=item['diagram_seed'],
                maxX=settings.get('width',1),maxY=settings.get('height',1),
                structure_complexity=item['structure_complexity'])
    if setup=='annotation':
        from geo_env_annotation import AnnotationEnv
        env=AnnotationEnv(addressing=addressing,**kwargs)
    elif setup in ('compositional','no_tools'):
        from geo_env import Env
        env=Env(**kwargs)
    else:raise ValueError(setup)
    actual=geometry_sha256(env.res_map)
    if actual!=item['geometry_sha256']:
        # Cross-platform floating-point arithmetic can differ in the last bits.
        # Never relax vertex identities, labeled boundaries, or topology.
        expected=json.loads((ROOT/'dataset'/item['graph_path']).read_text())
        actual_regions={f.letter:list(dict.fromkeys(v.num for v in f.vertices))
                        for f in env.res_map.faces if f.bounded}
        expected_regions={f['label']:f['vertex_ids'] for f in expected['regions']}
        actual_vertices={v.num:(float(v.p.x),float(v.p.y)) for v in env.res_map.vertices}
        expected_vertices={v['id']:(v['x'],v['y']) for v in expected['vertices']}
        same_coordinates=(actual_vertices.keys()==expected_vertices.keys() and
            all(math.isfinite(a) and math.isfinite(b) and abs(a-b)<=1e-12
                for k in actual_vertices for a,b in zip(actual_vertices[k],expected_vertices[k])))
        same_bounds=(len(env.res_map.bounds)==len(expected['bounds']) and
            all(math.isfinite(float(a)) and math.isfinite(float(b)) and abs(float(a)-float(b))<=1e-12
                for a,b in zip(env.res_map.bounds,expected['bounds'])))
        if actual_regions!=expected_regions or not same_coordinates or not same_bounds:
            raise RuntimeError(f'Diagram reconstruction mismatch for {item["item_id"]}: {actual}')
    return env
