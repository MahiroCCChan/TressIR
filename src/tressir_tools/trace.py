"""LLM-authored image contours -> inspectable previews -> the same v4 parameters.

No segmentation model, colour thresholding, or remote inference is used here.
Coordinates are normalized to 0..1000 across the complete reference image.
"""
import base64,copy,hashlib,html,json,math,os,re,shutil
from pathlib import Path
import bpy
import numpy as np
from . import sheet_v4,fields,review,production,sheet_math as geometry

SCHEMA='sword06c.trace.v1'
MANIFEST_SCHEMA='sword06c.trace-preview.v1'
EVIDENCE=('observed','inferred','simplified')


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write(path,value):
    production._atomic(path,json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8'))


def _name(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,39}',value):
        raise ValueError('Use a short ASCII ID, e.g. A, P0, TIP_L; no path characters.')
    return value


def _xy(value):
    v=np.asarray(value,float)
    if v.shape!=(2,) or not np.isfinite(v).all() or (v<0).any() or (v>1000).any():
        raise ValueError('Coordinates must be [u,v], each 0..1000 across the complete image.')
    return v


def _read_source(document,trace_path):
    source=document['source'];path=(Path(trace_path).parent/source['image']).resolve()
    if _sha(path)!=source['sha256']:raise ValueError('Reference image changed. Prepare the source again, then review the trace.')
    pixels=review.read_pixels(path)
    if list(pixels.shape[1::-1])!=[source['width_px'],source['height_px']]:
        raise ValueError('Reference dimensions differ from the prepared image.')
    return path,pixels


def _projection(document):
    source=document['source'];c=document['calibration'];origin=_xy(c['origin_uv'])
    top,bottom=map(float,c['height_span_v']);height=float(c['height_mm'])
    if not 0<=top<bottom<=1000 or not .1<=height<=2000:raise ValueError('Invalid height calibration.')
    width,h=float(source['width_px']),float(source['height_px'])
    if width<=0 or h<=0:raise ValueError('Invalid image dimensions.')
    scale=np.array([width/h,1.])*height/(bottom-top)
    return origin,scale


def compile_candidate(document,candidate_id):
    """Compile one vector interpretation into a canonical, validated v4 profile."""
    if document.get('schema')!=SCHEMA:raise ValueError('Expected sword06c.trace.v1.')
    candidates=document['candidates']
    if not 1<=len(candidates)<=3:raise ValueError('Provide one candidate; at most three for a stated ambiguity.')
    ids=[_name(c['id']) for c in candidates]
    if len(ids)!=len(set(ids)):raise ValueError('Candidate IDs must be unique.')
    if candidate_id not in ids:raise ValueError('Unknown candidate ID: '+str(candidate_id))
    candidate=copy.deepcopy(candidates[ids.index(candidate_id)]);nodes=candidate['nodes']
    if not 3<=len(nodes)<=64:raise ValueError('Use 3..64 boundary nodes, without repeating the closing node.')
    node_ids=[_name(n['id']) for n in nodes]
    if len(node_ids)!=len(set(node_ids)):raise ValueError('Boundary node IDs must be unique.')
    origin,scale=_projection(document);points=[];segments=[];anchors=[]
    pixel_scale=np.array([document['source']['width_px'],document['source']['height_px']])/1000
    for i,node in enumerate(nodes):
        following=nodes[(i+1)%len(nodes)];start=_xy(node['point']);end=_xy(following['point'])
        if np.linalg.norm((end-start)*pixel_scale)<.01:raise ValueError('Consecutive boundary nodes coincide.')
        kind=node.get('kind','boundary')
        if kind not in ('boundary','tip','notch','extremum'):raise ValueError('Unknown boundary node kind.')
        basis=node.get('out_evidence','observed')
        if basis not in EVIDENCE:raise ValueError('out_evidence must be observed, inferred or simplified.')
        # Missing handles mean a straight segment, represented as a cubic.
        a=_xy(node['out']) if 'out' in node else start+(end-start)/3
        b=_xy(following['in']) if 'in' in following else start+2*(end-start)/3
        controls=np.array([start,a,b,end]);length=np.linalg.norm(np.diff(controls,axis=0)*pixel_scale,axis=1).sum()
        count=max(2,min(512,int(math.ceil(length/2))))
        sampled=geometry.bezier(controls,np.linspace(0,1,count,endpoint=False))
        points.extend(sampled);segments.append({'from':node['id'],'to':following['id'],'basis':basis,'points_uv':np.vstack([sampled,end]).tolist()})
        anchors.append({'id':node['id'],'kind':kind,'xy':((start-origin)*scale).tolist()})
    if len(points)>4096:raise ValueError('Curve sampling budget exceeded; simplify the control polygon.')
    points=np.asarray(points);mm=(points-origin)*scale
    p=sheet_v4.new_profile(mm.tolist(),anchors,candidate.get('name',candidate_id),document['part_id'])
    for note in candidate.get('notes',[]):
        if note.get('basis') not in EVIDENCE or not isinstance(note.get('text'),str):raise ValueError('Notes need basis and text.')
        if not set(note.get('at',[])).issubset(set(node_ids)):raise ValueError('A note refers to an unknown node.')
    depth=candidate.get('depth')
    if depth is None:
        height=document['calibration']['height_mm']
        depth={'basis':'default','note':'Editable initial bend and thickness; not measured from the image.',
               'stations':[{'u':u,'center_y_mm':-height*.12*u*u,'half_depth_mm':height*.008,'tilt_deg':0} for u in (0,.33,.67,1)]}
    if depth.get('basis') not in ('default','estimated'):raise ValueError('Image-trace depth is default or estimated, not measured ground truth.')
    rows=depth['stations']
    if not 4<=len(rows)<=24:raise ValueError('Use 4..24 depth stations, including u=0 and u=1.')
    if rows[0]['u']!=0 or rows[-1]['u']!=1:raise ValueError('Depth stations must include u=0 and u=1.')
    samples={'u':[r['u'] for r in rows], 'center_y_m':[r['center_y_mm']/1000 for r in rows],
             'half_depth_m':[r['half_depth_mm']/1000 for r in rows], 'rotation_rad':[math.radians(r.get('tilt_deg',0)) for r in rows]}
    p['depth_field']=fields.fit_depth_field(samples,min(len(rows),18),1e-5)
    for ridge in candidate.get('ridges',[]):
        _name(ridge['id']);control=np.array([_xy(x) for x in ridge['points']])
        if control.shape!=(4,2) or not 0<=ridge['height_mm']<=20 or not .1<=ridge['radius_mm']<=100:
            raise ValueError('A ridge needs four cubic points, positive radius and height 0..20 mm.')
        p['design']['ridge_guides'].append({'points':((control-origin)*scale).tolist(),'height':ridge['height_mm'],'radius':ridge['radius_mm']})
    p['history']=[{'operation':'llm-authored-image-trace','candidate':candidate_id,'source_sha256':document['source']['sha256'],
                   'calibration':copy.deepcopy(document['calibration']),'notes':candidate.get('notes',[]),'depth_basis':depth['basis'],'depth_note':depth.get('note','')}]
    p['trace_review']={'candidate':candidate_id,'source':copy.deepcopy(document['source']),'nodes':nodes,'segments':segments,
                       'notes':candidate.get('notes',[]),'depth':depth,'calibration':copy.deepcopy(document['calibration'])}
    # Canonical coordinates, including any orientation normalization, are used
    # by BOTH preview drawing and the unchanged v4 generator.
    poly,_,_=sheet_v4._outline(p)
    v,f,uv,special=sheet_v4.build_mesh(p)
    ridge_paths=[(geometry.guide_path(r)/scale+origin).tolist() for r in p['design']['ridge_guides']]
    return p,{'points_uv':(poly/scale+origin).tolist(),'ridges_uv':ridge_paths,'quality':special['quality'],'vertices':len(v),'triangles':len(f)}


def _line(pixels,a,b,color,width=2):
    a=np.asarray(a);b=np.asarray(b);n=max(1,int(np.linalg.norm(b-a)*1.5))
    q=np.rint(a+np.linspace(0,1,n+1)[:,None]*(b-a)).astype(int)
    for dx in range(-width,width+1):
        for dy in range(-width,width+1):
            if dx*dx+dy*dy>width*width:continue
            x=q[:,0]+dx;y=q[:,1]+dy;valid=(x>=0)&(y>=0)&(x<pixels.shape[1])&(y<pixels.shape[0])
            pixels[y[valid],x[valid]]=color


def _opaque(pixels):
    p=pixels.copy();p[:,:,:3]=p[:,:,:3]*p[:,:,3:]+(1-p[:,:,3:]);p[:,:,3]=1
    return p


def _preview_png(pixels,p,meta,path):
    h,w=pixels.shape[:2];factor=min(1,1600/max(w,h));H,W=max(1,int(h*factor)),max(1,int(w*factor))
    base=_opaque(pixels)[(np.arange(H)/factor).astype(int)[:,None],(np.arange(W)/factor).astype(int)]
    xy=np.asarray(meta['points_uv'])*[W/1000,H/1000];overlay=base.copy();shape=np.ones_like(base)
    lo=np.maximum(0,np.floor(xy.min(axis=0)-28).astype(int));hi=np.minimum([W,H],np.ceil(xy.max(axis=0)+28).astype(int))
    X,Y=np.meshgrid(np.arange(lo[0],hi[0]),np.arange(lo[1],hi[1]));inside=geometry.inside(np.column_stack([X.ravel()+.5,Y.ravel()+.5]),xy).reshape(X.shape)
    region=shape[lo[1]:hi[1],lo[0]:hi[0]];region[inside]=(.76,.88,.9,1)
    for segment in p['trace_review']['segments']:
        color=(.0,.40,.37,1) if segment['basis']=='observed' else (.8,.30,.025,1)
        points=np.asarray(segment['points_uv'])*[W/1000,H/1000]
        for a,b in zip(points[:-1],points[1:]):
            _line(overlay,a,b,color,2);_line(shape,a,b,color,2)
    for node in p['trace_review']['nodes']:
        pos=_xy(node['point'])*[W/1000,H/1000]
        for canvas in (overlay,shape):
            for key in ('in','out'):
                if key in node:_line(canvas,pos,_xy(node[key])*[W/1000,H/1000],(.58,.55,.65,1),1)
            _line(canvas,pos,pos,(.65,.05,.30,1),4)
            x,y=np.rint(pos+[6,-10]).astype(int)
            if 0<=x<W-100 and 0<=y<H-16:review.draw_label(canvas,x,y,node['id'],1,(.45,.01,.12,1))
    for ridge in meta['ridges_uv']:
        points=np.asarray(ridge)*[W/1000,H/1000]
        for a,b in zip(points[:-1],points[1:]):
            _line(overlay,a,b,(.45,.18,.65,1),1);_line(shape,a,b,(.45,.18,.65,1),1)
    review.save_pixels(path.with_name(path.stem+'-overlay.png'),overlay)
    tiles=[x[lo[1]:hi[1],lo[0]:hi[0]] for x in (base,overlay,shape)];th,tw=tiles[0].shape[:2]
    board=np.ones((th+40,tw*3+32,4),np.float32);board[:,:,:3]=.97
    for i,tile in enumerate(tiles):
        x=i*(tw+16);board[40:,x:x+tw]=tile;review.draw_label(board,x+5,12,('SOURCE','OVERLAY','PARAMETERS')[i],2,(.12,.17,.21,1))
    review.save_pixels(path,board)


def _svg(p,meta,image_data,focus):
    e=html.escape;nodes=p['trace_review']['nodes'];body=[]
    body.append(f'<image class="source" x="0" y="0" width="1000" height="1000" preserveAspectRatio="none" href="{image_data}"/>')
    points=' '.join(f'{x:.5f},{y:.5f}' for x,y in meta['points_uv'])
    body.append(f'<polygon class="fill" points="{points}" fill="#29b5a6" opacity=".12"/>')
    for s in p['trace_review']['segments']:
        points=' '.join(f'{x:.5f},{y:.5f}' for x,y in s['points_uv'])
        color='#00796b' if s['basis']=='observed' else '#dd791b'
        body.append(f'<polyline class="outline" points="{points}" fill="none" stroke="{color}" stroke-width="2" vector-effect="non-scaling-stroke"/>')
    for node in nodes:
        x,y=node['point']
        for key in ('in','out'):
            if key in node:
                a,b=node[key];body.append(f'<line class="controls" x1="{x}" y1="{y}" x2="{a}" y2="{b}" stroke="#918b9e" vector-effect="non-scaling-stroke"/>')
                body.append(f'<circle class="controls" cx="{a}" cy="{b}" r="2" fill="#918b9e"/>')
        body.append(f'<g class="controls"><circle cx="{x}" cy="{y}" r="3" fill="#ae2252"/><text x="{x+5}" y="{y-5}" fill="#832443" font-size="11">{e(node["id"])}</text></g>')
    for ridge in meta['ridges_uv']:
        points=' '.join(f'{x:.5f},{y:.5f}' for x,y in ridge)
        body.append(f'<polyline class="outline" points="{points}" fill="none" stroke="#804cab" stroke-dasharray="5 3" stroke-width="1.5" vector-effect="non-scaling-stroke"/>')
    return f'<svg role="img" viewBox="{focus}" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">'+''.join(body)+'</svg>'


def _html_page(compiled,image_path,pixels,manifest):
    suffix=image_path.suffix.lower();mime='image/png' if suffix=='.png' else 'image/jpeg'
    image_data=f'data:{mime};base64,'+base64.b64encode(image_path.read_bytes()).decode('ascii')
    all_points=np.vstack([m['points_uv'] for _,m in compiled]);lo=np.maximum(0,all_points.min(axis=0)-30);hi=np.minimum(1000,all_points.max(axis=0)+30)
    focus=' '.join(str(v) for v in (*lo,*(hi-lo)));ratio=(hi[0]-lo[0])*pixels.shape[1]/((hi[1]-lo[1])*pixels.shape[0])
    cards=[];options=[];e=html.escape
    for p,m in compiled:
        trace=p['trace_review'];cid=trace['candidate'];options.append(f'<option value="{cid}">{cid}</option>')
        notes=''.join(f'<li><b>{e(n["basis"])} · {e(", ".join(n.get("at",[])))}</b> — {e(n["text"])}</li>' for n in trace['notes']) or '<li>未提供局部解释。请核对轮廓后补充需要说明的处理。</li>'
        warnings='；'.join(m['quality'].get('warnings',[])) or '当前拓扑检查通过'
        cards.append(f'<article data-id="{cid}"><div class="picture" style="aspect-ratio:{ratio}">{_svg(p,m,image_data,focus)}</div><aside><h2>候选 {cid}</h2><p>{e(warnings)}</p><p>{m["vertices"]} 顶点 · {m["triangles"]} 三角面</p><h3>LLM 的判断说明</h3><ul>{notes}</ul><h3>三维深度</h3><p>{e(trace["depth"]["basis"])}：{e(trace["depth"].get("note",""))}</p><p class="muted">这张图核对二维轮廓；深度和辅助曲面修形还需在 Blender 看多视角。</p><p><a href="{cid}.profile.json" download>生成用参数 JSON</a> · <a href="{cid}-review.png">三栏核对 PNG</a></p><p class="muted">参数指纹：{manifest["candidates"][cid]["sha256"][:16]}</p></aside></article>')
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>TressIR · 轮廓核对</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f4f1;color:#263235;font:15px/1.65 system-ui,sans-serif}header,main{max-width:1240px;margin:auto;padding:22px}h1{font-size:25px;margin:0}header p{margin:6px 0;color:#627172}.toolbar{display:flex;gap:20px;align-items:center;flex-wrap:wrap;padding:15px 0;border-top:1px solid #cbd4d0}select{font:inherit;padding:5px 12px}article{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(280px,1fr);gap:30px;background:white;padding:24px;border:1px solid #dce2df}.picture{width:100%;max-height:78vh;background:white}svg{width:100%;height:100%}aside{overflow-wrap:anywhere}h2{margin-top:0}h3{font-size:15px;margin:24px 0 6px}ul{padding-left:18px}li{margin:12px 0}.muted{font-size:13px;color:#627172}a{color:#00796b}body.no-controls .controls{display:none}body.source-only .outline,body.source-only .fill,body.source-only .controls{display:none}body.shape-only .source{display:none}@media(max-width:700px){article{grid-template-columns:1fr}}
</style><header><h1>轮廓核对 · 同一份参数进入三维</h1><p>绿色：观察到的边界；橙色：推测或简化。颜色表示 LLM 自述，不是自动测得的准确率。</p><div class="toolbar"><label>候选 <select id="candidate">'''+''.join(options)+'''</select></label><label>显示 <select id="mode"><option value="overlay">叠图</option><option value="source-only">原图</option><option value="shape-only">提取轮廓</option></select></label><label><input type="checkbox" id="controls" checked>控制点</label><label>原图透明度 <input id="opacity" type="range" min="0" max="1" step=".05" value="1"></label></div></header><main>'''+''.join(cards)+'''</main><script>
const candidate=document.querySelector('#candidate');function refresh(){document.querySelectorAll('article').forEach(a=>a.style.display=a.dataset.id===candidate.value?'grid':'none');document.body.className=document.querySelector('#mode').value+(document.querySelector('#controls').checked?'':' no-controls');document.querySelectorAll('.source').forEach(x=>x.style.opacity=document.querySelector('#opacity').value)}document.querySelectorAll('select,input').forEach(x=>x.addEventListener('input',refresh));refresh();
</script></html>'''


def prepare(image_path,output_dir,part_id='PART01',height_mm=100):
    """Copy a reference, make its coordinate grid and an empty LLM input file."""
    image_path=Path(image_path).resolve();out=Path(output_dir).resolve()
    if image_path.suffix.lower() not in ('.png','.jpg','.jpeg'):raise ValueError('Use a PNG or JPEG reference.')
    pixels=review.read_pixels(image_path);h,w=pixels.shape[:2];digest=_sha(image_path)
    if not .1<=float(height_mm)<=2000:raise ValueError('Height must be 0.1..2000 mm.')
    production._id(part_id)
    if (out/'trace.json').exists():raise ValueError('This trace folder already contains work. Choose a new folder or edit its existing trace.json.')
    out.mkdir(parents=True,exist_ok=True);source=out/('reference'+image_path.suffix.lower())
    if source!=image_path:shutil.copy2(image_path,source)
    p={'schema':SCHEMA,'part_id':part_id,'source':{'image':source.name,'width_px':w,'height_px':h,'sha256':digest},
       'calibration':{'origin_uv':[500,0],'height_span_v':[0,1000],'height_mm':float(height_mm)},'candidates':[]}
    _write(out/'trace.json',p)
    grid=_opaque(pixels)
    for i in range(11):
        x=min(w-1,int(i*w/10));y=min(h-1,int(i*h/10));color=(.7,.53,.78,1)
        _line(grid,[x,0],[x,h-1],color,1);_line(grid,[0,y],[w-1,y],color,1)
        if i<10:review.draw_label(grid,min(x+4,w-60),5,str(i*100),2,(.35,.05,.42,1));review.draw_label(grid,5,min(y+6,h-20),str(i*100),2,(.35,.05,.42,1))
    review.save_pixels(out/'coordinate-grid.png',grid)
    prompt=Path(__file__).with_name('LLM_TRACE_PROMPT.txt')
    if not prompt.exists():prompt=Path(__file__).resolve().parents[1]/'LLM_TRACE_PROMPT.txt'
    if prompt.exists():shutil.copy2(prompt,out/'LLM_TRACE_PROMPT.txt')
    return {'trace':str(out/'trace.json'),'grid':str(out/'coordinate-grid.png'),'source':str(source)}


def preview(trace_path,output_dir=None):
    """Compile once and write profiles, overlays and a manifest. No scene meshes change."""
    path=Path(trace_path).resolve();document=json.loads(path.read_text(encoding='utf-8-sig'));image_path,pixels=_read_source(document,path)
    production._id(document['part_id']);digest=_sha(path)
    if not document.get('candidates'):raise ValueError('The LLM has not filled candidates in trace.json yet.')
    compiled=[compile_candidate(document,c['id']) for c in document['candidates']]
    out=Path(output_dir).resolve() if output_dir else path.parent/'reviews'/digest[:16]
    out.mkdir(parents=True,exist_ok=True)
    manifest={'schema':MANIFEST_SCHEMA,'trace_path':os.path.relpath(path,out),'trace_sha256':digest,
              'source_path':os.path.relpath(image_path,out),'source_sha256':_sha(image_path),'part_id':document['part_id'],'candidates':{}}
    for p,meta in compiled:
        cid=p['trace_review']['candidate'];profile=out/(cid+'.profile.json');_write(profile,p)
        manifest['candidates'][cid]={'path':profile.name,'sha256':_sha(profile),'review_png':cid+'-review.png','quality':meta['quality']}
        _preview_png(pixels,p,meta,out/(cid+'-review.png'))
    production._atomic(out/'review.html',_html_page(compiled,image_path,pixels,manifest).encode('utf-8'))
    # Manifest last: an incomplete export cannot be used by the generation entry.
    _write(out/'preview_manifest.json',manifest)
    return {'manifest':str(out/'preview_manifest.json'),'html':str(out/'review.html'),'candidates':list(manifest['candidates'])}


def generate(context,manifest_path,candidate_id,project_root):
    """Build precisely the reviewed profile. A modified input requires a new preview."""
    path=Path(manifest_path).resolve();m=json.loads(path.read_text(encoding='utf-8'))
    if m.get('schema')!=MANIFEST_SCHEMA:raise ValueError('Expected a trace preview manifest.')
    for file_key,hash_key in [('trace_path','trace_sha256'),('source_path','source_sha256')]:
        if _sha(path.parent/m[file_key])!=m[hash_key]:raise ValueError('Trace or reference changed after preview. Run Preview again before generation.')
    _name(candidate_id)
    if candidate_id not in m['candidates']:raise ValueError('Candidate is not present in this preview.')
    entry=m['candidates'][candidate_id];profile_path=(path.parent/entry['path']).resolve()
    if not profile_path.is_relative_to(path.parent) or _sha(profile_path)!=entry['sha256']:raise ValueError('Reviewed profile changed; regenerate the preview.')
    p=json.loads(profile_path.read_text(encoding='utf-8'));obj=production.build_candidate(context,p,m['part_id'],project_root)
    obj['s06c_trace_preview']=str(path);obj['s06c_trace_profile_sha256']=entry['sha256'];obj['s06c_trace_candidate']=candidate_id
    return obj
