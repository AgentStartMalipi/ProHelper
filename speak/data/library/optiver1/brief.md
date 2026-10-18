# Call brief: Optiver — Graduate Software Engineer (Amsterdam), etapa 1: entrevista con recruiter

## Participants
- me: Maria Alejandra Lizarazo P. ("Maria"), Junior Cloud Support Engineer at Amadeus (since Apr 2026); former AWS Intern (Jun 2025 - Mar 2026). Bogota, Colombia; Spanish citizen (EU, no visa needed in the Netherlands). Spanish native, English C1, French B1.
- them: un/a recruiter de Optiver Amsterdam. El correo de invitación (12/10/2026) lo mandó Valeria (recruiter); no está confirmado que sea ella quien entreviste.

## Call
- Behavioural interview, 30 min, Zoom (app de escritorio), en inglés.
- Fecha: jueves 22/10/2026, 7:30 Bogotá = 14:30 Ámsterdam (antes del turno de Amadeus de las 10:00).
- Objetivo oficial: "get to know you, learn about your experiences and understand your motivation to join Optiver". Piden entender qué hace Optiver, reflexionar sobre fortalezas y debilidades y llevar preguntas.
- Según candidatos: 20–30 min, "very structured and fast paced", guion fijo; verifican el CV con preguntas de detalle y profundizan en UN proyecto. Sin cálculo mental ni acertijos para SWE. Respuesta: del día siguiente a ~1 semana.
- Proceso completo después: Tech Screening (45 min) → System Design + Live Coding (1 h c/u) → Final (Behavioural + Tech Fundamentals) → Offer Day en Ámsterdam. Bloqueo de 8 meses si fallo una etapa.

## Role (resumen del anuncio oficial: optiver.com/join-us/jobs/technology/amsterdam/graduate-software-engineer)
- Construir sistemas que funcionan en mercados financieros en vivo, donde la velocidad y la fiabilidad afectan los resultados del trading. Trabajo cercano con traders, researchers e ingenieros.
- Responsabilidades: diseñar soluciones simples y bien arquitecturadas; usar herramientas de IA agéntica y construir agentes y flujos propios; mejorar rendimiento y mantenibilidad; crear herramientas reutilizables por otros equipos.
- Formación: Global Academy de Optiver (teoría de trading + stack técnico) y un mentor dedicado.
- Requisitos: grado en CS o afín; graduación entre agosto 2024 y agosto 2027; máximo 3 años de experiencia; C++, Python o Java; algoritmos, concurrencia, sistemas operativos y bases de datos; interés en finanzas.
- Beneficios publicados: bonus por rendimiento, 25 días de vacaciones el primer año (30 desde el segundo), reubicación.
- Encaje fuerte: el anuncio pide IA agéntica (mi prototipo multi-agente en Bedrock y los agentes con Amazon Q CLI), Python, depurar sistemas en producción (Amadeus; ver abajo: depuro, no construyo) y fundamentos (arquitectura, SO y concurrencia en la carrera).

## CV enviado (copia exacta, v5, enviada el 04/10/2026)
Maria Alejandra Lizarazo P.
Software Engineer • B.S. Systems and Computer Engineering, 2025
marializarazopiqueras@gmail.com • +57 317 887 4252 • EU citizen (Spain), no sponsorship needed
linkedin.com/in/malelizarazo • github.com/Malelizarazo • malelizarazo.github.io/Portafolio • Relocating to Amsterdam

Profile
Software engineer (2025) with two engineering degrees and a quantitative background, who builds AI agents and workflows in Python, ships software people rely on, and debugs high-availability production systems on Linux and Kubernetes.

Education
B.S. Systems and Computer Engineering (Computer Science) • B.S. Chemical Engineering, 2025
Universidad de los Andes, Bogotá (top-ranked university in Colombia) • GPA 4.03/5.0 overall; Systems and Computer Engineering courses 4.17/5.0
Coursework: data structures and algorithms, algorithm design and analysis, computer architecture (C and x86 assembly), operating systems and concurrency, computer networks, relational databases, modelling, simulation and optimisation, calculus and differential equations.

Achievements
- Winner, AWS LATAM New Hire Jam Day 2025 (14 technical challenges): the only LATAM team to complete all 14, with one person fewer than other teams. Solved a secure, authenticated VM-to-VM tunnel no other team completed by re-reading the full specification, finding a misconfiguration in the environment and rebuilding it cleanly.
- Five AWS certifications: Solutions Architect Associate, Machine Learning Engineer Associate, Generative AI Developer Professional, Cloud Practitioner and AI Practitioner (Generative AI Developer – Professional in 2026).

Experience
Junior Cloud Support Engineer | Amadeus | Apr 2026 – Present
- Troubleshoot deployed microservices on Linux and Kubernetes/OpenShift in a 24/7 Follow-the-Sun team supporting high-availability travel platforms; the operation handles ~4,600 incidents/week with >90% frontline resolution.
- Diagnose incidents from Grafana and Prometheus metrics and escalate them with clear written evidence; built personal automations that surface the key health signals from multiple dashboards before manual review.

Intern | Amazon Web Services (AWS) | Jun 2025 – Mar 2026
- Developed a multi-agent Generative AI prototype in Python (Amazon Bedrock AgentCore, Strands Agents): an orchestrator coordinating specialized agents with tool calling, memory and retrieval-augmented generation.
- Built and shipped web applications with KPI tracking and team performance dashboards used by 200+ sales professionals across LATAM, turning requirements from stakeholders in several countries into features.
- Built AI agents with Amazon Q Developer CLI (now Kiro CLI) to automate email workflows and content generation.

Freelance Developer | External client – payment automation | Mar 2025 – Apr 2025
- Built a Power Automate / Power Apps workflow that calls a Colombian bank's existing REST API and automates 2,000+ weekly payouts; added dashboards to monitor successful and reversed transactions and stored credentials in Azure Key Vault.

Projects
- Thesis – can a protein's melting temperature be predicted from its sequence? (2024–2025): built a pipeline over 20,000+ Meltome Atlas sequences (UniProt REST API), generated ESM-2 language-model embeddings and trained PyTorch MLP/LSTM regressors; benchmarked them against Random Forest and Azure ML AutoML baselines (best LSTM: R² 0.74, MAE 4.54 °C) and served the model as a Dockerised web app. github.com/Malelizarazo/protein-thermostability-predictor
- Real-time computer vision state tracker (2025–2026): event-driven Python application around a PyTorch EfficientNet-B0 model (99.26% validation accuracy), JSON configuration and automated logging; automated perceptual-hash de-duplication cut 4,000+ raw images to 870 clean samples.
- Industrial data analysis (freelance, 2023): analysed 40+ SCADA process variables from a petroleum refinery in Python, correlating operating conditions with product quality to give the client ML-based recommendations.

Skills
Languages: Python, Java, SQL, TypeScript/JavaScript • Systems: Linux, Kubernetes/OpenShift, Docker, AWS, Grafana, Prometheus, Git, CI/CD
AI and data: PyTorch, Scikit-learn, Pandas, NumPy, LLM agents, tool calling, RAG • Spoken: Spanish (native), English (C1), French (B1)
Interests: puzzles and escape rooms, regular LeetCode problem solving, automating my own workflows, strength training

### Ojo con el CV (pueden preguntar)
- "~4,600 incidents/week with >90% frontline resolution" es de toda la operación, no mío. Decirlo así. Mi volumen personal (Maria, 15/10): varía mucho; días tranquilos ~10 incidentes, y ha llegado a cientos, cuando el equipo se organizó para repartirlos. Ver 'personal_incident_volume'.
- Los ~3.000 dashboards/alertas los gestiona el equipo; yo no los creé.
- Amadeus: investigo y diagnostico incidentes en sistemas en producción, y los arreglo o escalo con evidencia. NO construyo, desarrollo ni despliego sistemas en Amadeus. Nunca decir "I build production systems" ni "I ship software" sobre Amadeus. Decir: "At Amadeus I debug production systems; now I want to build them". Lo que sí construí y entregué: las landing pages y dashboards de AWS, el flujo freelance de pagos y la app de la tesis.
- El script de triage: no está en mis notas cuándo lo hice respecto a cada incidente. Nunca decir "after that incident I built a script".
- Freelance: NO construí la API del banco; construí el flujo que la llama.
- Tesis: 20.000+ secuencias (no 22.000), sin PySpark.
- Intereses: puzzles, escape rooms y LeetCode son "passion" (lo número uno que buscan); tener un ejemplo concreto de cada uno.

## Lecciones de la entrevista del CERN (2026-10-14) — aplicar aquí
- Nunca quitarme mérito ("I was nothing in particular"): contar el trabajo técnico (ver 'aws_internship_technical').
- Antes de decir "no", buscar lo más parecido que hice (VMs -> hackathon 'vm_experience'; Puppet/Ansible -> CDK 'config_management').
- "I haven't done that" una sola vez; después, directo a cómo lo haría.
- Primero la respuesta en una frase, luego el detalle, y cerrar con seguridad.
- Si no entiendo una pregunta: "Just to make sure: do you mean X or Y?", no "can you repeat".
- Casos de Amadeus a alto nivel: sin herramientas internas, fechas ni detalles del ticket.
- Saber qué herramientas usa el equipo antes de la entrevista.
- Hablar despacio: una candidata pasó en 2025 tras reprobar dos años, "speaking slower".

## Preguntas que debo hacer
- "Is the start date for this role flexible, or are there fixed intake dates for the Academy?"
- "How are graduates matched to a team after the Academy, and how much say do they have?"
- "The posting mentions building agents and agentic workflows. How are software engineers using that day to day at Optiver?"
- "What do the graduates who do really well in their first year have in common?"
- "What does the mentorship look like after the Academy ends?"
- No preguntar en esta etapa: salario, vacaciones, horario ni trabajo remoto.
