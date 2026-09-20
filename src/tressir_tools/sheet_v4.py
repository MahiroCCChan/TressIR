"""Feature-preserving connected sheets with compact depth fields and bounded refinement."""
import copy
from collections import Counter
import numpy as np
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt
from . import sheet_math as g,fields,quality
from .clump import signed_volume

SCHEMA='sword06c.sheet.v4'
DEFAULTS={'target_edge_m':.002,'max_refinement_passes':4,'max_vertices':16000,'target_aspect':15.,
          'edge_thickness_m':.00012,'edge_fade_m':.003,'fairing_strength':.12,'fairing_max_displacement_m':.0005}

def new_profile(outline_mm,anchors=None,name='Sheet',part_id=None):
    """Minimal vector input in millimeters; the canonical JSON supplies all defaults."""
    xy=np.asarray(outline_mm,float);height=float(np.ptp(xy[:,1]))
    cfg={'outline_polyline':xy.tolist(),'ridge_guides':[],'shared_bend':[[float(xy[:,1].min()),0.],[float(xy[:,1].max()),0.]],
         'shell_thickness':.8,'edge_thickness':.12,'tip_relief_fade_distance':3.,'crosswise_crown':0.,'grid_step':2.,'boundary_step':1.,
         'placement':{'root_m':[0,0,0],'x_unit_m':.001,'height_unit_m':.001,'depth_unit_m':.001}}
    p={'schema':SCHEMA,'name':name,'units':'meters','matrix_world':np.eye(4).tolist(),'design':cfg,'anchors':anchors or [],'history':[{'operation':'vector_outline_authored','height_mm':height}],'deformers':[]}
    if part_id:p['part_id']=part_id
    return upgrade(p)

def upgrade(profile):
    p=copy.deepcopy(profile)
    if p.get('schema') not in (SCHEMA,'sword06c.sheet.v3'):raise ValueError('Expected a v3/v4 sheet profile.')
    if p['schema']!=SCHEMA:
        p['schema']=SCHEMA;p.setdefault('history',[]).append({'operation':'upgrade-sheet-generator-v4','preserves_design_input':True})
    settings={**DEFAULTS,**p.get('generation',{})};p['generation']=settings
    cfg=p['design'];p.setdefault('anchors',[{'id':'tip_'+str(i+1),'kind':'tip','xy':v} for i,v in enumerate(cfg.get('declared_tip_points',[]))])
    p.setdefault('branches',[])
    if 'depth_measurements' in p:
        options=p.pop('depth_fit',{});p['depth_field']=fields.fit_depth_field(p.pop('depth_measurements'),**options)
        p.setdefault('history',[]).append({'operation':'control_fit','fit':p['depth_field']['fit']})
    return p

def _outline(profile):
    cfg=profile['design'];poly=np.asarray(cfg['outline_polyline'],float) if 'outline_polyline' in cfg else g.outline(cfg)
    if len(poly)>1 and np.linalg.norm(poly[0]-poly[-1])<1e-10:poly=poly[:-1]
    if poly.ndim!=2 or poly.shape[1]!=2 or len(poly)<3 or not np.isfinite(poly).all():raise ValueError('Invalid closed vector outline.')
    pl=cfg['placement'];scale=np.array([pl['x_unit_m'],pl['height_unit_m']],float)
    if (scale<=0).any():raise ValueError('Outline units must be positive.')
    metric=poly*scale
    if (np.linalg.norm(np.roll(metric,-1,axis=0)-metric,axis=1)<1e-9).any():raise ValueError('Outline contains duplicate adjacent points.')
    area=np.sum(metric[:,0]*np.roll(metric[:,1],-1)-np.roll(metric[:,0],-1)*metric[:,1])
    if abs(area)<1e-12:raise ValueError('Outline has no usable area.')
    if area<0:poly=poly[::-1];metric=metric[::-1]
    # Reject self-crossing vector input rather than silently unioning it and losing a notch.
    for i,(a,b) in enumerate(zip(metric,np.roll(metric,-1,axis=0))):
        c=metric[i+2:];d=np.roll(metric,-1,axis=0)[i+2:]
        if i==0 and len(c):c=c[:-1];d=d[:-1]
        if not len(c):continue
        cross=lambda u,v:u[...,0]*v[...,1]-u[...,1]*v[...,0]
        e=b-a;other=d-c;den=cross(e,other);valid=np.abs(den)>1e-16
        s=np.zeros(len(c));t=s.copy();s[valid]=cross(c[valid]-a,other[valid])/den[valid];t[valid]=cross(c[valid]-a,e)/den[valid]
        if np.any(valid&(s>-1e-8)&(s<1+1e-8)&(t>-1e-8)&(t<1+1e-8)):raise ValueError('Outline self-intersects; repair its vector segments before generation.')
    ids=set()
    for anchor in profile.get('anchors',[]):
        if anchor['id'] in ids:raise ValueError('Anchor IDs must be unique.')
        ids.add(anchor['id'])
        if anchor.get('kind') not in ('tip','notch','extremum','boundary'):raise ValueError('Unknown anchor kind.')
        if np.linalg.norm(metric-np.array(anchor['xy'])*scale,axis=1).min()>1e-7:raise ValueError('Anchor '+anchor['id']+' must coincide with a vector-outline vertex/Bezier junction.')
    return poly,metric,scale

def _sample_boundary(poly,edge):
    points=[]
    for a,b in zip(poly,np.roll(poly,-1,axis=0)):
        count=max(1,int(np.ceil(np.linalg.norm(b-a)/edge)))
        points.extend(a+np.arange(count)[:,None]/count*(b-a))
    return np.asarray(points)

def _triangulate(profile,polygon):
    s=profile['generation'];edge=float(s['target_edge_m']);cap=int(s['max_vertices'])
    if not 1e-5<=edge<=.1 or not 100<=cap<=100000:raise ValueError('Invalid target edge length or vertex budget.')
    boundary=_sample_boundary(polygon,edge);lo=polygon.min(axis=0);hi=polygon.max(axis=0)
    nx=int(np.ceil((hi[0]-lo[0])/edge));ny=int(np.ceil((hi[1]-lo[1])/edge))
    if nx*ny>cap*3:raise ValueError('Target edge length is too small for this outline; increase it or the explicit vertex budget.')
    grid=np.array([(x+(edge/2 if row%2 else 0),y) for row,y in enumerate(np.arange(lo[1]+edge/2,hi[1],edge)) for x in np.arange(lo[0]+edge/2,hi[0],edge)])
    if not len(grid):grid=polygon.mean(axis=0)[None,:]
    grid=grid[g.inside(grid,polygon)]
    grid=grid[g.polyline_distance(grid,np.vstack([polygon,polygon[0]]))>edge*.28]
    added=0;passes=0
    for iteration in range(int(s['max_refinement_passes'])+1):
        points=np.vstack([boundary,grid]);span=max(np.ptp(polygon,axis=0));origin=polygon.mean(axis=0)
        if len(points)>cap:raise ValueError('Triangulation exceeds the explicit vertex budget.')
        verts,_,faces,*_=delaunay_2d_cdt([Vector(x) for x in (points-origin)/span],[],[list(range(len(boundary)))],1,1e-9,False)
        p=np.asarray(verts)*span+origin;tri=np.asarray(faces,int)
        if tri.ndim!=2 or tri.shape[1]!=3:raise ValueError('Constrained triangulation did not produce triangles.')
        if not g.inside(p[tri].mean(axis=1),polygon).all():raise ValueError('Triangulation leaked outside the outline.')
        a,b,c=p[tri[:,0]],p[tri[:,1]],p[tri[:,2]];cross=(b[:,0]-a[:,0])*(c[:,1]-a[:,1])-(b[:,1]-a[:,1])*(c[:,0]-a[:,0])
        tri[cross<0]=tri[cross<0][:,[0,2,1]]
        # Exact boundary coordinates matter for semantic anchors, not float32 CDT output.
        for value in boundary:
            j=np.argmin(np.linalg.norm(p-value,axis=1))
            if np.linalg.norm(p[j]-value)>span*2e-6:raise ValueError('Triangulation lost a constrained boundary point.')
            p[j]=value
        if iteration==int(s['max_refinement_passes']):break
        a,b,c=p[tri[:,0]],p[tri[:,1]],p[tri[:,2]]
        e=np.stack([np.linalg.norm(b-a,axis=1),np.linalg.norm(c-b,axis=1),np.linalg.norm(a-c,axis=1)],axis=1)
        area=np.abs((b[:,0]-a[:,0])*(c[:,1]-a[:,1])-(b[:,1]-a[:,1])*(c[:,0]-a[:,0]))
        bad=(e.max(axis=1)**2/np.maximum(area,1e-30)>s['target_aspect'])|(e.max(axis=1)>edge*1.8)
        if not bad.any():break
        candidates=[]
        for idx in np.flatnonzero(bad):
            t=tri[idx];q=p[t];ab=q[1]-q[0];ac=q[2]-q[0]
            try:center=q[0]+np.linalg.solve(2*np.array([ab,ac]),[ab@ab,ac@ac])
            except np.linalg.LinAlgError:continue
            if not g.inside(center[None,:],polygon)[0]:continue
            if g.polyline_distance(center[None,:],np.vstack([polygon,polygon[0]]))[0]<edge*.12:continue
            if np.linalg.norm(p-center,axis=1).min()<edge*.12:continue
            if candidates and np.linalg.norm(np.array(candidates)-center,axis=1).min()<edge*.2:continue
            candidates.append(center)
        if not candidates:break
        if len(points)+len(candidates)>cap:break
        grid=np.vstack([grid,candidates]);added+=len(candidates);passes+=1
    counts=Counter(tuple(sorted((int(a),int(b)))) for t in tri for a,b in zip(t,np.roll(t,-1)))
    rim=[(int(a),int(b)) for t in tri for a,b in zip(t,np.roll(t,-1)) if counts[tuple(sorted((int(a),int(b))))]==1]
    return p,tri,rim,{'refinement_passes':passes,'inserted_interior_points':added,'boundary_vertices':len(boundary),
                     'limits':'Bounded constrained refinement preserves exact vector corners; acute anchors may retain slender feature triangles.'}

def surfaces(profile,points,poly):
    cfg=profile['design'];s=profile['generation'];pl=cfg['placement'];metric_scale=np.array([pl['x_unit_m'],pl['height_unit_m']])
    front,back,_,bumps=g.map_surface(cfg,points,poly)
    distance=g.polyline_distance(points*metric_scale,np.vstack([poly,poly[0]])*metric_scale)
    fade=np.clip(distance/s['edge_fade_m'],0,1);fade=fade*fade*(3-2*fade)
    edge_half=s['edge_thickness_m']/2
    if edge_half<=0 or s['edge_fade_m']<=0:raise ValueError('Rim thickness and fade distance must be positive.')
    u=np.clip((points[:,1]-poly[:,1].min())/np.ptp(poly[:,1]),0,1)
    if 'depth_field' in profile:
        d=fields.evaluate(profile['depth_field'],u)
        mid=d['center_y_m']+np.tan(d['rotation_rad'])*(front[:,0]-d['center_x_m'])
        half=edge_half+(np.maximum(d['half_depth_m'],edge_half)-edge_half)*fade
        front[:,1]=mid-half-bumps*pl['depth_unit_m'];back[:,1]=mid+half
    else:
        # Preserve the authored v3 ridge front, while replacing edge thickness
        # with a physical, independently specified taper.
        mid=(front[:,1]+back[:,1])/2;half=np.maximum((back[:,1]-front[:,1])/2,edge_half)
        half=edge_half+(half-edge_half)*fade;front[:,1]=mid-half;back[:,1]=mid+half
    anchors={a['id']:a for a in profile.get('anchors',[])}
    for branch in profile.get('branches',[]):
        if branch['anchor_id'] not in anchors:raise ValueError('A local branch refers to an unknown anchor.')
        anchor=anchors[branch['anchor_id']];tip=np.asarray(anchor['xy']);tip_u=(tip[1]-poly[:,1].min())/np.ptp(poly[:,1]);start=branch['start_u']
        if not 0<=start<tip_u or branch['radius_m']<=0:raise ValueError('A branch must start above its tip and have a positive radius.')
        fade_u=np.clip((u-start)/(tip_u-start),0,1);fade_u=fade_u*fade_u*(3-2*fade_u)
        dx=front[:,0]-tip[0]*metric_scale[0];weight=fade_u*np.exp(-(dx/branch['radius_m'])**2)
        tilt=float(branch.get('tilt_rad',0))
        if abs(tilt)>1.2:raise ValueError('Local sheet tilt exceeds its graph representation.')
        delta=weight*(branch.get('offset_y_m',0)+np.tan(tilt)*dx)
        front[:,1]+=delta;back[:,1]+=delta
    return front,back

def build_mesh(profile):
    p=upgrade(profile);poly,metric,scale=_outline(p);xy,tri,rim,refinement=_triangulate(p,metric);points=xy/scale
    front,back=surfaces(p,points,poly);n=len(points);s=p['generation'];boundary_ids=np.unique(np.asarray(rim).ravel())
    locked=np.zeros(n,bool);locked[boundary_ids]=True;feature=np.zeros(n,bool);anchor_errors={}
    for anchor in p['anchors']:
        dist=np.linalg.norm(xy-np.asarray(anchor['xy'])*scale,axis=1);index=np.argmin(dist)
        anchor_errors[anchor['id']]=float(dist[index]);feature|=dist<s['target_edge_m']*1.6
        if dist[index]>1e-8:raise ValueError('A protected anchor moved during generation.')
    for guide in p['design'].get('ridge_guides',[]):
        ridge=g.guide_path(guide)*scale;locked|=g.polyline_distance(xy,ridge)<s['target_edge_m']*.45
    locked|=feature
    if s['fairing_strength']>0:
        mid=(front[:,1]+back[:,1])/2;half=(back[:,1]-front[:,1])/2
        if (half<=0).any():raise ValueError('Front/back sheet branches cross before fairing.')
        mid=quality.constrained_fair(mid,xy,tri,locked,s['fairing_strength'],s['fairing_max_displacement_m'])
        # Fair only the mid-surface; existing positive local thickness is preserved.
        front[:,1]=mid-half;back[:,1]=mid+half
    verts=np.vstack([front,back]);faces=tri[:,[0,2,1]].tolist()+(tri+n).tolist()
    for a,b in rim:faces.extend([(a,b,b+n),(a,b+n,a+n)])
    f=np.asarray(faces,int);uv=(points-poly.min(axis=0))/np.ptp(poly,axis=0);uv=np.vstack([uv,uv])[f]
    if signed_volume(verts,f)<0:f=f[:,[0,2,1]];uv=uv[:,[0,2,1]]
    regions=np.r_[np.where(feature[tri].any(axis=1),2,0),np.where(feature[tri].any(axis=1),2,0),np.ones(2*len(rim),int)]
    report=quality.analyze(verts,f,regions);report['anchors']=anchor_errors;report['refinement']=refinement
    if not report['valid']:raise ValueError('Generated shell failed validity: '+', '.join(report['blocking']))
    sharp={tuple(sorted(e)) for e in rim}|{tuple(sorted((a+n,b+n))) for a,b in rim}
    return verts,f,uv,{'smooth_faces':2*len(tri),'sharp_edges':sharp,'regions':regions.tolist(),'quality':report}

def guide_grid(profile,nu=5,nv=9):
    p=upgrade(profile);poly,_,_=_outline(p);lo=poly.min(axis=0);hi=poly.max(axis=0);pad=(hi[0]-lo[0])*.08
    points=np.array([(x,t) for t in np.linspace(lo[1],hi[1],nv) for x in np.linspace(lo[0]-pad,hi[0]+pad,nu)])
    f,b=surfaces(p,points,poly)
    return (f+b)/2
