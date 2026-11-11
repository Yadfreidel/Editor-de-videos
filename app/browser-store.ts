'use client';
const prefix='clip.browser.';
function read(table:string):any[]{return JSON.parse(localStorage.getItem(prefix+table)||'[]')}
function save(table:string,record:any){const rows=read(table);const next=[record,...rows.filter(r=>r.id!==record.id)];try{localStorage.setItem(prefix+table,JSON.stringify(next))}catch{throw Error('No queda espacio en este navegador. Descarga tus proyectos antes de continuar.')}return record}
function response(value:any,status=200){return new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}})}
export async function browserApi(path:string,options:RequestInit={}):Promise<Response>{
 const method=options.method||'GET';const url=new URL(path,'https://clip.invalid');path=url.pathname;const data=typeof options.body==='string'?JSON.parse(options.body):{};
 if(path==='/api/health')return response({local:false,browser:true,ffmpeg:false,piper:false,whisper:false,ollama:false,external:false,workspace:'Almacenamiento de este navegador'});
 if(path==='/api/production/status')return response({role:'anonymous',browser:true,remoteConfigured:false});
 if(path==='/api/jobs')return response([]);
 if(['/api/projects','/api/brands','/api/assets','/api/metrics','/api/batches'].includes(path)&&method==='GET')return response(read(path.slice(5)));
 if(path==='/api/brand')return response({color:'#b9e977',font:'Arial',logo:''});
 if(path==='/api/create'){
  if(data.mode==='topic')return response({detail:'La generación con Ollama requiere el servidor de video. Selecciona «De tu guion a la pantalla» para continuar en el navegador.'},409);
  const parts=String(data.text||'').split(/\n\s*\n|(?<=[.!?])\s+/).map((s:string)=>s.trim()).filter(Boolean);
  if(!parts.length)return response({detail:'Escribe un guion antes de crear el storyboard.'},422);
  const palette:Record<string,string[]>= {Documental:['#173c38','#4a392a','#263d50'],Podcast:['#333044','#242a3b'],Noticias:['#153e5c','#263f64'],Educativo:['#38543d','#405b57']};
  const colors=palette[data.template]||palette.Documental;const title=String(data.text).split(/\s+/).slice(0,9).join(' ').slice(0,100);
  return response(save('projects',{id:crypto.randomUUID(),title,template:data.template||'Documental',sources:data.sources||[],hooks:[`¿Qué necesitas saber sobre ${title.toLowerCase()}?`,`Por qué importa: ${title}`,`Una perspectiva sobre ${title}`],description:title,review:'',brand:'#b9e977',font:'Arial',logo:'',voiceVolume:1,musicVolume:.15,music:'',updated:new Date().toISOString(),scenes:parts.slice(0,50).map((text:string,i:number)=>({id:crypto.randomUUID(),text,overlay:text.split(/\s+/).slice(0,8).join(' '),duration:Math.max(2,text.split(/\s+/).length/2.5),color:colors[i%colors.length],asset:'',audio:'',originalAudio:false,captions:[],start:0,zoom:1,x:.5,verified:false}))}));
 }
 if(/^\/api\/projects\/[^/]+$/.test(path)){
  const id=path.split('/').pop();if(method==='PUT')return response(save('projects',{...data,updated:new Date().toISOString()}));const p=read('projects').find(p=>p.id===id);return p?response(p):response({detail:'Proyecto no encontrado en este navegador.'},404);
 }
 if(path==='/api/metrics'&&method==='POST')return response(save('metrics',{...data,id:crypto.randomUUID()}));
 if(path==='/api/brands'&&method==='POST')return response(save('brands',{...data,id:crypto.randomUUID(),updated:new Date().toISOString()}));
 if(/^\/api\/brands\/[^/]+$/.test(path)&&method==='PUT')return response(save('brands',{...data,id:path.split('/').pop(),updated:new Date().toISOString()}));
 if(path.endsWith('/validate')&&path.startsWith('/api/brands/'))return response({warnings:['La vista previa MP4 y la validación de fuentes instaladas requieren conectar el servidor de video.']});
 if(path.endsWith('/duplicate')&&path.startsWith('/api/brands/')){const b=read('brands').find(b=>b.id===path.split('/')[3]);return b?response(save('brands',{...b,id:crypto.randomUUID(),name:b.name+' · copia'})):response({detail:'Marca no encontrada'},404)}
 if(path==='/api/analytics')return response({publications:read('metrics').length,groups:[],note:'Conecta el servidor para importar CSV y calcular comparaciones.'});
 return response({detail:'Esta función necesita el servidor de video (Python y FFmpeg). GitHub Pages publica la interfaz; puedes crear y guardar guiones/storyboards aquí o conectar tu servidor desde la barra superior.'},409);
}
