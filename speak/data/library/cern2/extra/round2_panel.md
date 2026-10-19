# CERN 2.ª ronda: preguntas probables por entrevistador

Lunes 19/10/2026, 8:00–8:30 Bogotá. Panel: Lüders, Vâlsan, Luna Durán, Kulikowski, Cutrina Vilalta.
Dificultad: 🟢 fácil · 🟡 media · 🔴 difícil · 💻 código. Preguntas en inglés; pistas en español. Las respuestas largas están en `ROUND2_QUESTION_BANK.md` y `research/CERN_SECURITY_TECH_RESEARCH.md`.
Lo que se sabe de cada persona viene de sus charlas públicas; **qué preguntará cada uno es una suposición.** En 30 minutos con 5 personas, cada uno hará 1–3 preguntas: no hace falta memorizar las 100, sino reconocer los temas.

**Regla para el código:** piensa en voz alta, di primero el enfoque ("I'd read the file line by line, split on tabs, count per source IP…"), escribe lo simple primero y luego menciona mejoras (casos raros, rendimiento). Si te piden pseudocódigo, vale.

---

## 1. Stefan Lüders (CISO): encaje, motivación y visión del puesto (22)
1. 🟢 "Since we last spoke, what have you done to prepare?" → Puppet, slides de Liviu, "One click to many". Solo lo que hayas hecho de verdad.
2. 🟢 "Introduce yourself to the team in two minutes." → La versión de `ROUND2_QUESTION_BANK.md` §3.
3. 🟢 "Why do you want to move from operations into security?"
4. 🟢 "What do you know about what our team does?" → SOC, campus, data centre, WLCG, sistemas de control; revisiones de seguridad, 2FA, firewalls nuevos.
5. 🟢 "What part of the role excites you most, and what part worries you?" → Emoción: el SOC y el M365 review. Preocupación: Puppet y la escala; plan para aprender.
6. 🟡 "You'll spend the first months reviewing M365 settings one by one. That's not glamorous. How do you stay motivated?" → Es como una investigación; documentar bien sirve para siempre; cada ajuste reduce riesgo real (julio 2026).
7. 🟡 "How do you explain to a physicist why we're taking away something they use?" → Por qué, riesgo concreto, alternativa, plazo, a quién acudir.
8. 🟡 "Exceptions kill cyber security. When would you still grant one?"
9. 🟡 "What's the difference between security in a bank and at CERN?" → Libertad académica, BYOD, miles de institutos; defensa en profundidad.
10. 🟡 "Tell me about a time you pushed back on a request."
11. 🟡 "How do you prioritise when everything is 'urgent'?" → Impacto x probabilidad x exposición; internet-facing primero.
12. 🟡 "Where do you see yourself at the end of the 2+1 years?"
13. 🟡 "You'll be on stand-by sometimes, nights and weekends. Is that OK?" → Sí; ya trabajas en un equipo 24/7.
14. 🟡 "What would you do in your first week if nobody gave you a task?"
15. 🟡 "How do you learn a completely new technology fast? Give an example." → Certificaciones de AWS; hackathon.
16. 🔴 "If you found that one of our own team's services was misconfigured, how would you raise it?" → En privado, con evidencia y propuesta; sin culpar.
17. 🔴 "What is the biggest security risk to CERN right now, in your opinion?" → Robo de identidad/credenciales + phishing con IA (julio 2026); proveedores y cadena de suministro.
18. 🔴 "If you had to cut the attack surface of CERN by 20% in one year, where would you start?" → Inventario de servicios expuestos a internet, cerrar lo que nadie usa, todo detrás del SSO con 2FA.
19. 🔴 "How would you measure if the security team is doing a good job?" → Tiempo hasta detectar y contener, % de servicios cumpliendo los Security Principles, cobertura de 2FA, parches críticos dentro de plazo.
20. 🔴 "Security vs usability: tell me about a decision where you had to balance them."
21. 🟡 "Do you have other interviews or offers? When could you start?" → Sí, otros procesos; fecha honesta según tu preaviso real en Amadeus.
22. 🟢 "Any questions for us?" → Elige 2 de `ROUND2_QUESTION_BANK.md` §7.

---

## 2. Liviu Vâlsan (SOC): monitorización, Linux, kernel, trazabilidad (24)
1. 🟢 "What's a SOC, and what does a SOC analyst do all day?"
2. 🟢 "What is Zeek?" → Monitor de red que convierte el tráfico en logs estructurados (conn, dns, http, ssl) + framework de intel.
3. 🟢 "Zeek vs Suricata/Snort?" → Logs ricos para investigar vs firmas que disparan alertas.
4. 🟢 "What's an IoC? Give three examples." → IP, dominio, hash de fichero (también URL, user agent).
5. 🟡 "What is MISP and how do its IoCs reach Zeek?"
6. 🟡 "Why put Kafka between sensors and storage?" → Desacopla, absorbe picos, varios consumidores.
7. 🟡 "We see ~3.5 billion connections a day and tens of thousands of raw alerts. How do you get to a few dozen?" → Falsos positivos, agregar, correlacionar, enriquecer; revisar cada regla de ajuste.
8. 🟡 "Traffic is encrypted and we don't decrypt it. What can you still detect?" → Metadatos, DNS, SNI, certificados, JA3/JA4, beaconing.
9. 🟡 "A pod looks compromised. How do you trace what happened inside the container?" → Eventos runtime con usuario, proceso/padre, ejecutable, argumentos y hora; identidad host/contenedor; reconstruir árbol y centralizar. Correlacionar con app y auditoría API, que no registra todos los comandos internos. Verificar contención y preservar evidencia.
10. 🟡 "Which fields would you log for every command executed on a host, and why?" → uid, euid, pid, ppid, binario, argumentos, tty, hora, host. Así reconstruyes quién lanzó qué y desde qué proceso padre.
11. 🟡 "How do you see which kernel modules are loaded, and why does security care?" → `lsmod`, `modinfo`; un módulo malicioso = rootkit.
12. 🔴 "Blocklist vs allowlist of kernel modules: pros and cons?" → Allowlist es más segura pero puede romper hardware o drivers raros; por eso se hace con un "delayed blocking" y con métricas primero.
13. 🔴 "What is eBPF and why is it useful for security?" → Programas pequeños y verificados dentro del kernel sin módulos; observar syscalls, red, ejecuciones con poco coste; base de Falco, Tetragon y eBPF LSM.
14. 🔴 "A new Linux local privilege escalation CVE comes out. Walk me through the response." → Identify → determine exposure → mitigate (p. ej. bloquear el módulo vulnerable o sysctl) → remediate (parche/kernel nuevo + reboot) → verify.
15. 🟡 "What's the difference between uid and euid?" → uid = quién eres; euid = con qué permisos actúa el proceso (p. ej. un binario setuid corre con euid 0).
16. 🟡 "Which Linux commands would you use to check a suspicious host?" → `ss -tupn`, `ps auxf`, `last`, `journalctl`, `crontab -l`, `systemctl list-timers`, `find -mtime`, `ls -la ~/.ssh`.
17. 🟡 "What's a reverse shell and how would you spot one in Zeek logs?" → Conexión saliente larga a un puerto raro, iniciada desde un servidor; poco volumen, sesión interactiva.
18. 🔴 "What is beaconing and how would you detect it?" → Conexiones periódicas a un mismo destino; mirar la regularidad de los intervalos (desviación baja).
19. 🟡 "How would you detect password spraying against the SSO?" → Muchos usuarios, pocos intentos cada uno, mismas IPs; contrastar con logins exitosos.
20. 💻🟡 **Contar conexiones por IP en un conn.log de Zeek.** "Given a Zeek conn.log (tab-separated, header lines start with '#'), print the top 10 source IPs by number of connections."
```python
from collections import Counter

def top_sources(path, n=10):
    counts = Counter()
    fields = None
    with open(path) as f:
        for line in f:
            if line.startswith("#fields"):
                fields = line.rstrip("\n").split("\t")[1:]
                continue
            if line.startswith("#"):
                continue
            row = dict(zip(fields, line.rstrip("\n").split("\t")))
            counts[row["id.orig_h"]] += 1
    return counts.most_common(n)
```
   Repregunta: "The file is 1.2 TB." → No cabe en memoria el fichero, pero el contador sí (o usar Spark/OpenSearch, como hace el SOC); leer en streaming.
21. 💻🟡 **Cruzar con IoCs.** "You have a set of malicious IPs from MISP. Return every connection whose destination is in that set."
```python
def intel_hits(rows, bad_ips):
    bad = set(bad_ips)                      # búsqueda O(1)
    return [r for r in rows if r["id.resp_h"] in bad]
```
   Repregunta: "And domains?" → Hacer lo mismo con dns.log (`query`), y normalizar a minúsculas y sin punto final.
22. 💻🔴 **Detectar beaconing.** "Given timestamps of connections from one host to one destination, decide if it looks like beaconing."
```python
from statistics import mean, pstdev

def looks_like_beacon(timestamps, min_events=10, max_cv=0.1):
    if len(timestamps) < min_events:
        return False
    ts = sorted(timestamps)
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    avg = mean(gaps)
    return avg > 0 and pstdev(gaps) / avg < max_cv   # intervalos muy regulares
```
   Repregunta: "Malware adds jitter." → Subir el umbral, usar la mediana, o mirar también el tamaño de los paquetes.
23. 💻🟡 **Allowlist de módulos del kernel.** "Write a script that compares loaded kernel modules to an allowlist and reports the rest."
```python
def unexpected_modules(allowlist_path="allowlist.txt"):
    with open(allowlist_path) as f:
        allowed = {l.strip() for l in f if l.strip() and not l.startswith("#")}
    with open("/proc/modules") as f:          # lo mismo que lsmod
        loaded = {line.split()[0] for line in f}
    return sorted(loaded - allowed)
```
   Repregunta: "How do you roll this out to 15,000 nodes?" → Primero solo reportar (como report-only), recoger datos por hostgroup, construir la allowlist con Puppet y luego bloquear.
24. 💻🔴 **Árbol de procesos.** "Given events with pid, ppid and command, print the chain of parents for a suspicious pid." → Diccionario pid→evento; subir por ppid hasta que no exista o sea 1; cuidado con bucles (conjunto de visitados).

---

## 3. José Carlos Luna Durán (análisis, IA, forense, WLCG) (21)
1. 🟢 "What is the WLCG and why is its security hard?" → Red mundial de computación del LHC con unos 170 centros de cálculo en más de 40 países; cada sitio tiene sus administradores; un sitio comprometido afecta a todos.
2. 🟢 "What security risks do you see in people using AI tools at CERN?" → Fuga de datos, prompt injection, agentes con demasiados permisos, código generado inseguro, paquetes inventados, phishing con IA.
3. 🟡 "Explain prompt injection to a physicist."
4. 🟡 "You built a multi-agent prototype. How would you secure it if it went to production?" → Mínimas herramientas por agente, sin secretos en el prompt, validar entradas y salidas, logs de cada llamada, humano para acciones con impacto. Recuerda: fue un **prototipo**.
5. 🟡 "Should CERN allow AI coding assistants? Under which conditions?" → Herramientas aprobadas, no pegar datos confidenciales, revisar el código como si fuera de un desconocido, escanear dependencias.
6. 🔴 "An AI agent has access to a user's mailbox. What could go wrong?" → Un correo con instrucciones ocultas hace que el agente reenvíe datos o mande phishing interno (como julio 2026 pero automático).
7. 🟡 "LLM crawlers are hammering our websites. What can we do?" → Rate limiting, caché, robots.txt (no basta), detección por comportamiento, desafíos tipo proof-of-work, bloquear rangos conocidos; cuidado con no bloquear a usuarios reales.
8. 🟡 "What is a rootkit? User-mode vs kernel-mode?"
9. 🔴 "Can you trust a compromised machine to investigate itself?" → No del todo; mirar desde fuera (red, logs ya enviados, disco desde otro sistema); reconstruir.
10. 🟡 "What do you collect first in a forensic investigation, and in which order?" → De lo más volátil a lo menos: memoria, conexiones y procesos, luego disco y logs.
11. 🟡 "How do you preserve evidence?" → Copias, hashes, no trabajar sobre el original, cadena de custodia, notas con hora.
12. 🟡 "What would you look for in auth logs after a stolen SSH key?" → Logins desde IPs nuevas, horas raras, saltos a otros hosts (movimiento lateral), uso de la misma llave en varias máquinas.
13. 🔴 "A Tier-2 site in the WLCG is mining cryptocurrency on its worker nodes. Your steps?" → Avisar al sitio y coordinar (no es tu infraestructura), compartir IoCs vía MISP, buscar esos IoCs en el CERN, revisar credenciales compartidas.
14. 🟡 "What is responsible vulnerability disclosure?" → Avisar en privado al responsable, dar tiempo para parchear, publicar después; nunca explotar más de lo necesario para demostrarlo.
15. 🟢 "What is a CVE and a CVSS score?"
16. 🟡 "Why isn't CVSS enough to prioritise?" → No incluye tu exposición ni si se explota activamente (KEV, EPSS).
17. 🔴 "Time-to-exploit is now negative with AI. What does that change for us?" → Los exploits salen antes que el parche: más mitigaciones rápidas (bloquear, aislar), inventario al día, menos superficie expuesta.
18. 🟡 "Tell me about a time you were wrong about a root cause."
19. 💻🟡 **Detectar secretos en un repo (como el secret detection de GitLab).** "Scan files for things that look like AWS keys or private keys."
```python
import re, pathlib

PATTERNS = {
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private_key": re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}

def scan(repo):
    for path in pathlib.Path(repo).rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for name, rx in PATTERNS.items():
                if rx.search(line):
                    print(f"{path}:{i}: {name}")
```
   Repregunta: "Lots of false positives?" → Lista de excepciones, entropía, ignorar tests; y lo importante: **rotar** el secreto, no solo borrarlo (sigue en el historial de git).
20. 💻🟡 **Logs de SSH.** "From /var/log/secure, count failed logins per source IP and flag IPs with more than 20."
```python
import re
from collections import Counter

FAILED = re.compile(r"Failed password for (invalid user )?\S+ from (\d+\.\d+\.\d+\.\d+)")

def brute_force(path, threshold=20):
    c = Counter()
    with open(path) as f:
        for line in f:
            m = FAILED.search(line)
            if m:
                c[m.group(2)] += 1
    return {ip: n for ip, n in c.items() if n > threshold}
```
21. 💻🔴 **Crawler o humano.** "Given web access logs, find clients that make more than 100 requests per minute." → Agrupar por (IP, minuto) con un Counter; repregunta: ventana deslizante con `deque` en lugar de minutos fijos.

---

## 4. Dawid Kulikowski (desarrollo, web, escaneo, vulnerabilidades) (22)
1. 🟢 "What's your strongest programming language? Show me how you'd structure a small tool." → Python; funciones pequeñas, argparse, logging, tests.
2. 🟢 "HTTP vs HTTPS?" → TLS: cifrado, integridad, autenticación del servidor con certificado.
3. 🟢 "What happens when you type a URL in the browser?" → DNS, TCP, TLS, petición HTTP, respuesta, render.
4. 🟢 "Name some of the OWASP Top 10." → Inyección, control de acceso roto, XSS, configuración insegura, componentes vulnerables, SSRF, fallos de autenticación.
5. 🟡 "Explain SQL injection and how to prevent it." → Consultas parametrizadas; ORM (Django); mínimo privilegio en la BD.
6. 🟡 "Explain XSS. Stored vs reflected?" → Escapar la salida (Django lo hace por defecto), CSP.
7. 🟡 "What is SSRF and why is it dangerous in a cloud?" → El servidor hace peticiones por ti; puede llegar al servicio de metadatos y robar credenciales.
8. 🟡 "What is CSRF and how does Django protect against it?" → Token CSRF en formularios + cookies SameSite.
9. 🟡 "How would you find all web servers on CERN's network and what they run?" → Escaneo de puertos, banner/headers, versión, guardar en un índice buscable (como Barad-Dûr).
10. 🔴 "A new CVE in a web framework is published. How do you find every affected server in an hour?" → Consultar el índice de servicios por producto y versión, priorizar los expuestos a internet, avisar a dueños, mitigar con WAF.
11. 🟡 "Why OpenSearch for this and not just PostgreSQL?" → Búsqueda de texto completo y agregaciones rápidas sobre muchos documentos; Postgres para datos relacionales y estado.
12. 🟡 "What's Redis typically used for in such a tool?" → Caché y colas de tareas (p. ej. Celery).
13. 🟡 "What is an insecure IoT device and why does CERN care?" → Cámaras, impresoras con credenciales por defecto o firmware viejo; puerta de entrada.
14. 🔴 "How do you scan responsibly without breaking fragile devices?" → Limitar la velocidad, excluir sistemas de control, ventanas acordadas, avisar a los dueños.
15. 🟡 "How do you store passwords in a web app?" → Hash lento con sal (bcrypt, argon2); nunca cifrado reversible.
16. 🟡 "What would you check in a code review for security?" → Entradas sin validar, consultas construidas con strings, secretos, permisos, dependencias, logs con datos sensibles.
17. 💻🟢 **Arreglar una SQL injection.** "What's wrong with this and how do you fix it?"
```python
# Vulnerable
cursor.execute(f"SELECT * FROM users WHERE login = '{login}'")
# Arreglado: consulta parametrizada
cursor.execute("SELECT * FROM users WHERE login = %s", (login,))
# En Django: User.objects.filter(login=login)
```
18. 💻🟡 **Versión vulnerable.** "Given a list of services (host, product, version) and a vulnerable range, return the affected hosts."
   Primero confirmar ecosistema y límites del rango. Usar su comparador, conservando la versión completa. Filtrar producto y evaluar cada rango afectado del aviso; devolver hosts afectados y una lista separada de versiones desconocidas o inválidas. No hay un parser universal basado en tuplas numéricas.
   Repregunta: "Versions like '2.4.58-ubuntu1'?" → NO quitar el sufijo. Conservar epoch/revisión cuando existan; comparar con reglas Debian y el aviso correspondiente al paquete y release de Ubuntu. Un backport puede corregir el problema sin cambiar la versión upstream. `packaging.version` es para PEP 440, no para versiones Debian arbitrarias.
   Casos límite: prereleases, metadatos de build en SemVer, extremos incluidos/excluidos, ramas afectadas disjuntas, versión inválida. Un banner de red no confirma el nivel de parche. Ver code_vulnerable_versions y las repreguntas version_*.
19. 💻🟡 **Chequear cabeceras de seguridad.** "Write a function that checks a website for missing security headers."
```python
import requests

REQUIRED = ["Strict-Transport-Security", "Content-Security-Policy",
            "X-Content-Type-Options", "X-Frame-Options"]

def missing_headers(url):
    r = requests.get(url, timeout=5)
    return [h for h in REQUIRED if h not in r.headers]   # requests ignora mayúsculas
```
   Repregunta: "For 10,000 sites?" → Concurrencia (ThreadPoolExecutor o asyncio), timeouts, reintentos, guardar resultados.
20. 💻🟡 **Credenciales por defecto.** "How would you check if a device still uses a default password, safely?" → Lista pequeña de credenciales por defecto por fabricante, un solo intento por credencial, con permiso y sin bloquear cuentas; registrar todo.
21. 💻🔴 **Escáner de puertos simple.** "Write a minimal TCP port check."
```python
import socket

def open_ports(host, ports, timeout=0.5):
    found = []
    for p in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            if s.connect_ex((host, p)) == 0:
                found.append(p)
    return found
```
   Repregunta: "Why use nmap/masscan instead?" → nmap: detección de servicios y versiones (-sV) y scripts; masscan: descubrimiento de puertos muy rápido a gran escala, sin detectar versiones. Escanear solo con autorización.
22. 🟡 "Tell me about a bug you found in your own code and how you found it."

---

## 5. Pau Cutrina Vilalta (rol desconocido: mezcla de infraestructura y cloud) (21)
1. 🟢 "What's the difference between a VM and a container?" → El contenedor comparte el kernel del host; la VM tiene el suyo. Aislamiento más fuerte en la VM.
2. 🟢 "Kubernetes vs OpenShift?" → OpenShift = Kubernetes con valores por defecto más estrictos (SCC restricted, UID aleatorio no-root), rutas, registro integrado.
3. 🟡 "How would you harden a Kubernetes cluster?" → RBAC, Pod Security restricted, NetworkPolicies default-deny, imágenes escaneadas de Harbor, secretos fuera, audit logs, Falco.
4. 🟡 "Why are Kubernetes Secrets not really secret?" → Base64 en etcd; cifrar etcd, RBAC, Vault.
5. 🟡 "What is a NetworkPolicy? Write one that denies all egress from a namespace." → `podSelector: {}`, `policyTypes: [Egress]`, sin reglas `egress`.
6. 🟡 "Someone ran `kubectl exec` into a production pod at 3 am. What do you do?"
7. 🟡 "Security groups in OpenStack/AWS: what are they?" → Firewall por VM, con estado; separar front-end y back-end.
8. 🟢 "What's least privilege? Give an example from your work." → IAM (lo estudiaste para las certificaciones de AWS); el script que solo lee.
9. 🟡 "CERN is starting to use AWS, GCP, Azure and Oracle. What would you secure first in a new cloud account?" → Root/admin con MFA y sin claves, SSO, logs de auditoría (CloudTrail), alertas de gasto, buckets privados por defecto, mínimo privilegio.
10. 🟡 "How do you prevent a public S3 bucket or storage bucket?" → Block Public Access a nivel de cuenta, políticas de la organización, escaneo de configuración.
11. 🟡 "Infrastructure as code: why is it good for security?" → Revisable, repetible, auditable en git; escaneable antes de desplegar.
12. 🟡 "What is a WAF and what are its limits?"
13. 🟡 "What is TLS doing, step by step, in simple terms?"
14. 🟡 "How does SSH key authentication work?" → El servidor tiene la clave pública; el cliente demuestra que tiene la privada firmando un desafío.
15. 🔴 "Why would we want 2FA on SSH, and what breaks if we enforce it?" → Robo de llaves; rompe automatizaciones y cuentas de servicio → usar cuentas de servicio sin login interactivo o certificados SSH.
16. 🔴 "Design: how would you add MFA to an old internal portal that doesn't support it?" → Ponerlo detrás de un proxy con el SSO; mientras tanto, más monitoreo.
17. 🟡 "How do you rotate a secret used by 50 services without downtime?" → Soportar dos secretos a la vez, actualizar consumidores, retirar el viejo.
18. 💻🟡 **Revisar manifests de Kubernetes.** "Given a pod spec as a dict, flag privileged containers, root users and hostPath volumes."
```python
def risky(pod):
    issues = []
    spec = pod.get("spec", {})
    for c in spec.get("containers", []):
        sc = c.get("securityContext", {})
        if sc.get("privileged"):
            issues.append(f"{c['name']}: privileged")
        if sc.get("runAsUser") == 0 or not sc.get("runAsNonRoot", False):
            issues.append(f"{c['name']}: may run as root")
        if sc.get("allowPrivilegeEscalation", True):
            issues.append(f"{c['name']}: privilege escalation allowed")
    for v in spec.get("volumes", []):
        if "hostPath" in v:
            issues.append(f"volume {v['name']}: hostPath")
    return issues
```
   Repregunta: "How would you enforce this instead of just reporting?" → Pod Security Admission "restricted", OPA Gatekeeper o Kyverno.
19. 💻🟡 **Imagen con CVEs.** "Given a scanner's JSON output (list of {package, severity}), fail the CI build if there's any CRITICAL."
```python
import json, sys

def gate(report_path, blocking=("CRITICAL",)):
    with open(report_path) as f:
        vulns = json.load(f)
    bad = [v for v in vulns if v["severity"] in blocking]
    for v in bad:
        print(f"{v['severity']}: {v['package']}")
    sys.exit(1 if bad else 0)
```
20. 💻🟡 **Bash rápido.** "One-liner: the 5 IPs with most failed SSH logins."
```bash
grep "Failed password" /var/log/secure | grep -oE "from [0-9.]+" | awk '{print $2}' | sort | uniq -c | sort -rn | head -5
```
   Si no lo sacas de memoria, di el plan: filtrar → extraer IP → contar → ordenar. Es lo que valoran.
21. 💻🔴 **Comparar con la baseline (estilo M365 review).** "You have the current settings and a baseline as dicts. Report what differs."
```python
def drift(current, baseline):
    return {k: (current.get(k), want) for k, want in baseline.items()
            if current.get(k) != want}
```
   Repregunta: "How would you decide which drift to fix first?" → Por riesgo y por cuántos usuarios afecta; report-only antes de cambiar.

---

## 6. Si te ponen código en vivo: cómo comportarte
- Repite el problema con tus palabras y pregunta 1 cosa ("Can I assume the file fits in memory?").
- Di el enfoque antes de escribir. Escribe la versión simple que funciona.
- Prueba con un ejemplo pequeño en voz alta.
- Termina con mejoras: casos raros, rendimiento, seguridad (timeouts, entradas no confiables).
- Si te bloqueas: "Let me write it in pseudocode first." Es mejor que el silencio.
