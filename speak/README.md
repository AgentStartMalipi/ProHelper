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

En vivo, las notas solo registran lo que se dijo: no sugieren respuestas. La
evaluación de cómo te fue y qué mejorar sale en las notas finales, cuando la
grabación se detiene.

## Arrancar

Doble clic en `run_speak.bat`. La primera vez crea `.venv-speak`, instala las
dependencias (PySide6, faster-whisper) y copia `.env.example` a `.env`. La
primera vez que pulses Start Listening se descarga el modelo de voz
(`small`, unos 480 MB). Después carga en segundos.

`run_speak.bat notes` abre directamente Notas de llamada.

Diagnóstico sin interfaz (micrófono, modelo de voz y LLM):

    .venv-speak\Scripts\python.exe -m speak --check

Como SCREEN, usa tu login de Claude Code: **no necesitas API key**.

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
- **Generar notas**: tipo `entrevista`, `reunion`, `venta` o `llamada`. La
  pestaña *Preguntas detectadas* sale al instante, por reglas y sin LLM, e
  incluye qué porcentaje hablaste tú.

Todo queda en `data/notes/<fecha>/` (audio, `transcript.md`, `notes.md` y,
si fue en vivo, `transcript_live.md` y `notes_live.md`).

Por consola:

    .venv-speak\Scripts\python.exe -m speak.notes record --mode entrevista
    .venv-speak\Scripts\python.exe -m speak.notes analyze RUTA --mode reunion
    .venv-speak\Scripts\python.exe -m speak.notes analyze RUTA --no-llm

## Configuración (`speak/.env`)

| Variable | Qué hace |
|---|---|
| `LLM_PROVIDER` | `claude_cli` (tu login) o `anthropic` (SDK + `API_KEY`) |
| `LLM_MODEL` | Id completo. `claude-sonnet-5` de serie: medido, primer token ~2,5 s. Haiku 4.5 tardó 28 s en el primer token |
| `STT_MODEL` | `base` (más rápido), `small` (de serie), `medium` / `large-v3` (más preciso, lento en CPU) |
| `STT_LANGUAGE` | `en`, `es` o vacío (autodetectar) |
| `SILENCE_THRESHOLD` | ms para cerrar una pregunta tuya (900) |
| `ANSWER_SILENCE` | ms para cerrar una respuesta tuya (2500) |
| `MAX_SILENCE` | tope: con este silencio siempre se cierra (6000) |
| `CONTEXT_WINDOW` | intercambios que viajan completos al LLM; los anteriores, en una línea |
| `TTS_ENABLED`, `TTS_RATE` | voz del entrevistador (voz de Windows) |
| `LIVE_NOTES_INTERVAL` | segundos entre borradores de notas en vivo (60). `0` = en vivo solo transcripción y preguntas, sin LLM |

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
- **`simulator.py`** no depende de Qt: todo entra por una cola y lo procesa un
  solo hilo. La UI solo escucha callbacks.

## Pruebas

    .venv-speak\Scripts\python.exe -m unittest discover -s speak/tests -t .

Son 43 y no usan micrófono, red ni modelos. El detector de turnos cubre:
pregunta corta, pregunta de varias frases, pausa dentro de una pregunta (con
y sin puntos suspensivos), follow-up, alguien pensando en voz alta, solo
muletillas, afirmación sin pregunta, turno reabierto, transcripción
pendiente, tope de silencio y español. También hay pruebas de punta a punta
del simulador con dobles (pregunta → respuesta → evaluación, aclaración a
mitad de respuesta, botón Terminé), del pipeline de notas y de las notas en
vivo (dos pistas a distinta frecuencia → transcripción Yo/Ellos → borrador).
