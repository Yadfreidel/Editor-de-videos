import './globals.css';
import './production.css';
import CloudAccess from './cloud-access';
export const metadata={title:'Clip Studio · Tu próxima historia',description:'Estudio local de videos cortos en español'};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="es"><head><meta name="referrer" content="no-referrer"/></head><body><CloudAccess>{children}</CloudAccess></body></html>}
