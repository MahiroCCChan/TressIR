"""Editable clumps with independent section axes and rotation. No bpy dependency."""
import copy
import math
from collections import Counter
import numpy as np

SCHEMA='sword06c.clump.v3'

def default_edits(n=12):
    return [{'t':float(t),'offset_m':[0.,0.,0.],'axis_scale':[1.,1.],'angle_offset_rad':0.} for t in np.linspace(0,1,n)]

def smooth(a,passes=3):
    a=np.array(a,float).copy();first=a[0].copy();last=a[-1].copy()
    for _ in range(passes):
        if a.ndim==1:a=np.convolve(np.pad(a,(2,2),mode='edge'),[1/16,4/16,6/16,4/16,1/16],mode='valid')
        else:a=np.column_stack([smooth(a[:,j],1) for j in range(a.shape[1])])
    a[0]=first;a[-1]=last
    return a

def interpolate(x,y,t):
    """Local cubic Hermite interpolation; user controls, not 128 independent edits."""
    x=np.asarray(x,float);y=np.asarray(y,float);t=np.asarray(t,float)
    if len(x)==1:return np.broadcast_to(y[0],t.shape+y.shape[1:]).copy()
    m=np.gradient(y,x,axis=0);i=np.clip(np.searchsorted(x,t,side='right')-1,0,len(x)-2)
    h=x[i+1]-x[i];u=np.clip((t-x[i])/h,0,1)
    if y.ndim>1:u=u[:,None];h=h[:,None]
    return (2*u**3-3*u*u+1)*y[i]+(u**3-2*u*u+u)*h*m[i]+(-2*u**3+3*u*u)*y[i+1]+(u**3-u*u)*h*m[i+1]

def validate(profile):
    if profile.get('schema')!=SCHEMA:raise ValueError('Expected '+SCHEMA)
    samples=profile['base_samples']
    if len(samples)<8:raise ValueError('Need at least 8 section samples.')
    a=np.array([r['axes_m'] for r in samples]);c=np.array([r['center_m'] for r in samples]);ang=np.array([r['angle_rad'] for r in samples])
    if a.shape!=(len(samples),2) or c.shape!=(len(samples),3):raise ValueError('Malformed section samples.')
    if not np.isfinite(np.concatenate([a.ravel(),c.ravel(),ang])).all():raise ValueError('Non-finite section data.')
    if (a<=0).any():raise ValueError('Non-tip section axes must be positive.')
    if not (np.diff(c[:,2])<0).all():raise ValueError('Sections must descend along local Z.')
    if profile.get('handedness',1) not in (-1,1):raise ValueError('Invalid section handedness.')
    n=profile.get('section_vertices',48)
    if not isinstance(n,int) or n<8 or n%4:raise ValueError('Section vertex count must be a multiple of four, >=8.')
    ts=[e['t'] for e in profile['edit_controls']]
    if len(ts)<2 or ts[0]!=0 or ts[-1]!=1 or not (np.diff(ts)>0).all():raise ValueError('Edit controls must increase from t=0 to t=1.')
    if any(min(e['axis_scale'])<=0 for e in profile['edit_controls']):raise ValueError('Axis scales must be positive.')
    for e in profile['edit_controls']:
        if not np.isfinite([*e['offset_m'],*e['axis_scale'],e['angle_offset_rad']]).all():raise ValueError('Non-finite edit control.')
    if not np.isfinite([*profile['tip_m'],*profile.get('root_cap_m',c[0])]).all():raise ValueError('Non-finite cap.')
    st=np.array([r['t'] for r in samples])
    if st[0]!=0 or st[-1]>1 or not (np.diff(st)>0).all():raise ValueError('Sample t values must increase within 0..1.')
    if profile.get('end_mode','point') not in ('point','flat'):raise ValueError('Unsupported end mode.')

def evaluated_samples(profile):
    validate(profile);rows=profile['base_samples'];t=np.array([r['t'] for r in rows])
    centers=np.array([r['center_m'] for r in rows]);axes=np.array([r['axes_m'] for r in rows]);angles=np.unwrap([r['angle_rad'] for r in rows])
    edits=profile['edit_controls'];et=[e['t'] for e in edits]
    centers+=interpolate(et,[e['offset_m'] for e in edits],t)
    axes*=np.exp(interpolate(et,np.log([e['axis_scale'] for e in edits]),t))
    angles+=interpolate(et,[e['angle_offset_rad'] for e in edits],t)
    if not (np.diff(centers[:,2])<0).all():raise ValueError('This edit folds section heights; reduce the Z offset or use a deformation guide.')
    return centers,axes,angles

def build_mesh(profile):
    centers,axes,angles=evaluated_samples(profile);nr=len(centers);nc=profile['section_vertices']
    theta=np.arange(nc)*2*np.pi/nc
    u=np.cos(theta);v=np.sign(np.sin(theta))*np.abs(np.sin(theta))**profile.get('section_power',1.)
    if 'section_points' in profile:
        section=np.asarray(profile['section_points'],float)
        if section.shape!=(nc,2) or not np.isfinite(section).all():raise ValueError('Invalid normalized section points.')
        u,v=section.T
    handed=profile.get('handedness',1)
    result=[]
    for c,(a,b),angle in zip(centers,axes,angles):
        ca,sa=np.cos(angle),np.sin(angle)
        result.append(c+np.column_stack([a*u*ca-b*v*sa*handed,a*u*sa+b*v*ca*handed,np.zeros(nc)]))
    tip=np.array(profile['tip_m'],float)+np.array(profile['edit_controls'][-1]['offset_m'])
    root=np.array(profile.get('root_cap_m',profile['base_samples'][0]['center_m']),float)+np.array(profile['edit_controls'][0]['offset_m'])
    if profile.get('end_mode','point')=='point' and tip[2]>=centers[-1,2]:raise ValueError('Pointed tip must stay below the last ring.')
    verts=np.vstack(result+[tip[None,:],root[None,:]])
    faces=[];uv=[]
    for i in range(nr-1):
        for j in range(nc):
            k=(j+1)%nc;a=i*nc+j;b=(i+1)*nc+j;c=(i+1)*nc+k;d=i*nc+k
            faces.extend([(a,b,c),(a,c,d)])
            uv.extend([[(j/nc,i/nr),(j/nc,(i+1)/nr),((j+1)/nc,(i+1)/nr)],[(j/nc,i/nr),((j+1)/nc,(i+1)/nr),((j+1)/nc,i/nr)]])
    for j in range(nc):
        k=(j+1)%nc;a=(nr-1)*nc+j;b=(nr-1)*nc+k
        faces.extend([(a,nr*nc,b),(nr*nc+1,j,k)])
        uv.extend([[(j/nc,(nr-1)/nr),((j+.5)/nc,1),((j+1)/nc,(nr-1)/nr)],[(.5,.5),((u[j]+1)/2,(v[j]+1)/2),((u[k]+1)/2,(v[k]+1)/2)]])
    faces=np.array(faces,int);uv=np.array(uv)
    if signed_volume(verts,faces)<0:faces=faces[:,[0,2,1]];uv=uv[:,[0,2,1]]
    return verts,faces,uv

def signed_volume(v,f):
    v=np.asarray(v);f=np.asarray(f);tri=v[f]-v.mean(axis=0)
    return float(np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2])).sum()/6)

def mesh_checks(v,f):
    v=np.asarray(v);f=np.asarray(f);edges=Counter(tuple(sorted((int(a),int(b)))) for face in f for a,b in zip(face,np.roll(face,-1)))
    tri=v[f];area=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)*.5
    return {'vertices':len(v),'triangles':len(f),'closed_edges':all(n==2 for n in edges.values()),'degenerate_triangles':int((area<1e-15).sum()),'volume_m3':signed_volume(v,f)}

def recover_rings(vertices,section_vertices=48,matrix_world=None,source_name='',provenance=''):
    """Recover the ellipse parameters from a stored ring mesh without fitting the source MMD."""
    vertices=np.asarray(vertices,float);nr=(len(vertices)-2)//section_vertices
    if nr*section_vertices+2!=len(vertices):raise ValueError('Not a ring mesh with a tip and root cap.')
    theta=np.arange(section_vertices)*2*np.pi/section_vertices
    A=np.column_stack([np.ones(section_vertices),np.cos(theta),np.sin(theta)])
    rows=[];errors=[];signs=[]
    for i in range(nr):
        r=vertices[i*section_vertices:(i+1)*section_vertices];coef=np.linalg.lstsq(A,r,rcond=None)[0]
        c,U,V=coef;a=np.linalg.norm(U[:2]);b=np.linalg.norm(V[:2]);angle=math.atan2(U[1],U[0])
        if max(abs(U[2]),abs(V[2]))>1e-6:raise ValueError('Ring is not horizontal in object-local coordinates.')
        if abs(np.dot(U[:2],V[:2]))>max(a*b*1e-3,1e-12):raise ValueError('Ellipse axes are not orthogonal.')
        sign=1 if np.linalg.det(np.array([U[:2],V[:2]]))>=0 else -1;signs.append(sign)
        rows.append({'t':i/nr,'center_m':c.tolist(),'axes_m':[float(a),float(b)],'angle_rad':float(angle)})
        errors.append(float(np.linalg.norm(A@coef-r,axis=1).max()))
    if len(set(signs))!=1:raise ValueError('Section handedness changes along the mesh.')
    p={'schema':SCHEMA,'name':source_name,'units':'meters','frame':'object-local XY sections, descending local Z','matrix_world':matrix_world or np.eye(4).tolist(),'section_vertices':section_vertices,'section_power':1.,'handedness':signs[0],'base_samples':rows,'tip_m':vertices[-2].tolist(),'root_cap_m':vertices[-1].tolist(),'edit_controls':default_edits(),'history':[{'operation':'recover-parameters-from-existing-generated-v07','source_object':source_name,'source_record':provenance}],'deformers':[]}
    rebuilt,_,_=build_mesh(p);error=float(np.linalg.norm(rebuilt-vertices,axis=1).max())
    if error>2e-6:raise ValueError(f'Ellipse recovery error is too large: {error} meters.')
    return p,{'max_vertex_error_m':error,'section_fit_error_m':max(errors),'ring_count':nr,'section_vertices':section_vertices}

def from_legacy(data,matrix_world=None):
    c=np.array(data['centerline'],float)*.001;w=np.array(data['half_width'])*.001;d=np.array(data['half_depth'])*.001
    end_mode=data.get('end_mode','point');count=len(c) if end_mode=='flat' else len(c)-1
    p={'schema':SCHEMA,'name':data.get('part_id','LegacyClump'),'units':'meters','frame':'object-local XY sections, descending local Z','matrix_world':matrix_world or np.eye(4).tolist(),'section_vertices':48,'section_power':1.4,'handedness':1,'base_samples':[{'t':i/(len(c)-1),'center_m':x.tolist(),'axes_m':[float(w[i]),float(d[i])],'angle_rad':0.} for i,x in enumerate(c[:-1])],'tip_m':c[-1].tolist(),'root_cap_m':c[0].tolist(),'edit_controls':default_edits(),'history':[{'operation':'legacy-thin-clump-import','source_provenance':data.get('provenance','unknown')}],'deformers':[]}
    p['end_mode']=end_mode
    p['base_samples']=[{'t':i/(len(c)-1),'center_m':c[i].tolist(),'axes_m':[float(w[i]),float(d[i])],'angle_rad':0.} for i in range(count)]
    if 'section' in data:p['section_points']=data['section'];p['section_vertices']=len(data['section'])
    return p

def fit_reference(vertices,faces,matrix_world=None,name='SourceFit',rings=128,smooth_passes=3):
    """Measure plane intersections, fit support ellipses, smooth high-level parameters."""
    v=np.asarray(vertices,float);tri=np.array([t for f in faces for t in [(f[0],f[j],f[j+1]) for j in range(1,len(f)-1)]],int)
    zmax=float(v[:,2].max());zmin=float(v[:,2].min());height=zmax-zmin
    if height<=1e-6:raise ValueError('Reference must have a nonzero local Z span.')
    directions=np.column_stack([np.cos(np.arange(16)*np.pi/16),np.sin(np.arange(16)*np.pi/16)])
    Qdesign=np.column_stack([directions[:,0]**2,2*directions[:,0]*directions[:,1],directions[:,1]**2])
    values=[];valid=[];Z=np.linspace(zmax,zmin,rings+1)[:-1]
    for index,z in enumerate(Z):
        zp=min(z,zmax-height*1e-5);points=[]
        for a,b in [(0,1),(1,2),(2,0)]:
            p=v[tri[:,a]];q=v[tri[:,b]];dz=q[:,2]-p[:,2]
            mask=(np.minimum(p[:,2],q[:,2])<=zp)&(np.maximum(p[:,2],q[:,2])>=zp)&(np.abs(dz)>1e-12)
            p=p[mask];q=q[mask];u=(zp-p[:,2])/(q[:,2]-p[:,2]);points.extend((p+u[:,None]*(q-p))[:,:2])
        if len(points)<3:continue
        xy=np.unique(np.round(np.asarray(points),9),axis=0)
        if len(xy)<3:continue
        projected=xy@directions.T;mn=projected.min(axis=0);mx=projected.max(axis=0)
        center=np.linalg.lstsq(directions,(mn+mx)/2,rcond=None)[0]
        q=np.linalg.lstsq(Qdesign,((mx-mn)/2)**2,rcond=None)[0]
        eigen,axes=np.linalg.eigh([[q[0],q[1]],[q[1],q[2]]]);eigen=np.maximum(eigen,1e-10)
        angle=math.atan2(axes[1,1],axes[0,1]);a,b=np.sqrt(eigen[::-1])
        values.append([center[0],center[1],math.log(a),math.log(b),angle]);valid.append(index)
    if len(valid)<8:raise ValueError('Not enough valid source sections; choose a single descending clump.')
    values=np.asarray(values);values[:,4]=np.unwrap(values[:,4]*2)/2
    full=np.column_stack([np.interp(np.arange(rings),valid,values[:,j]) for j in range(5)])
    full=smooth(full,smooth_passes)
    bottom=v[np.isclose(v[:,2],zmin,atol=height*1e-5)].mean(axis=0)
    rows=[{'t':i/rings,'center_m':[float(a[0]),float(a[1]),float(z)],'axes_m':np.exp(a[2:4]).tolist(),'angle_rad':float(a[4])} for i,(a,z) in enumerate(zip(full,Z))]
    p={'schema':SCHEMA,'name':name,'units':'meters','frame':'object-local XY sections, descending local Z','matrix_world':matrix_world or np.eye(4).tolist(),'section_vertices':48,'section_power':1.,'handedness':1,'base_samples':rows,'tip_m':bottom.tolist(),'root_cap_m':rows[0]['center_m'],'edit_controls':default_edits(),'history':[{'operation':'source-mesh-measured-reference','method':'16-direction horizontal section supports -> general ellipse -> longitudinal parameter smoothing','smooth_passes':smooth_passes,'source_vertices':len(v),'source_faces':len(faces)}],'deformers':[]}
    return p
