import type { NextConfig } from 'next';
const pages=process.env.CLIP_STATIC_EXPORT==='true';
const config: NextConfig = {
 devIndicators:false,turbopack:{root:process.cwd()},
 ...(pages?{output:'export' as const,trailingSlash:true,basePath:process.env.NEXT_PUBLIC_BASE_PATH||'',distDir:'.next-pages',images:{unoptimized:true}}:{
 async headers(){return [{source:'/review/:path*',headers:[{key:'Referrer-Policy',value:'no-referrer'},{key:'Cache-Control',value:'private, no-store'}]}]},
 async rewrites(){return [{source:'/api/:path*',destination:'http://127.0.0.1:8000/api/:path*'},{source:'/media/:path*',destination:'http://127.0.0.1:8000/media/:path*'},{source:'/review/:token',destination:'/review?token=:token'}]}
 })
};
export default config;
