# Producción por lotes y revisión privada

La ampliación conserva el editor y la identidad visual clara con verdes del proyecto. No se cambió `scripts/start.ps1`, no se añadió facturación y no hace falta una cuenta para producir o exportar localmente.

## Repetir la prueba principal en Windows

Si ya tienes Clip Studio instalado, actualiza las dependencias de Python:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-optional.txt
npm.cmd ci
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

Abre http://127.0.0.1:3000. Si ya había un backend iniciado, detenlo antes de arrancar el nuevo; no ejecutes dos instancias sobre el mismo directorio de trabajo.

Para reproducir exactamente las dependencias de Python probadas en Windows con Python 3.14, se incluye `backend/requirements-lock.txt`. Puedes instalarlo con `.\.venv\Scripts\python.exe -m pip install -r backend/requirements-lock.txt`. En otros entornos usa los requisitos generales/optativos y comprueba las dependencias disponibles de ese sistema. `pip check` pasó sin conflictos en el equipo de prueba.

1. En **Marcas → Nuevo perfil**, escribe un nombre. Elige color de acento, fondo, tipografía, colores/tamaño/posición de subtítulos, posición del texto, logo y plantilla de portada. Pulsa **Guardar perfil**. Las advertencias identifican fuentes o logos que faltan; reemplázalos antes de exportar.
2. En **Lotes → Crear lote de clips**, carga un video propio o autorizado, confirma la autorización, elige cantidad, duración objetivo y el perfil de marca. El espacio de cliente es opcional: puedes dejar «Mi estudio individual».
3. Pulsa **Crear lote de clips**. La primera vez se descarga el modelo Whisper si no está en caché. La selección usa una sola transcripción; al regenerar o crear otro lote del mismo archivo y modelo, se reutiliza. Si ya tienes una transcripción, abre la opción manual y pega segmentos JSON con `start`, `end`, `text` y palabras opcionales. Los tiempos son segundos desde el inicio del original.
4. En la bandeja, reproduce el original de cada candidato, revisa rango/duración/motivo y abre **Título, descripción, portada y ganchos**. Guarda los textos. **Editar en el editor existente** permite cambiar cortes, subtítulos, audio y encuadre. **Volver a la bandeja del lote** fuerza el guardado y conserva los cambios.
5. Pulsa **Aprobar** en dos clips y **Descartar** en un tercero. Cualquier decisión se puede revertir con «Pendiente» o con la decisión contraria. Elige versión A o B de cada aprobado. Los dos ganchos son textos editables en pantalla durante los primeros tres segundos; no reemplazan ni inventan lo que dijo la persona. La narración original se conserva. Para cambiar narración usa las herramientas de voz del editor.
6. Selecciona 720p o 1080p y pulsa **Exportar aprobados**. Espera a «ZIP · Listo» y pulsa **Descargar ZIP**. Incluye MP4, portada, publicación, SRT y créditos de cada resultado disponible, más `resumen.json`. Los nombres contienen proyecto, variante y trabajo, sin colisiones. Un descartado no se incorpora.

Si uno falla, los otros MP4 y el ZIP parcial permanecen disponibles. Corrige el recurso/corte en el editor y pulsa **Reintentar fallidos y actualizar ZIP**. Los trabajos correctos se reutilizan. Repetir la solicitud no vuelve a renderizar la misma edición y variante. «Cancelar pendientes» conserva proyectos, decisiones y resultados terminados.

La huella incluye la revisión del motor de render. Una actualización del motor puede producir un resultado nuevo conservando los archivos previos; las solicitudes repetidas dentro de la misma revisión reutilizan el trabajo.

El resumen muestra clips propuestos, aprobados y exportados. El progreso representa el promedio de trabajos de la última exportación; un trabajo terminado con error o cancelado cuenta como procesado, y se muestran los errores aparte. No se calculan horas ahorradas ni se predice rendimiento. La cola es FIFO, con un solo trabajo pesado a la vez; FFmpeg usa dos hilos de codificación por defecto (`CLIP_RENDER_THREADS`, entre 1 y 8).

## Marcas y compatibilidad visual

Los perfiles se guardan en `brand_profiles`; los proyectos reciben un `brandSnapshot` independiente. Modificar el perfil no cambia proyectos ya editados ni versiones de revisión. **Duplicar** crea otro perfil. Al reaplicar desde un lote, selecciona los clips y confirma que se reemplazarán colores, tipografía, logo, subtítulos, posiciones y portada. Texto, audio, cortes y encuadre se conservan.

El perfil antiguo de `/api/brand` y sus controles anteriores siguen funcionando. Los perfiles nombrados de **Marcas** se administran por separado. Los proyectos antiguos no necesitan un `brandSnapshot`: mantienen los valores previos y los valores por defecto del render.

La tarjeta interactiva es orientativa. **Previsualizar marca en MP4** genera una prueba visual sin narración con el motor real de exportación y la configuración actual del formulario. Cambiar el perfil invalida esa vista previa. El enlace **Ver MP4 y revisar el encuadre** abre el archivo real, que es la misma vista previa audiovisual utilizada para exportación y revisión. No hay un segundo motor que interprete de manera distinta los datos del render. La portada propia se genera aparte a partir del texto editable y de la misma marca.

Las pruebas comprobaron el logo tanto en el PNG como en un fotograma decodificado del MP4, los colores y la configuración ASS aplicada, las versiones A/B y una portada distinta de la tarjeta del video. Arial/Georgia/Consolas dependen de las fuentes instaladas. En Linux se ofrece DejaVu Sans como alternativa; si falta una fuente, hay una advertencia y el render utiliza la disponible. Para coincidir entre equipos, instala la misma fuente o elige una disponible en ambos. Linux no se ejecutó en este equipo.

## Encuadre de entrevistas

En el **Inspector → Encuadre inteligente**:

- **Manual** conserva el zoom y desplazamiento horizontal existentes y siempre está disponible.
- **Seguimiento** analiza solo la escena a 640 píxeles de ancho máximo y dos muestras por segundo. OpenCV detecta rostros frontales y comprueba ojos para reducir falsos positivos; los asocia por proximidad espacial, suaviza movimientos y conserva el último encuadre si desaparecen brevemente. Elige el rostro que seguirá el clip. Los números son pistas espaciales temporales, no identidades.
- **Pantalla dividida** coloca dos encuadres en columnas verticales. Elige el rostro de cada lado o define cada posición a mano. No exige detectar rostros.
- **Corregir encuadre por tramo** permite añadir posiciones desde un segundo de la escena. Los datos se guardan en la escena y el render los interpola. Puedes quitar correcciones o volver a Manual. Para ignorar correcciones anteriores, elimínalas; cambiar el modo no las borra silenciosamente.

Esto **no identifica al hablante**. No se implementa diarización audiovisual ni se deduce quién habla a partir de un rostro. Con audio mezclado no hay señal suficiente: la app lo dice y deja elegir. Los movimientos rápidos, perfiles, oclusiones, gafas u ojos poco visibles pueden impedir detectar una cara. Revisa el MP4 real. Analizar rostros es un trabajo cancelable y sus resultados solo se aplican cuando pulsas **Aplicar detección**.

Se probaron videos de un rostro, dos rostros, ningún rostro y desaparición temporal, usando una fotografía de prueba de dominio público. Se comprobaron los tres modos renderizados y que cambiar Manual produce fotogramas distintos en el archivo final. Los archivos y el informe están en `workspace/framing-verification` y `framing-verification.json`.

## Espacios y revisión de versiones

**Clientes** se desbloquea con una clave local, sin cuenta ni proveedor externo:

```powershell
Get-Content workspace/owner-access.txt
```

Introduce su contenido en «Clave del propietario». La sesión utiliza una cookie HttpOnly/SameSite. Esta clave autoriza al propietario; para un revisor crea un enlace por versión, y para un colaborador crea una clave limitada a los clientes seleccionados. El propietario puede revocar colaboradores con `POST /api/collaborators/{id}/revoke`; la interfaz muestra su identificador al crearlo. Una clave de colaborador se introduce en el mismo formulario local.

1. Crea un espacio y asocia una marca si quieres. Puedes crear un lote directamente en ese espacio o copiar un proyecto individual con **Copiar al espacio**. La copia de un proyecto también duplica sus medios para no restringir el original individual.
2. Abre el editor y genera un MP4. Vuelve a **Clientes**, pulsa **Actualizar**, elige el render terminado y **Crear revisión de esta versión**.
3. La revisión guarda una copia inmutable del MP4 seleccionado, la instantánea del proyecto, su hash y el número de versión. Los medios de revisión están en `private_reviews`, fuera de los directorios estáticos.
4. Reproduce la vista previa real, introduce un segundo exacto o usa la posición del reproductor y escribe un comentario. Se puede responder, resolver y reabrir. Los comentarios y decisiones registran autor, rol, versión y fecha.
5. Aprueba esa versión o solicita cambios. Un render nuevo crea otra revisión pendiente y conserva el historial de las anteriores. Reusar el mismo render no crea versiones duplicadas.
6. **Crear enlace local privado** produce un acceso limitado a un cliente, un clip y esa versión, con vencimiento y revocación. Comprueba el enlace en otra ventana/contexto sin sesión de propietario. Un invitado no recibe permiso para el editor, otros clientes, otros medios ni versiones posteriores.

El servidor comprueba autorización antes de servir datos, medios y acciones. También bloquea copiar una referencia a un medio privado dentro de un proyecto individual para eludir permisos. Los flujos individuales anteriores continúan siendo locales y no requieren autenticación; los espacios de agencia sí exigen su sesión local.

### Acceso desde fuera de la PC

**No se configuró ni se desplegó un servicio remoto.** El arranque sigue escuchando solo en `127.0.0.1`. «Compartir fuera de esta PC» explica que falta el servicio y permite descargar la vista previa. No se sube ningún original ni preview. No se ha probado revisión remota en un entorno real.

Un adaptador remoto futuro deberá solicitar confirmación de la vista previa concreta antes de subirla, usar HTTPS, conservar permisos por cliente/clip/versión, revocación y vencimiento, y autorizar cada lectura, comentario o decisión en el servidor remoto. No basta con publicar la carpeta `media` ni reenviar el puerto del editor. En esta entrega se probaron los controles de acceso, enlaces vencidos y revocados **localmente**, sin declarar una infraestructura remota que no existe.

## Rendimiento e importación

El CSV anterior sigue funcionando en **Rendimiento**. La nueva pantalla **Análisis** añade previsualización y corrección de asociaciones antes de guardar. Acepta identificador de proyecto, identificador de clip o título; un título repetido se marca ambiguo y requiere elegir el proyecto. Las filas se validan antes de guardar la transacción.

Columnas anteriores: `project,variant,platform,period,views,average,watched,interactions,followers`. Nuevas opcionales: `account,publicationId,publishedAt,window,hookType,duration,template,format`. Usa porcentajes de 0 a 100 y duración/media en segundos. Vacío significa dato faltante y cero sigue siendo cero.

```csv
project,variant,platform,account,publicationId,period,window,views,average,watched,interactions,followers,hookType,duration,template,format
ID_CLIP,A,TikTok,@mi_cuenta,publicacion-01,2026-11-01 a 2026-11-03,48h,1000,18,60,40,,pregunta,30,Podcast,9:16
ID_CLIP,B,TikTok,@mi_cuenta,publicacion-02,2026-11-01 a 2026-11-03,48h,900,16,53,30,,dato,30,Podcast,9:16
```

Con `publicationId`, la identidad usa cuenta, plataforma e identificador de publicación más ventana: una reimportación actualiza ese registro, incluso si corriges su asociación. Sin identificador ni fecha de publicación se deduplican filas idénticas; para distinguir publicaciones distintas del mismo clip o actualizar sus cifras, aporta `publicationId`. No se adivina que dos publicaciones son la misma. Los datos antiguos no se eliminan ni se reinterpretan como si tuvieran una cuenta conocida.

Las comparaciones separan cuenta, plataforma y ventana. Una cuenta sin registrar se muestra como tal y no produce conclusiones. Se puede filtrar gancho, duración máxima, plantilla y formato. Los promedios excluyen valores faltantes e indican su N. Para una observación de porcentaje visto se exigen dos tipos de gancho con al menos cinco publicaciones medidas cada uno. Sigue siendo una observación descriptiva; no controla audiencia, fecha, inversión ni otros factores, y no atribuye causalidad. La duración tomada del proyecto al importar se marca internamente como `projectSnapshot`; para el dato publicado exacto, inclúyelo en el CSV.

**Probar plantilla y gancho** crea otro proyecto y lo identifica como hipótesis. No promete repetir el resultado ni altera el proyecto medido.

## Migraciones y respaldo

Se usan migraciones aditivas y transaccionales:

| Versión | Nombre | Cambio |
|---|---|---|
| 1 | `legacy_baseline` | Reconoce/crea las tablas JSON existentes sin reescribir proyectos. |
| 2 | `production_workspaces` | Añade perfiles, lotes, transcripciones, clientes, revisiones, capacidades de revisión, colaboradores y registro de importaciones. |
| 3 | `idempotent_requests` | Añade la asociación única entre huella de solicitud y trabajo. |
| 4 | `private_job_scopes` | Completa el alcance de cliente en trabajos auxiliares anteriores que referencian proyectos o medios privados, sin modificar proyectos. |

`schema_migrations` registra la ejecución. Antes de migrar una base existente se genera `studio.before-vN.sqlite3` para la versión de destino (actualmente v4), si ese respaldo aún no existe. Todas las sentencias pendientes se aplican en una transacción; ante un fallo, se revierte y la API de producción informa un error recuperable. Se suspende el acceso a los datos mientras la migración falla, evitando perder los controles de privacidad. Corrige el problema (por ejemplo, permisos o espacio en disco) y reinicia. Los respaldos no se restauran automáticamente sobre datos nuevos.

La línea base de esta sesión está en la ruta registrada por `baseline-location.json`: copia de fuentes principales, backup SQLite con la API de backup, datos de prueba separados e informe con exportaciones 720p y 1080p. No había repositorio Git. `compatibility-verification.json` comprueba que los proyectos previos y `scripts/start.ps1` siguen intactos. No se restablecieron archivos ni se limpió el directorio de trabajo.

## Verificación reproducible

Desde la raíz, con las dependencias y voz de README instaladas:

```powershell
npm.cmd run typecheck
npm.cmd run build
.\.venv\Scripts\python.exe scripts/verify-existing-project.py
.\.venv\Scripts\python.exe scripts/verify.py
.\.venv\Scripts\python.exe scripts/verify-production.py
.\.venv\Scripts\python.exe scripts/verify-framing.py
.\.venv\Scripts\python.exe scripts/verify-review.py
.\.venv\Scripts\python.exe scripts/verify-analytics.py
.\.venv\Scripts\python.exe scripts/verify-restart.py
.\.venv\Scripts\python.exe scripts/verify-whisper-batch.py
```

`verify-existing-project.py` abre una copia SQLite del proyecto más antiguo, modifica la copia y comprueba 720p/1080p con voz, subtítulos y conservación de campos desconocidos; verifica que el original siga idéntico. `verify.py` crea el video narrado utilizado en la prueba de Whisper; `verify-production.py` crea el original de barras y tono empleado por revisión, reinicio y navegador. `verify-framing.py` descarga una foto de prueba de dominio público si aún no está guardada. RSS, extracción pública y primera descarga de modelos requieren internet; las otras operaciones son locales. Los scripts de integración usan subdirectorios de prueba independientes y no sobrescriben proyectos del estudio.

Con ambos servidores del estudio iniciados:

```powershell
npx.cmd playwright install chromium
node scripts/ui-check.cjs
node scripts/production-ui-check.cjs
```

Las pruebas de navegador crean registros identificados `Marca UI`, `Lote UI` y `Cliente UI` con medios generados para prueba en el estudio activo. No modifican proyectos previos. Las capturas nuevas y el ZIP descargado están en `workspace/ui-production-check`; se comprobaron escritorio 1440 × 1050 y móvil 390 × 844.

Informes: `production-verification.json`, `framing-verification.json`, `review-verification.json`, `analytics-verification.json`, `restart-verification.json`, `whisper-batch-verification.json`, `production-ui-verification.json` y los informes anteriores. La prueba de Whisper instrumenta la llamada real del motor y comprueba una sola invocación entre dos lotes y una regeneración. La de reinicio levanta un backend de prueba en un puerto local libre, cancela trabajos, reinicia de verdad y reintenta una instantánea interrumpida, conservando edición y resultados.
