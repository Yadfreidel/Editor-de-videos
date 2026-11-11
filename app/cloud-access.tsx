'use client';
import {useEffect,useState} from 'react';
import {isServerHosted,apiFetch} from './connection';
export default function CloudAccess({children}:{children:React.ReactNode}){
 const [ready,setReady]=useState(false),[allowed,setAllowed]=useState(false),[review,setReview]=useState(false),[key,setKey]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{
  if(!isServerHosted)return;
  if(window.location.pathname.startsWith('/review')){setReview(true);setReady(true);return}
  const expired=()=>{setAllowed(false);setReady(true);setError('Tu sesión terminó. Vuelve a entrar para continuar.')};window.addEventListener('clip:auth-expired',expired);
  apiFetch('/api/access/session').then(async r=>{if(!r.ok)throw Error('No se pudo comprobar la sesión');const s=await r.json();setAllowed(s.role==='owner'||s.role==='collaborator')}).catch(e=>setError(e.message)).finally(()=>setReady(true));
  return()=>window.removeEventListener('clip:auth-expired',expired)
 },[]);
 if(!isServerHosted)return children;
 if(!ready)return <div className="cloud-login"><p>Comprobando acceso al estudio privado…</p></div>;
 if(review||allowed)return children;
 return <main className="cloud-login"><div className="surface"><div className="eyebrow">CLIP STUDIO · ESTUDIO PRIVADO EN LÍNEA</div><h1>Tu estudio, desde cualquier lugar.</h1><p>Entra con tu clave de acceso. Tus videos y proyectos no son públicos.</p><form onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');try{const r=await apiFetch('/api/access/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:key.trim()})});const value=await r.json();if(!r.ok)throw Error(value.detail||'No se pudo iniciar sesión');setKey('');setAllowed(true)}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}}}><label className="field">Clave privada<input aria-label="Clave privada" type="password" autoComplete="current-password" required value={key} onChange={e=>setKey(e.target.value)}/></label><button className="primary full" disabled={busy}>{busy?'Comprobando…':'Entrar al estudio'}</button></form>{error&&<div role="alert" className="alert error">{error}</div>}<p className="inline-note">El propietario administra la clave como secreto de su proveedor de hosting. Nunca se publica en GitHub.</p></div></main>
}
