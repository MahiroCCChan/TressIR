"""Math helpers reused unchanged from the connected-sheet experiment."""
import numpy as np

def bezier(points,t):
    p=np.asarray(points,float); t=np.asarray(t,float).reshape(-1,1)
    return (1-t)**3*p[0]+3*(1-t)**2*t*p[1]+3*(1-t)*t*t*p[2]+t**3*p[3]

def guide_path(guide,n=100):
    segments=guide.get('segments') or [guide['points']]
    return np.vstack([bezier(s,np.linspace(0,1,n)) for s in segments])

def outline(cfg):
    points=[];start=cfg['outline_start']
    for a,b,end in cfg['outline_cubics']:
        controls=np.array([start,a,b,end],float)
        n=max(3,int(np.linalg.norm(np.diff(controls,axis=0),axis=1).sum()/cfg['boundary_step']))
        points.extend(bezier(controls,np.linspace(0,1,n,endpoint=False)))
        start=end
    p=np.array(points)
    if np.sum(p[:,0]*np.roll(p[:,1],-1)-np.roll(p[:,0],-1)*p[:,1])<0:p=p[::-1]
    return p

def inside(points,polygon):
    p=np.atleast_2d(points);answer=np.zeros(len(p),bool)
    for a,b in zip(polygon,np.roll(polygon,-1,axis=0)):
        crosses=(a[1]>p[:,1])!=(b[1]>p[:,1])
        if abs(b[1]-a[1])>1e-12:
            x=(b[0]-a[0])*(p[:,1]-a[1])/(b[1]-a[1])+a[0]
            answer ^= crosses & (p[:,0]<x)
    return answer

def polyline_distance(points,path):
    p=np.atleast_2d(points);answer=np.full(len(p),np.inf)
    for a,b in zip(path[:-1],path[1:]):
        d=b-a;den=np.dot(d,d)
        if den<1e-12:continue
        t=np.clip((p-a)@d/den,0,1)
        answer=np.minimum(answer,np.linalg.norm(p-a-t[:,None]*d,axis=1))
    return answer

def bend(cfg,t):
    knots=np.asarray(cfg['shared_bend'],float);x=knots[:,0];y=knots[:,1]
    slopes=np.gradient(y,x)
    j=np.clip(np.searchsorted(x,t,side='right')-1,0,len(x)-2)
    dt=x[j+1]-x[j];s=np.clip((t-x[j])/dt,0,1)
    return (2*s**3-3*s**2+1)*y[j]+(s**3-2*s**2+s)*dt*slopes[j]+(-2*s**3+3*s**2)*y[j+1]+(s**3-s**2)*dt*slopes[j+1]

def map_surface(cfg,points,polygon,relief=True):
    p=np.asarray(points,float);x,t=p.T
    distance=polyline_distance(p,np.vstack([polygon,polygon[0]]))
    edge_fade=np.clip(distance/cfg['tip_relief_fade_distance'],0,1)
    edge_fade=edge_fade*edge_fade*(3-2*edge_fade)
    root_fade=np.clip(t/10,0,1);root_fade=root_fade*root_fade*(3-2*root_fade)
    bumps=np.zeros(len(p))
    if relief:
        for guide in cfg['ridge_guides']:
            line=guide_path(guide)
            d=polyline_distance(p,line)
            bumps+=guide['height']*np.exp(-(d/guide['radius'])**2)
        bumps*=edge_fade*root_fade
    # Smooth overall shallow crosswise crown; no width-derived thickness.
    crown=cfg['crosswise_crown']*(1-(x/30)**2)*np.sin(np.pi*np.clip(t/115,0,1))
    depth=bend(cfg,t)+crown
    thickness=cfg['edge_thickness']+(cfg['shell_thickness']-cfg['edge_thickness'])*edge_fade
    pl=cfg['placement'];sx=pl['x_unit_m'];sz=pl['height_unit_m'];sy=pl['depth_unit_m']
    front=np.column_stack([x*sx,-(depth+bumps+thickness*.5)*sy,-t*sz])
    back=np.column_stack([x*sx,-(depth-thickness*.5)*sy,-t*sz])
    return front,back,thickness,bumps
