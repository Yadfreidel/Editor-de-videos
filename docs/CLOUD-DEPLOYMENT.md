# Servidor privado en internet

GitHub Pages publica la interfaz estática. Python, FFmpeg, Piper y Whisper se ejecutan en un servicio Docker separado que también sirve la interfaz completa bajo el mismo dominio HTTPS. Así el teléfono puede iniciar sesión y reproducir videos privados sin depender de cookies de terceros.

## Despliegue preparado

`render.yaml` define un servicio Render de una instancia con disco persistente de 10 GB y despliegue automático desactivado. El plan `standard` (1 CPU, 2 GB) es de pago. Crear el Blueprint requiere una cuenta conectada y aprobar previamente el coste vigente. Este archivo no crea recursos por sí solo.

1. Conecta el repositorio en Render y crea un Blueprint usando `render.yaml` después de aprobar el presupuesto.
2. Espera a que se construyan la interfaz y los modelos de voz/transcripción. El disco se monta en `/data` al arrancar.
3. Obtén `CLIP_OWNER_KEY` desde las variables privadas de Render y guárdala en tu gestor de contraseñas. Entra en la URL HTTPS del servicio con esa clave. No la añadas a GitHub ni al código del navegador.
4. Comprueba crear un proyecto, generar un MP4, descargarlo y volver a abrir el proyecto tras reiniciar el servicio.

El plan gratuito de Render no conserva un disco persistente. El servicio procesa una tarea a la vez; los videos largos pueden tardar y no hay garantía de capacidad para múltiples usuarios simultáneos. El contenedor incluye modelos CPU; no incluye Ollama. Los datos actuales del PC no se copian automáticamente. Mantén copias de seguridad independientes del disco.

## Seguridad y configuración

En remoto son obligatorios `CLIP_REMOTE=true` y una `CLIP_OWNER_KEY` de al menos 32 caracteres. El servidor rechaza el inicio si falta la clave. Las sesiones usan cookies HttpOnly, Secure y SameSite Strict. API, archivos y documentación requieren acceso; los enlaces de revisión tienen su propio token revocable. El dominio debe usar HTTPS. No publiques el puerto interno sin TLS delante.

`CLIP_WORKSPACE=/data`, `CLIP_FRONTEND_DIR=/app/frontend`, `PORT` y `RENDER_EXTERNAL_URL` se resuelven en el contenedor/proveedor. Se permite una instancia y un proceso para SQLite y la cola local. El límite de subida configurado es 256 MB. Git y Docker excluyen `.env`, claves, modelos locales y archivos de usuario.

## Validación

`python scripts/verify-cloud.py` comprueba el aislamiento de acceso, cookies HTTPS, MP4 narrado, permisos por cliente y revisiones privadas en un espacio de prueba. El workflow `cloud-container.yml` construye la imagen Linux y prueba modelos reales, MP4, transcripción, exportación ZIP, revisión y persistencia tras reiniciar. Ese workflow verifica el contenedor; no lo publica en internet.

Fuentes: https://render.com/docs/blueprint-spec, https://render.com/docs/disks, https://render.com/docs/free y https://render.com/pricing.
