"""Evaluacion de la busqueda (no es una prueba unitaria: imprime hit@k).

    .venv-speak\\Scripts\\python.exe -m speak.tests.retrieval_eval

Base chica y realista: documentos comerciales en espanol y tecnicos en
ingles, y preguntas como las que haria un cliente en una llamada, en los dos
idiomas y cruzadas (pregunta en ingles sobre un documento en espanol y al
reves). `max_chars` bajo para obligar a buscar (con pocos documentos,
`search` los manda todos y no hay nada que medir).
"""

from __future__ import annotations

from speak.knowledge import KnowledgeBase

DOCS = {
    "precios_2026.md": "Lista de precios 2026. Auditoría energética de vapor: 12.000 USD por planta. "
                       "Monitoreo IoT: 450 USD al mes por planta. Anticipo del 30 %. Descuento del 7 % "
                       "desde tres plantas.",
    "propuesta_acme.md": "Propuesta para Acme. Plazo de ejecución: 8 semanas desde el anticipo. "
                         "Entregables: informe de pérdidas, plan de mejoras priorizado y tablero de "
                         "indicadores.",
    "casos_exito.md": "Caso Cementos X: ahorro del 11 % en consumo de vapor y retorno de la inversión "
                      "en 14 meses. Caso Lácteos Y: redujo 9 % el gas natural.",
    "garantia.md": "Garantía de resultados: si el ahorro medido es menor al 5 %, se devuelve el 50 % "
                   "del valor de la auditoría. Soporte en español de lunes a viernes.",
    "equipo.md": "Equipo del proyecto: un ingeniero líder certificado CEM, dos técnicos de campo y "
                 "una analista de datos.",
    "security_whitepaper.md": "Security overview. Data is encrypted at rest with AES-256 and in transit "
                              "with TLS 1.2. Single sign-on via SAML and Azure AD. SOC 2 Type II report "
                              "available under NDA.",
    "architecture.md": "Platform architecture. Sensors publish over MQTT to an edge gateway. The cloud "
                       "backend runs on AWS: API Gateway, Lambda and Aurora PostgreSQL. Data retention "
                       "is 5 years. Availability SLA 99.9 %.",
    "integration_guide.md": "Integration guide. REST API with OAuth 2.0 client credentials. Webhooks "
                            "for alarms. Export to SAP PM and Power BI connectors. Rate limit 100 "
                            "requests per minute.",
    "sensor_datasheet.md": "SV-200 steam sensor datasheet. Measurement range 0 to 25 bar, accuracy "
                           "0.5 %. ATEX zone 2 certified. Battery life 5 years.",
    "onboarding.md": "Onboarding: installation takes two days per plant. Training for operators is "
                     "four hours, delivered remotely.",
}

# (pregunta, documento esperado, tipo)
QUESTIONS = [
    ("¿Cuánto cuesta la auditoría?", "precios_2026.md", "es→es"),
    ("¿Tienen descuento si contratamos varias plantas?", "precios_2026.md", "es→es"),
    ("¿En cuánto tiempo entregan?", "propuesta_acme.md", "es→es"),
    ("¿Qué ahorro lograron en otros clientes?", "casos_exito.md", "es→es"),
    ("¿Qué pasa si no se logra el ahorro?", "garantia.md", "es→es"),
    ("¿Quién va a estar en el equipo?", "equipo.md", "es→es"),
    ("How is the data encrypted?", "security_whitepaper.md", "en→en"),
    ("Do you support SSO with Azure AD?", "security_whitepaper.md", "en→en"),
    ("What is your uptime SLA?", "architecture.md", "en→en"),
    ("Can it integrate with SAP?", "integration_guide.md", "en→en"),
    ("What's the sensor accuracy?", "sensor_datasheet.md", "en→en"),
    ("How long does installation take?", "onboarding.md", "en→en"),
    ("How much does the audit cost?", "precios_2026.md", "en→es"),
    ("What's the payback period?", "casos_exito.md", "en→es"),
    ("Do you offer a guarantee?", "garantia.md", "en→es"),
    ("What is the delivery timeline?", "propuesta_acme.md", "en→es"),
    ("Who is on the project team?", "equipo.md", "en→es"),
    ("¿Cómo cifran los datos?", "security_whitepaper.md", "es→en"),
    ("¿Tienen inicio de sesión único?", "security_whitepaper.md", "es→en"),
    ("¿Cuál es la disponibilidad garantizada?", "architecture.md", "es→en"),
    ("¿Se integra con SAP?", "integration_guide.md", "es→en"),
    ("¿Qué precisión tiene el sensor?", "sensor_datasheet.md", "es→en"),
    ("¿Cuánto dura la instalación?", "onboarding.md", "es→en"),
    ("¿Cuánto tiempo guardan los datos?", "architecture.md", "es→en"),
]


# Escritas DESPUES de armar el diccionario bilingue, sin mirarlo: miden si
# generaliza o solo se aprendio las preguntas de arriba.
HELD_OUT = [
    ("What would we pay per plant?", "precios_2026.md", "en→es"),
    ("Is there any upfront payment?", "precios_2026.md", "en→es"),
    ("How many weeks until we get the results?", "propuesta_acme.md", "en→es"),
    ("Which companies have you worked with and what did they save?", "casos_exito.md", "en→es"),
    ("What happens if we don't see savings?", "garantia.md", "en→es"),
    ("Who would be leading the work?", "equipo.md", "en→es"),
    ("What do we receive at the end?", "propuesta_acme.md", "en→es"),
    ("¿Tienen reporte SOC 2?", "security_whitepaper.md", "es→en"),
    ("¿Cómo se conectan los sensores?", "architecture.md", "es→en"),
    ("¿Hay límite de llamadas a la API?", "integration_guide.md", "es→en"),
    ("¿Cuánto dura la batería del sensor?", "sensor_datasheet.md", "es→en"),
    ("¿La capacitación es presencial?", "onboarding.md", "es→en"),
    ("¿Pueden mandar alertas cuando hay una falla?", "integration_guide.md", "es→en"),
    ("¿Los datos quedan en la nube de Amazon?", "architecture.md", "es→en"),
]


def evaluate(k: int = 3, questions=None) -> dict[str, tuple[int, int]]:
    questions = QUESTIONS if questions is None else questions
    kb = KnowledgeBase()
    for name, text in DOCS.items():
        kb.add_text(name, text)
    out: dict[str, tuple[int, int]] = {}
    misses = []
    index = kb._extra_idx()  # el ranking puro, sin el atajo de "cabe todo"
    for q, want, kind in questions:
        hits = [c.source for _, c in index.search(q, k)]
        ok = want in hits
        h, n = out.get(kind, (0, 0))
        out[kind] = (h + ok, n + 1)
        if not ok:
            misses.append(f"  ✗ [{kind}] {q}  → {hits} (esperaba {want})")
    return out, misses


if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    for label, qs in (("diseño", QUESTIONS), ("nuevas", HELD_OUT)):
        results, misses = evaluate(questions=qs)
        print(f"--- preguntas {label} ---")
        for kind, (h, n) in results.items():
            print(f"{kind}: hit@3 {h}/{n}")
        print("\n".join(misses))
