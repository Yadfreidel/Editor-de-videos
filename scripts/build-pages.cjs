const {spawnSync}=require('node:child_process');
const path=require('node:path');
const fs=require('node:fs');
const env={...process.env,CLIP_STATIC_EXPORT:'true',NEXT_PUBLIC_STATIC_EXPORT:'true',NEXT_PUBLIC_BASE_PATH:process.env.NEXT_PUBLIC_BASE_PATH??'/Editor-de-videos'};
const result=spawnSync(process.execPath,[require.resolve('next/dist/bin/next'),'build'],{env,stdio:'inherit'});
if(result.status!==0)process.exit(result.status||1);
fs.writeFileSync(path.join('.next-pages','.nojekyll'),'');
