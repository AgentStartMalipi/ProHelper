# CERN 2.ª ronda: banco de preguntas

**Lunes 19/10/2026, 8:00–8:30 Bogotá = 15:00–15:30 Ginebra, Zoom, "with some of my team members". Lüders: "come as you are".**
Junta tres investigaciones del 16/10: `research/CERN_ROUND2_PROCESS_RESEARCH.md` (proceso y equipo), `research/CERN_SECURITY_TECH_RESEARCH.md` (stack y respuestas técnicas largas) y `research/CERN_ROUND2_OUTSIDE_AI_RESEARCH.md` (la otra IA). Las respuestas largas están en la investigación técnica; aquí van las cortas.

## 1. Qué esperar
- **No es un "board" de staff.** Para graduados, el CERN solo habla de "an online interview with the hiring manager(s)". En r/CERN: "Fellow interviews are done by the hiring supervisor and the format is very loose."
- **Patrón más repetido en GRAE de IT (3 relatos 2025–2026):** 1.ª charla con el supervisor y 2.ª **más técnica con el equipo**. Esta es la tuya.
- **Lo más probable:** 2–4 personas del equipo; conversación técnica de "¿cómo harías X?" sobre el puesto y un repaso de tus proyectos. Puede haber alguna pregunta de comportamiento.
- **Live coding:** solo aparece en relatos de software, nunca en seguridad o infraestructura. Poco probable, pero ten un editor de Python a mano por si acaso.
- **Quién decide:** el supervisor (Lüders) con los jefes de sección y de grupo; RR. HH. comunica. Respuesta entre 1 día y ~4 semanas. Una 3.ª ronda suele aparecer solo si hay empate.
- **PANEL CONFIRMADO (invitación de Zoom, 16/10): Stefan Lüders, Liviu Vâlsan, José Carlos Luna Durán, Dawid Kulikowski y Pau Cutrina Vilalta.** 5 personas.
  - **Stefan Lüders (CISO):** ya lo conoces. Probablemente modera.
  - **Liviu Vâlsan (SOC; el "Levi/Livio" de la 1.ª ronda):** Zeek, Kafka, OpenSearch, MISP; charla del 30/09/2026 sobre módulos del kernel en lista blanca, eBPF LSM, parcheo de escaladas de privilegios en 5 pasos y trazabilidad de comandos (uid, pid, binario, argumentos). Preguntará por SOC, Linux y trazabilidad.
  - **José Carlos Luna Durán (Cyber Security Analyst y WLCG Security Officer, 20+ años en el CERN, varias vulnerabilidades publicadas a su nombre):** charlas de 2025–2026 sobre "AI and Cybersecurity: Power, Risk, and Responsibility" (human-in-the-loop, fuga de datos, exceso de confianza), "Linux Rootkits, the forensic delusion" y la estrategia contra el tráfico automatizado (crawlers de LLM). Puede preguntar por IA y agentes (tienes el prototipo multi-agente), forense en Linux y rootkits.
  - **Dawid Kulikowski (llegó hace poco a la Computer Security Office):** construyó "Barad-Dûr", un buscador interno tipo Shodan (Django, OpenSearch, PostgreSQL, Redis) para encontrar servicios web inseguros y responder a CVEs; antes cazaba vulnerabilidades. Perfil técnico y joven: probablemente preguntas de Python, desarrollo y vulnerabilidades web.
  - **Pau Cutrina Vilalta (CERN):** lo único público es que asistió a la Thematic CERN School of Computing on Security 2022 ([Indico](https://indico.cern.ch/event/1106023/contributions/4653277)). No se sabe su rol actual.
- Son 30 minutos: **respuestas de 1 minuto**, primero la frase directa y luego 2–3 detalles.

## 2. Las 15 más probables
| # | Pregunta | Por qué | Dónde está la respuesta |
|---|---|---|---|
| 1 | "Tell us about yourself / your background." | Siempre sale | Abajo, §3 |
| 2 | "Walk us through a project you did. What exactly did you do?" (deep dive) | 4 fuentes | §5 |
| 3 | "Last time you hadn't used Puppet/Ansible/Chef. Have you looked at it?" | Tu punto flojo; Puppet es su columna vertebral | Tech 3.2 |
| 4 | "A pod looks compromised. What do you do? How do you trace what happened inside the container?" | Tu otro punto flojo; tema de Liviu | Tech 3.5 + §4 |
| 5 | "You need to review hundreds of M365 / Google Workspace settings. How?" | 1/3 del puesto | Tech 3.1 Q1 |
| 6 | "How do you assess collateral damage before enabling a setting?" | Palabras de Lüders | Tech 3.1 Q2 + E3 |
| 7 | "The device-code phishing in July: what would you change?" | Su incidente real (28/07/2026) | Tech 3.1 Q3 |
| 8 | "How would you harden a Kubernetes/OpenShift cluster?" | Ya preguntado; lo repetirán más a fondo | Tech 3.3 |
| 9 | "How do you deal with the constant stream of CVEs in container images?" | Ya preguntado; fue bien | Tech 3.4 |
| 10 | "What is Zeek? How is it different from Suricata? How does MISP fit?" | Es el SOC de Liviu | Tech 3.6 |
| 11 | "Which Linux commands would you use to…?" / "How would you harden a Linux server?" / kernel modules | Reportado en GRAP + Lüders mencionó módulos del kernel | Tech 3.9 + §4 |
| 12 | "A user reports a compromised account. Walk us through it." | Caso clásico | Tech E1 |
| 13 | "You have operational but limited security experience. Why should we hire you?" | Pregunta lógica para tu perfil | §3 |
| 14 | "Tell us about a time you worked with someone less cooperative / disagreed." | Ejemplo oficial de la formación de entrevistadores del CERN | §5 |
| 15 | "What questions do you have for us?" | Siempre | §7 |

## 3. Respuestas base (inglés)
**Tell us about yourself (≤60 s):**
"I'm a systems and computing engineer from Universidad de los Andes; I also studied chemical engineering. Since April I've been a cloud support engineer at Amadeus, where I investigate production incidents on Linux, Kubernetes and OpenShift, using Splunk and Grafana, and I write my own Python scripts to speed up the first checks. Before that I was at AWS, where I built internal web tools used by more than 200 people, prototyped a multi-agent assistant on Bedrock, and won the LATAM new-hire hackathon by building an authenticated tunnel between two virtual machines. What I enjoy most is investigating how systems fail, and security is where that matters most, which is why this role excites me."

**Why should we hire you with limited security experience?**
"You'd get someone who already investigates real production systems every day: building a timeline from logs, testing hypotheses, deciding when to escalate and explaining it clearly. What I don't have yet is the security-specific depth, and I've shown I learn fast: I earned five AWS certifications, including Solutions Architect Associate. For a graduate role, I think that's the right combination: solid operational habits and the motivation to grow into security."
*(Corregido: son CINCO certificaciones de AWS (Maria, 2026-10-17). Lo de haber leído sobre Puppet/SOC solo si Maria lo confirma.)*

**Why CERN / why security?**
"Security is the part of operations where you're not just fixing a failure, you're dealing with someone actively trying to hide. And at CERN it's a harder and more interesting problem: an open, academic environment with thousands of users and their own devices, where you can't just lock everything down. You have to protect the science without stopping it. I'd learn more here in two years than almost anywhere else."

**AWS (sin quitarte mérito):** usar la versión de `ROUND2_PREP.md`. Nunca "I was nothing… sales".
**VMs:** el hackathon (dos EC2, security groups, túnel autenticado; volviste a leer la especificación y reconstruiste el entorno).

## 4. Preguntas técnicas: versión de 1 minuto
**Puppet / Ansible / Chef**
- Las tres describen en código cómo debe estar una máquina y son *idempotentes*. Puppet y Chef: agente en cada nodo que *pull* y corrige la deriva. Ansible: sin agente, *push* por SSH con YAML.
- Por qué importa en seguridad: baseline igual en todos los nodos, corrige cambios manuales y todo queda en git (quién, cuándo, revisión).
- CERN: ~15.000 nodos con Puppet, hostgroups + Hiera, Foreman, migración a OpenVox, secretos de teigi a Vault/OpenBao (VoxConf, jul 2026).
- "I haven't written a Puppet module yet, but I'd like to start there."

**Trazabilidad en un contenedor (la respuesta que faltó)**
"I would reconstruct the process chain from runtime events, using user IDs, process and parent IDs, executable, arguments and timestamps. I would tag events with host and container identity and send them centrally. API audit logs add Kubernetes requests, not every command inside a shell. I would correlate these with application logs and verify containment while preserving evidence."
- Repreguntas: IDs reutilizados requieren identidad de host/contenedor y tiempo de inicio; sin eventos históricos no se puede reconstruir todo. Las NetworkPolicies son aditivas: añadir deny-egress no garantiza aislamiento. Ver las respuestas container_audit_limits, container_process_identity, container_missing_history y container_isolation_limits.
- Repregunta probable: "Falco vs Zeek?" → Falco ve llamadas al sistema dentro del host; Zeek ve la red. Se complementan.

**Linux**
- Hardening: instalación mínima, parches, SSH con llaves (sin root ni contraseña; 2FA como en LXPLUS), sudo mínimo, firewall, SELinux en enforcing, logs enviados fuera del host y todo en Puppet.
- Comandos: `ss -tupn` (conexiones), `ps auxf` / `top` (procesos), `journalctl` (logs), `last` / `/var/log/secure` (logins), `crontab -l` + `systemctl list-timers` (persistencia), `find / -mtime -1` (ficheros cambiados), `lsmod` / `modinfo` / `modprobe -r` (módulos del kernel).
- Módulos del kernel: un módulo malicioso = rootkit. Liviu habló (30/09/2026) de pasar de lista negra a **lista blanca** de módulos y de eBPF LSM. Pregunta para él: "How is the delayed blocking of kernel module loading going?" (solo si lees sus slides).

**M365 / Google Workspace**
- Método: partir de una baseline (CISA ScubaGear / ScubaGoggles, que solo leen y no cambian nada) + CIS → lista de huecos → para cada uno: qué hace, quién lo usa según los logs, qué rompe y recomendación → report-only → piloto → despliegue por fases con comunicación, excepciones con dueño y fecha de caducidad, y rollback.
- Primeros ajustes a mirar: autenticación heredada, flujos débiles (device code), consentimiento de apps OAuth, compartir fuera (SharePoint/OneDrive/Teams/Drive), reenvío automático de correo, número de administradores globales, registro de auditoría.
- Device code (julio 2026): bloquearlo con Conditional Access (authentication flows), primero revisar quién lo usa legítimamente y probar en report-only; además, reducir la vida del token y limitar los correos salientes.
- No afirmes que el CERN usa Conditional Access, Secure Score o PIM (no está confirmado). Pregúntalo.

**SOC (Liviu)**
- Pipeline: Zeek + Fluent Bit → Kafka → OpenSearch (búsqueda), Spark (analítica), HDFS (largo plazo); OpenStack + Puppet. Kafka desacopla productores y consumidores y absorbe picos.
- Decenas de miles de alertas → unas docenas: quitar falsos positivos, agregar, correlacionar y enriquecer (dueño del activo).
- No descifran el tráfico: aun así se ve quién habla con quién, DNS, nombre del servidor TLS, certificados y patrones de *beaconing*.

**IA y agentes (Luna Durán)**
"What are the risks of AI agents?" → "The main one is prompt injection: an agent reads a web page or an email with hidden instructions and follows them, using the user's permissions. Then data leakage, over-trust in the output, and agents with more permissions than they need. When I built my multi-agent prototype at AWS, the lesson was to give each agent only the tools it needs and to check its output, not trust it blindly. For anything with real impact I'd keep a human in the loop."
*(Solo di lo de "the lesson" si es cierto para ti; si no, quita esa frase.)*

**Rootkits y forense en Linux (Luna Durán)**
"Can you trust a compromised machine to investigate itself?" → "Not fully. A rootkit can hide processes, files and connections from tools like `ps` or `ls` on that same machine. That's why you also look from outside: network logs from the SOC, logs that were already shipped centrally, or analysing the disk from another system. And usually you rebuild instead of cleaning."

**Vulnerabilidades web y escaneo (Kulikowski)**
- OWASP Top 10, en una frase cada una de las principales: inyección (SQL), control de acceso roto, XSS, configuración insegura, componentes vulnerables y desactualizados, SSRF.
- "How would you find exposed or insecure services across CERN?" → "Scan the network and the web servers regularly, fingerprint what's running and its version, store it in a searchable index, and when a new CVE comes out, query the index to find who's affected and notify the owner. I read that you built something like that with Barad-Dûr." *(Solo si lo leíste: slides de CH-CERTs del 07/05/2026.)*

## 5. Comportamiento (modelo de competencias del CERN)
Método de los entrevistadores del CERN: piden un ejemplo y repreguntan "Tell me more about…", "Exactly how did you reach that conclusion?", "What was the outcome?". Habla en 1.ª persona: "I did X because Y, the outcome was Z" (no "we").

| Competencia | Pregunta probable | Tu historia |
|---|---|---|
| Solving problems | "A problem where the root cause wasn't obvious." | Hackathon: el reto que nadie resolvió; volviste a leer la especificación y viste que el entorno estaba mal desde el principio. O el caso de login de Amadeus, a alto nivel (sin nombres). |
| Learning and sharing knowledge | "Something you learned quickly on your own." | 3 certificaciones de AWS; tus scripts; lo que leíste de Puppet. |
| Communicating effectively | "Explaining something technical to a non-technical person." | Apps para 200+ personas de ventas en AWS. |
| Working in teams | "Someone less cooperative / a disagreement." | El desacuerdo del grupo de laboratorio de Ingeniería Química (queso / leche UHT), del perfil. |
| Accountability | "A mistake you made." | La primera tesis: confiaste en una sola fuente; ahora verificas con varias. **Nunca culpes al director.** |
| Achieving results / Managing self | "How you prioritise many incidents at once." | Equipo 24/7 follow-the-sun en Amadeus: impacto y urgencia primero, y escalar con evidencia. |
| Flexibility | "Priorities changed suddenly." | Pendiente: piensa un ejemplo real tuyo. |

**Excepción a la seguridad (cultura CERN):** "A physicist needs 2FA off / a port open for an experiment." → entender la necesidad real, buscar alternativa, y si no la hay, excepción mínima con dueño, caducidad y más monitoreo. "Exceptions kill cyber security" (Lüders), así que es el último recurso.

## 6. Reglas para no meter la pata
- Nunca afirmes que has hecho hardening, usado Puppet o Ansible ni administrado M365. Frase puente: "I haven't done that in production. Here's how I'd approach it…"
- El script: "It only reads, using my own login. Before sharing it with the team, I'd have it reviewed and switch to whatever access the team approves, and document exactly what it does." No digas que tiene un rol de solo lectura.
- IAM en AWS: lo estudiaste para las certificaciones; no digas que lo configuraste en producción.
- Sin nombres de clientes, tickets, herramientas internas ni servicios de Amadeus.
- "I read your article…" solo si lo leíste.

## 7. Preguntas para ellos (elige 2)
1. "For the Microsoft 365 review, do you have a test tenant, or do you rely on report-only mode and pilot groups?"
2. "How does the team evaluate the impact on users before deploying a setting across CERN?"
3. "Which internal networks are next for SOC monitoring once the new firewalls are in place?"
4. "What would a good first three months look like for someone in this role?"
5. Para Liviu, si leíste sus slides: "In your Zeek talk, tens of thousands of raw alerts become a few dozen. How much of that tuning is automated?"

## 8. Estudio antes del lunes (≈3 h, en este orden)
1. Slides de Liviu: Zeek Workshop 2026 (20 min) y "Evolving security threat landscape", 30/09/2026 (20 min). Links en las dos investigaciones.
2. "One click to many" (home.cern, 28/07/2026) + Microsoft "Block authentication flows" (20 min).
3. Puppet: "Puppet language: resources" + slides de VoxConf 2026 "Migrating to OpenVox at CERN" (40 min).
4. Página de CISA SCuBA (15 min).
5. Kubernetes: Pod Security Standards + RBAC good practices (30 min).
6. En voz alta: §3, la trazabilidad (§4) y los escenarios E1, E2 y E3 de la investigación técnica (30 min).
