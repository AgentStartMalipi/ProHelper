"""Pruebas del helper.

Se corren desde la raiz del proyecto con:

    .venv\\Scripts\\python.exe -m tests.run

No usan pytest a proposito: el proyecto no arrastra mas dependencias de las
que necesita para funcionar. Ninguna prueba llama a Claude (eso cuesta dinero);
para probar la ida y vuelta real esta `python -m helper --selftest`.
"""

from __future__ import annotations

import ctypes
import json
import pathlib
import sys
import tempfile
import threading
import time

results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((name, bool(cond), extra))
    mark = "PASA " if cond else "FALLA"
    line = f"  {mark} {name}"
    if extra:
        line += f"  ->  {extra}"
    print(line)


def section(title: str) -> None:
    print(f"\n{title}")


# --------------------------------------------------------------------- atajo


def test_hotkey() -> None:
    from helper.hotkey import HotkeyError, HotkeyListener, parse

    section("[atajo] parseo")
    mods, key = parse("ctrl+shift+c")
    check("ctrl+shift+c se parsea", mods > 0 and key == ord("C"))

    for bad, why in (
        ("c", "una tecla sola"),
        ("ctrl+", "solo modificadores"),
        ("ctrl+shift+n~", "tecla desconocida"),
    ):
        try:
            parse(bad)
            check(f"rechaza {bad!r} ({why})", False)
        except HotkeyError:
            check(f"rechaza {bad!r} ({why})", True)

    section("[atajo] varios a la vez")
    from helper.config import Config, normalize_hotkeys

    check("alt+3 se parsea", parse("alt+3")[1] == ord("3"))
    check("viene de serie junto a ctrl+shift+c",
          Config()["hotkeys"] == ["ctrl+shift+c", "alt+3"],
          str(Config()["hotkeys"]))
    check("una config vieja de un solo atajo se migra",
          Config({"hotkey": "ctrl+alt+k"})["hotkeys"] == ["ctrl+alt+k"])
    check("se quitan duplicados y mayusculas",
          normalize_hotkeys(["ALT+3", "alt+3", " ctrl+shift+c "])
          == ["alt+3", "ctrl+shift+c"])
    check("lo que escribes con comas se parte",
          normalize_hotkeys(" ctrl+shift+c , alt+3 ,".split(","))
          == ["ctrl+shift+c", "alt+3"])

    section("[atajo] registro y disparo real")
    fired = threading.Event()
    listener = HotkeyListener("ctrl+shift+f9", fired.set)
    listener.start()
    check("registra con Windows", True)

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    KEYUP = 0x0002
    VK = {"ctrl": 0x11, "shift": 0x10, "f9": 0x78}
    time.sleep(0.3)
    for k in ("ctrl", "shift", "f9"):
        user32.keybd_event(VK[k], 0, 0, 0)
    time.sleep(0.05)
    for k in ("f9", "shift", "ctrl"):
        user32.keybd_event(VK[k], 0, KEYUP, 0)

    check("dispara el callback", fired.wait(3.0))
    listener.stop()
    check("se detiene limpio", True)

    section("[atajo] dos atajos disparan los dos")
    from helper.hotkey import HotkeyManager

    recibidos: list[str] = []
    manager = HotkeyManager({s: recibidos.append for s in ("ctrl+shift+f10", "alt+8")})
    manager.start()
    check("los dos quedan activos", len(manager.activos) == 2, str(manager.activos))
    check("ninguno fallo", not manager.fallidos, str(manager.fallidos))

    time.sleep(0.3)
    for secuencia in ([0x11, 0x10, 0x79], [0x12, 0x38]):
        for vk in secuencia:
            user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.05)
        for vk in reversed(secuencia):
            user32.keybd_event(vk, 0, KEYUP, 0)
        time.sleep(0.4)

    check("ctrl+shift+f10 disparo", "ctrl+shift+f10" in recibidos, str(recibidos))
    check("alt+8 disparo", "alt+8" in recibidos, str(recibidos))

    section("[atajo] si uno esta ocupado, el otro sigue")
    otro = HotkeyManager({s: (lambda x: None) for s in ("ctrl+shift+f10", "ctrl+shift+f11")})
    otro.start()
    check("el libre entra", "ctrl+shift+f11" in otro.activos, str(otro.activos))
    check("el ocupado se reporta", any(s == "ctrl+shift+f10" for s, _ in otro.fallidos),
          str([s for s, _ in otro.fallidos]))
    check("sigue habiendo atajo", otro.alguno_activo)
    otro.stop()
    manager.stop()


# -------------------------------------------------------------------- config


def test_config() -> None:
    from helper import config as cfgmod
    from helper.config import DEFAULTS, Config

    section("[config] mezcla con los defaults")
    old = Config({"hotkeys": ["ctrl+alt+k"], "clave_obsoleta": 1})
    check("conserva lo guardado", old["hotkeys"] == ["ctrl+alt+k"])
    check("rellena claves nuevas", old["model"] == DEFAULTS["model"])
    check("descarta claves obsoletas", "clave_obsoleta" not in old.data)
    check("anida sin perder defaults", old["capture"]["monitor_index"] == 1)

    section("[config] guardar y releer")
    tmp = pathlib.Path(tempfile.mkdtemp())
    original = cfgmod.config_path
    cfgmod.config_path = lambda: tmp / "config.json"
    try:
        cfg = Config()
        cfg["hotkeys"] = ["ctrl+shift+j"]
        cfg.save()
        check("no deja el .tmp tirado", not (tmp / "config.json.tmp").exists())
        check("relee lo escrito", Config.load()["hotkeys"] == ["ctrl+shift+j"])
        check("el json es valido", isinstance(
            json.loads((tmp / "config.json").read_text(encoding="utf-8")), dict))

        (tmp / "config.json").write_text("{esto no es json", encoding="utf-8")
        check("config corrupta cae a defaults",
              Config.load()["hotkeys"] == DEFAULTS["hotkeys"])
    finally:
        cfgmod.config_path = original

    section("[config] las mejoras a los defaults llegan al usuario")
    tmp2 = pathlib.Path(tempfile.mkdtemp())
    original = cfgmod.config_path
    cfgmod.config_path = lambda: tmp2 / "config.json"
    try:
        cfg = Config()
        cfg["hotkeys"] = ["ctrl+alt+p"]    # esto si lo cambia el usuario
        cfg.save()
        escrito = json.loads((tmp2 / "config.json").read_text(encoding="utf-8"))
        check("guarda lo que cambiaste", escrito.get("hotkeys") == ["ctrl+alt+p"])
        check("no congela el prompt por defecto", "concision" not in escrito,
              str(sorted(escrito)))
        check("no congela las plantillas", "presets" not in escrito)
        # normalize_presets hace strip() al texto: si un default trae espacios
        # o saltos sobrantes, deja de coincidir consigo mismo y save() lo
        # congela en disco, que es justo lo que _SUPERADOS intenta evitar.
        sucias = [p["nombre"] for p in cfgmod.DEFAULTS["presets"]
                  if p["texto"] != p["texto"].strip()]
        check("las plantillas por defecto ya vienen limpias", not sucias, str(sucias))

        # Un default congelado en disco no debe pisar al default nuevo.
        viejo = dict(escrito)
        viejo["concision"] = "reglas viejas que nadie edito"
        cfgmod._SUPERADOS["concision"].add(cfgmod._huella(viejo["concision"]))
        (tmp2 / "config.json").write_text(json.dumps(viejo), encoding="utf-8")
        recargado = Config.load()
        check("un default superado se reemplaza",
              recargado["concision"] == DEFAULTS["concision"])
        check("y tus ajustes sobreviven", recargado["hotkeys"] == ["ctrl+alt+p"])
        cfgmod._SUPERADOS["concision"].discard(cfgmod._huella("reglas viejas que nadie edito"))

        # Lo que el usuario si edito tiene que respetarse.
        mio = dict(escrito)
        mio["concision"] = "estas reglas las escribi yo"
        (tmp2 / "config.json").write_text(json.dumps(mio), encoding="utf-8")
        check("un prompt tuyo se respeta",
              Config.load()["concision"] == "estas reglas las escribi yo")
    finally:
        cfgmod.config_path = original

    section("[config] el prompt explica el vocabulario")
    reglas = Config().full_system_prompt("")
    seguido = " ".join(reglas.split())
    check("prohibe dar por sabido el vocabulario",
          "Nunca des por sabido el vocabulario" in seguido)
    check("pide palabras llanas", "palabras llanas" in seguido)
    textos = [p["texto"] for p in DEFAULTS["presets"]]
    check("hay plantilla para explicacion llana",
          any("vocabulario" in t for t in textos))
    check("hay plantilla para enfoque sin codigo",
          any("No me des el codigo" in t for t in textos))

    section("[config] system prompt")
    full = Config().full_system_prompt("Critica el diseno.")
    check("incluye el pre-prompt", "Critica el diseno." in full)
    check("limita la longitud", "3 frases" in full)


# ------------------------------------------------------------------ captura


def test_capture() -> None:
    from helper import capture

    section("[captura] monitores")
    monitors = capture.list_monitors()
    check("detecta al menos uno", len(monitors) >= 1, f"{len(monitors)} monitor(es)")

    section("[captura] modos")
    tmp = pathlib.Path(tempfile.mkdtemp())
    for mode in ("active_monitor", "active_window", "all"):
        try:
            path = capture.capture_to_file(tmp / f"{mode}.png", mode=mode, max_edge=600)
            check(f"{mode} produce un PNG", path.stat().st_size > 0)
        except capture.CaptureError as exc:
            check(f"{mode} produce un PNG", False, str(exc))

    section("[captura] reescalado y errores")
    from PIL import Image

    with Image.open(tmp / "all.png") as img:
        check("respeta el lado maximo", max(img.size) <= 600, f"{img.size}")

    try:
        capture.grab(mode="monitor", monitor_index=99)
        check("avisa del monitor inexistente", False)
    except capture.CaptureError as exc:
        check("avisa del monitor inexistente", "99" in str(exc), str(exc))

    try:
        capture.grab(mode="inventado")
        check("avisa del modo desconocido", False)
    except capture.CaptureError:
        check("avisa del modo desconocido", True)


# -------------------------------------------------------------- cliente CLI


def test_client() -> None:
    from helper.claude_client import ClaudeError, _parse, _user_message
    from helper.config import Config

    section("[cliente] mensaje de entrada")
    msg = json.loads(_user_message("hola", None))
    check("sin imagen manda solo texto", len(msg["message"]["content"]) == 1)

    tmp = pathlib.Path(tempfile.mkdtemp()) / "x.png"
    from PIL import Image

    Image.new("RGB", (8, 8), "red").save(tmp)
    msg = json.loads(_user_message("hola", tmp))
    blocks = msg["message"]["content"]
    check("con imagen manda imagen + texto", len(blocks) == 2)
    check("la imagen va primero", blocks[0]["type"] == "image")
    check("va en base64 png", blocks[0]["source"]["media_type"] == "image/png")

    section("[cliente] lectura del stream")
    stream = (
        '{"type":"system"}\n'
        "no es json\n"
        '{"type":"result","result":"listo","total_cost_usd":0.02,'
        '"duration_ms":1500,"session_id":"abc"}\n'
    )
    parsed = _parse(stream)
    check("saca el evento result", parsed["result"] == "listo")
    check("tolera lineas que no son json", True)

    try:
        _parse('{"type":"system"}\n')
        check("avisa si no hubo result", False)
    except ClaudeError:
        check("avisa si no hubo result", True)

    try:
        _parse('{"type":"result","is_error":true,"result":"algo fallo"}\n')
        check("propaga el error de Claude", False)
    except ClaudeError as exc:
        check("propaga el error de Claude", "algo fallo" in str(exc))

    section("[cliente] argumentos del CLI")
    from helper.claude_client import ClaudeClient

    client = ClaudeClient(Config())
    args = client._args("sid-1", resume=False, system_prompt="SP")
    check("abre con --session-id", "--session-id" in args)
    check("fija el system prompt al abrir", "SP" in args)
    check("corre sin herramientas", args[args.index("--tools") + 1] == "")
    check("ignora MCP del usuario", "--strict-mcp-config" in args)
    check("ignora skills", "--disable-slash-commands" in args)
    check("no pregunta permisos", args[args.index("--permission-mode") + 1] == "dontAsk")

    args = client._args("sid-1", resume=True, system_prompt="SP")
    check("resume con --resume", "--resume" in args)
    check("no repite el system prompt al resumir", "--system-prompt" not in args)


# --------------------------------------------------------------- sesion y UI


def test_session() -> None:
    from helper.session import Session

    section("[sesion] estado")
    s = Session(preprompt="x")
    check("arranca sin capturas", s.captures == 0 and not s.started)
    first = s.next_shot_path()
    s.record(0.03)
    check("tras un turno toca resumir", s.started)
    check("numera las capturas", s.next_shot_path() != first)
    check("acumula el costo", abs(s.total_cost_usd - 0.03) < 1e-9)
    check("la carpeta existe", s.shots_dir.exists())

    section("[sesion] usar pasados")
    conv, resume = s.conversation_for_next()
    check("marcado: sigue la conversacion de la sesion", conv == s.session_id and resume)
    s.use_history = False
    conv, resume = s.conversation_for_next()
    check("desmarcado: conversacion nueva, sin resumir", conv != s.session_id and not resume)
    check("cada suelta es otra conversacion", s.conversation_for_next()[0] != conv)
    turns = s.history_turns
    s.record(0.01, in_history=False)
    check("una suelta no cuenta como turno de la principal", s.history_turns == turns)
    check("pero si como captura y costo", s.captures == 2 and abs(s.total_cost_usd - 0.04) < 1e-9)
    s.use_history = True
    check("al volver a marcar, retoma la principal",
          s.conversation_for_next() == (s.session_id, True))
    fresh = Session(preprompt="x", use_history=False)
    fresh.record(0.01, in_history=False)
    fresh.use_history = True
    check("si la principal nunca existio, la abre en vez de resumir",
          fresh.conversation_for_next() == (fresh.session_id, False))

    shots = s.shots_dir
    s.close()
    check("borra la carpeta al cerrar", not shots.exists())


def test_memoria() -> None:
    from helper import memoria
    from helper.memoria import Entry

    section("[memoria] la nota se separa de la respuesta")
    limpio, memo = memoria.parse("**B) 42**\nPorque si.\n\nMEMO: tabla de ventas 2023, B=42")
    check("quita la linea MEMO", "MEMO" not in limpio and limpio.endswith("Porque si."))
    check("guarda la nota", memo == "tabla de ventas 2023, B=42", memo)
    _, memo = memoria.parse("respuesta\n**MEMO:** `algo`  \n\n")
    check("tolera negrita, backticks y lineas vacias al final", memo == "algo", memo)
    texto, memo = memoria.parse("MEMO: no es la ultima\nsigue la respuesta")
    check("solo cuenta si es la ultima linea", memo == "" and "MEMO" in texto)

    section("[memoria] pedir capturas de vuelta")
    check("NEED solo", memoria.needs("NEED: 2", 5) == [2])
    check("varias y con #", memoria.needs("NEED: #1, #3", 5) == [1, 3])
    check("nunca la actual ni futuras", memoria.needs("NEED: 5, 9", 5) == [])
    check("maximo dos", len(memoria.needs("NEED: 1,2,3", 5)) == memoria.MAX_NEED)
    check("NEED dentro de una respuesta no cuenta",
          memoria.needs("La respuesta es B.\nNEED: 1", 5) == [])

    section("[memoria] el prompt")
    p1 = memoria.build_prompt([], "Q", 1)
    check("la primera no ofrece NEED", "NEED" not in p1 and "MEMO" in p1)
    largo = "x " * 2000
    entries = [Entry(n=i, memo=f"nota {i}", answer=largo if i == 20 else f"resp {i}",
                     question="mi duda" if i == 3 else "")
               for i in range(1, 21)]
    p = memoria.build_prompt(entries, "Q", 21)
    check("lleva todas las notas", all(f"#{i}: nota {i}" in p for i in range(1, 21)))
    # 20 notas, FULL_TURNS=12: de la #9 en adelante llevan respuesta.
    check("las viejas sin respuesta", "resp 8" not in p and "resp 9" in p)
    check("recorta respuestas largas", len(p) < 6000, str(len(p)))
    check("lleva tus preguntas escritas", "my question: mi duda" in p)
    check("ofrece NEED hasta la anterior", "from 1 to 20" in p)
    pf = memoria.build_prompt(entries, "Q", 21, fetched=[4])
    check("tras re-enviar, ya no ofrece NEED", "NEED is no longer allowed" in pf
          and "from 1 to" not in pf)


def test_app() -> None:
    from helper.claude_client import Reply
    from helper.config import Config
    from helper.session import Session
    from helper.ui.app import App

    cfg = Config()
    cfg.save = lambda: None  # type: ignore[method-assign]
    app = App(cfg)
    app.panel.place_at(60, 60)

    section("[app] captura sin sesion abierta")
    app.request_capture()
    check("no se marca ocupado", app.busy is False)
    check("avisa en el estado", "sesion" in app.panel.status.cget("text").lower(),
          repr(app.panel.status.cget("text")))

    section("[app] disparo doble")
    app.session = Session(preprompt="x", capture_mode="active_monitor")
    app.panel.show_session(app._status(), app.hotkey_hint)
    app.busy = True
    app.request_capture()
    check("ignora el segundo disparo", "curso" in app.panel.status.cget("text").lower(),
          repr(app.panel.status.cget("text")))

    section("[app] cerrar sesion mientras responde")
    app.end_session()
    check("se niega a cerrar ocupado", app.session is not None)
    app.busy = False

    section("[app] respuesta huerfana")
    stale = app.session.session_id
    app.end_session()
    check("la sesion se cierra", app.session is None)
    app._on_reply(stale, Reply("texto viejo", 0.01, 100, stale))
    check("descarta la respuesta sin romper", app.busy is False)

    section("[app] panel")
    app.session = Session(preprompt="x", capture_mode="active_monitor")
    app.panel.show_session(app._status(), app.hotkey_hint)
    largo = "palabra " * 60
    app.panel.set_answer(largo)
    app.panel.update()
    visible = app.panel.answer.yview()[1]
    check('una respuesta larga entra o se puede rodar', visible > 0.0)
    check('hay boton visible para capturar',
          app.panel.capture_button.winfo_ismapped() == 1)
    from helper.ui import theme
    check("el ancho queda fijo", app.panel.winfo_width() == theme.WIDTH,
          f"{app.panel.winfo_width()} vs {theme.WIDTH}")

    app.panel.set_answer("corta")
    app.panel.update()
    check("se encoge con respuestas cortas", app.panel.answer.cget("height") <= 3,
          str(app.panel.answer.cget("height")))

    app.panel.toggle_collapse()
    app.panel.update()
    check("colapsa al encabezado", app.panel.winfo_height() <= app.panel.header_height + 4,
          str(app.panel.winfo_height()))
    app.panel.toggle_collapse()
    app.panel.update()
    check("vuelve a desplegar", app.panel.winfo_height() > app.panel.header_height + 4)

    app.panel.after(50, app.quit)
    app.run()


def test_plantillas() -> None:
    """Las plantillas guardan prompts largos, con nombre para el boton."""
    from helper import lang
    from helper.config import DEFAULTS, Config, normalize_presets

    section("[plantillas] formato")
    for preset in DEFAULTS["presets"]:
        check(f"{preset['nombre'][:30]!r} tiene nombre y texto",
              bool(preset.get("nombre")) and bool(preset.get("texto")))

    section("[plantillas] se admite el formato viejo")
    convertido = normalize_presets(["una plantilla de antes"])
    check("una cadena suelta se convierte",
          convertido[0] == {"nombre": "una plantilla de antes",
                            "texto": "una plantilla de antes"})
    check("una lista vacia cae a las de serie",
          normalize_presets([]) == list(DEFAULTS["presets"]))
    check("la basura se descarta",
          normalize_presets([{"nombre": "x"}, 42, ""]) == list(DEFAULTS["presets"]))

    section("[plantillas] la de LeetCode")
    leet = next((p for p in DEFAULTS["presets"] if "LeetCode" in p["nombre"]), None)
    check("existe", leet is not None)
    texto = leet["texto"] if leet else ""
    check("distingue editor vacio de editor con codigo",
          "IF IT IS EMPTY" in texto and "IF IT ALREADY HAS CODE" in texto)
    check("pide la idea sin jerga primero", "no jargon" in texto)
    check("pide explicar cada tecnica que nombre", "what it means" in texto)
    check("pide complejidad", "complexity" in texto)
    check("sigue el lenguaje del editor", "selected in the editor" in texto)
    check("evita micro-optimizaciones", "No micro-optimization" in texto)
    check("esta escrita en ingles", lang.detect(texto) == lang.INGLES,
          str(lang.detect(texto)))
    check("es larga de verdad", len(texto) > 900, f"{len(texto)} caracteres")

    section("[plantillas] LeetCode: codigo correcto")
    check("tiene un caso para codigo ya correcto",
          "that is correct" in texto)
    check("pide desglose linea por linea", "LINE-BY-LINE" in texto)
    check("pide coste de tiempo y memoria por linea",
          "time and space cost" in texto)
    check("pide el total al final", "TOTAL time and the TOTAL space" in texto)
    check("distingue roto de correcto",
          "that is broken" in texto and "that is correct" in texto)

    section("[plantillas] LeetCode: tests en rojo")
    # Las comprobaciones no dependen de donde caiga cada salto de linea.
    texto_seguido = " ".join(texto.split())
    check("mira los resultados de los tests", "a test is red" in texto_seguido)
    check("reconoce los estados de fallo",
          all(x in texto_seguido for x in ("Wrong Answer", "Runtime Error",
                                           "Time Limit Exceeded")))
    check("pide seguir la entrada que falla paso a paso",
          "step by step" in texto and "Do not guess" in texto)
    check("pide arreglar la causa, no el sintoma",
          "the cause, not the symptom" in texto)
    check("no deja inventar un arreglo a ciegas",
          "instead of inventing a fix" in texto)

    section("[plantillas] Data science: opcion multiple")
    ds = next((p for p in DEFAULTS["presets"]
               if "Data science" in p["nombre"]), None)
    check("existe la plantilla de DS", ds is not None)
    dst = ds["texto"] if ds else ""
    check("cubre el dominio de data science",
          "machine learning" in dst and "statistics" in dst)
    check("prioriza la velocidad", "SPEED is the priority" in dst)
    check("primera linea = letra y opcion",
          "letter and the text of the correct option" in dst)
    check("no repasa las incorrectas", "Do not go through the wrong options" in dst)
    # En ingles a proposito: asi responde en ingles a los quizzes en ingles.
    check("esta escrita en ingles", lang.detect(dst) == lang.INGLES,
          str(lang.detect(dst)))
    # Se midio que Opus (global) es mas rapido con imagenes: sin override.
    check("usa el modelo global (sin override)", "model" not in ds if ds else False)

    section("[plantillas] Depurar repo desconocido")
    dep = next((p for p in DEFAULTS["presets"]
                if "Depurar" in p["nombre"]), None)
    check("existe la plantilla de depurar", dep is not None)
    dpt = dep["texto"] if dep else ""
    check("dice que trabaja por capturas", "por capturas" in dpt)
    check("insiste en usar la memoria", "RECUERDA" in dpt)
    check("da hipotesis primero", "hipotesis mas probable" in dpt)
    check("pide un solo siguiente paso", "UNA sola accion" in dpt)
    check("decodifica las pistas de la otra IA",
          "pista de la IA" in dpt or "IA que me guia" in dpt)
    check("prohibe inventar", "No inventes" in dpt)
    check("va estrechando", "estrechando" in dpt)
    check("esta en espanol", lang.detect(dpt) == lang.ESPANOL, str(lang.detect(dpt)))
    check("usa el modelo global (sin override)",
          "model" not in dep if dep else False)

    section("[plantillas] una plantilla puede fijar su modelo")
    from helper.config import normalize_presets as _np
    conv = _np([{"nombre": "rapida", "texto": "x", "model": "claude-haiku-4-5",
                 "effort": "low"}])
    check("conserva el modelo de la plantilla", conv[0].get("model") == "claude-haiku-4-5")
    check("conserva el effort", conv[0].get("effort") == "low")
    sin = _np([{"nombre": "normal", "texto": "y"}])
    check("sin modelo no inventa clave", "model" not in sin[0])

    section("[plantillas] el cliente usa el modelo de la sesion")
    from helper.claude_client import ClaudeClient
    cli = ClaudeClient(Config())
    args = cli._args("sid", resume=False, system_prompt="SP",
                     model="claude-haiku-4-5", effort="low")
    check("el override llega a --model",
          args[args.index("--model") + 1] == "claude-haiku-4-5")
    args2 = cli._args("sid", resume=False, system_prompt="SP")
    check("sin override usa el global",
          args2[args2.index("--model") + 1] == DEFAULTS["model"])

    section("[plantillas] tu prompt pesa mas que las reglas de serie")
    cfg = Config()
    prompt = cfg.full_system_prompt("MI PLANTILLA")
    check("el pre-prompt va despues de las reglas",
          prompt.index("MI PLANTILLA") > prompt.index("PRIMERA LINEA"))
    check("y antes de la regla de idioma",
          prompt.index("MI PLANTILLA") < prompt.rindex("IDIOMA"))


def test_idioma() -> None:
    """El idioma lo manda lo que escribe el usuario, no el prompt interno."""
    from helper import lang
    from helper.config import DEFAULT_QUESTION, Config

    section("[idioma] deteccion")
    casos = [
        ("Explain the approach briefly.", lang.INGLES),
        ("What is wrong with this code?", lang.INGLES),
        ("Explicame el enfoque brevemente.", lang.ESPANOL),
        ("Que error hay aqui?", lang.ESPANOL),
        ("Critica este diseño", lang.ESPANOL),   # por la enye
        ("", None),
        ("xyz 123 %%", None),
    ]
    for texto, esperado in casos:
        obtenido = lang.detect(texto)
        check(f"{texto[:28]!r} -> {esperado}", obtenido == esperado, str(obtenido))

    section("[idioma] la regla va escrita en el idioma destino")
    cfg = Config()
    en = cfg.language_rule("Explain this")
    es = cfg.language_rule("Explicame esto")
    check("la de ingles esta en ingles", "ENGLISH" in en, en.splitlines()[0])
    check("la de espanol esta en espanol", "espanol" in es, es.splitlines()[0])
    check("la de ingles neutraliza el sesgo",
          "does NOT set the language" in en)

    section("[idioma] cierra el prompt")
    # Puesta antes, el bloque largo en espanol la tapaba y respondia en
    # espanol pasara lo que pasara.
    prompt = cfg.full_system_prompt("Explain this")
    check("la regla es lo ultimo", prompt.rstrip().endswith(en.rstrip()),
          repr(prompt[-60:]))

    section("[idioma] ajuste forzado")
    check("forzado a ingles ignora tu espanol",
          "ENGLISH" in Config({"language": "en"}).language_rule("hola que tal"))
    check("forzado a espanol ignora tu ingles",
          "espanol" in Config({"language": "es"}).language_rule("hello there"))

    section("[idioma] sin texto tuyo")
    check("cae a un idioma predecible", "espanol" in cfg.language_rule(""))
    check("el disparador automatico no cuenta como idioma",
          DEFAULT_QUESTION not in cfg.language_rule(""))


def test_idioma_en_la_pregunta() -> None:
    """Una pregunta escrita a mitad de sesion tambien fija el idioma."""
    from helper.config import DEFAULT_QUESTION, Config
    from helper.ui.app import App

    cfg = Config()
    cfg.save = lambda: None  # type: ignore[method-assign]
    app = App(cfg)

    section("[idioma] la pregunta puntual manda")
    check("una pregunta en ingles pide respuesta en ingles",
          "(Answer in English.)" in app._con_idioma("What is this?"))
    check("una en espanol pide respuesta en espanol",
          "(Responde en espanol.)" in app._con_idioma("Que es esto?"))
    check("el disparador automatico se deja en paz",
          app._con_idioma(DEFAULT_QUESTION) == DEFAULT_QUESTION)

    app.cfg["language"] = "en"
    check("con idioma forzado no se toca la pregunta",
          app._con_idioma("Que es esto?") == "Que es esto?")

    app.panel.after(50, app.quit)
    app.run()


def test_formato_respuesta() -> None:
    """El prompt tiene que pedir RESPUESTAS, no descripciones de la pantalla."""
    from helper.config import DEFAULT_QUESTION, Config

    section("[formato] la pregunta por defecto pide una respuesta")
    check("no pide describir la pantalla", "que ves" not in DEFAULT_QUESTION.lower(),
          DEFAULT_QUESTION)

    section("[formato] el prompt cubre los tres tipos de pregunta")
    reglas = Config().full_system_prompt("")
    # El prompt va con saltos de linea para leerse bien; las comprobaciones de
    # contenido no deben depender de donde caiga cada corte.
    seguido = " ".join(reglas.split())
    for tipo in ("OPCION MULTIPLE", "CODIGO", "PREGUNTA ABIERTA", "SIN PREGUNTA CLARA"):
        check(f"contempla {tipo.lower()}", tipo in reglas)
    check("prohibe describir antes de responder",
          "describir la pantalla" in seguido)
    check("manda que la respuesta vaya primero", "PRIMERA LINEA" in reglas)
    check("pide el codigo en un bloque", "```" in reglas)
    check("pide vinetas con guion", '"- "' in reglas)
    check("pide acentos graves para identificadores", "acentos graves" in reglas)


def test_render_codigo() -> None:
    from helper.config import Config
    from helper.ui.app import App

    cfg = Config()
    cfg.save = lambda: None  # type: ignore[method-assign]
    app = App(cfg)
    # El area de respuesta solo tiene geometria en estado de sesion.
    from helper.session import Session

    app.session = Session(preprompt="", capture_mode="active_monitor")
    app.panel.show_session(app._status(), app.hotkey_hint)

    section("[render] bloque de codigo")
    app.panel.set_answer(
        "El bug esta en la linea 13.\n\n```python\nX_val, _, _ = f(X_val, m, s)\n```"
    )
    app.panel.update()
    mostrado = app.panel.answer.get("1.0", "end")
    check("quita las cercas", "```" not in mostrado)
    check("conserva el codigo", "X_val, _, _ = f(X_val, m, s)" in mostrado)
    check("marca el codigo como monospace",
          len(app.panel.answer.tag_ranges("code")) >= 2)
    check("no marca la prosa como codigo",
          "El bug" not in app.panel.answer.get(*app.panel.answer.tag_ranges("code")[:2]))

    section("[render] texto sin codigo")
    app.panel.set_answer("Una respuesta normal, sin nada de codigo.")
    app.panel.update()
    check("no aplica el tag sin cercas",
          len(app.panel.answer.tag_ranges("code")) == 0)

    def tiene(tag: str) -> bool:
        return len(app.panel.answer.tag_ranges(tag)) >= 2

    section("[render] jerarquia")
    app.panel.set_answer("La respuesta corta\n\nY el detalle debajo, explicando.")
    app.panel.update()
    check("destaca la primera linea", tiene("lead"))
    check("el detalle va en cuerpo normal", tiene("body"))

    app.panel.set_answer("Un solo parrafo sin nada debajo que lo acompane.")
    app.panel.update()
    check("un parrafo solo no se destaca", not tiene("lead"))

    largo = "Una primera linea tan larga que ya no es un titular sino un " \
            "parrafo entero, y por tanto no deberia ir en negrita porque " \
            "ocuparia varias lineas destacadas."
    app.panel.set_answer(largo + "\n\nDetalle aparte.")
    app.panel.update()
    check("un titular demasiado largo se degrada", not tiene("lead"))

    section("[render] vinetas y marcas dentro de linea")
    app.panel.set_answer(
        "Titulo\n\n- primero con `codigo`\n- segundo en **negrita**\n3. tercero"
    )
    app.panel.update()
    mostrado = app.panel.answer.get("1.0", "end")
    check("convierte los guiones en vinetas", mostrado.count("•") == 2, repr(mostrado))
    check("conserva el numero de una lista ordenada", "3. tercero" in mostrado)
    check("no deja los guiones", "- primero" not in mostrado)
    check("aplica el tag de vineta", tiene("bullet"))
    check("codigo dentro de linea en monospace", tiene("inline"))
    check("negrita dentro de linea", tiene("strong"))
    check("quita los acentos graves", "`" not in mostrado)
    check("quita los asteriscos", "**" not in mostrado)

    section("[mover] las flechas desplazan el panel dentro de la pantalla")
    from helper.config import Config as _Config

    check("hay atajo de serie para mover", _Config()["move_hotkey"] == "alt+4",
          _Config()["move_hotkey"])

    app.panel.place_at(300, 300, None)
    app.panel.update_idletasks()
    x0, y0 = app.panel.winfo_x(), app.panel.winfo_y()
    app.panel.nudge(24, 0)
    app.panel.update_idletasks()
    check("derecha mueve en x", app.panel.winfo_x() == x0 + 24,
          f"{app.panel.winfo_x()} vs {x0 + 24}")
    app.panel.nudge(0, 24)
    app.panel.update_idletasks()
    check("abajo mueve en y", app.panel.winfo_y() == y0 + 24)

    ancho, alto = app.panel.winfo_width(), app.panel.winfo_height()
    sw, sh = app.panel.winfo_screenwidth(), app.panel.winfo_screenheight()
    app.panel.nudge(99999, 99999)   # empujon imposible
    app.panel.update_idletasks()
    check("no se sale por la derecha", app.panel.winfo_x() <= sw - ancho)
    check("no se sale por abajo", app.panel.winfo_y() <= sh - alto)
    app.panel.nudge(-99999, -99999)
    app.panel.update_idletasks()
    check("no se sale por arriba/izquierda",
          app.panel.winfo_x() >= 0 and app.panel.winfo_y() >= 0,
          f"({app.panel.winfo_x()}, {app.panel.winfo_y()})")

    section("[mover] el modo se enciende y apaga con el mismo atajo")
    check("empieza apagado", app.modo is None)
    app._toggle_move_mode()
    check("Alt+4 lo enciende", app.modo == "mover", repr(app.modo))
    check("toma las cuatro flechas", len(app._flechas) >= 4, str(len(app._flechas)))
    check("marca el estado en el panel", app.panel._modo_mover is True)
    app._toggle_move_mode()
    check("Alt+4 otra vez lo apaga", app.modo is None)
    check("suelta las flechas", app._flechas == [])
    check("cancela el apagado automatico", app._mover_timeout is None)

    section("[mover] una flecha suelta solo mueve si el modo esta activo")
    app.panel.place_at(400, 400, None)
    app.panel.update_idletasks()
    fijo = (app.panel.winfo_x(), app.panel.winfo_y())
    app._con_flecha("right")   # modo apagado
    app.panel.update_idletasks()
    check("con el modo apagado no se mueve",
          (app.panel.winfo_x(), app.panel.winfo_y()) == fijo)

    section("[render] el panel se ensancha con codigo")
    from helper.ui import theme as tema

    app.panel.set_answer("Respuesta normal, sin nada de codigo.")
    app.panel.update()
    estrecho = app.panel.winfo_width()
    check("sin codigo usa el ancho normal", estrecho == tema.WIDTH,
          f"{estrecho} vs {tema.WIDTH}")

    app.panel.set_answer("Fallo\n\n```python\nresultado = calcular(a, b, c)\n```")
    app.panel.update()
    ancho = app.panel.winfo_width()
    check("con codigo se ensancha", ancho == tema.WIDTH_CODE,
          f"{ancho} vs {tema.WIDTH_CODE}")
    check("y es mas ancho que antes", ancho > estrecho)

    app.panel.set_answer("Y vuelve a una respuesta corta.")
    app.panel.update()
    check("vuelve a encogerse", app.panel.winfo_width() == estrecho,
          str(app.panel.winfo_width()))

    section("[render] el panel nunca tapa la pantalla")
    app.panel.set_answer("Fallo\n\n```python\n" + "linea = 1\n" * 60 + "```")
    app.panel.update()
    alto = app.panel.winfo_height()
    pantalla = app.panel.winfo_screenheight()
    check("una respuesta enorme sigue cabiendo", alto < pantalla * 0.85,
          f"{alto}px de {pantalla}")
    check("lo que sobra se puede rodar", app.panel.answer.yview()[1] < 1.0)

    section("[render] la respuesta cabe entera")
    for etiqueta, txt in (
        ("corta", "Si."),
        ("parrafo", "Porque " + "palabra " * 40),
        ("con codigo", "Fallo\n\nExplicacion.\n\n```python\n" + "x = 1\n" * 6 + "```"),
    ):
        app.panel.set_answer(txt)
        app.panel.update()
        visible = app.panel.answer.yview()[1]
        check(f"{etiqueta}: se ve entera o se puede rodar",
              visible >= 0.999 or app.panel.answer.cget("height") >= 18,
              f"visible={visible:.3f} alto={app.panel.answer.cget('height')}")

    section("[render] lo que copias esta limpio")
    app.panel.set_answer("Fallo\n\n```python\nx = f(1)\n```")
    app.panel.update()
    app.panel._copy()
    copiado = app.panel.clipboard_get()
    check("sin cercas en el portapapeles", "```" not in copiado, repr(copiado))
    check("conserva el codigo", "x = f(1)" in copiado)

    app.panel.after(50, app.quit)
    app.run()


def test_panel_multimonitor() -> None:
    """El panel tiene que poder vivir en un monitor que no sea el primario."""
    from helper import capture
    from helper.capture import Monitor
    from helper.config import Config
    from helper.ui import dialogs
    from helper.ui.app import App

    falsos = [
        Monitor(1, 0, 0, 1920, 1080, "Primario", True),
        Monitor(2, 1920, 0, 2560, 1440, "Secundario", False),
    ]
    real = capture.list_monitors
    capture.list_monitors = lambda: falsos  # type: ignore[assignment]
    dialogs.capture.list_monitors = lambda: falsos  # type: ignore[assignment]
    try:
        cfg = Config()
        cfg.save = lambda: None  # type: ignore[method-assign]
        app = App(cfg)
        panel = app.panel

        section("[multimonitor] limites")
        virtual = panel._bounds()
        solo_2 = panel._bounds(2)
        check("el area virtual pasa del primario", virtual[2] > solo_2[0],
              f"virtual={virtual}")
        check("el monitor 2 empieza donde acaba el 1", solo_2[0] > 0, f"mon2={solo_2}")

        section("[multimonitor] colocacion")
        panel.place_at(None, None, 2)
        panel.update_idletasks()
        check("el panel aterriza en el monitor 2", panel.winfo_x() >= solo_2[0],
              f"x={panel.winfo_x()}, monitor2 empieza en {solo_2[0]}")

        panel.place_at(99999, 99999, None)
        panel.update_idletasks()
        check("una posicion imposible se reencuadra", panel.winfo_x() <= virtual[2],
              f"x={panel.winfo_x()}")

        section("[multimonitor] el selector ofrece las dos pantallas")
        dlg = dialogs.SessionDialog(panel, cfg)
        modos = list(dlg.target.modes._rows.keys())
        check("ofrece 'un monitor especifico'", "monitor" in modos)
        dlg.target.modes.set("monitor")
        dlg.target.monitor_rows.set("2")
        check("devuelve el monitor elegido", dlg.target.get()["monitor_index"] == 2)
        dlg.destroy()

        app.panel.after(50, app.quit)
        app.run()
    finally:
        capture.list_monitors = real  # type: ignore[assignment]
        dialogs.capture.list_monitors = real  # type: ignore[assignment]


def test_dpi() -> None:
    """El modo DPI tiene que estar fijado, no depender del orden de imports.

    Esta fue una regresion real: al importar `capture` desde el panel, mss
    volvia el proceso DPI-aware justo mientras se creaba la ventana. Tk se
    quedaba con la pantalla virtualizada (1536 en vez de 1920) pero ya
    colocaba en pixeles fisicos, y el panel aparecia a 400px de la esquina y
    un 20% mas pequeno.
    """
    from helper import capture, dpi
    from helper.ui import theme

    section("[dpi] conciencia declarada")
    dpi.enable_awareness()
    factor = dpi.scale_factor()
    check("el factor es razonable", 0.5 <= factor <= 4.0, f"x{factor}")

    section("[dpi] Tk y mss hablan en la misma unidad")
    from helper.config import Config
    from helper.ui.app import App

    cfg = Config()
    cfg.save = lambda: None  # type: ignore[method-assign]
    app = App(cfg)
    panel = app.panel
    panel.update_idletasks()

    fisico = next(m for m in capture.list_monitors() if m.primary)
    check("tk ve el ancho fisico", panel.winfo_screenwidth() == fisico.width,
          f"tk={panel.winfo_screenwidth()} fisico={fisico.width}")
    check("las medidas se escalan con el dpi",
          theme.WIDTH == round(theme._BASE_WIDTH * factor),
          f"WIDTH={theme.WIDTH} factor={factor}")

    section("[dpi] el panel aterriza en la esquina")
    panel.place_at(None, None, None)
    panel.update_idletasks()
    margen_der = fisico.width - (panel.winfo_x() + panel.winfo_width())
    margen_inf = fisico.height - (panel.winfo_y() + panel.winfo_height())
    check("margen derecho correcto", margen_der == 24, f"{margen_der}px")
    check("margen inferior correcto", margen_inf == 64, f"{margen_inf}px")

    app.panel.after(50, app.quit)
    app.run()


def test_aislamiento_sesiones() -> None:
    """Una sesion = un prompt, y ninguna hereda nada de otra."""
    from helper.config import Config
    from helper.session import Session
    from helper.ui import dialogs
    from helper.ui.app import App

    section("[sesiones] cada una va por su cuenta")
    a = Session(preprompt="soy A")
    b = Session(preprompt="soy B")
    check("conversaciones con id distinta", a.session_id != b.session_id)
    check("carpetas de capturas separadas", a.shots_dir != b.shots_dir)
    check("cada una conserva su prompt", (a.preprompt, b.preprompt) == ("soy A", "soy B"))
    a.close()
    b.close()

    cfg = Config()
    cfg.save = lambda: None  # type: ignore[method-assign]
    app = App(cfg)

    section("[sesiones] la sesion nueva no hereda el prompt anterior")
    app.session = Session(preprompt="instrucciones de la sesion anterior")
    dlg = dialogs.SessionDialog(app.panel, cfg)
    escrito = dlg.preprompt.get("1.0", "end").strip()
    check("la caja arranca vacia", escrito == "", repr(escrito))
    check("las plantillas siguen a mano", len(cfg["presets"]) > 0)
    dlg.destroy()

    section("[sesiones] editar no puede tocar el pre-prompt")
    sess = Session(preprompt="no me toques", capture_mode="active_monitor")
    app.session = sess
    ed = dialogs.EditSessionDialog(app.panel, cfg, sess)
    ed.target.modes.set("active_window")
    ed._accept()
    check("solo devuelve el target", set(ed.result) == {"mode", "monitor_index"},
          str(ed.result))
    check("el prompt de la sesion sigue igual", sess.preprompt == "no me toques")
    sess.close()

    section("[sesiones] la config no guarda pre-prompts")
    check("no queda last_preprompt", "last_preprompt" not in cfg.data)

    app.panel.after(50, app.quit)
    app.run()


# ------------------------------------------------------------ varias sesiones


def test_varias_sesiones() -> None:
    from helper.claude_client import Reply
    from helper.config import Config
    from helper.session import Session
    from helper.ui.app import MAX_SESIONES, App

    cfg = Config()
    cfg.save = lambda: None  # type: ignore[method-assign]
    app = App(cfg)

    section("[sesiones] varias abiertas a la vez")
    a = Session(preprompt="primera", capture_mode="active_monitor")
    b = Session(preprompt="segunda", capture_mode="active_window")
    app.sessions.extend([a, b])
    app.indice = 0
    check("la activa es la primera", app.session is a)
    check("el estado dice en cual estas", "[1/2]" in app._status(), app._status())
    check("y como se llama", "primera" in app._status(), app._status())

    section("[sesiones] cada sesion se identifica con un titulo")
    from helper.session import titulo_desde_prompt
    check("sin prompt lo dice", titulo_desde_prompt("") == "Sin pre-prompt")
    check("el prompt corto va entero",
          titulo_desde_prompt("Depurar el build") == "Depurar el build")
    largo = titulo_desde_prompt("Resuelve los quizzes de estadistica en pantalla")
    check("el largo se acorta", len(largo) <= 29, repr(largo))
    check("corta por palabra entera", " " not in largo[-2:], repr(largo))
    con_plantilla = Session(preprompt="parrafos y parrafos", title="Data science")
    check("la plantilla titula la sesion", con_plantilla.label == "Data science")

    section("[sesiones] las flechas rotan entre ellas")
    app.modo = "cambiar"
    app._con_flecha("right")
    check("derecha pasa a la siguiente", app.session is b)
    check("el estado se actualiza", "[2/2]" in app._status(), app._status())
    app._con_flecha("right")
    check("da la vuelta al llegar al final", app.session is a)
    app._con_flecha("left")
    check("izquierda va hacia atras", app.session is b)
    app.modo = None

    section("[sesiones] cada una conserva su respuesta")
    a.remember("respuesta de la primera")
    b.remember("respuesta de la segunda")
    app.indice = 0
    app._mostrar_sesion_activa()
    check("el panel muestra la de la activa",
          "primera" in app.panel.answer.get("1.0", "end"))
    app.indice = 1
    app._mostrar_sesion_activa()
    check("al cambiar aparece la otra",
          "segunda" in app.panel.answer.get("1.0", "end"))

    section("[sesiones] la respuesta llega a SU sesion, no a la activa")
    app.indice = 0
    app._mostrar_sesion_activa()   # como si hubieras cambiado con las flechas
    app._on_reply(b.session_id, Reply("tardia", 0.02, 100, b.session_id))
    check("se guarda en la sesion que pregunto", b.last_answer == "tardia")
    check("no pisa la que estas mirando",
          "primera" in app.panel.answer.get("1.0", "end"))

    section("[sesiones] cerrar una deja vivas las demas")
    app.indice = 1
    app.end_session()
    check("queda una abierta", len(app.sessions) == 1, str(len(app.sessions)))
    check("la que queda es la otra", app.session is a)
    check("sin varias, el estado no numera", "[" not in app._status(), app._status())
    app.end_session()
    check("sin sesiones vuelve a vacio", app.session is None)

    section("[sesiones] el tope")
    check("el tope es 6", MAX_SESIONES == 6, str(MAX_SESIONES))

    section("[sesiones] el modo cambiar necesita dos")
    app.sessions.append(Session(preprompt="unica"))
    app.indice = 0
    app._toggle_switch_mode()
    check("con una sola no entra", app.modo is None)
    app.sessions.append(Session(preprompt="otra"))
    app._toggle_switch_mode()
    check("con dos si entra", app.modo == "cambiar", repr(app.modo))
    check("toma solo izquierda y derecha", len(app._flechas) in (2, 3),
          str(len(app._flechas)))
    app._toggle_switch_mode()
    check("el mismo atajo lo apaga", app.modo is None)

    section("[sesiones] los dos modos no se pisan")
    app._toggle_move_mode()
    check("mover activo", app.modo == "mover")
    app._toggle_switch_mode()
    check("cambiar reemplaza a mover", app.modo == "cambiar", repr(app.modo))
    app._stop_modo()
    check("suelta las flechas al salir", app._flechas == [])

    section("[sesiones] hay atajo de serie para cambiar")
    check("alt+2 de serie", cfg["switch_hotkey"] == "alt+2", cfg["switch_hotkey"])

    section("[historial] las respuestas se acumulan en la sesion")
    hs = Session(title="historial")
    app.sessions.append(hs); app.indice = len(app.sessions) - 1
    hs.remember("aviso de apertura", "dim", reemplaza=True)
    app._mostrar_sesion_activa()
    check("el aviso no se acumula", len(hs.historial) == 1, str(len(hs.historial)))
    for i in (1, 2, 3):
        app.busy = True
        app._on_reply(hs.session_id, Reply(f"Respuesta {i}.", 0.01, 100, hs.session_id))
    app.panel.update()
    check("cada respuesta suma una entrada", len(hs.historial) == 4,
          str(len(hs.historial)))
    check("el panel las pinta todas", len(app.panel._entradas) == 4)
    check("lo anterior sigue a la vista",
          "Respuesta 1." in app.panel.answer.get("1.0", "end"))
    check("la ultima queda abajo del todo",
          app.panel.answer.yview()[1] >= 0.999, str(app.panel.answer.yview()))
    check("copiar da solo la ultima",
          app.panel.answer.get("ultima_respuesta", "end").strip() == "Respuesta 3.",
          repr(app.panel.answer.get("ultima_respuesta", "end").strip()))

    section("[historial] el panel sigue midiendo la ultima respuesta")
    # Sin esto el area crecia con una respuesta larga y ya no volvia a
    # encogerse: medía la ventana asomada al historial, no la ultima entrada.
    app.busy = True
    largo = chr(10).join(f"- punto {i}" for i in range(14))
    app._on_reply(hs.session_id, Reply(largo, 0.01, 100, hs.session_id))
    app.panel.update()
    alta = int(app.panel.answer.cget("height"))
    app.busy = True
    app._on_reply(hs.session_id, Reply("Corta.", 0.01, 100, hs.session_id))
    app.panel.update()
    baja = int(app.panel.answer.cget("height"))
    check("una respuesta larga agranda el area", alta >= 8, str(alta))
    check("y una corta lo vuelve a encoger", baja <= 4, f"{baja} (venia de {alta})")

    section("[historial] Alt+5 activa el modo releer")
    check("alt+5 de serie", cfg["scroll_hotkey"] == "alt+5", cfg["scroll_hotkey"])
    antes = app.panel.answer.yview()
    app._toggle_scroll_mode()
    check("entra en modo scroll", app.modo == "scroll", repr(app.modo))
    check("toma arriba y abajo", len(app._flechas) in (2, 3), str(len(app._flechas)))
    app._con_flecha("up"); app._con_flecha("up"); app.panel.update()
    check("las flechas suben por el historial",
          app.panel.answer.yview()[0] < antes[0],
          f"{app.panel.answer.yview()[0]:.3f} vs {antes[0]:.3f}")
    app._toggle_scroll_mode(); app.panel.update()
    check("el mismo atajo sale del modo", app.modo is None)
    check("y vuelve a la ultima respuesta",
          app.panel.answer.yview()[1] >= 0.999, str(app.panel.answer.yview()))
    app.end_session()

    section("[atajos] traer al frente")
    check("alt+f de serie", cfg["front_hotkey"] == "alt+f", cfg["front_hotkey"])
    app.panel.update()
    alto = app.panel.winfo_height()
    app.panel.toggle_collapse(); app.panel.update()
    app.events.put(("frente", None)); app._drain(); app.panel.update()
    check("el atajo lo despliega si estaba encogido",
          app.panel.winfo_height() >= alto - 4, str(app.panel.winfo_height()))
    check("y lo deja encima", bool(app.panel.attributes("-topmost")))

    section("[atajos] encoger el panel")
    check("alt+e de serie", cfg["collapse_hotkey"] == "alt+e", cfg["collapse_hotkey"])
    app.panel.update()
    alto = app.panel.winfo_height()
    app.events.put(("colapsar", None)); app._drain(); app.panel.update()
    check("el atajo colapsa al encabezado",
          app.panel.winfo_height() <= app.panel.header_height + 4,
          str(app.panel.winfo_height()))
    app.events.put(("colapsar", None)); app._drain(); app.panel.update()
    check("y lo vuelve a desplegar", app.panel.winfo_height() == alto,
          f"{app.panel.winfo_height()} vs {alto}")

    section("[plantillas] depurar: correcciones exactas")
    dep = next(p["texto"] for p in cfg["presets"] if "Depurar" in p["nombre"])
    check("dice reemplazar o insertar", "REEMPLAZA o INSERTA" in dep)
    check("pide archivo y rango de lineas", "rango exacto" in dep)
    check("pide el antes y el despues", "ANTES:" in dep and "DESPUES:" in dep)
    check("pide lineas de ancla", "linea de ancla" in dep)
    check("prohibe inventarse los numeros", "no te los inventes" in dep)
    check("ancla por texto si no hay numeros", "por texto" in dep)
    check("guia que archivo capturar", "el archivo y el rango de lineas" in dep)
    check("dice que significaria cada resultado", "cada resultado" in dep)
    check("redacta la consulta a la IA guia", "mensaje LITERAL" in dep)
    check("la consulta va lista para copiar", "listo para copiar" in dep)

    section("[plantillas] variantes what if")
    whatif = next((p for p in cfg["presets"] if "what if" in p["nombre"]), None)
    check("la plantilla esta", whatif is not None)
    if whatif:
        t = whatif["texto"]
        check("busca el comentario en el editor", "what if" in t)
        check("cubre los dos marcadores de comentario",
              "# what if" in t and "// what if" in t)
        check("pide decir si el codigo actual sobrevive", "STILL WORKS" in t)
        check("exige un input concreto cuando rompe", "concrete input" in t)
        check("pide complejidad antes y despues", "BEFORE and AFTER" in t)
        check("no inventa enmiendas si no las hay", "do not invent one" in t)
        check("el nombre avisa de la memoria", "memoria" in whatif["nombre"])
        check("se apoya en las capturas anteriores",
              "REMEMBER EVERY EARLIER SCREENSHOT" in t)
        check("misma foto = otra via",
              "SAME AS THE PREVIOUS ONE" in t and "ANOTHER WAY" in t)
        check("prohibe el maquillaje como via nueva", "is NOT another" in t)
        check("compara con las vias ya dadas", "compare it with the ones" in t)
        check("admite quedarse sin vias", "run out of distinct approaches" in t)
        check("si la foto cambio, vuelve al camino normal",
              "If the screenshot DID change" in t)

    section("[plantillas] el work simulation de Amazon")
    nombres = [p["nombre"] for p in cfg["presets"]]
    amazon = next((p for p in cfg["presets"] if "Amazon" in p["nombre"]), None)
    check("la plantilla esta", amazon is not None, str(nombres))
    if amazon:
        check("nombra los Leadership Principles",
              "Leadership Principle" in amazon["texto"])
        check("cubre el caso de la peor opcion",
              "LEAST effective" in amazon["texto"])

    section("[plantillas] pruebas de aptitud (SHL y similares)")
    apt = next((p for p in cfg["presets"] if "SHL" in p["nombre"]), None)
    check("la plantilla esta", apt is not None, str(nombres))
    if apt:
        t = apt["texto"]
        check("formato fijo", all(k in t for k in
              ("ANSWER:", "CONFIDENCE:", "WHY:", "SHORTCUT:")))
        check("cubre True / False / Cannot Say", "Cannot Say" in t)
        check("responde en ingles", t.rstrip().endswith("Answer in English."))

    app.panel.after(50, app.quit)
    app.run()


def main() -> int:
    for test in (
        test_hotkey,
        test_config,
        test_capture,
        test_client,
        test_session,
        test_memoria,
        test_app,
        test_plantillas,
        test_idioma,
        test_idioma_en_la_pregunta,
        test_formato_respuesta,
        test_render_codigo,
        test_panel_multimonitor,
        test_dpi,
        test_aislamiento_sesiones,
        test_varias_sesiones,
    ):
        test()

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n{passed}/{total} pruebas pasan")
    if passed != total:
        print("\nFallaron:")
        for name, ok, extra in results:
            if not ok:
                print(f"  - {name}  {extra}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
