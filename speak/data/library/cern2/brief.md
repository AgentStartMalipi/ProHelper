# Call brief: CERN GRAE — Computer Security (IT-DI-CSO-2026-190-GRAE) — 2.ª RONDA

## Participants
- me: Maria Alejandra Lizarazo P. ("Maria"), Junior Cloud Support Engineer at Amadeus (since Apr 2026); former AWS Intern (Jun 2025 - Mar 2026). Bogota, Colombia; Spanish citizen relocating to Geneva / French border area. Spanish native, English C1, French B1.
- them: Dr. Stefan Lüders, Computer Security Architect at CERN (IT-DI-CSO). Perfil muy técnico (físico reconvertido a ciberseguridad, con trayectoria pública: papers y charlas). Espera rigor, precisión y ownership. Es el arquitecto del equipo al que entraría Maria.

## Call
- 2.ª ronda: lunes 19/10/2026, 8:00–8:30 Bogotá = 15:00–15:30 Ginebra. Zoom, "with some of my team members". Lüders: "come as you are".
- 1.ª ronda (14/10, Lüders + Liviu) ya pasó: no repetir historias como nuevas; referirse a ellas ("as I mentioned last time").
- 30 minutos, 5 personas: respuestas de ~1 minuto, primero la frase directa y luego 2–3 detalles.

## Panel (lo que se sabe viene de charlas públicas; qué preguntará cada uno es una suposición)
- Stefan Lüders (CISO, hiring manager): encaje, motivación, visión del puesto, excepciones, prioridades. Probablemente modera.
- Liviu Vâlsan (SOC; el "Levi" de la 1.ª ronda): Zeek, Kafka, OpenSearch, MISP; charla 30/09/2026 sobre lista blanca de módulos del kernel, eBPF LSM, parcheo de escaladas de privilegios y trazabilidad de comandos (uid, pid, binario, argumentos). Linux y SOC.
- José Carlos Luna Durán (Cyber Security Analyst, WLCG Security Officer): IA y ciberseguridad (human-in-the-loop, fuga de datos), rootkits y forense en Linux, crawlers de LLM, WLCG.
- Luna Durán, fuentes verificadas en Indico (18/10):
  - Bio (CHEP 2026, "AI and Cybersecurity: Power, Risk, and Responsibility"): Cyber Security Analyst at CERN y WLCG Security Officer; más de 20 años en el CERN; vulnerabilidades publicadas a su nombre. La charla: riesgos de usar IA (fuga de datos, mal uso del modelo, confiar de más en lo automático), la revisión humana sigue siendo esencial; la IA cambia las amenazas (ataques automáticos, ingeniería social a escala, scraping agresivo); la IA es un multiplicador "when guided by human judgment". Maria leyó el resumen: puede decir "I read the abstract of your CHEP talk".
  - Slides de HEPiX primavera 2025 ("Computer Security Update", 02/04/2025). Maria las lee antes de la entrevista: puede decir "I went through your HEPiX slides from last spring". Contenido: identidad (credenciales robadas, infostealers, reutilización de contraseñas, credenciales en repositorios; en el CERN 45.000 cuentas con 2FA, WebAuthn + OTP, hacia sesiones de 12 h); vulnerabilidades (software viejo, SBOM, catálogo KEV de CISA, contraseñas por defecto, un token WLCG filtrado por logs demasiado verbosos); caso Tier-2 (invierno 2024): criptominería, BMC expuesto a internet con credenciales por defecto, fácil de encontrar con Shodan, poca monitorización, el atacante tuvo meses, movimiento lateral, todas las credenciales dejaron de ser de confianza, reconstrucción completa; CI/CD (secretos en logs, GitHub Actions, self-hosted runners); DDoS o scraping agresivo para LLMs (difícil: el límite depende de cada app; hasta ahora respuesta reactiva bloqueando subredes, protocolos o países; captchas y proof-of-work como Cloudflare Turnstile o Anubis); "incidents happen, and will happen to you too, be prepared"; Forensics Cheatsheet & toolkit (cern.ch/forensics) para las primeras fases de un incidente; taller de forense y respuesta a incidentes (29-30/09/2025, CERN), SOC working group, boletín de seguridad WLCG.
  - Charla sobre rootkits en Linux: NO verificada (solo un título visto por otra IA). Nunca citarla.
- Dawid Kulikowski (llegó hace poco al CSO): construyó "Barad-Dûr" (buscador interno tipo Shodan: Django, OpenSearch, PostgreSQL, Redis); vulnerabilidades web, Python, escaneo.
- Pau Cutrina Vilalta (actualizado 18/10, fuentes públicas): operaciones de seguridad locales y RESPUESTA A INCIDENTES en el CERN; líder del Incident Response Task Force de EGI (la grid europea), con la tarea de "deriving monitoring rules"; antes software engineer en el computing de CMS. Dio charlas con Romain Wartel sobre ransomware y cibercrimen (p. ej. "'Black Hole Locker' Ransomware Affiliate Program", IT Technical Forum, 06/10/2023) y la charla de seguridad de la sesión de bienvenida (marzo 2025). Maria NO leyó esas charlas: nunca "I read/watched your talk"; como mucho "I saw you've given talks on ransomware". Probables preguntas: primera hora de un ransomware, cómo entran los grupos, programas de afiliados, reglas de monitorización sin inundar el SOC, explicar seguridad a usuarios nuevos.
- Preguntas probables por persona: 'round2_panel'. Respuestas cortas base: 'round2_bank'. Respuestas listas para leer: 'round2_answers'.

## Reglas 2.ª ronda (verificadas con Maria)
- Certificaciones de AWS: CINCO (ver más abajo). Nunca decir cuándo ni cómo las estudió.
- "What have you done to prepare since we last spoke?": solo lo que Maria confirmó: Puppet y las lecturas de la sección "Lecturas desde la 1.ª ronda". Nada más. NUNCA la mejora del triage script en esta respuesta (Maria 2026-10-18: centrarla en lo que estudió del CERN).
- Nunca afirmar que hizo hardening, usó Puppet/Ansible o administró M365. Puente: "I haven't done that in production. Here's how I would approach it..."
- Multi-agent prototype: fue un prototipo de práctica, hecho sola, para el programa interno AWSome Builder. Nunca "in production". No inventar "the lesson I learned" del prototipo.
  Hechos del repo (JOBSEARCH/interview_prep/AB2GymCoachAI_REPO_REVIEW.md, 2026-10-18): diseñado para Bedrock AgentCore, CONSTRUIDO como prototipo parcial en Amazon Bedrock Agents (orquestador supervisor + agente de entrenamiento + agente de nutrición; action groups con Lambdas en Python sobre DynamoDB); CDK en TypeScript (NUNCA "CDK in Python"); Cognito, API Gateway, WAF. Strands, los servicios de AgentCore (Identity incluido) y la Knowledge Base/RAG solo en el diagrama. Cada agente solo tenía sus herramientas; el chat no pasaba el usuario autenticado a los agentes y su rol era amplio (InvokeAgent sobre *); sin aprobación humana ni guardrails.
- No afirmar que el CERN usa Conditional Access, Secure Score o PIM: preguntarlo.
- Las slides de Liviu (HTCondor, 30/09) y su charla de Zeek: Maria las leyó (confirmado 2026-10-17). Barad-Dûr: Maria SÍ leyó las slides de Dawid (confirmado 2026-10-18), ver la sección de Barad-Dûr abajo. Para "which systems are affected by a new CVE" desde dentro (imágenes), citar "The road to SBOM"; desde fuera (qué hosts lo corren), Barad-Dûr. Citar Barad-Dûr como mucho una vez en la entrevista.

## Role
GRAE (Graduate Research and Engineering) en el CSO (Computer Security Office), Dept. IT (IT-DI). No es software genérico: es seguridad operativa y de arquitectura. Foco en SOC, seguridad cloud y pentesting, dentro de una institución científica internacional.

## Objective
Pasar la entrevista y demostrar: (1) base técnica sólida en seguridad de redes, Linux y cloud, (2) capacidad de aprender herramientas nuevas, (3) encaje con cultura internacional y con las guardias/trabajo nocturno, (4) motivación real por el CERN y por la ciencia.

## Responsabilidades reales del puesto (del anuncio)
1. SOC: mantener, dar soporte y ampliar la infraestructura de detección y respuesta a incidentes, con herramientas open source: Zeek (análisis de tráfico), OpenSearch (logs), Apache Kafka (flujos de datos), Kubernetes, MISP (inteligencia de amenazas).
2. Seguridad en la nube: configurar servicios cloud de IT (AWS, GCP, Azure, Oracle) y revisar la seguridad de Microsoft 365 y Google Workspace.
3. Extras: otros proyectos de seguridad, asesoría y pruebas de penetración.

## Lo que piden (mapear cada punto a mis experiencias)
- Diseño de redes y protocolos de comunicación.
- Administración y mantenimiento de sistemas (preventivo y correctivo).
- Seguridad informática, configuraciones seguras, análisis de seguridad y pentesting.
- Preferible: monitoreo y respuesta a amenazas.
- Muy buen conocimiento de Linux/UNIX, virtualización y bases de datos.
- Shell scripting y Python o C. Kubernetes.
- Buenas prácticas de desarrollo seguro en AWS, Google y Microsoft cloud.
- Inglés fluido y compromiso de aprender francés.

## Fit de elegibilidad (confirmado)
- Nacional de país miembro (España). Máx. 2 años desde graduación. Título pregrado/máster, sin PhD. Sin contrato previo de fellow/graduado en CERN. Todo cumplido.

## Condiciones
- 24 meses, ampliable a 36. CHF 5.266/mes (pregrado) o 5.793 (máster). Híbrido, 40h.
- 30 días de vacaciones + cierre anual. Seguro, pensión, mudanza, clases de idiomas.
- GUARDIAS y trabajo de noche, domingos o festivos cuando sea necesario. Inicio previsto 1-oct-2026 (ya pasó: preguntar fecha real en la entrevista).

## Preguntas probables (seguridad + behavioral)
Técnicas:
- "Explica la diferencia entre IDS e IPS. ¿Dónde encaja Zeek?"
- "¿Cómo funciona el handshake TLS a grandes rasgos? ¿Qué es un certificado X.509?"
- "¿Qué mirarías primero al asegurar un clúster de Kubernetes?"
- "¿Cómo detectarías un incidente en tráfico de red? ¿Qué logs y fuentes usarías?"
- "Diferencia entre autenticación y autorización. Ejemplos de fallos típicos."
- "¿Cómo asegurarías un bucket/rol de AWS? ¿Qué es IAM y qué errores comunes ves?"
- "¿Qué es MISP y para qué sirve la inteligencia de amenazas?"
- "¿Has hecho pentesting? Describe un hallazgo y cómo lo explotarías/arreglarías."
- "Linux: describe un troubleshooting de sistema y qué comandos usarías."

Behavioral (STAR comprimido):
- "Cuéntame un bug/incidente difícil que resolviste."
- "Un proyecto del que estés orgullosa."
- "Un desacuerdo técnico con un compañero. ¿Cómo lo resolviste?"
- "¿Cómo trabajas en equipos grandes e internacionales?"
- "¿Estás dispuesta a guardias y turnos nocturnos/festivos?"
- "¿Por qué el CERN? ¿Por qué seguridad?" (investigación, ciencia, impacto, entorno internacional)

## Questions to ask
- "¿Cuál es el mayor reto de seguridad hoy en una infraestructura científica abierta como el CERN?"
- "¿Cómo está estructurado el equipo CSO y con qué áreas (WLCG, grid, IT) colabora?"
- Las preguntas finales están en 'questions_for_them' (orden y reservas); usar esas.
- "What would someone in this role work on in the first months?" (nunca decir "GRAE": es la jerga del código de la oferta)
- "What would a realistic start date look like?" (nunca "October 1st already passed": suena a reclamo)
- "How is the on-call rota organised in the team?"
- Más hechos verificados del CERN (2026-10-13): artículo "Are you a team player?" (13 ene 2025): un infostealer en el PC personal de un colega robó contraseñas de Chrome, entre ellas la de una instancia de prueba de un servicio crítico; los atacantes intentaron tomarla y producción se salvó. Campañas de phishing propias del CERN: 15.2% y luego ~22% de clics ("about one in five"). NO verificados (nunca decirlos): "11%", "10,000+ websites", que el artículo "Copied, committed, KO" hable de Polyfill.

## Preparation since round one — confirmed by Maria, 2026-10-16
- Maria reviewed topics she struggled with in the first interview, especially Puppet and tracing activity inside containers.
- She shared a study checklist. Its unchecked items are a plan, NOT proof she watched every video, read every linked document, completed every block or ran a hands-on lab.
- Safe answer: "I went back over the topics I struggled with in our first interview, especially Puppet and tracing activity inside containers."
- Discuss the concepts she reviewed, but do not claim production experience or a completed practical exercise.

## Gaps a cubrir antes de la entrevista
- Si no hay experiencia directa con Zeek/Kafka/MISP: preparar cómo lo aprendería y qué es cada uno.
- Repasar Kubernetes (hardening, RBAC, network policies) y AWS IAM (roles, políticas, least privilege).
- No tengo pentesting propio. Ejemplos de análisis de seguridad: el túnel, el script de solo lectura, Key Vault.
- Triage script (details from the code, 2026-10-12): see 'triage_script_details'. She uses it for her own investigations at Amadeus: never call it one-off, a test or something she doesn't use. Read-only means the script only does GETs, reads pages and screenshots; it is NOT enforced by a read-only role or scope: never claim it is. Authentication = my own SSO session in Chrome (MFA), plus the page's anti-CSRF token for the ticket API; no stored keys. It opens only the first Thanos, Grafana and Splunk link; it doesn't find root cause or update tickets. MEJORA RECIENTE (Maria, 2026-10-18): lo amplió con Copilot, la única IA aprobada del todo por Amadeus para datos internos; ahora busca incidentes pasados parecidos y reutiliza las búsquedas que funcionaron, y guarda una lista de partes de la arquitectura que aún no entiende (su plan de estudio en días tranquilos). Ella revisa cada query que Copilot redacta antes de ejecutarla. Llamarlo siempre "script", nunca "agent". Ya salió en la 1.ª ronda (27:21) y a Stefan le gustó ("writing scripts left and right to make your life easier"). Cuándo usarlo: Copilot aprobado si sale IA o el prototipo multiagente (Luna Durán); incidentes pasados si Liviu o Pau preguntan cómo investiga; la lista de lo que no entiende si preguntan cómo aprende (Stefan); "only reads, with my own login" si preguntan si es seguro. NUNCA contar: miedo, sudor frío, la formación que no se dio, que piensa irse, el post de LinkedIn, detalles internos de Amadeus.
- Scripting (Maria, 2026-10-12): a small PowerShell script at Amadeus (NEVER at AWS) that refreshes the incident queue page so she sees it up to date; daily Linux command line at Amadeus, mainly `kubectl get pods | grep` to find specific pods. Never claim "shell scripting" or bash scripting in general beyond that. The AWS public-event script: say "a small script that collected public event information", never "web scraping" or "agents".
- Key Vault (Maria, 2026-10-12): detalles en 'key_vault_details'. Cómo se autenticaba el flujo ante el propio Key Vault NO está en mis notas: nunca decir managed identity, service principal ni access policies como algo que usé; eso solo como "today I'd...". Quién accedía al vault: la intención era solo el flujo, sin confirmar.
- Recent changes (Maria, 2026-10-12): see 'recent_changes_how'. Not in my notes: which tool holds the change records, and what exactly the TLS change was (certificate, protocol version, ciphers...). Never name a tool or a specific TLS setting as fact. Logs: ALF (Amadeus Logging Facility, internal), see 'logging_facility_alf'. Never claim GitOps, deployment annotations or CI/CD pipeline history as something I used, and never deny them either: where I saw the change record is NOT in my notes. Recent case (from the real ticket, 2026-10-09): see 'login_failure_case'. It was AUTHENTICATION, not TLS: never mention TLS, certificates or a handshake for it. My part: the investigation in Splunk and finding the candidate change; the SRE team confirmed it and owns the fix. Change records (Maria, 2026-10-13): I searched them in an internal tool that lets us search for recent changes, then compared timestamps; the tool's name is not in my notes, never name it. My own part, in my words: see 'login_contribution'. Not in my notes: how the LDAP / Keycloak setup works inside. Never name the airport, the airline, hosts or ticket numbers.
- Payment link case (real ticket, 2026-10-05): see 'third_party_link_down'. My part was only checking our side (Splunk, Grafana, maintenance calendar); the payments team found the provider didn't respond; I did not contact the provider or find the root cause. Never name the merchant, the link or the provider. Number of affected transactions: NOT in my notes. The ONLY facts: an alert said the link to one external payment provider was down and card payments were timing out; in Splunk the card payment dashboard showed a spike of failures from 15:00 GMT, already going down when I looked; Grafana and the maintenance calendar showed nothing planned on our side that explained it; the payments team confirmed the provider hadn't answered for about 40 minutes; the link recovered on its own. The failures DID show on our side: never say 'no errors', 'our side was clean' or 'no deploys'. Never invent who saw it ('customers at checkout', 'a link on our pages') or that I found the root cause.
- Slides de Liviu en HTCondor, slide 10 (verificado 2026-10-18): "Time-to-Exploit has gone negative" (exploits publicados antes de que las distribuciones saquen el parche). Cita para "mitigar antes de parchear".
- WLCG (verificado 2026-10-18, wlcg-public.web.cern.ch): unos 170 centros de cálculo en más de 40 países. Nunca "thousands of institutes" ni "150 sites".
- OpenVox (público, VoxConf 16/07/2026, "Migrating to OpenVox at CERN"): el CERN migra su flota Puppet (~15.000 nodos) a OpenVox, el fork comunitario de Puppet. Maria NO leyó esas slides: "since you're migrating to OpenVox", nunca "I read".
- Token del banco: si alguna vez llegó a caducar o fallar en la práctica NO se sabe. Nunca "it never happened", "it was never a problem", "I never saw it fail", "it never ran out on me" ni "it did expire". Respuesta a "did it ever fail/expire?": "I organised the batches precisely so that wouldn't happen." y el porqué (lotes largos, unas tres horas).
- Freelance: el vault lo creó ella (confirmado 2026-10-12). La API del banco SÍ permitía consultar el estado de un pago (Maria, 2026-10-18): la idempotencia (ID único antes de la llamada, estado guardado antes de enviar, consultar el estado antes de reintentar) se cuenta como algo que hizo.
- Charlas de Luna Durán "Agents gone wild" y la de rootkits: solo se conocen los títulos. NUNCA citarlas.
- Ronda 1 (transcripción 14/10): Stefan dijo que la revisión de M365 ya se hizo hace unos dos años y que el trabajo cloud es más o menos un tercio del tiempo al principio.
- Incidentes de Amadeus (Maria, 2026-10-18): son incidentes de PRODUCCIÓN, NO de seguridad. Si una pregunta da por hecho que ya hace seguridad o ciberseguridad en Amadeus o AWS ("continue that cybersecurity path", "your security incidents"), aclararlo primero en una línea: "Just to clarify, the incidents I handle at Amadeus are production incidents, not security incidents." Nunca llamarlos security incidents.
- My role at Amadeus (Maria, 2026-10-12): I investigate incidents, then fix them or escalate them with evidence. She does NOT protect, secure or harden any platform, nor prevent recurrence (internal fact: never SAY these negatives aloud; at most "securing the platform sits with other teams"): never say "I protect / secure / make sure it can't happen again" about Amadeus.
- Publications (checked 2026-10-12): see 'cern_publication'. Never say "I can't point to one": always name "One click to many" (CERN Computer Security Office, 28 July 2026). Facts only from that section: device code authentication, 90-day token, more than 5000 recipients, 108 clicked, tokens revoked. The ICALEPCS 2025 paper is by S. Lüders himself: mention it only if the talk goes to control systems, chemical engineering or his work, and never claim "flat networks" from it (not in the paper).
- Numbers to say (Maria misreads them live): the device code token = "three months" (never "90 days": it sounds like "nineteen"); about two hundred thousand personal devices; more than five thousand recipients; 108 clicked. Use only these; if a number is not here, describe it without one.
- CERN article "The cost of a compromise" (home.cern, checked 2026-10-13): a WLCG Tier-2 site was compromised for months and used for cryptomining; it was disconnected after detection in October 2024. Use it only as the reason to keep logs longer (intrusions are found months later). Never name the site.
- CERN facts (checked 2026-10-12, CSO Online interview with Lüders, Dec 2025): about 200,000 BYOD devices on the network; they can't install software on devices they don't own, so they monitor the network ("defense in depth"). MFA is NOT mandatory for everyone ("not everyone willingly uses multifactor authentication"): never say CERN made 2FA mandatory.
- Preparar la respuesta a guardias/turnos nocturnos (decir sí con argumento).

## Lecturas desde la 1.ª ronda (Maria, 2026-10-17; de interview_prep/cern/FRASES_LO_QUE_ESTUDIE.md)
- Puppet (repaso general).
- Falco (introducción) y las slides de Liviu en el HTCondor Workshop (30/09/2026): campos de log por comando
  (uid, euid, pid, ppid, binario, argumentos, tty); 5 pasos ante una escalada de privilegios (identify, determine
  exposure, mitigate, remediate, verify); paso de blocklist a allowlist de módulos del kernel con "delayed blocking".
- Bulletin "One click to many" (julio 2026), doc de Microsoft "Block authentication flows", CISA SCuBA / ScubaGear.
- Kubernetes Pod Security Standards (Privileged / Baseline / Restricted).
- Bulletin "The road to SBOM" (30/09/2026): GitLab dependency scanning, listado de componentes de contenedores en
  OpenStack, software gateway con cuarentena de 12–48 h.
  OJO: la cuarentena es para paquetes NUEVOS que se descargan (por si son maliciosos), NO para imágenes ya
  desplegadas con una CVE. Para "qué imágenes/workloads tienen el paquete vulnerable" lo que encaja es: un SBOM por
  imagen dice cuáles lo contienen, y el artículo cuenta que los contenedores gestionados por OpenStack ya listan sus
  componentes. Nunca citar la cuarentena para una CVE en algo ya desplegado.
- Bulletin "Copied, committed, KO" (17/06/2026): visibilidad, proxy central con cooldown.
- Charla de Liviu en Zeek Workshop 2026 ("Zeek and the Balance between Academic Freedom, Industrial Operations & Security"): Zeek → Kafka → Spark/OpenSearch, MISP. La cifra de conexiones NO es de esta charla: usar la de las slides de HTCondor.
- Slides de Liviu en HTCondor (verificadas 2026-10-18 en Indico): "Shared responsibility" entre service managers (conocer su entorno, evaluar relevancia, riesgo e impacto, parchear, validar y comunicar) y equipos de seguridad (claridad sobre vulnerabilidades y mitigación, coordinar, compartir inteligencia y herramientas, vigilar las de alto impacto). SOC del CERN: ~6 TB/día, ~3.500 millones de conexiones de red al día, ~2.500 millones de peticiones DNS, ~8.000 millones de ejecuciones de comandos; ~50M IoCs de más de 1500 pares; ~300 informes al mes, ~200 tickets al mes, 5-10 incidentes graves al año. Trazabilidad: uid, euid, gid, egid, pid, ppid, binario, argumentos, tty.
- AWS: en la 1.ª ronda se quitó mérito ("I was nothing"); corregirlo. CINCO certificaciones (Maria, 2026-10-17): Solutions Architect Associate, Machine Learning Engineer Associate, Generative AI Developer Professional, Cloud Practitioner, AI Practitioner (las dos básicas).
- Certificaciones de AWS: nunca decir cuándo ni cómo las estudió ("on my own", "while working full time", "alongside my job at Amadeus"): no está en las notas.
- Salir de Amadeus (Maria, 2026-10-18): razón principal, crecer en otro país y en seguridad; siente que ya aprendió lo central del rol junior. Hay también un tema de cultura del equipo, PRIVADO: nunca detalles, nunca criticar a Amadeus ni a compañeros, nunca "es una historia para otro momento", y nunca decir que el equipo está bien o que no hay ningún problema (no es verdad). Si insisten: "there is also a culture side, it's not the team where I see myself long term; I prefer not to go into details about colleagues". Nunca inventar cómo está organizado Amadeus (qué equipo hace seguridad, etc.).

## Barad-Dûr (slides de Dawid Kulikowski, "Automated computing asset discovery and monitoring", CH-CERTs, 07/05/2026; Maria las leyó)
- Problema: entornos académicos con controles permisivos; identificar y agrupar servicios de otros equipos, encontrar IoT inseguro, ver otras instancias de la misma aplicación, responder a vulnerabilidades graves. LanDB registra los dispositivos y su responsable.
- Es un PILOTO, un "search engine for internal web services", inspirado por dos incidentes: una vulnerabilidad crítica de Magento y un sitio del WLCG comprometido por una interfaz IPMI expuesta. No había procedimiento formal y los virtual hosts lo complicaban.
- Ingiere transferencias de zona DNS, recoge información de cada sitio, interfaz tipo Shodan con API.
- Busca por: certificado TLS, capturas de pantalla, recursos con hashes, redirecciones, cabeceras, hashes perceptuales de las capturas (botón "Similar"). Guarda histórico y notifica cambios. Agrupa duplicados (misma IP, DNS frente a IP, puertos).
- Lenguaje de búsqueda con AND, OR, NOT, comodines. Lema: "If you see it, you can search with it!"
- Ejemplo en las slides: un servidor XRootD con certificado de la CERN Grid CA caducado y todas las cabeceras de seguridad ausentes.
- Tecnología: Django, Huey (workers, "simpler than Celery"), OpenSearch + PostgreSQL, Redis.
- NO está en las slides (nunca inventarlo): tamaño, nº de sitios, frecuencia de escaneo, quién lo usa, si ya está en producción, qué CVE de Magento.
- Puppet: Maria SÍ leyó sobre los run reports y el modo noop (confirmado 2026-10-18). Fue documentación general de Puppet, NO un artículo del CERN ni del Bulletin: nunca "your Bulletin on Puppet" ni "your article on Puppet".

