import './globals.css';
import './production.css';
export const metadata={title:'Clip Studio · Tu próxima historia',description:'Estudio local de videos cortos en español'};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="es"><body>{children}</body></html>}
