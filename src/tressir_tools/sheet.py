"""Connected multi-tip sheets, sharing the v3 editing and review infrastructure."""
import numpy as np
from collections import Counter
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt
from . import sheet_math as g
from .clump import signed_volume

SCHEMA='sword06c.sheet.v3'

def build_mesh(profile):
    if profile.get('schema')!=SCHEMA:raise ValueError('Expected '+SCHEMA)
    cfg=profile['design'];poly=g.outline(cfg);lo=poly.min(axis=0);hi=poly.max(axis=0);step=cfg['grid_step']
    grid=np.array([(x+(step/2 if row%2 else 0),y) for row,y in enumerate(np.arange(lo[1]+step/2,hi[1],step)) for x in np.arange(lo[0]+step/2,hi[0],step)])
    grid=grid[g.inside(grid,poly)];grid=grid[g.polyline_distance(grid,np.vstack([poly,poly[0]]))>step*.42]
    points=np.vstack([poly,grid]);v,_,f,*_=delaunay_2d_cdt([Vector(p) for p in points],[],[list(range(len(poly)))],1,1e-7,False)
    p=np.array(v);tri=np.array(f,int)
    if not g.inside(p[tri].mean(axis=1),poly).all():raise ValueError('The outline crosses itself near a notch; repair its Bezier controls.')
    cross=(p[tri[:,1],0]-p[tri[:,0],0])*(p[tri[:,2],1]-p[tri[:,0],1])-(p[tri[:,1],1]-p[tri[:,0],1])*(p[tri[:,2],0]-p[tri[:,0],0])
    tri[cross<0]=tri[cross<0][:,[0,2,1]]
    counts=Counter(tuple(sorted((int(a),int(b)))) for face in tri for a,b in zip(face,np.roll(face,-1)))
    boundary=[(int(a),int(b)) for face in tri for a,b in zip(face,np.roll(face,-1)) if counts[tuple(sorted((int(a),int(b))))]==1]
    front,back,_,_=g.map_surface(cfg,p,poly);n=len(p);verts=np.vstack([front,back])
    faces=tri[:,[0,2,1]].tolist()+(tri+n).tolist()
    for a,b in boundary:faces.extend([(a,b,b+n),(a,b+n,a+n)])
    faces=np.array(faces,int);uv=(p-lo)/(hi-lo);uv=np.vstack([uv,uv])[faces]
    if signed_volume(verts,faces)<0:faces=faces[:,[0,2,1]];uv=uv[:,[0,2,1]]
    sharp={tuple(sorted(e)) for e in boundary}|{tuple(sorted((a+n,b+n))) for a,b in boundary}
    return verts,faces,uv,{'smooth_faces':2*len(tri),'sharp_edges':sharp}

def guide_grid(profile,nu=5,nv=9):
    cfg=profile['design'];poly=g.outline(cfg);lo=poly.min(axis=0);hi=poly.max(axis=0)
    pad=(hi[0]-lo[0])*.08
    points=np.array([(x,t) for t in np.linspace(lo[1],hi[1],nv) for x in np.linspace(lo[0]-pad,hi[0]+pad,nu)])
    f,b,_,_=g.map_surface(cfg,points,poly,relief=False)
    return (f+b)/2
