# Clip Studio

Estudio local de videos cortos en español. Next.js + TypeScript + Tailwind 4, FastAPI, SQLite y FFmpeg. Interfaz con Crear, Tendencias, Proyectos, Recursos, Rendimiento y Ajustes. No publica en plataformas ni predice viralidad.

La ampliación añade **Lotes, Marcas, Clientes y Análisis**. Consulta [la prueba principal paso a paso en Windows, migraciones y revisión privada](docs/PRODUCTION.md) y [la organización futura Individual / Pro / Agencia](docs/LEVELS.md). Todas las funciones siguen incluidas, sin cobros. El editor anterior y su arranque se conservan.

**Publicación web:** [Abrir la interfaz en GitHub Pages](https://yadfreidel.github.io/Editor-de-videos/). Consulta [despliegue y límites de Pages](docs/GITHUB-PAGES.md). Pages publica la app interactiva en modo navegador; la generación y exportación de video requieren el servidor local o una API propia.

## Inicio en Windows

Instala Node.js 20.9 o superior y Python 3.11 o superior de 64 bits. Se probó con Node 24 y Python 3.14 en Windows. Desde PowerShell, en esta carpeta:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
```

El binario de FFmpeg se instala con `imageio-ffmpeg`; no hace falta ponerlo en PATH. Puedes usar tu propia compilación con `FFMPEG_PATH`. FFprobe externo se recomienda para inspección independiente, pero la aplicación usa FFmpeg y las pruebas usan PyAV para verificar resolución y codecs.

Para voz española, revisa primero [licencias y condiciones](docs/PROVIDERS.md), después descarga el modelo:

```powershell
.\.venv\Scripts\python.exe -m piper.download_voices --download-dir workspace/models es_ES-sharvard-medium
```

Configura `.env` (creado a partir de `.env.example`):

```dotenv
PIPER_MODEL=workspace/models/es_ES-sharvard-medium.onnx
WHISPER_MODEL=tiny
WHISPER_DEVICE=cpu
EXTERNAL_ENABLED=true
```

`tiny` permite comprobar el flujo rápidamente; `small` suele dar mejor transcripción en español a costa de recursos. La primera transcripción descarga el modelo: requiere internet y puede tardar varios minutos. CPU usa int8. Para GPU configura `WHISPER_DEVICE=cuda` y las dependencias CUDA/cuDNN indicadas por faster-whisper.

Inicia ambos servidores con:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

Abre **http://127.0.0.1:3000**. Ctrl+C detiene el inicio conjunto. Si prefieres dos terminales:

```powershell
# Terminal 1
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
# Terminal 2
npm.cmd run dev
```

No ejecutes un segundo backend en el mismo puerto. API documentada en http://127.0.0.1:8000/docs. El estudio está pensado para uso individual en localhost; no lo expongas directamente a internet.

## Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-optional.txt
npm ci
cp .env.example .env
.venv/bin/python -m piper.download_voices --download-dir workspace/models es_ES-sharvard-medium
# Edita PIPER_MODEL en .env
sh scripts/start.sh
```

Instala fuentes DejaVu si tu distribución no las trae. Georgia y Consolas usan las fuentes del sistema Windows; en Linux vuelven a la fuente disponible para renderizar. El flujo de Linux está preparado, pero no se ejecutó en este equipo Windows.

## Flujo de guion a MP4

1. Elige «De tu guion a la pantalla», pega texto o usa el ejemplo. Cada frase/párrafo crea una escena. También hay un proyecto de demostración original, «Una pausa también es progreso».
2. Elige una plantilla. Cambia la paleta inicial; todas las escenas siguen siendo editables. Guarda color, fuente y logotipo como perfil de marca para los proyectos nuevos. La duración del guion se estima por palabras: no se acelera la voz para forzar una duración objetivo.
3. Crea el storyboard. Edita texto hablado, tarjeta, color, duración y orden. Carga fotos o videos propios, recorta con inicio/duración, ajusta zoom y encuadre horizontal. La posición vertical del encuadre se centra.
4. Usa Piper al exportar o genera/previsualiza voz por escena. También puedes cargar narración propia y música; los controles de volumen permiten silenciar pistas. La música se reduce con sidechain durante el audio de la voz. Activa «Audio del video original» para conservarlo en clips.
5. Revisa las afirmaciones de cada escena y conserva fuentes con fechas. Ajusta la descripción, los tres ganchos y la revisión sobre etiquetado. Los ganchos son propuestas de plantilla, no afirmaciones comprobadas.
6. Exporta 720 × 1280 o 1080 × 1920. Descarga MP4, SRT, portada PNG, texto de publicación y créditos JSON. La portada es la primera tarjeta, editable con su texto, color y marca. Puedes exportar A y B como trabajos independientes.

El storyboard es una representación rápida: sus subtítulos son estimados. La reproducción del **render terminado** es la vista previa audiovisual de referencia y usa exactamente el mismo archivo que descargas. Piper amplía una escena si la narración necesita más tiempo; el trabajo devuelve los tiempos efectivos. El SRT exportado utiliza esos tiempos. Una narración propia se recorta/rellena a la duración que indiques: ajusta ese valor al audio para evitar cortar palabras. Si cambias la narración, vuelve a generar el render.

Los subtítulos manuales se dividen en grupos cortos con tiempos estimados. Los clips con transcripción importan segmentos reales y, cuando Whisper devuelve palabras, generan resaltado progresivo. Editar el texto elimina las marcas anteriores para evitar reutilizarlas incorrectamente. Los subtítulos ya incrustados en un video fuente no se pueden borrar automáticamente: desactiva los nuevos o utiliza el original limpio.

## Video largo, enlaces y actualidad

- **Video propio:** carga MP4/MOV/MKV/WebM, confirma autorización, elige 15/30/45/60/90 s y transcribe. Se proponen hasta diez segmentos contiguos con una razón heurística y advertencia de contexto. El número depende del material; un video demasiado corto no produce tres clips artificiales. Los cortes respetan límites de segmento de Whisper; no hay clasificación semántica avanzada. «Editar clip» conserva audio, inicio y tiempos de subtítulos. Ajusta el inicio y duración antes de exportar; si cambias el corte, revisa también sus subtítulos.
- **Sin Whisper:** pega un JSON con `[{"start":0,"end":8,"text":"Texto autorizado"}]`. No se inventa una transcripción.
- **Enlace:** extrae párrafos de páginas públicas, sin evadir paywalls. Verifica que tengas permiso para reutilizar el texto. Si falla, pega texto autorizado. Los enlaces YouTube/TikTok requieren transcripción pegada; no se descarga audiovisual ajeno. Las fuentes se conservan sin marcar sus afirmaciones como verificadas.
- **Tema:** instala Ollama, descarga un modelo de tu elección con licencia adecuada y define `OLLAMA_MODEL`. El adaptador llama a `/api/generate` en el servidor local, con JSON. Sin modelo el flujo de guion sigue disponible. No se comprobó generación con Ollama en este equipo.
- **Tendencias:** RSS funcional de BBC Mundo, por defecto, para consulta personal. Muestra títulos, enlaces y fechas; no inventa señales de interés ni datos de República Dominicana. País e idioma están visibles y la ausencia de cobertura geográfica se informa. Categoría hace búsqueda literal en títulos; período filtra la fecha. El uso comercial del RSS puede requerir permiso: cambia `RSS_URL` por una fuente autorizada. Hay entrada manual y tres enfoques por tema.

## Datos y trabajos

`workspace/studio.sqlite3` conserva proyectos, trabajos, métricas y el registro de recursos. `uploads/` contiene originales; `jobs/` contiene temporales y `exports/` los resultados. Los trabajos se procesan de uno en uno para limitar presión de memoria. Puedes cancelar procesos FFmpeg/Piper; Whisper comprueba cancelación entre segmentos. Tras reiniciar, los trabajos incompletos quedan en error recuperable. Reintentar crea otro trabajo y mantiene el historial.

El guardado automático tiene una espera de 500 ms. Exportar fuerza el guardado primero y renderiza una instantánea: las ediciones posteriores no cambian un trabajo ya iniciado. Cada exportación tiene nombre único con proyecto, variante e identificador. Los archivos temporales no se purgan automáticamente; revisa su tamaño periódicamente. Conserva copias de `workspace` para respaldar tus proyectos.

Métricas manuales o CSV UTF-8:

```csv
project,variant,platform,period,views,average,watched,interactions,followers
ID_DEL_PROYECTO,A,TikTok,2026-11-01 a 2026-11-07,1000,18,60,45,
ID_DEL_PROYECTO,B,TikTok,2026-11-01 a 2026-11-07,1200,20,66,50,
```

Duración media en segundos y porcentaje visto entre 0 y 100. Los vacíos se conservan como `null`, nunca como ceros. La tabla permite comparar variantes de igual plataforma/período; no contiene resultados de demostración ni conclusiones causales.

Seguridad de enlaces: HTTP/HTTPS en puertos estándar, resolución y comprobación de todas las IP, conexión fijada a IP validada con SNI original, redirecciones comprobadas, bloqueo de IP privadas/reservadas, 2 MB y tiempo de descarga limitado. Se valida tamaño/formato de archivos y se invoca FFmpeg con argumentos, sin shell. Las rutas de medios no exponen SQLite ni `.env`.

## Verificación

```powershell
npm.cmd run typecheck
npm.cmd run build
.\.venv\Scripts\python.exe scripts/verify.py
# Con ambos servidores iniciados:
npx.cmd playwright install chromium
node scripts/ui-check.cjs
```

`scripts/verify.py` requiere los motores opcionales, la voz configurada e internet para el RSS. Produce archivos reales, usa PyAV para decodificar video/audio y guarda `verification.json`. Se verificaron las dos resoluciones, codecs, audio audible, diferencia de duración de pistas inferior a 150 ms, archivos auxiliares, edición persistente, recorte con audio original, video largo de 100 s con transcripción temporal, rechazo de enlaces privados/inaccesibles, proveedor no configurado, cancelación y valores de métricas ausentes. `whisper-verification.json` documenta además una transcripción **real con Whisper tiny** del video largo. Las pruebas de integracion crean sus proyectos, trabajos y medios en workspace/verification, separados del estudio principal.

Playwright crea un storyboard, edita texto, abre exportación y comprueba ausencia de desbordamiento horizontal en escritorio (1440 × 1100) y móvil (390 × 844). Las capturas están en `desktop.png`, `mobile.png`, `editor-desktop.png` y `editor-mobile.png`.

## Alcance pendiente

Quedan pendientes catálogo visual externo con filtros de derechos, generación local de imágenes, publicación vía APIs oficiales, evaluación editorial semántica avanzada y paquetes de tipografías multiplataforma. Las tarjetas de estilo no son paquetes de animación completos. El seguimiento local de rostros, pantalla dividida, lotes, perfiles y revisión privada local ya están implementados en la ampliación. No hay servicio remoto de revisión desplegado, sincronización cloud ni garantía de resultados en plataformas. Ollama, CUDA y otras voces requieren instalación/configuración y pruebas propias. La detección de rostros no identifica al hablante.
