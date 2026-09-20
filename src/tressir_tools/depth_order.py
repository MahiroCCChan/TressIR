"""Sampled orthographic depth ordering. Explicitly not an exact collision solver."""
import numpy as np

def _raster(v,f,axis,lo,hi,resolution):
    # Camera is on the negative side of the axis. Smaller depth is in front.
    other=[i for i in range(3) if i!=axis];p=v[:,other];step=(hi-lo)/resolution
    near=np.full((resolution,resolution),np.inf);far=np.full_like(near,-np.inf)
    for t in f:
        q=p[t];depth=v[t,axis];a,b,c=q;den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(den)<1e-18:continue
        lower=np.maximum(0,np.floor((q.min(axis=0)-lo)/step).astype(int));upper=np.minimum(resolution-1,np.floor((q.max(axis=0)-lo)/step).astype(int))
        if (upper<lower).any():continue
        X,Y=np.meshgrid(np.arange(lower[0],upper[0]+1),np.arange(lower[1],upper[1]+1));xy=lo+(np.stack([X,Y],axis=-1)+.5)*step
        A=((b[1]-c[1])*(xy[...,0]-c[0])+(c[0]-b[0])*(xy[...,1]-c[1]))/den
        B=((c[1]-a[1])*(xy[...,0]-c[0])+(a[0]-c[0])*(xy[...,1]-c[1]))/den;C=1-A-B
        mask=(A>=-1e-8)&(B>=-1e-8)&(C>=-1e-8);z=A*depth[0]+B*depth[1]+C*depth[2]
        iy,ix=Y[mask],X[mask];near[iy,ix]=np.minimum(near[iy,ix],z[mask]);far[iy,ix]=np.maximum(far[iy,ix],z[mask])
    return near,far

def compare(front_vertices,front_faces,back_vertices,back_faces,axis='Y',front_sign=-1,gap_m=.0002,resolution=72,bounds_2d_m=None):
    if axis not in 'XYZ' or len(axis)!=1 or front_sign not in (-1,1):raise ValueError('Choose an X/Y/Z axis and camera-side sign.')
    if not 8<=resolution<=256 or gap_m<0:raise ValueError('Invalid depth check resolution or gap.')
    k='XYZ'.index(axis);a=np.asarray(front_vertices,float).copy();b=np.asarray(back_vertices,float).copy()
    # Convert either camera side to the smaller-is-nearer convention.
    a[:,k]*=-front_sign;b[:,k]*=-front_sign;other=[i for i in range(3) if i!=k]
    lo=np.maximum(a[:,other].min(axis=0),b[:,other].min(axis=0));hi=np.minimum(a[:,other].max(axis=0),b[:,other].max(axis=0))
    if bounds_2d_m is not None:lo=np.maximum(lo,bounds_2d_m[0]);hi=np.minimum(hi,bounds_2d_m[1])
    if (hi<=lo).any():return {'overlap_samples':0,'violations':0,'status':'no_projected_overlap','resolution':resolution}
    an,af=_raster(a,np.asarray(front_faces),k,lo,hi,resolution);bn,bf=_raster(b,np.asarray(back_faces),k,lo,hi,resolution)
    mask=np.isfinite(an)&np.isfinite(bn);margin=bn[mask]-af[mask]-gap_m
    return {'overlap_samples':int(mask.sum()),'violations':int((margin< -1e-7).sum()),'min_clearance_m':float((margin+gap_m).min()) if len(margin) else None,
            'required_gap_m':gap_m,'status':'sampled' if len(margin) else 'no_sampled_overlap','resolution':resolution,
            'limits':'Tests projected overlap on a finite grid, including full front/back intervals; does not prove absence of all intersections.'}
