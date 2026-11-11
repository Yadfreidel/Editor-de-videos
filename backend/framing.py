"""Local face detection and spatial tracking. Never identifies the active speaker."""
import math
from fastapi import HTTPException,Request
from pydantic import BaseModel,Field

def unit(value,default=.5):
    try:return max(0.,min(1.,float(value))) if math.isfinite(float(value)) else default
    except (ValueError,TypeError):return default

def track_samples(samples,width,height):
    tracks=[]
    for sample in samples:
        t=sample['time'];assigned=set()
        for box in sorted(sample['boxes'],key=lambda b:b[0]):
            x,y,w,h=box;cx=(x+w/2)/width;cy=(y+h/2)/height
            options=[(abs(tr['cx']-cx)+abs(tr['cy']-cy),tr) for tr in tracks if tr['id'] not in assigned]
            distance,tr=min(options,key=lambda a:a[0]) if options else (1,None)
            if distance>.28:tr=None
            if tr is None:
                tr={'id':str(len(tracks)+1),'label':'Rostro '+str(len(tracks)+1),'cx':cx,'cy':cy,'frames':[],'detections':0,'lastSeen':t};tracks.append(tr)
            cropw=min(width,height*9/16);offset=unit((cx*width-cropw/2)/max(1,width-cropw))
            previous=tr['frames'][-1]['x'] if tr['frames'] else offset
            smooth=previous+max(-.1,min(.1,(offset-previous)*.35))
            tr.update(cx=cx,cy=cy,lastSeen=t,detections=tr['detections']+1)
            tr['frames'].append({'t':round(t,3),'x':round(smooth,5),'cx':round(cx,5),'visible':True});assigned.add(tr['id'])
        for tr in tracks:
            if tr['id'] not in assigned and tr['frames']:tr['frames'].append({'t':round(t,3),'x':tr['frames'][-1]['x'],'cx':tr['frames'][-1]['cx'],'visible':False})
    return [tr for tr in tracks if tr['detections']>=2]

def path_expression(points,default=.5):
    clean=sorted({round(max(0,float(p['t'])),3):unit(p.get('x'),default) for p in points if 't' in p}.items())[:240]
    if not clean:return str(unit(default))
    if len(clean)==1:return str(clean[0][1])
    def tree(lo,hi):
        if hi-lo==1:
            t,x=clean[lo];nt,nx=clean[lo+1]
            return f'({x}+({nx-x})*max(0,min(1,(t-{t})/{max(.001,nt-t)})))'
        mid=(lo+hi)//2
        return f'if(lt(t,{clean[mid][0]}),{tree(lo,mid)},{tree(mid,hi)})'
    return tree(0,len(clean)-1)

def crop_points(framing,side=None):
    chosen=str(framing.get('person' if side is None else side,'1' if side!='right' else '2'))
    track=next((tr for tr in framing.get('tracks',[]) if str(tr['id'])==chosen),None)
    points=[{'t':p['t'],'x':p.get('x',.5)} for p in (track or {}).get('frames',[])]
    corrections=framing.get('corrections',[])
    if corrections:points=[p for p in points if p['t']<min(float(x['t']) for x in corrections)]+[{'t':float(x['t']),'x':unit(x.get('x'))} for x in corrections]
    return points

def video_graph(scene,width,height):
    framing=scene.get('framing') or {};mode=framing.get('mode','manual');zoom=max(1,min(3,float(scene.get('zoom',1))));x=unit(scene.get('x',.5))
    if mode=='split':
        half=width//2
        def side_expr(side,default):
            chosen=str(framing.get(side,'1' if side=='left' else '2'));tr=next((tr for tr in framing.get('tracks',[]) if str(tr['id'])==chosen),None)
            if tr and not framing.get('corrections'):
                sw=max(1,framing.get('sourceWidth',width));sh=max(1,framing.get('sourceHeight',height));cropw=min(sw,sh*(half/height))
                return path_expression([{'t':p['t'],'x':unit((p.get('cx',.5)*sw-cropw/2)/max(1,sw-cropw))} for p in tr['frames']],default)
            return path_expression(crop_points(framing,side),framing.get(side+'X',default))
        l=side_expr('left',.25);r=side_expr('right',.75)
        return f"[0:v]split=2[ls][rs];[ls]scale={half}:{height}:force_original_aspect_ratio=increase,crop={half}:{height}:x='(iw-ow)*({l})':y='(ih-oh)/2',setsar=1[lv];[rs]scale={half}:{height}:force_original_aspect_ratio=increase,crop={half}:{height}:x='(iw-ow)*({r})':y='(ih-oh)/2',setsar=1[rv];[lv][rv]hstack=inputs=2,fps=30[basev]"
    expression=path_expression(crop_points(framing),x) if mode=='follow' or framing.get('corrections') else str(x)
    return f"[0:v]scale={int(width*zoom)//2*2}:{int(height*zoom)//2*2}:force_original_aspect_ratio=increase,crop={width}:{height}:x='(iw-ow)*({expression})':y='(ih-oh)/2',setsar=1,fps=30[basev]"

def install_framing(app,c,protect):
    class Detect(BaseModel):
        projectId:str
        sceneIndex:int=Field(default=0,ge=0)
    def detect_work(jid,payload):
        try:import cv2
        except ImportError:raise ValueError('Instala opencv-python-headless. El encuadre manual sigue disponible.')
        capture=cv2.VideoCapture(str(c.file_path(payload['asset'])))
        if not capture.isOpened():raise ValueError('No se pudo abrir el video para analizar rostros')
        classifier=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
        eyes=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_eye_tree_eyeglasses.xml')
        if classifier.empty():raise ValueError('No está disponible el clasificador local de rostros.')
        sw=int(capture.get(cv2.CAP_PROP_FRAME_WIDTH));sh=int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total=capture.get(cv2.CAP_PROP_FRAME_COUNT)/max(1,capture.get(cv2.CAP_PROP_FPS))
        start=payload['start'];duration=min(payload['duration'],max(0,total-start));samples=[];size=min(640,sw)
        try:
            for n in range(max(1,math.ceil(duration*2))):
                c.check_cancel(jid);t=n/2;capture.set(cv2.CAP_PROP_POS_MSEC,(start+t)*1000);success,frame=capture.read()
                if not success:break
                frame=cv2.resize(frame,(size,max(1,round(sh*size/sw))));gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
                boxes=classifier.detectMultiScale(gray,scaleFactor=1.1,minNeighbors=6,minSize=(30,30))
                verified=[]
                for box in boxes:
                    x,y,w,h=map(int,box);region=gray[y:y+int(h*.65),x:x+w];region=cv2.resize(region,(w*2,max(1,int(h*.65)*2)))
                    if not eyes.empty() and len(eyes.detectMultiScale(region,scaleFactor=1.1,minNeighbors=2,minSize=(8,8)))>0:verified.append([x,y,w,h])
                samples.append({'time':t,'boxes':verified})
                c.update_job(jid,progress=int((n+1)/max(1,duration*2)*95))
            tracks=track_samples(samples,size,max(1,round(sh*size/sw)))
            return {'tracks':tracks,'sourceWidth':sw,'sourceHeight':sh,'sampleInterval':.5,'samples':len(samples),'asset':payload['asset'],'start':start,'duration':duration,'speakerIdentified':False,'notice':'Detección espacial, no identificación del hablante. Con audio mezclado no se asocia voz y rostro: elige la persona. Se conserva el encuadre si desaparece; revisa el render.' if tracks else 'No se detectaron rostros estables. Usa Manual o define ambos encuadres en Pantalla dividida.'}
        finally:capture.release()
    @app.post('/api/framing/analyze')
    def analyze(req:Detect,request:Request):
        p=protect(request,c.get('projects',req.projectId))
        if req.sceneIndex>=len(p['scenes']):raise HTTPException(404,'Escena no encontrada')
        s=p['scenes'][req.sceneIndex]
        if not s.get('asset'):raise HTTPException(422,'Carga un video para analizar rostros. Manual siempre está disponible.')
        return c.production_enqueue('framing',{'projectId':p['id'],'clientId':p.get('clientId',''),'sceneId':s['id'],'asset':s['asset'],'start':s.get('start',0),'duration':s['duration']},detect_work)
    c.production_workers['framing']=detect_work
