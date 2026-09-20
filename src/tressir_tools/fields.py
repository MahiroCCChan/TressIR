"""Compact, regularized depth fields. Standard NumPy; no training or extra runtime."""
import numpy as np

CHANNELS=('center_x_m','center_y_m','half_depth_m','rotation_rad')

def knots_for(n):
    if not 4<=n<=64:raise ValueError('Use 4..64 spline coefficients; 12..24 is recommended for measured fields.')
    return np.r_[np.zeros(4),np.arange(1,n-3)/(n-3),np.ones(4)]

def basis(u,knots):
    u=np.asarray(u,float).reshape(-1);k=np.asarray(knots,float)
    if not np.isfinite(u).all() or (u<0).any() or (u>1).any():raise ValueError('Field u must lie in 0..1.')
    B=((u[:,None]>=k[:-1])&(u[:,None]<k[1:])).astype(float)
    for degree in range(1,4):
        out=np.zeros((len(u),B.shape[1]-1))
        for j in range(out.shape[1]):
            a=k[j+degree]-k[j];b=k[j+degree+1]-k[j+1]
            if a>0:out[:,j]+=(u-k[j])/a*B[:,j]
            if b>0:out[:,j]+=(k[j+degree+1]-u)/b*B[:,j+1]
        B=out
    B[u==1]=0;B[u==1,-1]=1
    return B

def _fit(u,y,n,smoothing,anchors):
    knots=knots_for(n);B=basis(u,knots);q=np.linspace(0,1,max(129,n*8))
    # The penalty approximates the integral of squared second derivative in
    # normalized u, rather than changing silently with measurement sample count.
    D=np.diff(basis(q,knots),n=2,axis=0)/(q[1]-q[0])**2
    R=D.T@D/len(D);weights=np.ones(len(u));C=basis([a[0] for a in anchors],knots) if anchors else None
    values=np.array([a[1] for a in anchors]) if anchors else None
    for _ in range(4):
        normal=B.T@(weights[:,None]*B)/weights.sum()+smoothing*R+np.eye(n)*1e-12
        rhs=B.T@(weights*y)/weights.sum()
        if anchors:
            A=np.block([[normal,C.T],[C,np.zeros((len(C),len(C)))]])
            coef=np.linalg.solve(A,np.r_[rhs,values])[:n]
        else:coef=np.linalg.solve(normal,rhs)
        residual=B@coef-y;mad=np.median(np.abs(residual-np.median(residual)))
        scale=max(1.4826*mad,float(np.ptp(y))*1e-5,1e-10)
        weights=np.minimum(1,2.5*scale/np.maximum(np.abs(residual),1e-30))
    return coef,{'rms':float(np.sqrt(np.mean((B@coef-y)**2))),'max':float(np.abs(B@coef-y).max())}

def fit_depth_field(samples,controls=18,smoothing=1e-5,anchors=None):
    """Fit center/half-depth/tilt together; unwrap tilt and fit depth in log space.

    samples: {u, center_y_m, half_depth_m, rotation_rad, optional center_x_m}.
    anchors: [{u, center_y_m: ..., ...}]; specified channels are exact constraints.
    """
    u=np.asarray(samples['u'],float)
    if u.ndim!=1 or len(u)<4 or not np.isfinite(u).all():raise ValueError('Need at least four finite measurement rows.')
    order=np.argsort(u);u=u[order]
    if u[0]<0 or u[-1]>1 or not (np.diff(u)>0).all():raise ValueError('Measurement u must be unique and in 0..1.')
    if not np.isfinite(smoothing) or smoothing<0:raise ValueError('Smoothing must be finite and non-negative.')
    coef={};residuals={};anchors=anchors or []
    for name in CHANNELS:
        y=np.asarray(samples.get(name,np.zeros(len(u))) if name=='center_x_m' else samples[name],float)
        if y.shape!=u.shape or not np.isfinite(y).all():raise ValueError('Invalid channel '+name)
        y=y[order]
        if name=='half_depth_m':
            if (y<=0).any():raise ValueError('Half-depth must be positive.')
            y=np.log(y)
        if name=='rotation_rad':y=np.unwrap(y*2)/2
        fixed=[]
        for a in anchors:
            if name not in a:continue
            value=float(a[name])
            if name=='half_depth_m':
                if value<=0:raise ValueError('Anchored half-depth must be positive.')
                value=np.log(value)
            if name=='rotation_rad':value+=np.round((np.interp(a['u'],u,y)-value)/np.pi)*np.pi
            fixed.append((float(a['u']),value))
        c,res=_fit(u,y,int(controls),smoothing,fixed);coef[name]=c.tolist();residuals[name]=res
    field={'schema':'sword06c.depth-field.v1','model':'affine-midplane-thickness','knots':knots_for(int(controls)).tolist(),
           'coefficients':coef,'half_depth_encoding':'log','anchors':anchors,
           'fit':{'measurements':len(u),'controls':int(controls),'smoothing':smoothing,'residuals':residuals,
                  'rotation_period_rad':float(np.pi),'method':'robust cubic B-spline with integrated second-derivative penalty'}}
    evaluate(field,np.linspace(0,1,257))
    return field

def evaluate(field,u):
    if field.get('schema')!='sword06c.depth-field.v1':raise ValueError('Unsupported depth-field schema.')
    k=np.asarray(field['knots'],float);n=len(k)-4
    if n<4 or not np.isfinite(k).all() or (np.diff(k)<0).any() or not np.allclose(k[:4],0) or not np.allclose(k[-4:],1):raise ValueError('Invalid clamped cubic knots.')
    B=basis(u,k);out={}
    for name in CHANNELS:
        c=np.asarray(field['coefficients'][name],float)
        if c.shape!=(n,) or not np.isfinite(c).all():raise ValueError('Invalid spline coefficients for '+name)
        y=B@c
        if name=='half_depth_m':y=np.exp(y)
        if not np.isfinite(y).all():raise ValueError('Depth field overflows.')
        out[name]=y
    # This sheet representation is a graph in local XZ. Near-vertical XY
    # sections belong in a clump/sweep representation, not an exploding tan().
    if (np.abs(np.cos(out['rotation_rad']))<.15).any():raise ValueError('Section tilt is too close to vertical for an XZ sheet; split/reorient this part.')
    return out

def set_control(field,index,values):
    import copy
    result=copy.deepcopy(field);n=len(field['knots'])-4
    if not 0<=index<n:raise ValueError('Depth control index is out of range.')
    for key,value in values.items():
        if key not in CHANNELS:raise ValueError('Unknown depth control channel.')
        value=float(value)
        if key=='half_depth_m':
            if value<=0:raise ValueError('Half-depth must be positive.')
            value=np.log(value)
        coef=np.array(result['coefficients'][key]);coef[index]=value
        constraints=[a for a in result.get('anchors',[]) if key in a]
        if constraints:
            C=basis([a['u'] for a in constraints],result['knots']);target=np.array([a[key] for a in constraints],float)
            if key=='half_depth_m':target=np.log(target)
            if key=='rotation_rad':target+=np.round((C@coef-target)/np.pi)*np.pi
            coef+=C.T@np.linalg.lstsq(C@C.T,target-C@coef,rcond=None)[0]
        result['coefficients'][key]=coef.tolist()
    evaluate(result,np.linspace(0,1,257))
    return result

def measure_sheet_field(vertices,faces,z_top,z_bottom,controls=18,smoothing=1e-5,samples=160):
    """Source-mesh measurement adapter; caller supplies the independently saved outline."""
    v=np.asarray(vertices,float);f=np.array([(p[0],p[i],p[i+1]) for p in faces for i in range(1,len(p)-1)],int)
    if z_top<=z_bottom:raise ValueError('Top must exceed bottom in local Z.')
    rows={key:[] for key in ('u',*CHANNELS)}
    for u in np.linspace(.001,.999,samples):
        z=z_top+(z_bottom-z_top)*u;points=[]
        for a,b in ((0,1),(1,2),(2,0)):
            p=v[f[:,a]];q=v[f[:,b]];dz=q[:,2]-p[:,2]
            m=(np.minimum(p[:,2],q[:,2])<=z)&(np.maximum(p[:,2],q[:,2])>=z)&(np.abs(dz)>1e-12)
            p=p[m];q=q[m];t=(z-p[:,2])/(q[:,2]-p[:,2]);points.extend((p+t[:,None]*(q-p))[:,:2])
        if len(points)<4:continue
        xy=np.unique(np.round(points,10),axis=0)
        if np.ptp(xy[:,0])<1e-7:continue
        cx=(xy[:,0].min()+xy[:,0].max())/2
        slope,cy=np.linalg.lstsq(np.column_stack([xy[:,0]-cx,np.ones(len(xy))]),xy[:,1],rcond=None)[0]
        residual=xy[:,1]-(slope*(xy[:,0]-cx)+cy);lo,hi=np.percentile(residual,[2,98]);cy+=(hi+lo)/2
        row=(u,cx,cy,max((hi-lo)/2,1e-5),np.arctan(slope))
        for key,value in zip(rows,row):rows[key].append(float(value))
    if len(rows['u'])<8:raise ValueError('Not enough valid measured sections; select one locally descending part.')
    return fit_depth_field(rows,controls,smoothing),rows
