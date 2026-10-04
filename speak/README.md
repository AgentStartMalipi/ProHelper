# SPEAK

La parte de voz del helper (la de capturas es **SCREEN**, `run.bat`). Tiene dos
herramientas independientes:

1. **Simulador de entrevistas.** La app hace de entrevistador: genera la
   pregunta según tu CV y el puesto, te la lee en voz alta, tú respondes
   hablando, y **después** de responder te da feedback, un QUICK ANSWER y una
   respuesta modelo.
2. **Notas de llamada.** Grabas una llamada real (con permiso de todos) o
   importas un audio o una transcripción. Saca la transcripción Yo/Ellos y
   notas: preguntas, problemas, decisiones, pendientes, preguntas sin
   responder y temas para estudiar. Con **En vivo**, mientras grabas ya ves
   la transcripción, las preguntas y un borrador de notas.
   - **Copiloto**: en ventas, reuniones, soporte y llamadas, cuando el otro
     pregunta algo te muestra qué responder, sacado de tus documentos y del
     brief que preparaste antes (**🧭 Preparar llamada**).

En modo **entrevista** el copiloto no responde en vivo: soplarte respuestas
mientras te evalúan engaña al entrevistador. Para eso está el simulador, que
te prepara antes. Las notas en vivo solo registran lo que se dijo; la
evaluación de cómo te fue sale en las notas finales.

## Arrancar

Doble clic en `run_speak.bat`. La primera vez crea `.venv-speak`, instala las
dependencias (PySide6, faster-whisper) y copia `.env.example` a `.env`. La
primera vez que pulses Start Listening se descarga el modelo de voz
(`small`, unos 480 MB). Después carga en segundos.

`run_speak.bat notes` abre directamente Notas de llamada.

Diagnóstico sin interfaz (micrófono, de qué salida se graba "Ellos", modelo
de voz y LLM):

    .venv-speak\Scripts\python.exe -m speak --check

Probar cada micrófono con tu voz y saber cuál usar (`probar_microfonos.bat`
hace lo mismo con doble clic; con `--auto` no hay que pulsar Enter). El
resultado queda en `speak/data/mic_test.txt`:

    .venv-speak\Scripts\python.exe -m speak --mics [--auto]

Si "Ellos" no aparece en vivo: el loopback graba **después** del volumen de
Windows (medido: con el volumen bajo, la voz llegó 37 dB por debajo). SPEAK
le sube la ganancia sola a la pista en vivo (hasta ×100), pero si la llamada
suena por otra salida que no es la de Windows por defecto (unos audífonos
USB/Bluetooth), pon esa salida en `LOOPBACK_DEVICE`; `--check` lista las que
hay.

Como SCREEN, usa tu login de Claude Code: **no necesitas API key**.


## ¿Dónde estoy?

Al abrir SPEAK sale una pantalla de inicio con dos opciones: **🎓 Practicar una
entrevista** o **📞 Llamada real**. Cada ventana tiene arriba una franja de
color que dice qué está pasando:

| Color | Significa |
|---|---|
| 🟣 Morada | Práctica: la app es el entrevistador |
| ⚪ Gris | Llamadas, sin grabar (dice si el copiloto se activará) |
| 🔴 Roja | **En llamada**: grabando con copiloto activo, con el reloj |
| 🟠 Naranja | Grabando **solo notas**, sin copiloto (y por qué) |
| 🔵 Azul | Procesando la transcripción y las notas |

El título de la ventana dice lo mismo, para distinguirlas en la barra de tareas.
`run_speak.bat notes` abre directo Llamadas; `python -m speak --practice`, el simulador.

## Simulador

1. A la izquierda: tipo de entrevista, idioma, puesto, empresa, y pega tu CV y
   la descripción del puesto. Se guardan solos (`data/profile.json`).
2. **Start Listening** → el entrevistador pregunta (se ve y se oye).
3. Responde en voz alta. Tu respuesta aparece transcrita en vivo (con ~1-2 s de
   retraso en CPU).
   - Si preguntas algo ("can I assume the array is sorted?"), el
     entrevistador te aclara sin darte la solución, y sigues respondiendo.
   - Tu respuesta se da por terminada tras ~2,5 s de silencio, o al pulsar
     **Terminé** (F9). Si retomas enseguida después de un cierre, se reabre:
     no te corta.
4. Llega la evaluación en streaming: **Feedback** (nota 1-5), **QUICK ANSWER**
   (3-6 puntos para estructurar la respuesta oral) y **Detailed answer** con la
   estructura del tipo de pregunta:

   | Tipo | Estructura |
   |---|---|
   | BEHAVIORAL | STAR, mejorando *tu* historia + el principio que demuestra |
   | CODING | interpretación, enfoque, complejidad, pseudocódigo, Python, edge cases |
   | SYSTEM_DESIGN | requisitos, supuestos, arquitectura, componentes, flujo, tradeoffs, escala |
   | TECHNICAL_CONCEPT | respuesta corta + puntos de apoyo |
   | FOLLOW_UP | modifica la respuesta modelo anterior, no empieza de cero |

5. **Siguiente pregunta**, **Repregunta** (profundiza en lo que dijiste),
   **Regenerate** (otra evaluación de la misma respuesta) o **Clear Context**.
   También puedes escribir una pregunta propia para practicarla.

Cada sesión se guarda en `data/sessions/`.

## Notas de llamada

- **Grabar**: primero hay que marcar que los participantes aceptaron la
  grabación. Graba dos pistas: tu micrófono (`me.wav` → "Yo") y el audio del
  sistema por loopback (`them.wav` → "Ellos"). Así se sabe quién es quién sin
  adivinar voces. **Usa audífonos**; con parlantes el micrófono capta al otro
  (se filtra el eco, pero con audífonos queda perfecto).
- **En vivo** (casilla junto a Grabar, activada de serie): mientras grabas,
  cada pista pasa por Whisper local frase a frase. Las pestañas
  *Transcripción* y *Preguntas detectadas* se llenan al momento (con 1-3 s de
  retraso en CPU), y *Notas* muestra un borrador que Claude reescribe cada
  `LIVE_NOTES_INTERVAL` segundos si hubo conversación nueva. **✨ Actualizar
  notas** lo pide ya. El borrador trae resumen, preguntas y temas, problemas,
  decisiones, pendientes y datos clave. Al detenerse se guardan
  `transcript_live.md` y `notes_live.md`, y la grabación pasa igual por la
  transcripción completa (más precisa), de donde salen las notas finales.
- **Importar audio**: cualquier grabación. Con Whisper local sale un solo
  hablante; con `STT_PROVIDER=assemblyai` (y `ASSEMBLYAI_API_KEY` en `.env`)
  sale diarizada.
- **Importar transcripción**: VTT de Teams/Zoom, o texto `Nombre: frase` con
  `[mm:ss]` opcional. También se puede pegar en el cuadro y corregir nombres a
  mano antes de generar.
- **Generar notas**: tipo `entrevista`, `reunion`, `venta`, `soporte`,
  `arquitectura` o `llamada`. La
  pestaña *Preguntas detectadas* sale al instante, por reglas y sin LLM, e
  incluye qué porcentaje hablaste tú.

Todo queda en `data/notes/<fecha>/` (audio, `transcript.md`, `notes.md` y,
si fue en vivo, `transcript_live.md` y `notes_live.md`).

## Copiloto

Tres piezas:

1. **Carpeta de conocimiento** (`KB_DIR`, de serie `speak/data/knowledge`):
   tus PDF, Word, PowerPoint, Excel, Markdown, texto y CSV de siempre
   (portafolio, fichas técnicas, precios, casos de éxito), y archivos
   técnicos: draw.io (salen componentes y conexiones), YAML, Terraform, SQL,
   PlantUML, Mermaid. De Word salen tablas, cuadros de texto, encabezados y
   pies; de PowerPoint, tablas y **notas del orador**; de Excel, cada hoja con
   los valores de las fórmulas y los porcentajes. Los CSV de Excel en español
   (separados por `;`) y los textos en UTF-16 o ANSI se leen bien. Un PDF
   **escaneado** (solo imagen) no tiene texto: aparece como error con el
   aviso de adjuntar una captura para que Claude la lea. Se indexa sola al
   abrir Notas de llamada, en segundo plano, y solo relee los archivos que
   cambiaron. Todo local.
2. **🧭 Preparar llamada** (antes de la llamada): un mini chat. Le cuentas de
   qué va ("mañana con el gerente de planta de Acme, quieren bajar vapor,
   estudia la propuesta v2"), adjuntas o pegas los documentos de esa llamada
   (propuesta, correos, notas del cliente), y te pregunta lo que falte,
   detecta huecos y propone lo que te pueden preguntar. **✨ Armar brief**
   escribe el brief: contexto y objetivo, mensajes clave, datos con su
   fuente, preguntas probables con respuesta preparada, objeciones y lo que
   no hay que prometer. El brief es editable y queda guardado
   (`data/prep/current.json`) hasta que pulses **Nueva preparación**.
3. **En vivo** (panel derecho de Notas de llamada, grabando con **En vivo**):
   cuando el otro termina una pregunta, busca en el brief y los documentos y
   Claude escribe **Respuesta** (lista para decir), hasta 3 datos de apoyo y
   la fuente. Si no está en tus fuentes lo dice (⚠) y propone una salida
   segura; no inventa precios, cifras ni compromisos. Medido con
   `claude-sonnet-5`: primer texto ~3 s, respuesta completa ~6-7 s.
   **⚡ Responder ahora (F8)** responde a lo último que dijo el otro aunque no
   parezca pregunta. **📌 Siempre visible** deja la ventana encima de Teams o
   Zoom. Al detener queda `copilot.md` en la carpeta de la llamada.

**Guía del copiloto** (en Preparar llamada, como el pre-prompt de SCREEN):
quién eres y cómo quieres que responda. Pesa más que el formato, el largo, el
tono y el idioma de serie. Lo que no puede cambiar es que no invente cifras
ni compromisos. Se aplica a las respuestas en vivo, al chat y al brief, y se
lee en cada respuesta, así que cambiarla a mitad de llamada vale para la
siguiente. No se borra con **Nueva preparación**. Plantillas:

| Plantilla | Para qué |
|---|---|
| Venta consultiva B2B | Traduce los datos a lo que gana el cliente, cierra con una pregunta de descubrimiento y no ofrece descuentos |
| Manejo de objeciones | Reconoce, responde con dato o caso, y confirma si quedó resuelto. No habla mal de la competencia |
| Soporte técnico | Primero lo que falta para diagnosticar, luego pasos numerados; no promete fechas |
| Reunión con gerencia | Conclusión o cifra primero, riesgos con impacto, y qué decisión se necesita |
| Solo la frase (lo más rápido) | Una línea de máximo 25 palabras |
| Solutions architect | Recomendación + su tradeoff; si depende de un requisito desconocido, la pregunta que lo aclara; no compromete costos ni dimensionamiento |
| Siempre en español | Aunque el otro hable en inglés |

### Exploración y archivos en plena llamada (p. ej. arquitecto de soluciones)

Modo **`arquitectura`**: llamada técnica con un cliente donde tú eres el
arquitecto. Te pasan el contexto (diagramas, documentos) y hay que ver si
alcanza para proponer, y qué preguntar.

- **🔍 ¿Qué me falta? (F9)**, pestaña *Exploración* del copiloto: con la
  conversación (si la hay), el brief y los documentos da un **veredicto** (¿alcanza
  para proponer?), las **3 próximas preguntas** priorizadas por cuánto cambian
  la solución, la **cobertura** por dimensión (✅ / ◐ / ❌: objetivo, volumen y
  picos, arquitectura actual, integraciones, datos, SLA/latencia/RPO/RTO,
  seguridad, cumplimiento, infraestructura, operación, presupuesto y
  decisores, dolores) y un **Ojo** con contradicciones y supuestos no
  confirmados. Antes de la llamada sirve para ver si el contexto que te
  dieron es suficiente (también en Preparar llamada, donde el resultado
  queda en el chat y entra al brief). Grabando en vivo se reescribe sola cada
  `DISCOVERY_INTERVAL` segundos con conversación nueva, y al adjuntar algo.
  Otros modos tienen sus dimensiones: en `venta`, necesidad, impacto,
  decisores, presupuesto, plazos, competencia; en `soporte`, síntoma,
  entorno, reproducción, lo que ya se probó.
- **📎 Adjuntar / 📋 Pegar** (panel del copiloto): en cualquier momento,
  también en plena llamada. Los documentos entran al instante. Las
  **imágenes** (capturas de diagramas) las describe Claude una vez
  (~12-15 s): componentes, conexiones, zonas, y las dudas de lo que el dibujo
  no confirma; esa descripción queda buscable como un documento más.
- Las notas finales en modo `arquitectura` traen arquitectura actual,
  requisitos, restricciones y supuestos, riesgos técnicos, huecos de
  información con la pregunta para cada uno, opciones esbozadas y próximos
  pasos. Al detener queda `exploracion.md` en la carpeta de la llamada.

Cuándo da la pregunta por terminada (la gente hace pausas a mitad de una
idea): la pregunta es **todo** lo que el otro dijo desde tu última
intervención. Responde cuando empiezas a hablar tú o tras `COPILOT_QUIET_S`
de silencio (3 s si la frase quedó colgada: "…and", "porque", "…"), y nunca
con audio suyo aún sin transcribir. Si ya respondió y el otro sigue, rehace la
respuesta con la pregunta completa en el mismo sitio.

La búsqueda es léxica (BM25) con tildes normalizadas y raíces de 5 letras
("audit" encuentra "auditoría"), más un diccionario bilingüe de unos 100
términos comerciales y técnicos para cuando preguntan en inglés sobre
documentos en español o al revés ("guarantee" → "garantía", "¿cómo cifran los
datos?" → "encrypted"). Medido con `python -m speak.tests.retrieval_eval`
(acierto en los 3 primeros): en el mismo idioma 12/12; cruzadas escritas
aparte del diccionario, 11/14 con él y 5/14 sin él. Lo que no encuentra son
paráfrasis sin palabras en común ("upfront payment" por "anticipo"). Si todo
lo cargado cabe en el contexto (unos 6.000 caracteres), va entero sin buscar.

Por consola:

    .venv-speak\Scripts\python.exe -m speak.notes record --mode entrevista
    .venv-speak\Scripts\python.exe -m speak.notes analyze RUTA --mode reunion
    .venv-speak\Scripts\python.exe -m speak.notes analyze RUTA --no-llm

## Configuración (`speak/.env`)

| Variable | Qué hace |
|---|---|
| `LLM_PROVIDER` | `claude_cli` (tu login) o `anthropic` (SDK + `API_KEY`) |
| `LLM_MODEL` | Id completo. `claude-sonnet-5` de serie: medido, primer token ~2,5 s. Haiku 4.5 tardó 28 s en el primer token |
| `STT_PROVIDER` | `faster_whisper` (local, gratis) o `deepgram` (nube, Nova-3: mucho mas preciso, entiende espanol e ingles mezclados; $200 gratis en console.deepgram.com, llave en `DEEPGRAM_API_KEY`) |
| `STT_MODEL` | `base` (más rápido), `small` (de serie), `medium` / `large-v3` (más preciso, lento en CPU) |
| `STT_LANGUAGE` | idioma del simulador: `en`, `es` o vacío (autodetectar) |
| `NOTES_STT_LANGUAGE` | idioma que se habla en Notas de llamada. Vacío (de serie): lo detecta en las primeras frases de cada hablante y lo fija. Medido: con `en`, una llamada en español sale traducida al inglés (109% de error); detectar en cada frase es 2× más lento |
| `STT_LIVE_MODEL` | modelo de Notas en vivo (`base`). Medido en una laptop de 8 hilos: 11,8 s de voz en 8 s con `base`, 22,6 s con `small` (no da abasto en vivo), 3,9 s con `tiny` (mucho peor). La transcripción final sigue con `STT_MODEL` |
| `STT_THREADS` | hilos de Whisper; `0` = todos (el default de la librería son 4) |
| `MIC_DEVICE` | micrófono (índice que da `--mics`); vacío = el de Windows. Cualquier índice sirve: si el micrófono no acepta 16 kHz se abre a su frecuencia y se remuestrea |
| `LOOPBACK_DEVICE` | de qué salida se graba "Ellos": parte del nombre (`Jabra`, `Headphones`); vacío = la salida por defecto de Windows |
| `SILENCE_THRESHOLD` | ms para cerrar una pregunta tuya (900) |
| `ANSWER_SILENCE` | ms para cerrar una respuesta tuya (2500) |
| `MAX_SILENCE` | tope: con este silencio siempre se cierra (6000) |
| `CONTEXT_WINDOW` | intercambios que viajan completos al LLM; los anteriores, en una línea |
| `TTS_ENABLED`, `TTS_RATE` | voz del entrevistador (voz de Windows) |
| `LIVE_NOTES_INTERVAL` | segundos entre borradores de notas en vivo (60). `0` = en vivo solo transcripción y preguntas, sin LLM |
| `COPILOT_ENABLED` | copiloto en vivo (`true`) |
| `KB_DIR` | carpeta de conocimiento; vacío = `speak/data/knowledge`. También se elige en Preparar llamada |
| `COPILOT_QUIET_S` | segundos de silencio del otro para dar su pregunta por terminada (1.2) |
| `DISCOVERY_INTERVAL` | segundos entre exploraciones en vivo, si hubo conversación nueva (90). `0` = solo con el botón / F9 |

Las API keys solo van en `.env`, nunca en el código; ⚙ Settings no las toca.

## Cómo funciona

```
Micrófono ─► audio_capture (VAD por energía + segmentador de frases)
              │ frases                          │ ticks de silencio
              ▼                                 ▼
          transcriber (faster-whisper) ─► turn_detector ─► simulator
                                                            │
             context_manager ◄── question_classifier ◄──────┤
                    │                                       ▼
                    └──────────► answer_generator ─► llm_client (streaming) ─► UI
```

- **`turn_detector.py`** decide cuándo terminó un turno combinando silencio,
  cómo termina la frase ("...find the maximum" o "...and" piden más silencio),
  interrogativos y peticiones ("tell me", "walk me through", "cuéntame"),
  aperturas conductuales que suelen seguir con otra frase, y contexto (las
  repreguntas). No cierra mientras falte texto por transcribir, y reabre el
  turno si la persona retoma enseguida. Estados: `LISTENING`,
  `SPEAKER_TALKING`, `POSSIBLE_END`, `QUESTION_COMPLETE`,
  `GENERATING_RESPONSE`. El mismo análisis marca preguntas en Notas de
  llamada.
- **`transcriber.py`**: la interfaz `SpeechToText` con faster-whisper (local) y
  AssemblyAI (archivos). Otro backend = otra clase.
- **`notes/live.py`**: Notas en vivo. Recibe copia del audio de la
  grabadora, lo pasa a 16 kHz, lo segmenta con el mismo VAD del simulador y
  lo transcribe con un `IncrementalTranscriber` por pista. Rellena con
  silencio según el reloj, porque el loopback de WASAPI no entrega nada
  mientras no suena nada y la última frase de "Ellos" quedaría abierta.
- **`knowledge.py`**: lee los documentos (Word, PowerPoint y Excel directo
  de su XML, PDF con `pypdf`), los parte en trozos de ~900 caracteres y los
  busca con BM25. Sin modelos ni descargas: el índice de la carpeta se arma
  al indexarla (con 9.000 trozos, unos segundos en segundo plano) y cada
  búsqueda tarda milisegundos. Los adjuntos van en un índice aparte que se
  rearma al instante.
- **`notes/copilot.py`**: `PrepSession` (chat y brief) y `Copilot` (cuándo
  responder y la respuesta en streaming). `Copilot.step()` es una iteración
  pura, así que las pruebas controlan el reloj.
- **`simulator.py`** no depende de Qt: todo entra por una cola y lo procesa un
  solo hilo. La UI solo escucha callbacks.

## Pruebas

    .venv-speak\Scripts\python.exe -m unittest discover -s speak/tests -t .

No usan micrófono, red ni modelos. El detector de turnos cubre:
pregunta corta, pregunta de varias frases, pausa dentro de una pregunta (con
y sin puntos suspensivos), follow-up, alguien pensando en voz alta, solo
muletillas, afirmación sin pregunta, turno reabierto, transcripción
pendiente, tope de silencio y español. También hay pruebas de punta a punta
del simulador con dobles (pregunta → respuesta → evaluación, aclaración a
mitad de respuesta, botón Terminé), del pipeline de notas y de las notas en
vivo (dos pistas a distinta frecuencia → transcripción Yo/Ellos → borrador),
de la base de conocimiento (archivos generados con Word, PowerPoint y Excel
reales y PDF de verdad en `speak/tests/fixtures`: tablas, cuadros de texto,
notas del orador, fórmulas, porcentajes, PDF escaneado, CSV de Excel con `;`,
UTF-16, ANSI, archivos bloqueados o dañados, caché, búsqueda cruzada entre
idiomas, índice consistente al adjuntar mientras se busca) y del
copiloto (espera al silencio, frase colgada, audio sin transcribir, pausa a
mitad de idea que rehace la respuesta, Responder ahora, nunca en entrevista,
brief y guía de la preparación) y de arquitectura (draw.io normal y
comprimido, imagen → descripción buscable, exploración antes y durante la
llamada, cuándo se refresca sola).
