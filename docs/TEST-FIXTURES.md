# Material de prueba

- Barras/figuras `testsrc2` y tono `sine`: generados por FFmpeg para pruebas propias, sin material audiovisual de terceros.
- Logo rojo y tarjetas: generados con Pillow, exclusivamente para validar posición, color y portadas.
- Voz española: Piper con `es_ES-sharvard-medium`, con condiciones y atribución en [PROVIDERS.md](PROVIDERS.md).
- Rostro de prueba: fotografía NASA de Eileen Collins distribuida como `skimage.data.astronaut`. La [documentación oficial de scikit-image](https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut) la identifica como dominio público, sin restricciones de copyright conocidas. [Archivo usado](https://raw.githubusercontent.com/scikit-image/scikit-image/v0.25.2/skimage/data/astronaut.png). Las pruebas componen una o dos copias de la misma imagen, desplazan la posición y ocultan un tramo. No representan una entrevista real ni identifican hablantes.

Los resultados sintéticos están identificados como pruebas y no sustituyen las integraciones funcionales: FFmpeg renderiza archivos reales y la prueba dedicada invoca Whisper sobre audio español real generado localmente.
