import os,sys,json,csv,io,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));os.environ['CLIP_WORKSPACE']='workspace/analytics-verification/'+uuid.uuid4().hex
from backend.main import app,Project,Scene,put,all_rows
from fastapi.testclient import TestClient
c=TestClient(app)
p=Project(title='Proyecto CSV anterior',scenes=[Scene(text='Una prueba.')]).model_dump();put('projects',p)
old=f'project,variant,platform,period,views,average,watched,interactions,followers\n{p["id"]},A,TikTok,2026-11-01 a 2026-11-07,0,,,,\n'.encode()
def upload(path,data):
 r=c.post('/api'+path,files={'file':('results.csv',data,'text/csv')});assert r.status_code==200,r.text;return r.json()
first=upload('/metrics/import',old);second=upload('/metrics/import',old);assert first[0]['id']==second[0]['id']
assert second[0]['views']==0 and second[0]['average'] is None
assert len([m for m in all_rows('metrics') if m['project']==p['id']])==1
print('Legacy CSV compatible, exact reimport idempotent, missing is not zero',flush=True)
same=Project(title=p['title'],scenes=[Scene(text='Otra prueba.')]).model_dump();put('projects',same)
ambiguous=upload('/analytics/import/preview',f'project,variant,platform,period,views\n{p["title"]},A,TikTok,48h,10\n'.encode())
assert ambiguous['rows'][0]['project']=='' and ambiguous['rows'][0]['error']
assert c.post('/api/analytics/import/commit',json={'rows':ambiguous['rows']}).status_code==422
rows=[]
for account in ('cuenta-1','cuenta-2'):
 for hook in ('pregunta','dato'):
  for i in range(5 if account=='cuenta-1' else 2):rows.append({'project':p['id'],'variant':'A' if hook=='pregunta' else 'B','platform':'TikTok','period':'48h','window':'48h','account':account,'publicationId':f'{account}-{hook}-{i}','watched':80 if hook=='pregunta' else 50,'views':100,'hookType':hook,'template':'Podcast','format':'9:16','duration':30})
for _ in range(2):
 r=c.post('/api/analytics/import/commit',json={'rows':rows});assert r.status_code==200,r.text
assert r.json()['unchanged']==len(rows)
assert c.post('/api/analytics/import/commit',json={'rows':[{**rows[0],'followers':'NaN'}]}).status_code==422
result=c.get('/api/analytics?account=cuenta-1&period=48h').json();assert result['publications']==10 and len(result['groups'])==1
group=result['groups'][0];assert group['count']==10 and all(h['watchedN']==5 for h in group['hooks'])
assert '80.0%' in group['observation'] and 'causalidad' in group['observation']
small=c.get('/api/analytics?account=cuenta-2').json();assert 'Datos insuficientes' in small['groups'][0]['observation']
other={**rows[0],'platform':'YouTube Shorts','publicationId':'different-platform','watched':99}
assert c.post('/api/analytics/import/commit',json={'rows':[other]}).status_code==200
allgroups=c.get('/api/analytics?account=cuenta-1').json();assert len(allgroups['groups'])==2
filtered=c.get('/api/analytics?account=cuenta-1&platform=TikTok&hookType=pregunta&duration=45&template=Podcast&format=9:16').json();assert filtered['publications']==5
metric=r.json()['records'][0];reuse=c.post('/api/analytics/reuse/'+metric['id'],json={});assert reuse.status_code==200
assert reuse.json()['id']!=p['id'] and reuse.json()['hookType']=='pregunta' and reuse.json()['template']=='Podcast'
Path('analytics-verification.json').write_text(json.dumps({'legacyCsv':True,'idempotentImport':True,'missingVersusZero':True,'ambiguousAssociationRequiresCorrection':True,'accountPlatformWindowSeparated':True,'sampleSizeDisplayed':True,'smallSamplesAvoidConclusion':True,'filters':True,'styleReuseAsHypothesis':True},indent=2),encoding='utf-8')
print('Analytics association, groups, sample sizes, filters and hypothesis reuse passed',flush=True)
