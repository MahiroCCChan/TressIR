"""Separate geometric validity from region-aware quality diagnostics."""
from collections import Counter,defaultdict
import numpy as np

def analyze(vertices,triangles,regions=None):
    v=np.asarray(vertices,float);f=np.asarray(triangles,int)
    if v.ndim!=2 or v.shape[1]!=3 or not np.isfinite(v).all():raise ValueError('Vertices must be finite 3D coordinates.')
    if f.ndim!=2 or f.shape[1]!=3 or f.min()<0 or f.max()>=len(v):raise ValueError('Invalid triangle indices.')
    tri=v[f];cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);double=np.linalg.norm(cross,axis=1)
    length=np.stack([np.linalg.norm(tri[:,i]-tri[:,(i+1)%3],axis=1) for i in range(3)],axis=1)
    ratio=np.divide(length.max(axis=1)**2,double,out=np.full(len(f),np.inf),where=double>1e-30)
    edges=defaultdict(list)
    for i,t in enumerate(f):
        for a,b in zip(t,np.roll(t,-1)):edges[tuple(sorted((int(a),int(b))))].append((i,a<b))
    duplicate=sum(n-1 for n in Counter(tuple(sorted(t)) for t in f).values() if n>1)
    boundary=sum(len(p)==1 for p in edges.values());multiple=sum(len(p)>2 for p in edges.values())
    winding=int(sum(len(p)==2 and p[0][1]==p[1][1] for p in edges.values()))
    degenerate=int((double<2e-15).sum());tags=np.asarray(regions if regions is not None else np.zeros(len(f),int))
    if tags.shape!=(len(f),):raise ValueError('Face region count mismatch.')
    zones={}
    for index,label in ((0,'body'),(1,'rim'),(2,'feature')):
        r=ratio[(tags==index)&np.isfinite(ratio)]
        zones[label]={'triangles':int((tags==index).sum()),'aspect_max':float(r.max()) if len(r) else 0.,'aspect_p95':float(np.percentile(r,95)) if len(r) else 0.,'aspect_over_50':int((r>50).sum())}
    normal=cross/np.maximum(double[:,None],1e-30);angles=[]
    for p in edges.values():
        if len(p)==2:
            a,b=p[0][0],p[1][0]
            if tags[a]==tags[b]==0:angles.append(float(np.degrees(np.arccos(np.clip(normal[a]@normal[b],-1,1)))))
    blocked=[]
    for value,label in ((duplicate,'duplicate_faces'),(boundary,'unexpected_open_edges'),(multiple,'non_manifold_edges'),(winding,'inconsistent_winding'),(degenerate,'degenerate_triangles')):
        if value:blocked.append(label)
    warnings=[]
    if zones['body']['aspect_max']>50:warnings.append('Body contains slender triangles; inspect their locations.')
    if angles and np.percentile(angles,95)>45:warnings.append('Large body normal changes; inspect curvature and feature classification.')
    return {'vertices':len(v),'triangles':len(f),'duplicate_faces':duplicate,'boundary_edges':boundary,'non_manifold_edges':multiple,'inconsistent_winding_edges':winding,
            'degenerate_triangles':degenerate,'regions':zones,'body_dihedral_p95_degrees':float(np.percentile(angles,95)) if angles else 0.,
            'blocking':blocked,'warnings':warnings,'valid':not blocked,
            'limits':'Closed-shell validity and region-aware diagnostics; not an artistic score or a complete self-intersection/animation test.'}

def constrained_fair(values,points,triangles,locked,strength=.1,max_delta=.001,iterations=120):
    """Data fidelity + squared graph Laplacian, solved only on unlocked variables."""
    y=np.asarray(values,float);p=np.asarray(points,float);f=np.asarray(triangles,int);locked=np.asarray(locked,bool)
    if strength<=0 or locked.all():return y.copy()
    edge=np.unique(np.sort(np.vstack([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1),axis=0);a,b=edge.T
    w=1/np.maximum(np.linalg.norm(p[a]-p[b],axis=1),1e-12)
    degree=np.bincount(np.r_[a,b],weights=np.r_[w,w],minlength=len(p));scale=np.median(degree[degree>0]);w/=scale;degree/=scale
    def L(x):return degree*x-np.bincount(np.r_[a,b],weights=np.r_[w*x[b],w*x[a]],minlength=len(x))
    def A(x):return x+strength*L(L(x))
    fixed=np.where(locked,y,0);rhs=y-A(fixed);rhs[locked]=0
    x=np.where(locked,0,y);r=rhs-A(x);r[locked]=0;d=r.copy();rr=r@r
    for _ in range(iterations):
        if rr<1e-24:break
        q=A(d);q[locked]=0;den=d@q
        if den<=0:break
        alpha=rr/den;x+=alpha*d;r-=alpha*q;next_rr=r@r
        if next_rr<1e-24:break
        d=r+(next_rr/rr)*d;rr=next_rr
    result=x+fixed;result=y+np.clip(result-y,-max_delta,max_delta);result[locked]=y[locked]
    return result
