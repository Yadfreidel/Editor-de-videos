'use client';
export function downloadProject(project:any,format:'json'|'srt'){
 let content='';
 if(format==='json')content=JSON.stringify(project,null,2);
 else{let t=0;const stamp=(seconds:number)=>{const ms=Math.round(seconds*1000);return `${String(Math.floor(ms/3600000)).padStart(2,'0')}:${String(Math.floor(ms/60000)%60).padStart(2,'0')}:${String(Math.floor(ms/1000)%60).padStart(2,'0')},${String(ms%1000).padStart(3,'0')}`};content=project.scenes.map((s:any,i:number)=>{const start=t;t+=s.duration;return `${i+1}\n${stamp(start)} --> ${stamp(t)}\n${s.text}\n`}).join('\n')}
 const url=URL.createObjectURL(new Blob([content],{type:format==='json'?'application/json':'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=`clip-${project.id}.${format}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
