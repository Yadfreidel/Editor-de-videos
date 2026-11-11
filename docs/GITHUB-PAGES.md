# Desplegar Clip Studio en GitHub Pages

Pages estaba sirviendo la raíz del repositorio con Jekyll, por eso aparecía el README como texto. Ahora `.github/workflows/pages.yml` compila Next.js y publica el sitio exportado, no los archivos fuente.

URL de este repositorio: **https://yadfreidel.github.io/Editor-de-videos/**

La configuración de Pages debe tener **Source: GitHub Actions**. El workflow se ejecuta al subir a `main` y también se puede lanzar desde Actions → «Publicar Clip Studio en Pages» → Run workflow. El despliegue utiliza el subdirectorio del repositorio, incluye JavaScript/CSS y la ruta estática de revisión, y conserva el arranque local anterior.

## Qué funciona sin servidor

En Pages se muestra la aplicación interactiva en **Modo navegador**:

- Crear storyboard a partir de un guion, editar escenas, textos, colores y tiempos.
- Guardar y abrir proyectos automáticamente en el almacenamiento de ese navegador.
- Descargar el proyecto editable en JSON y subtítulos SRT con tiempos estimados.
- Guardar perfiles de marca y métricas manuales localmente.

Los datos del navegador no son los proyectos SQLite de tu PC ni se suben al repositorio. Si cambias de navegador o borras sus datos, necesitarás tu copia JSON. La transcripción, Ollama, Piper, procesamiento de lotes y exportación MP4 necesitan el servidor de video: no se simulan ni se presentan como funciones de Pages.

**GitHub Pages no ejecuta Python, FFmpeg, SQLite ni servidores Next.js.** Para usar la aplicación completa en tu PC:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

Abre **http://127.0.0.1:3000**. La publicación en Pages no modifica ni expone esa base de datos, tus claves o tus videos.

## API opcional

La barra «Configurar servidor» admite el origen de una API propia. También se puede establecer la variable pública del repositorio **CLIP_API_URL**, que se incorpora como `NEXT_PUBLIC_API_URL` al compilar. Solo debe contener el origen HTTPS, nunca contraseñas o tokens. Dejarla vacía activa el modo navegador.

El backend mantiene `127.0.0.1` y CORS desactivado por defecto. Si administras un despliegue propio, permite únicamente el origen de tu interfaz, por ejemplo:

```dotenv
CLIP_ALLOWED_ORIGINS=https://yadfreidel.github.io
```

Esto no despliega el backend ni lo hace público. No se habilita `*`. Una API expuesta requiere su propio hosting, HTTPS, almacenamiento persistente y protección de acceso. Los medios privados de agencia necesitan una integración de autenticación de medios entre dominios; esta configuración individual de API no constituye un servicio remoto de revisión probado. Para esos flujos usa el despliegue completo bajo el mismo origen o el arranque local. No se ha contratado ni publicado un servicio externo de video.

## En el teléfono

«Servidor no conectado» es una limitación de la instalación web, no un fallo del teléfono. Ajustes distingue las funciones disponibles en el navegador de las que necesitan procesamiento en servidor; no indica que debas instalar FFmpeg o Python en iOS/Android. Las secciones no disponibles muestran una explicación antes de intentar trabajos, y cambiar de sección elimina errores anteriores.

No introduzcas `localhost` o `127.0.0.1` para acceder a tu PC desde el móvil: esas direcciones apuntan al propio teléfono. La configuración rechaza ese caso en móviles y verifica `/api/health` antes de guardar una conexión. Un servidor no accesible o sin permisos CORS no se guarda como conectado. La dirección no crea un servidor ni prepara un túnel por sí sola.

El procesamiento móvil completo necesita decidir dónde ejecutar el motor: una PC encendida con acceso HTTPS preparado, o un servidor en internet. Esta corrección de interfaz no despliega ese motor ni expone la PC a la red. Mientras no se conecte, siguen disponibles guiones, storyboard y descargas JSON/SRT; MP4, voz y transcripción continúan requiriendo servidor.

Prueba adicional con vista y agente de iPhone: `node scripts/mobile-pages-check.cjs`. Comprueba navegación sin errores engañosos, Ajustes adaptado, rechazo de localhost en el teléfono, comprobación de conexión antes de guardar y conservación de proyectos.

## Compilar y comprobar

```powershell
npm.cmd ci
npm.cmd run build:pages
.\.venv\Scripts\python.exe scripts/serve-pages.py
# En otra terminal:
node scripts/pages-ui-check.cjs
```

`build:pages` genera `.next-pages/` con HTML, JavaScript, CSS y `.nojekyll`. Ese directorio se publica como artefacto de Pages; no se debe seleccionar `/docs` ni la raíz de `main` como sitio Jekyll.

La prueba reproduce `/Editor-de-videos/` y verifica recursos sin 404, edición, guardado tras recargar, descarga JSON/SRT, móvil y la página estática de revisión. `npm run build` sigue compilando el modo local con su proxy FastAPI. Los enlaces locales antiguos `/review/TOKEN` siguen entrando por una reescritura; los enlaces de la versión estática usan `/review/#token=TOKEN`.
