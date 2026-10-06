"""Cliente de Groq: la otra opcion de modelo, ademas de Claude.

Habla con la API compatible con OpenAI de Groq por HTTP, con la libreria
estandar: el proyecto no arrastra un SDK para una sola llamada.

Tiene la misma forma que `ClaudeClient.send` para que la app no distinga. Dos
diferencias que si importan:

- Groq no guarda conversaciones. El historial de "Usar pasados" en modo
  imagenes se lleva aqui, en memoria, por id de conversacion. Las capturas
  viejas se guardan como texto: Groq acepta pocas imagenes por peticion.
- Si `groq_model` es de solo texto (gpt-oss, llama...) y el turno lleva una
  captura, esa peticion va al modelo de vision
  (`groq_vision_model`). Si no hay ninguno, se manda solo el texto.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from .claude_client import ClaudeError, Reply
from .log import log

API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Modelos de Groq que aceptan imagenes. Lo que no este aqui se trata como solo
# texto.
VISION_MODELS = {"qwen/qwen3.8-27b"}

# Tope de imagenes por peticion que acepta Groq.
MAX_IMAGES = 3

# Turnos que se guardan por conversacion. Mas alla, el contexto solo encarece
# y alarga la espera sin aportar.
MAX_TURNS = 20

# Lo que una captura descuenta del cupo de tokens por minuto (8000 en el plan
# gratuito), mientras no haya una medida. Medido: la imagen cuenta 2048 fijos
# para el limite, mas ~620 de instrucciones y la respuesta. Una plantilla
# larga gasta mas: por eso, tras cada respuesta, se usa lo que gasto esa.
COSTE_CAPTURA = 2800

# Para el limite, cada imagen cuenta 2048 tokens; en `usage` aparece con ~770.
# La diferencia hay que sumarla a mano.
RECARGO_IMAGEN = 2048 - 770

# Si Groq no dice cuanto esperar, lo que tarda en rellenarse el minuto.
PAUSA_POR_DEFECTO = 60.0
# Lo minimo que se espera tras un 429, diga Groq lo que diga.
PAUSA_MINIMA = 3.0

# Tras agotar el cupo DIARIO (200k tokens en el plan gratuito, ~50 capturas).
PAUSA_DIARIA = 300.0

PREVIOUS_SHOT = "[captura anterior: ya no la ves; usa lo que respondiste sobre ella]"


class GroqError(ClaudeError):
    """Hereda de ClaudeError para que la app los trate igual."""


class GroqLimite(GroqError):
    """Se agoto el cupo por minuto. `segundos`: cuanto falta para que vuelva."""

    def __init__(self, mensaje: str, segundos: float) -> None:
        super().__init__(mensaje)
        self.segundos = segundos


def _segundos(valor: str | None) -> float | None:
    """'7.66s', '1m30.5s', '142ms' o '12' -> segundos. None si no se entiende."""
    if not valor:
        return None
    valor = valor.strip()
    try:
        return float(valor)
    except ValueError:
        pass
    total, numero = 0.0, ""
    i = 0
    while i < len(valor):
        c = valor[i]
        if c.isdigit() or c == ".":
            numero += c
        elif valor.startswith("ms", i):
            total += float(numero or 0) / 1000
            numero = ""
            i += 1
        elif c in "hms":
            total += float(numero or 0) * {"h": 3600, "m": 60, "s": 1}[c]
            numero = ""
        else:
            return None
        i += 1
    return total if not numero else None


def _image_part(path: Path) -> dict:
    data = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}}


def _sin_imagenes(content: list[dict]) -> str:
    """Un mensaje con capturas, aplanado a texto para guardarlo en el historial."""
    partes = []
    for part in content:
        if part["type"] == "text":
            partes.append(part["text"])
        else:
            partes.append(PREVIOUS_SHOT)
    return "\n\n".join(partes)


class GroqClient:
    def __init__(self, config) -> None:
        self.config = config
        # id de conversacion -> mensajes (sin system prompt, sin imagenes).
        self._historial: dict[str, list[dict]] = {}
        # Hasta cuando (time.time()) no tiene sentido llamar: el cupo del
        # minuto esta agotado. La app manda esas capturas a Claude.
        self.pausa_hasta = 0.0
        # Lo que desconto la ultima captura del cupo; arranca en la estimacion.
        self.coste = COSTE_CAPTURA

    @property
    def pausa_restante(self) -> float:
        """Segundos que faltan para que Groq tenga cupo otra vez (0 = ya)."""
        return max(0.0, self.pausa_hasta - time.time())

    def _pausar(self, segundos: float) -> None:
        self.pausa_hasta = max(self.pausa_hasta, time.time() + segundos)

    def _medir_coste(self, data: dict, mensajes: list[dict]) -> None:
        """Cuanto desconto del cupo esta captura, para prever la siguiente."""
        try:
            total = int(data["usage"]["total_tokens"])
        except (KeyError, TypeError, ValueError):
            return
        imagenes = sum(
            1 for m in mensajes if isinstance(m["content"], list)
            for p in m["content"] if p.get("type") == "image_url"
        )
        if imagenes:  # sin imagen no es una captura: no sirve de medida
            self.coste = total + RECARGO_IMAGEN * imagenes

    def _anotar_cupo(self, headers) -> None:
        """Si lo que queda del minuto no da para otra captura, pausa ya.

        Asi la siguiente va directa a Claude en vez de gastar un intento en
        un 429 seguro.
        """
        try:
            quedan = int(headers.get("x-ratelimit-remaining-tokens"))
        except (TypeError, ValueError):
            return
        coste = self.coste
        if quedan >= coste:
            return
        lleno = _segundos(headers.get("x-ratelimit-reset-tokens"))
        try:
            tope = int(headers.get("x-ratelimit-limit-tokens"))
        except (TypeError, ValueError):
            tope = 0
        if lleno is None or tope <= quedan:
            self._pausar(PAUSA_POR_DEFECTO)
            log.info("groq: quedan %d tokens del minuto, no alcanza para otra "
                     "captura (~%d); pausa %.0fs", quedan, coste, PAUSA_POR_DEFECTO)
            return
        # El cupo se rellena poco a poco (medido: ~tope/60 por segundo), y
        # `reset-tokens` es lo que falta para llenarlo entero. No hace falta
        # tanto: basta con que vuelva a alcanzar para una captura.
        espera = lleno * (min(coste, tope) - quedan) / (tope - quedan)
        self._pausar(espera)
        log.info("groq: quedan %d de %d tokens del minuto, no alcanza para otra "
                 "captura (~%d); pausa %.1fs", quedan, tope, coste, espera)

    def _api_key(self) -> str:
        # El .env (GROQ_API_KEY) gana: es donde se configura a proposito.
        key = str(
            os.environ.get("GROQ_API_KEY") or self.config.get("groq_api_key") or ""
        ).strip()
        if not key:
            raise GroqError(
                "Falta la API key de Groq. Ponla en GROQ_API_KEY del archivo "
                ".env del proyecto (ver .env.example) y reinicia el helper."
            )
        return key

    def _modelo(self, con_imagen: bool) -> str:
        modelo = self.config["groq_model"]
        if con_imagen and modelo not in VISION_MODELS:
            return self.config.get("groq_vision_model") or modelo
        return modelo

    def send(
        self,
        session_id: str,
        question: str,
        image_path: Path | None = None,
        resume: bool = False,
        system_prompt: str = "",
        timeout: float = 120.0,
        model: str | None = None,
        effort: str | None = None,
        extra_images: list[tuple[str, Path]] | None = None,
    ) -> Reply:
        # `model`/`effort` vienen de plantillas pensadas para Claude: aqui no
        # aplican. El modelo de Groq sale de la configuracion.
        del model, effort
        key = self._api_key()

        content: list[dict] = []
        for label, path in (extra_images or [])[: MAX_IMAGES - 1]:
            content.append({"type": "text", "text": label})
            content.append(_image_part(path))
        if image_path is not None:
            content.append(_image_part(image_path))
        content.append({"type": "text", "text": question})

        hay_imagen = any(p["type"] == "image_url" for p in content)
        modelo = self._modelo(hay_imagen)
        if hay_imagen and modelo not in VISION_MODELS:
            # Sin modelo de vision: mejor una respuesta a ciegas avisada que
            # un error de la API.
            content = [{
                "type": "text",
                "text": "(No puedes ver la captura de pantalla: este modelo solo "
                        "lee texto. Dilo en una linea si la pregunta depende de "
                        "ella.)\n\n" + _sin_imagenes(content),
            }]

        # `resume` no hace falta: una conversacion sigue si ya tiene historial,
        # y las sueltas llegan siempre con un id nuevo.
        del resume
        previos = self._historial.get(session_id, [])
        mensajes: list[dict] = []
        if system_prompt:
            mensajes.append({"role": "system", "content": system_prompt})
        mensajes += previos
        mensajes.append({"role": "user", "content": content})

        body = json.dumps({"model": modelo, "messages": mensajes}).encode("utf-8")
        req = urllib.request.Request(
            API_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                # Sin User-Agent propio, el de urllib a veces lo bloquea el CDN.
                "User-Agent": "helper/1.0",
            },
            method="POST",
        )

        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self._medir_coste(data, mensajes)
                self._anotar_cupo(resp.headers)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                h = exc.headers
                espera = (_segundos(h.get("retry-after") if h else None)
                          or _segundos(h.get("x-ratelimit-reset-tokens") if h else None)
                          or PAUSA_POR_DEFECTO)
                # Visto en uso real: tras un 429 Groq puede decir 0s. Volver a
                # llamar al instante seria otro 429 seguro.
                espera = max(espera, PAUSA_MINIMA)
                detalle = _detalle(exc)
                diario = "per day" in detalle
                if diario:
                    # El cupo diario es una ventana movil de 24h: se libera de a
                    # poco y Groq dice "38s", pero tras ese rato la proxima
                    # captura tampoco cabe. Mejor no insistir en un buen rato.
                    espera = max(espera, PAUSA_DIARIA)
                self._pausar(espera)
                log.info("groq: rechazo por limite %s (429); pausa %.0fs",
                         "DIARIO" if diario else "por minuto", espera)
                raise GroqLimite(_error_429(exc, diario), espera) from None
            raise GroqError(_error_http(exc)) from None
        except TimeoutError:
            raise GroqError(f"Groq no respondio en {int(timeout)}s. Reintenta.") from None
        except urllib.error.URLError as exc:
            raise GroqError(f"No pude conectar con Groq: {exc.reason}") from None
        ms = int((time.time() - t0) * 1000)

        try:
            texto = (data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError):
            raise GroqError("Groq no devolvio una respuesta") from None

        guardado = previos + [
            {"role": "user", "content": _sin_imagenes(content)},
            {"role": "assistant", "content": texto},
        ]
        self._historial[session_id] = guardado[-2 * MAX_TURNS:]

        return Reply(
            text=texto,
            # Groq no devuelve costo; el plan gratuito no factura.
            cost_usd=0.0,
            duration_ms=ms,
            session_id=session_id,
            model=modelo,
        )


def _detalle(exc: urllib.error.HTTPError) -> str:
    """El mensaje de error de Groq. Se lee una vez: el cuerpo no se rebobina."""
    if not hasattr(exc, "_detalle"):
        try:
            exc._detalle = json.loads(exc.read().decode("utf-8"))["error"]["message"]
        except Exception:
            exc._detalle = str(exc.reason or "")
    return exc._detalle


def _error_429(exc: urllib.error.HTTPError, diario: bool) -> str:
    if diario:
        return ("Groq: se agoto el cupo DIARIO del plan gratuito (200.000 tokens, "
                "~50 capturas). Se va liberando a lo largo de las proximas horas.")
    # El tope por minuto (8000): cada captura descuenta ~2800-4500.
    espera = exc.headers.get("retry-after") if exc.headers else None
    cuanto = f"{espera}s" if espera else "un momento"
    return (f"Groq: tope de tokens por minuto del plan gratuito (~2-3 capturas "
            f"por minuto). Espera {cuanto} y reintenta.")


def _error_http(exc: urllib.error.HTTPError) -> str:
    if exc.code == 401:
        return "La API key de Groq no es valida. Revisala en Configuracion."
    if exc.code == 429:
        return _error_429(exc, "per day" in _detalle(exc))
    return f"Groq respondio {exc.code}: {_detalle(exc)}"
