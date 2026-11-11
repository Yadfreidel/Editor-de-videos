'use client';
import {use,useEffect,useState} from 'react';
import {ReviewPanel} from '../../advanced';
export default function PrivateReview({params}:{params:Promise<{token:string}>}){
 const {token}=use(params);const [review,setReview]=useState<any>(null),[media,setMedia]=useState(''),[error,setError]=useState('');
 async function call(path:string,data?:unknown){const r=await fetch('/api/reviewer'+path,{credentials:'omit',headers:{'Authorization':'Bearer '+token,...(data===undefined?{}:{'Content-Type':'application/json'})},...(data===undefined?{}:{method:'POST',body:JSON.stringify(data)})});const value=await r.json();if(!r.ok)throw Error(value.detail||'Enlace no válido');return value}
 async function refresh(){const r=await call('/session');setReview(r);return r}
 useEffect(()=>{let active=true;let objectUrl='';setReview(null);setMedia('');setError('');(async()=>{try{const r=await call('/session');if(!active)return;setReview(r);const video=await fetch(r.media,{credentials:'omit',headers:{Authorization:'Bearer '+token}});if(!video.ok)throw Error('El enlace no permite acceder a esta vista previa.');objectUrl=URL.createObjectURL(await video.blob());if(active)setMedia(objectUrl)}catch(e){if(active)setError(e instanceof Error?e.message:String(e))}})();return()=>{active=false;if(objectUrl)URL.revokeObjectURL(objectUrl)}},[token]);
 return <main className="local-review-page" style={{margin:'0 auto',width:'100%'}}><div className="eyebrow">CLIP STUDIO · REVISIÓN PRIVADA LOCAL</div>{error&&<div className="alert error" role="alert">{error}</div>}{review?<><h1>{review.title} · V{review.version}</h1><p className="inline-note">Acceso de {review.reviewer}. Este enlace autoriza únicamente esta versión.</p>{media?<ReviewPanel review={review} media={media} api={(path,data)=>call('/'+review.id+path,data)} onRefresh={refresh} onError={setError}/>:<p>Cargando vista previa autorizada…</p>}</>:!error&&<p>Comprobando permisos…</p>}</main>
}
