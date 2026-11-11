'use client';
import {browserApi} from './browser-store';
export const isPages=process.env.NEXT_PUBLIC_STATIC_EXPORT==='true';
export const basePath=process.env.NEXT_PUBLIC_BASE_PATH||'';
export function appPath(path:string){return basePath+(path.startsWith('/')?path:'/'+path)}
export function apiOrigin(){if(typeof window==='undefined')return process.env.NEXT_PUBLIC_API_URL||'';return localStorage.getItem('clip.apiOrigin')||process.env.NEXT_PUBLIC_API_URL||''}
export function browserMode(){return isPages&&!apiOrigin()}
export function mediaUrl(path:string){if(!path||/^(https?:|blob:|data:)/.test(path))return path;return apiOrigin()+path}
export function reviewUrl(path:string){if(!isPages)return path;const token=path.split('/').filter(Boolean).pop()||'';return appPath('/review/')+'#token='+encodeURIComponent(token)}
function normalize(value:any):any{if(typeof value==='string'&&value.startsWith('/media/'))return mediaUrl(value);if(Array.isArray(value))return value.map(normalize);if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,normalize(v)]));return value}
export async function apiFetch(path:string,options:RequestInit={}):Promise<Response>{
 if(browserMode())return browserApi(path,options);
 const origin=apiOrigin();const url=/^https?:/.test(path)?path:origin+path;
 const headers=new Headers(options.headers);const access=typeof window!=='undefined'?sessionStorage.getItem('clip.access.'+origin):null;
 if(origin&&access&&!headers.has('Authorization'))headers.set('x-owner-key',access);
 let response:Response;
 try{response=await fetch(url,{...options,headers,credentials:options.credentials||(origin?'omit':'same-origin')})}catch{throw Error('No se pudo conectar con el servidor de video. Revisa la dirección y sus permisos CORS, o usa el modo navegador.')}
 if(response.ok&&path==='/api/access/login'&&origin&&typeof options.body==='string'){sessionStorage.setItem('clip.access.'+origin,JSON.parse(options.body).key)}
 if(path==='/api/access/logout'&&origin)sessionStorage.removeItem('clip.access.'+origin);
 if(response.headers.get('content-type')?.includes('application/json'))return new Response(JSON.stringify(normalize(await response.json())),{status:response.status,headers:{'Content-Type':'application/json'}});
 return response;
}
