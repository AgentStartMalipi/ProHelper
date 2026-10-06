# helper

Dos herramientas en una carpeta:

| | Qué hace | Arranque |
|---|---|---|
| **SCREEN** | Capturas de pantalla → Claude te dice qué ve (este documento) | `run.bat` |
| **SPEAK** | Simulador de entrevistas por voz, y notas de llamada con copiloto: preparación con tus documentos, respuestas y exploración en vivo ([speak/README.md](speak/README.md)) | `run_speak.bat` (notas: `run_speak.bat notes`) |

Cada una tiene su entorno (`.venv` y `.venv-speak`), así que las dependencias
pesadas de SPEAK (PySide6, faster-whisper) no tocan a SCREEN.

# SCREEN

Un asistente visual que vive en una esquina de la pantalla. Abres una sesión,
aprietas `Ctrl+Shift+C`, y Claude te dice qué ve en tu pantalla — en dos o tres
frases, sin sacarte de lo que estabas haciendo.

Todas las capturas de una sesión entran en la **misma** conversación, así que
Claude ve las anteriores: la quinta pregunta no necesita re-explicar nada.

## Arrancar

Doble clic en `run.bat`. La primera vez prepara el entorno (un minuto); después
abre directo.

Requisitos: Windows, Python 3.10+, y Claude Code instalado y con sesión
iniciada (`claude` tiene que funcionar desde una terminal). **No necesitas API
key**: el helper invoca el CLI, que reutiliza tu login.

## Usar

1. **Nueva sesión** → eliges qué capturar y, si quieres, escribes un pre-prompt
   (el contexto que se mantiene todo el rato). Puedes dejarlo vacío.
2. `Ctrl+Shift+C` o `Alt+3` desde donde sea. El widget se esconde solo para no
   salir en su propia foto.
3. La respuesta aparece en el panel. **Copiar** manda la última al
   portapapeles.

Las respuestas **se acumulan en la sesión**: cada nueva se añade debajo,
separada por una raya con su número, y las anteriores siguen ahí. El panel se
ajusta al alto de la última, así que no crece sin control — el historial vive
encima y se alcanza con la rueda del ratón o con `Alt+5`.

La cajita de abajo es para una pregunta puntual: escribes ahí y Enter captura
con esa pregunta en vez del pre-prompt.

**Usar pasados** (la casilla debajo de la cajita, marcada por defecto): con ella
marcada, Claude recuerda las capturas anteriores de la sesión. Desmárcala para
preguntas sueltas: esa captura va sola (pre-prompt + la imagen actual). Cada
sesión recuerda su propia casilla.

Cómo recuerda se elige en `⚙` → **Cómo recuerda "Usar pasados"**:

- **Resumen** (de serie). No re-envía imágenes viejas. Claude cierra cada
  respuesta con una nota oculta (`MEMO: …`) de lo que importaba en esa pantalla
  — el enunciado, los números, el estado del código —, y la captura siguiente
  lleva solo la imagen actual más esas notas y el principio de cada respuesta.
  Si la nota no basta, Claude contesta `NEED: 3` y el helper le re-envía esa
  captura (siguen en disco hasta cerrar la sesión). Medido: **~$0.025 por
  captura, sea la segunda o la trigésima**; una que pide una imagen de vuelta,
  ~$0.06.
- **Imágenes**. Reanuda la conversación y Claude ve todas las capturas de
  verdad. Lo más fiel, pero re-envía todas en cada turno: medido, la tercera
  $0.14 y la trigésima $1.13.

### Plantillas

En el diálogo de nueva sesión, a un clic. El botón muestra el nombre, no el
texto, así que caben prompts de varios párrafos:

| Plantilla | Para qué |
|---|---|
| Resolver lo que hay en pantalla | El comportamiento por defecto |
| **LeetCode / ejercicios de código** | Editor vacío → solución. Código roto o test en rojo → traza esa entrada y lo arregla. Código correcto → lo devuelve línea por línea con la complejidad de tiempo y memoria de cada una, y el total. En inglés, así que responde en inglés |
| **LeetCode: what if… (con memoria)** | Para tantear variantes. Escribes en el editor un comentario `# what if el array viene ordenado` y lo trata como una enmienda al enunciado: te dice si tu código sobrevive, con qué entrada concreta se rompe si no, cómo se resuelve ahora y la complejidad antes → después. **Recapturar la misma pantalla sin cambiar nada pide otra vía distinta**, y recuerda las que ya te dio para no repetirlas |
| **Amazon SDE: work simulation** | Para el *work simulation* de Amazon: escenarios del día a día de un SDE (correos, tickets, code reviews, gráficas) con opciones a elegir. Da la letra, y justifica con el Leadership Principle que decide el caso. Distingue *most* de *least effective* y las preguntas de ranking. En inglés, como el examen |
| Explicar sin jerga | Define cada término que use |
| Solo el enfoque, sin código | Para resolverlo tú |
| Encontrar el error | Diagnóstico de lo que falle en pantalla |
| **Data science: opción múltiple (rápido)** | Va directo a la letra correcta con una frase de por qué. Para quizzes de estadística, ML, pandas, SQL. Escrita en inglés, así que responde en inglés (para español, ⚙ → Idioma) |
| **Aptitud SHL / Cubiks / Saville (banca)** | Pruebas de aptitud de bancos y consultoras: numérico, verbal (True / False / Cannot Say), lógico y juicio situacional. Responde `ANSWER / CONFIDENCE / WHY / SHORTCUT`, avisa si falta algo en la imagen y nunca deja una sin responder. En inglés |
| **Depurar repo desconocido (con memoria)** | Compañero de depuración iterativo. Capturas el error, luego código/pistas de otra IA, y va armando el diagnóstico apoyándose en las anteriores. Las correcciones vienen con archivo, rango de líneas, `REEMPLAZA`/`INSERTA` y bloques **antes/después** con líneas de ancla. Cada respuesta cierra con un paso: qué archivo y qué líneas capturar y qué significaría cada resultado — o, si vamos a ciegas, el mensaje literal para pegarle a la IA que te guía el repo |
| Traducir al español | |

Una plantilla puede fijar su propio modelo (`model`/`effort`); si no, usa el
global. La de opción múltiple **no** lo hace: medido, Opus es el más rápido con
imágenes — Haiku, pese a ser el "modelo rápido", resultó el más lento (8s vs
3s). Así que va con el global (Opus).

Tu pre-prompt pesa **más** que las reglas de serie: si una plantilla pide otra
estructura, gana la plantilla.

**Editar** cambia qué se captura a mitad de sesión. El pre-prompt no: queda
fijo al abrir y ahí se queda.

`Alt+4` enciende el **modo mover**: el punto del encabezado se pone naranja y
las flechas desplazan el panel. `Alt+4` otra vez (o `Esc`) lo apaga. Es un modo
y no un arrastre a propósito: hacerle clic al panel le da el foco y se lo quita
a lo que estuvieras haciendo; con las flechas globales el foco no se mueve.

Mientras el modo está activo las flechas dejan de funcionar en el resto de
Windows, así que se apaga solo tras 15 segundos sin tocar nada — por si te
olvidas.

El botón `—` (o `Alt+E` desde donde sea) colapsa el panel al encabezado; `Alt+F` lo trae al frente y desplegado sin capturar; `⚙` abre la configuración.

### Varias sesiones a la vez

Puedes tener hasta **6 sesiones abiertas**, cada una con su propio pre-prompt,
su target de captura y su costo. Con una sesión ya abierta, el botón
**+ Sesión** (en la fila de Copiar / Editar) añade otra y la deja activa; no
cierra las que ya tenías.

Cada sesión lleva un **título** para que sepas en cuál estás: el nombre de la
plantilla si usaste una, o las primeras palabras de tu pre-prompt si lo
escribiste tú (`Sin pre-prompt` si lo dejaste vacío). Sale en la línea de
estado — `[2/3] Depura el error de build… · Solo la ventana activa · 3
capturas` — y en grande cada vez que cambias de sesión.

`Alt+2` toma las flechas **← →** para rotar entre ellas. Igual que el modo
mover: se apaga con `Alt+2` otra vez, con `Esc`, o solo a los 15 segundos. El
estado muestra en cuál estás (`[2/3]`), y al cambiar el panel repinta la
respuesta de esa sesión — no se pierde nada.

**Cerrar sesión** cierra solo la activa; las demás siguen vivas. Si una
respuesta llega mientras estás mirando otra sesión, se guarda en la suya y el
panel te avisa.

Para qué sirve: dejar una sesión con el pre-prompt de LeetCode y otra con el de
depurar, y saltar entre las dos sin perder ninguna de las dos conversaciones.

### Elegir la IA: Claude, Groq o ChatGPT

Al abrir una sesión, arriba del todo, eliges quién responde: **Claude** (como
siempre), **Groq** (`qwen/qwen3.8-27b`) o **ChatGPT** (`gpt-6-luna`). La última elección queda guardada
y es la que sale marcada la próxima vez.

La API key de Groq va en un archivo `.env` en la raíz del proyecto (está en
`.gitignore`, nunca se sube):

1. Saca la key en <https://console.groq.com/keys> (empieza por `gsk_`).
2. Copia `.env.example` como `.env`, si no existe ya.
3. Ponla en la línea `GROQ_API_KEY=gsk_...` y reinicia el helper.

Si no hay `.env`, el diálogo de nueva sesión te la pide y la guarda en
`config.json`; la del `.env` gana sobre esa.

Con la sesión abierta, **clic derecho en el panel** abre un menú para cambiar
de IA sin cerrarla. Con **Usar pasados** en modo Resumen las notas de las
capturas anteriores son texto, así que la otra IA las recibe igual.

`qwen3.8-27b` ve las capturas y responde en ~1 s. Se pidió
`llama-3.1-8b-instant`, pero en Groq ese modelo ya es solo de Enterprise (con
una key normal la API responde 404). Si pones en `groq_model` uno de solo texto
(p. ej. `openai/gpt-oss-20b`), las preguntas con captura van a
`groq_vision_model`. Groq no devuelve costo, así que el panel marca $0.

**Relevo de Groq.** El plan gratuito de Groq da para ~3 capturas por minuto.
En una sesión de Groq, cuando el cupo no alcanza para otra captura, esa
captura la responde **Claude Sonnet 5.5** (el Claude más rápido medido, ~4 s,
~$0.012) y Groq vuelve solo en cuanto se recupera — unos segundos, no el minuto
entero: el cupo se rellena poco a poco y basta con que alcance para una. El pie
del panel dice `Respondió Claude · Groq vuelve en Ns`. Solo pasa con sesiones de
Groq; el modelo de relevo se cambia en `groq_fallback_model` (vacío = sin
relevo, sale el aviso de esperar).

**ChatGPT** va como Claude: por su CLI (`codex exec`), con tu login de ChatGPT
y sin API key. Hace falta Codex CLI instalado y con sesión iniciada
(`npm install -g @openai/codex` y `codex login`). Igual que con Claude, se le
apaga el harness de agente (shell, búsqueda web, skills, `AGENTS.md`) y se
reemplazan sus instrucciones por las del helper: la entrada baja de ~16k a
~8.6k tokens. Con cuenta de ChatGPT sirven `gpt-6-luna` (de serie) y
`gpt-6-astra`; `gpt-6.1-sol` y `gpt-5.4-mini` dan error.

Medido con la misma captura y el modo de serie de "Usar pasados":

| IA | Por captura | Costo |
|---|---|---|
| Groq `qwen3.8-27b` | 1–2 s (hasta ~5 s) | gratis, ~3 capturas/minuto |
| Claude Sonnet 5.5 | 3.8–4.9 s | ~$0.012 |
| Claude Opus 5 | 3.9–4.6 s | ~$0.03 |
| ChatGPT `gpt-6-luna` | 5.7–9.6 s | suscripción de ChatGPT |
| ChatGPT `gpt-6-astra` | 8.4–9.2 s | suscripción de ChatGPT |

### Una sesión, un prompt

Cada sesión es una conversación aparte con su propio juego de instrucciones, y
ninguna hereda nada de otra:

- La caja del pre-prompt arranca **vacía** cada vez. Si quieres repetir uno, lo
  tienes en **Plantillas** a un clic — pero a propósito, no por arrastre.
- El pre-prompt no se puede cambiar a mitad de sesión. Para otro prompt, otra
  sesión. Así una conversación nunca acaba con dos juegos de instrucciones
  encima.
- Las conversaciones no se mezclan: cada sesión tiene su propio UUID. Está
  comprobado — con dos sesiones abiertas, la segunda niega haber visto las
  capturas de la primera, y la primera sigue recordando las suyas.

### Qué responde según lo que haya en pantalla

Sin necesidad de pre-prompt, el helper identifica el tipo de pregunta y ajusta
el formato:

| En pantalla | Qué devuelve |
|---|---|
| Opción múltiple | La letra y el texto de la correcta, más una frase de por qué |
| Código con un error, o que falta escribir | Qué está mal en una o dos frases, y el código en monospace |
| Pregunta abierta | La respuesta directa, máximo 3 frases |
| Nada que parezca pregunta | Una frase de qué ve, y avisa que no encuentra pregunta |

Siempre empieza por la respuesta: no describe la pantalla antes.

La respuesta llega con formato, no como un bloque de texto corrido:

- La **primera línea es la respuesta**, destacada en negrita. El detalle va
  debajo, en cuerpo normal. Si la respuesta es un solo párrafo, no se destaca
  nada: un titular solo sirve si hay algo debajo con lo que contrastar.
- El **código** sale en monospace sobre fondo propio, y los nombres de
  variables o funciones que aparezcan en medio de una frase también.
- Las **listas** salen con viñetas y sangría colgante.
- **Copiar** te da el texto limpio, sin las marcas de formato.

El área de respuesta crece hasta caber entera. Cuando la respuesta trae código
el panel **se ensancha** (380 → 560px), porque una función entera partida por
la mitad se lee peor que en el editor; al volver a una respuesta corta, se
encoge. El alto nunca pasa del 72% de la pantalla: lo que sobre se rueda con la
rueda del ratón.

### Qué puede capturar

| Modo | Qué agarra |
|---|---|
| Monitor donde está el cursor | La pantalla en la que estás trabajando (por defecto) |
| Un monitor específico | Útil si dejas el widget en una pantalla y trabajas en otra |
| Solo la ventana activa | Recorta a la app en primer plano: menos ruido, más barato |
| Todos los monitores | Las dos pantallas en una sola imagen |

Con más de una pantalla, `⚙` añade **Mostrar el panel en**: capturas una
pantalla y lees la respuesta en la otra. Con una sola pantalla la opción no
aparece porque no significaría nada.

### Privacidad en pantalla compartida

El panel y sus diálogos se excluyen de las capturas de pantalla y del screen
sharing vía `SetWindowDisplayAffinity` (`WDA_EXCLUDEFROMCAPTURE`): tú los sigues
viendo en tu monitor, pero no salen en lo que grabe o comparta otra app. Es solo
Windows 10 2004 o posterior; en versiones anteriores, macOS o Linux la app
funciona igual, sin la exclusión. Para volver a permitir la captura está
`helper.privacy.allow_window_capture(ventana)`.

## Cuánto cuesta

Se factura contra tu suscripción de Claude Code. Una captura sale en **~$0.03**
y tarda **~4 segundos**.

Con **Usar pasados** en modo **Resumen** (de serie) el costo por captura no
crece con la sesión. En modo **Imágenes** sí: cada turno reenvía las capturas
anteriores, así que a las 10 capturas el panel te avisa; cerrar la sesión y
abrir otra resetea eso.

El helper llama al CLI con el harness apagado — sin skills, sin MCP, sin
CLAUDE.md, sin herramientas y con un system prompt mínimo. No es cosmético: sin
eso la misma pregunta costaba **$0.51** en vez de $0.03.

## Configuración

Vive en `%APPDATA%\helper\config.json` y se edita desde el botón `⚙`.

- **Atajos** — varios, separados por comas. De serie `ctrl+shift+c, alt+3`.
  Cada uno necesita al menos un modificador (`ctrl`, `alt`, `shift`, `win`):
  una tecla sola secuestraría esa tecla en todo Windows. Se aplican al guardar.
  Si otra aplicación ya tiene uno, los demás siguen funcionando y el panel te
  dice cuál se perdió.
- **Atajo para cambiar de sesión** — de serie `alt+2`. Con varias sesiones
  abiertas toma las flechas izquierda y derecha para rotar entre ellas.
- **Atajo para encoger el panel** — de serie `alt+e`. Deja solo el encabezado a
  la vista y lo vuelve a desplegar. No cierra la sesión ni pierde la respuesta:
  es el botón `—` sin buscarlo con el ratón.
- **Atajo para traer el panel al frente** — de serie `alt+f`. Lo pone encima de
  las demás ventanas y lo despliega si estaba encogido, sin hacer una captura.
- **Atajo para releer respuestas** — de serie `alt+5`. Toma las flechas arriba y
  abajo para subir por el historial de la sesión. Al salir (mismo atajo, `Esc`,
  o solos a los 15 segundos) el panel vuelve a la última respuesta.
- **Atajo para mover** — `alt+4` de serie. Enciende/apaga el modo mover con flechas.
- **Idioma** — automático por defecto: responde en el idioma en que escribas el
  pre-prompt o la pregunta. Si no escribes nada, responde en español. También
  puedes forzarlo a español o inglés.
- **Modelo de Claude** — Opus 5 por defecto; Sonnet 5 si quieres abaratar.
- **Groq** — la key en `GROQ_API_KEY` del `.env` (o `groq_api_key` aquí),
  `groq_model` (de serie `qwen/qwen3.8-27b`), `groq_vision_model` y
  `groq_fallback_model` (el relevo, de serie `claude-sonnet-5-5`). La IA de
  la última sesión se guarda en `provider` (`claude`, `groq` o `chatgpt`).
- **ChatGPT** — `codex_model` (de serie `gpt-6-luna`) y `codex_effort` (`low`).
- **Profundidad** — baja por defecto. Para "mirar y responder corto", razonar
  más no mejora la respuesta y sí la hace lenta.
- **Reglas de concisión** — las reglas de formato por tipo de pregunta. Si las
  tocas, ten en cuenta que una sola regla tipo "máximo 3 frases" mata las
  respuestas de código: el bloque copiable desaparece.
- **Mostrar el panel en** — solo aparece con más de un monitor.

## Cómo está armado

```
helper/
  hotkey.py         atajo global via RegisterHotKey de Win32
  capture.py        captura por monitor / ventana activa, y reescalado
  claude_client.py  subproceso `claude -p`, imagen en base64 por stdin
  session.py        UUID de conversación + pre-prompt fijo + contador
  memoria.py        pasados por resumen: notas MEMO y NEED para pedir una captura
  config.py         persistencia en %APPDATA% y el prompt del sistema
  lang.py           detecta si escribes en español o en inglés
  privacy.py        excluye las ventanas de las capturas (solo Windows)
  ui/
    app.py          controlador: cola de eventos, worker, estados
    panel.py        el panel flotante y el formato de la respuesta
    dialogs.py      nueva sesión y configuración
    widgets.py      botones planos, spinner, arrastre
    theme.py        colores y tipografías
```

Dos decisiones que vale la pena conocer si vas a tocar el código:

**El atajo usa `RegisterHotKey`, no un hook de teclado.** Registra una sola
combinación con el sistema y no ve ninguna otra tecla — por eso no dispara
alertas de antivirus, y por eso `helper.hotkey` rechaza atajos sin modificador.
`RegisterHotKey` registra por hilo, así que cada atajo tiene su propio listener:
si uno está ocupado por otra app, los demás no se enteran.

**La imagen va como bloque base64 por stdin**, no como ruta para que Claude la
abra con la herramienta `Read`. Se midieron las dos: base64 gasta un turno en
vez de dos, ~15% menos latencia, ~35% menos costo, y permite correr sin
ninguna herramienta habilitada.

**El código llega marcado con cercas ```**, y el panel las quita al mostrarlo.
Es un marcador, no decoración: sin él habría que adivinar por la forma de cada
línea si es código o prosa, y eso falla con frases que llevan paréntesis. Lo
mismo con `acentos graves` y **negrita**: el prompt los pide, el panel los
interpreta y los hace desaparecer.

**El alto del área de respuesta se corrige midiendo, no calculando.** Se estima
por píxeles y luego se pregunta al widget cuánto ve de verdad (`yview`),
creciendo hasta que no quede texto cortado. Hacen falta las dos cosas: la
cuenta en líneas ignora el espaciado entre bloques y el monospace, y la
medición sólo vale después de que la ventana adopte el alto nuevo.

**El idioma se decide en Python, no se le pide al modelo que lo deduzca.** Las
instrucciones del sistema son un bloque largo en español, y eso arrastra la
respuesta a español por mucho que se le pida otra cosa. Lo que sí funciona es
detectar el idioma de lo que escribes y darle la orden **escrita en ese
idioma**, al final del prompt. Sin las dos cosas — el idioma correcto y la
posición final — seguía respondiendo en español.

Por lo mismo, cuando no escribes nada no se promete seguir el idioma de la
pantalla: se probó y no se sostiene. Cae a español, que es predecible.

Tkinter no es thread-safe, así que el listener del atajo y el worker que habla
con Claude nunca tocan la UI: publican en una cola que el hilo de Tk drena.

## Probar

```
.venv\Scripts\python.exe -m tests.run          # 224 pruebas, no gastan tokens
.venv\Scripts\python.exe -m helper --selftest  # ida y vuelta real con Claude
.venv\Scripts\python.exe -m helper --selftest --turns 2   # verifica el contexto
.venv\Scripts\python.exe -m helper --capture-test         # un PNG por modo
.venv\Scripts\python.exe -m helper --monitors             # lista los monitores
```

## Si algo falla

**"no encuentro el comando `claude`"** — abre una terminal y escribe `claude`.
Si no funciona ahí, el helper tampoco lo va a encontrar.

**"otra aplicación ya tiene ese atajo"** — cambia el atajo en `⚙`. El helper
sigue sirviendo sin atajo: escribe en la cajita y Enter.

**El widget sale en su propia captura** — sube `HIDE_MS` en `ui/app.py`; 90ms
alcanza en máquinas normales, pero un equipo cargado puede necesitar más.
