const {chromium}=require('@playwright/test');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch();const context=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:3,isMobile:true,hasTouch:true,userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1'});
 const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(20000);
 await page.goto(process.env.CLIP_PAGES_URL||'http://127.0.0.1:8087/Editor-de-videos/');await page.getByText('Modo navegador',{exact:true}).waitFor();
 if((await page.locator('.local-pill').innerText()).includes('Modo local'))throw Error('Misleading local-server badge');
 if(!await page.getByRole('button',{name:'De un video a grandes clips'}).isDisabled())throw Error('Server-only creation not marked');
 await page.locator('#script').fill('Un guion desde mi teléfono. Mi proyecto debe conservarse.');await page.getByRole('button',{name:'Crear storyboard',exact:true}).click();await page.getByText('Inspector',{exact:true}).waitFor();
 for(const name of ['Tendencias','Lotes','Clientes','Análisis']){
  await page.locator('.sidebar').getByRole('button',{name,exact:true}).click();await page.locator('.server-required').waitFor();
  if(await page.locator('.alert[role=alert]').count())throw Error('Missing server shown as a failure');
 }
 await page.locator('.sidebar').getByRole('button',{name:'Ajustes',exact:true}).click();await page.getByRole('heading',{name:'Tu estudio en este navegador.'}).waitFor();
 if(await page.getByText('Sin configurar',{exact:true}).count()||await page.getByText(/Configura los proveedores en .env/).count())throw Error('Desktop-only setup shown on phone');
 await page.getByRole('button',{name:'Conectar servidor de video',exact:true}).click();await page.getByLabel('Dirección del servidor de video').fill('http://127.0.0.1:8000');
 await page.getByRole('button',{name:'Comprobar y conectar',exact:true}).click();await page.getByText(/localhost apunta al propio teléfono/).waitFor();
 if(await page.evaluate(()=>localStorage.getItem('clip.apiOrigin')))throw Error('Invalid loopback server persisted');
 await page.route('https://unreachable.invalid/api/health',r=>r.abort());await page.getByLabel('Dirección del servidor de video').fill('https://unreachable.invalid');await page.getByRole('button',{name:'Comprobar y conectar',exact:true}).click();await page.getByText(/No se pudo comprobar la conexión/).waitFor();
 if(await page.evaluate(()=>localStorage.getItem('clip.apiOrigin')))throw Error('Unverified server persisted');
 await page.getByRole('button',{name:'Usar modo navegador',exact:true}).click();await page.getByText('Modo navegador',{exact:true}).waitFor();
 await page.locator('.sidebar').getByRole('button',{name:'Ajustes',exact:true}).click();await page.getByRole('heading',{name:'Tu estudio en este navegador.'}).waitFor();
 if(await page.locator('.alert[role=alert]').count())throw Error('Stale server error on settings');
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Mobile overflow');
 fs.mkdirSync('workspace/mobile-pages-check',{recursive:true});await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:'workspace/mobile-pages-check/settings-iphone.png',fullPage:true});
 if(!await page.evaluate(()=>JSON.parse(localStorage.getItem('clip.browser.projects')||'[]').some(p=>p.title.includes('Un guion desde'))))throw Error('Project lost during setup');
 if(errors.length)throw Error(errors.join('\n'));await browser.close();console.log('Mobile checks passed: unavailable features, honest settings, no stale errors, verified setup, loopback protection and preserved projects.');
})().catch(e=>{console.error(e);process.exit(1)});
