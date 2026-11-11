import type { NextConfig } from 'next';
const config: NextConfig = {devIndicators:false,turbopack:{root:process.cwd()},async headers(){return [{source:'/review/:path*',headers:[{key:'Referrer-Policy',value:'no-referrer'},{key:'Cache-Control',value:'private, no-store'}]}]},async rewrites(){return [{source:'/api/:path*',destination:'http://127.0.0.1:8000/api/:path*'},{source:'/media/:path*',destination:'http://127.0.0.1:8000/media/:path*'}]}};
export default config;
