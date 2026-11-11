"""Idempotent CSV import, explicit association, and within-account observations."""
import csv
import io
import json
import hashlib
from collections import defaultdict
from fastapi import Request,HTTPException,UploadFile,File
from pydantic import BaseModel,Field,ValidationError,ConfigDict

class Publication(BaseModel):
    model_config=ConfigDict(allow_inf_nan=False)
    project:str
    variant:str='A'
    platform:str
    period:str
    account:str=''
    publicationId:str=''
    publishedAt:str=''
    window:str=''
    views:float|None=Field(default=None,ge=0)
    average:float|None=Field(default=None,ge=0)
    watched:float|None=Field(default=None,ge=0,le=100)
    interactions:float|None=Field(default=None,ge=0)
    followers:float|None=None
    hookType:str=''
    duration:float|None=Field(default=None,ge=0)
    template:str=''
    format:str='9:16'

def key_for(row):
    base={k:row.get(k,'') for k in ('project','variant','platform','period','account','publicationId','publishedAt','window')}
    if row.get('publicationId'):
        base={k:row.get(k,'') for k in ('platform','account','publicationId')};base['measurementWindow']=row.get('window') or row.get('period','')
    if not row.get('publicationId') and not row.get('publishedAt'):
        base.update({k:float(row[k]) if row.get(k) is not None else None for k in ('views','average','watched','interactions','followers')})
    return hashlib.sha256(json.dumps(base,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def install_analytics(app,c,protect,visible):
    def normalized(raw,request,strict=True):
        clean={k:(None if v=='' and k in ('views','average','watched','interactions','followers','duration') else v) for k,v in raw.items() if k in Publication.model_fields}
        try:row=Publication(**clean).model_dump()
        except ValidationError as e:raise HTTPException(422,str(e))
        try:p=protect(request,c.get('projects',row['project']))
        except HTTPException as e:
            if e.status_code==403 or strict:raise
            p={}
        protect(request,p)
        for field in ('account','platform','variant','period','publicationId','window'):row[field]=row[field].strip()
        for field in ('hookType','template','format'):
            if not row.get(field):row[field]=p.get(field,'')
        if row['duration'] is None and p:row['duration']=sum(s['duration'] for s in p['scenes']);row['durationSource']='projectSnapshot'
        row['clientId']=p.get('clientId','');return row
    def upsert(rows,request,strict=True):
        validated=[normalized(raw,request,strict) for raw in rows]
        old=c.all_rows('metrics');by_key={r.get('dedupeKey') or key_for(r):r for r in old};out=[];counts={'inserted':0,'updated':0,'unchanged':0}
        with c.db() as con:
            for row,raw in zip(validated,rows):
                key=key_for(row);previous=by_key.get(key)
                if previous:
                    protect(request,previous)
                    if previous.get('project')==row['project']:
                        for field in ('hookType','template','duration','durationSource'):
                            if raw.get(field) in (None,'') and previous.get(field) not in (None,''):row[field]=previous[field]
                record={'id':previous['id'] if previous else 'pub-'+key,'dedupeKey':key,**row}
                if previous:
                    same=all(previous.get(k)==v for k,v in row.items())
                    counts['unchanged' if same else 'updated']+=1
                else:counts['inserted']+=1
                con.execute('INSERT OR REPLACE INTO metrics VALUES (?,?)',(record['id'],json.dumps(record,ensure_ascii=False)));by_key[key]=record;out.append(record)
        return {**counts,'records':out}
    c.production_metric=lambda raw,request:upsert([raw],request,strict=False)['records'][0]
    c.production_metric_import=lambda rows,request:upsert(rows,request,strict=False)['records']
    @app.post('/api/analytics/import/preview')
    async def preview(request:Request,file:UploadFile=File(...)):
        raw=await file.read(1_000_001)
        if len(raw)>1_000_000:raise HTTPException(413,'CSV demasiado grande')
        try:rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
        except Exception as e:raise HTTPException(422,'CSV no válido: '+str(e))
        projects=visible(request,c.all_rows('projects'));output=[]
        for index,source in enumerate(rows):
            row={**source};ref=row.get('project') or row.get('clip') or ''
            matches=[p for p in projects if p['id']==ref or p['title'].casefold()==ref.casefold()]
            if not matches:
                clips=[clip for b in visible(request,c.all_rows('batches')) for clip in b['clips'] if clip['id']==ref]
                matches=[p for p in projects if any(clip['projectId']==p['id'] for clip in clips)]
            row['project']=matches[0]['id'] if len(matches)==1 else ''
            row['variant']=row.get('variant') or 'A';row['error']='' if len(matches)==1 else 'Asociación ausente o ambigua: elige un proyecto.'
            row['warnings']=[]
            if not row.get('account'):row['warnings'].append('Cuenta sin registrar: no se producirán conclusiones comparativas.')
            if not row.get('publicationId') and not row.get('publishedAt'):row['warnings'].append('Sin identificador/fecha de publicación: se deduplican filas idénticas; añade publicationId para actualizar la misma publicación.')
            row['row']=index+2;output.append(row)
        return {'rows':output,'projects':[{'id':p['id'],'title':p['title']} for p in projects],'columns':list(Publication.model_fields)}
    class Commit(BaseModel):rows:list[dict]
    @app.post('/api/analytics/import/commit')
    def commit(req:Commit,request:Request):
        for row in req.rows:
            if not row.get('project'):raise HTTPException(422,'Corrige todas las asociaciones antes de guardar. No se guardó ninguna fila.')
        return upsert(req.rows,request)
    @app.get('/api/analytics')
    def analytics(request:Request,account:str='',platform:str='',period:str='',hookType:str='',template:str='',format:str='',duration:str=''):
        rows=visible(request,c.all_rows('metrics'))
        for k,value in [('account',account),('platform',platform),('hookType',hookType),('template',template),('format',format)]:
            if value:rows=[r for r in rows if str(r.get(k,'')).casefold()==value.casefold()]
        if period:rows=[r for r in rows if period.casefold() in (str(r.get('window','')).casefold(),str(r.get('period','')).casefold())]
        if duration:
            try:maximum=float(duration)
            except ValueError:raise HTTPException(422,'La duración máxima debe ser un número de segundos')
            rows=[r for r in rows if r.get('duration') is not None and r['duration']<=maximum]
        grouped=defaultdict(list)
        for row in rows:grouped[(row.get('account',''),row['platform'],row.get('window') or row['period'])].append(row)
        groups=[]
        for (acct,plat,window),items in grouped.items():
            hooks=defaultdict(list)
            for item in items:hooks[item.get('hookType') or 'Sin clasificar'].append(item)
            aggregates=[]
            for kind,publications in hooks.items():
                stats={'hookType':kind,'count':len(publications)}
                for metric in ('watched','views'):
                    values=[r[metric] for r in publications if r.get(metric) is not None];stats[metric]=sum(values)/len(values) if values else None;stats[metric+'N']=len(values)
                aggregates.append(stats)
            comparable=[h for h in aggregates if h['watchedN']>=5 and h['hookType']!='Sin clasificar']
            observation='Datos insuficientes: hacen falta al menos dos tipos de gancho con cinco publicaciones con porcentaje visto en la misma cuenta, plataforma y ventana. No se recomienda un ganador.'
            if not acct:observation='Falta identificar la cuenta. Estos registros se muestran, pero no se comparan como si pertenecieran a una misma cuenta.'
            elif len(comparable)>=2:
                ordered=sorted(comparable,key=lambda h:h['watched'],reverse=True);top=ordered[0];other=ordered[1]
                observation=f"En esta cuenta, {top['watchedN']} publicaciones con gancho «{top['hookType']}» registraron {top['watched']:.1f}% visto de media, frente a {other['watched']:.1f}% en {other['watchedN']} con «{other['hookType']}», durante «{window}». Es una observación descriptiva; no prueba causalidad ni predice el próximo resultado."
            examples=[]
            for item in items:
                try:p=c.get('projects',item['project'])
                except HTTPException:continue
                if not any(x['id']==item['id'] for x in examples):examples.append({'id':item['id'],'title':p['title']})
                if len(examples)>=2:break
            groups.append({'key':hashlib.sha256(f'{acct}|{plat}|{window}'.encode()).hexdigest(),'account':acct,'platform':plat,'period':window,'periods':sorted({r['period'] for r in items}),'count':len(items),'hooks':aggregates,'observation':observation,'examples':examples})
        return {'publications':len(rows),'groups':groups,'note':'Solo se comparan cuenta, plataforma y ventana iguales. Los promedios excluyen datos faltantes e indican su tamaño de muestra.'}
    @app.post('/api/analytics/reuse/{key}')
    def reuse(key:str,request:Request):
        m=protect(request,c.get('metrics',key));p=protect(request,c.get('projects',m['project']));p.update(id=c.uid(),title='Hipótesis · '+p['title'],template=m.get('template') or p['template'],hookType=m.get('hookType') or 'original',description='Hipótesis editorial para probar. No presupone el mismo rendimiento.\n\n'+p.get('description',''),batchId='',updated=c.now())
        prompts={'pregunta':'¿Qué podemos aprender de esta idea?','dato':'Un dato para revisar con contexto','demostración':'Mira este paso con atención','historia':'La historia detrás de este momento'}
        if p['hookType'] in prompts:p['hooks']=[prompts[p['hookType']],*p.get('hooks',[])[:1]]
        return c.put('projects',p)
