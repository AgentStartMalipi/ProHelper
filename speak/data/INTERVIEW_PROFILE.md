# Interview profile: Maria Alejandra Lizarazo P.

> Context file for the SPEAK interview simulator. Last updated 2026-10-05.
> Sources: JOBSEARCH/candidate_profile.json (source of truth), JOBSEARCH/interview_prep/Docplanner_2026-10-08.md, JOBSEARCH/INTERVIEW_PROFILE.md, JOBSEARCH/APPLICATIONS.md.
> **Rules for the interviewer and evaluator:**
> - Only use the facts in this file. Never invent experience, numbers, tools, dates or job titles.
> - If a question needs something that isn't here, help Maria answer honestly: "I haven't used X yet; the closest thing I've done is Y."
> - Interviews are in English. Maria's Spanish is native and her English is C1.
> - Flag any answer that breaks a rule in "Red flags" below.

---

## Active Applications

| Company | Role | Likely focus in interviews |
|---|---|---|
| Docplanner | Junior Software Engineer – Early Career | FIRST CALL Thu 2026-10-08, 10:15 Bogotá / 17:15 Spain, 45 min video, English, with Krystyna Walewko (Talent Acquisition). Career journey and motivation, "Why Docplanner", brief intro focused on recent achievements, STAR examples (overcoming a challenge, taking initiative, making an impact, collaborating, sharing thoughts openly or giving feedback), relocation to Spain (role is 100% remote within Spain), salary (Maria stated EUR 40–48k in her application), notice period 2 weeks, why leaving Amadeus after ~6 months, stack fit (Node.js/TypeScript, React, AWS, Kubernetes, AI-assisted development), candidate asks 2–3 questions. Recruiter-style questions, not coding problems |
| Amazon (Data Engineer, Ring Agent Platforms, Madrid; SDE ML Early Career, Luxembourg; other SDE/DE roles) | SDE / Data Engineer | Online Assessment (coding, DS&A); Leadership Principles with STAR stories; for Ring: multi-agent experience. The Ring CV said "PySpark": correct it plainly if asked |
| Google | SWE II (L3), GTI Threat Intelligence, Málaga | Coding (arrays, strings, graphs, trees), "Googleyness", code review and debugging |
| Anthropic | Associate Applied AI, London (UK visa) | Building with Claude's API, agents, prompting, evaluation, customer discovery; why Anthropic |
| Uncountable | SWE, Implementations | Python data parsing, APIs, scientific data, customer integrations; chemistry background |
| Citrine Informatics | Materials Informatics Consultant (Germany, remote) | Materials and chemistry + ML, customer success, training users, travel |
| EUMETSAT | Temporary Data Services Engineer, Darmstadt | Kubernetes, Linux, IAM and API gateways, S3, CI/CD, IaC, SRE practices |
| Sierra | Agent Strategist (Spanish), Madrid | Customer problem framing, agent design and evaluation, executive communication |
| Binance | Junior SWE (AI & LLM), remote | Full-stack + LLM apps (RAG, agents, tool calling), AI coding tools |
| Others submitted earlier | Affirm, Optiver, Palantir FDSE Madrid, QuantCo, Mendix, UBS, Alpic, Van Lanschot Kempen, Devoteam, Axon, SUE, Celonis, Oracle, CERN, Stripe | — |

---

## Words to avoid and red flags

Avoid these words: passionate, results-driven, highly motivated, hardworking, fast learner, SDE Intern, PySpark, you posted

### Red flags (never say)
- **Salary:** never "you posted the salary" or "your published range". Docplanner did NOT publish a band: EUR 40–48k is what Maria asked for in her application. Say "As I mentioned in my application…".
- **AWS dates:** the internship was **Jun 2025 – Mar 2026** (10 months). Never 2024–2025.
- **Freelance:** she built a **Power Automate / Power Apps flow that consumes a Colombian bank's existing REST API** for a client company. She did NOT build or code an API, and she did NOT work for a bank.
- **Hackathon:** she **redeployed once, cleanly**, after finding the misconfiguration. Never "three times".
- **Thesis:** **PyTorch** (MLP/LSTM) on **ESM-2** embeddings, pandas for data. **No PySpark.** 20,000+ sequences (never 22,000). Best LSTM: **R² 0.74, MAE 4.54 °C**.
- **AWS campaign apps:** internal tools for AWS's own LATAM sales teams. Say "internal web applications that went live and were used by 200+ sales professionals during each four-week campaign". Don't say just "in production": it sounds like a customer-facing or global product.
- **Node.js:** only in coursework (NestJS on Node). Never claim Node.js in production. No React Native.
- **AWS title:** "Intern". Never "SDE Intern" or "Software Engineer Intern".
- **Team numbers:** ~4,600 incidents/week, >90% frontline resolution and ~3,000 dashboards/alerts belong to the Amadeus operation, not to Maria.
- **Amadeus:** no root cause analysis, no network engineering, no software development claimed there. Don't complain about Amadeus (no unpaid weekends, no schedule complaints).
- **GenAI work at AWS:** a **prototype**, not production.
- **Relocation:** never sound unsure; never give a long timeline.
- **Python script at Amadeus:** don't name a library, don't give time-saved numbers, don't say the team adopted it.

---

## 1. Snapshot

| | |
|---|---|
| Name | Maria Alejandra Lizarazo P. (written "Maria", no accent) |
| Based in | Bogotá, Colombia (UTC-5), relocating to Spain (leaning Valencia, flexible) |
| Citizenship | Spain (EU) and Colombia. No visa or sponsorship needed in Spain/EU |
| Education | Two bachelor's degrees, Universidad de los Andes, 2025 (graduated 2025-10-20): **Systems and Computer Engineering** (Computer Science) and **Chemical Engineering** |
| Current job | Junior Cloud Support Engineer, Amadeus (since April 2026) |
| Before | AWS Intern (Jun 2025 – Mar 2026, 10 months); freelance work; Python TA |
| Languages | Spanish (native), English (C1), French (B1) |
| Certifications | **3 AWS certifications:** Generative AI Developer – Professional (2026), Machine Learning Engineer – Associate (2026), Solutions Architect – Associate (2025). Also foundational: AI Practitioner (2026), Cloud Practitioner (2025) |
| Start date / notice | Available 1 November 2026; notice period 2 weeks |
| Salary stated to Docplanner | EUR 40–48k gross/year (her own expectation, stated in the application) |
| Links | github.com/Malelizarazo · malelizarazo.github.io/Portafolio |

---

## 2. Experience

### Amadeus: Junior Cloud Support Engineer (Apr 2026 – present, full-time)
- Supports high-availability production travel platforms in a **24/7 Follow-the-Sun team**.
- Troubleshoots deployed microservices on **Linux and Kubernetes/OpenShift** (for example recycling pods).
- Health and performance checks with **Grafana and Prometheus** dashboards and alerts.
- Reads network diagnostics (DNS, load balancers, firewalls) **to triage only**.
- **Escalates to engineering teams with clear written evidence**; documents procedures in **runbooks**.
- **Personal Python script:** uses her own authenticated access, **read-only**, to query the same data the monitoring pages show; produces a summary with links to the key graphs and a short explanation before her manual review. Makes analysis faster, including harder problems. Not shared with the team yet.
- Team-level numbers (the team's, not hers): ~4,600 incidents/week, >90% frontline resolution, ~3,000 dashboards and alerts as code.

### Amazon Web Services (AWS): Intern (Jun 2025 – Mar 2026, 10 months)
- Official title "Intern", inside the AWS LATAM sales organization.
- **Internal campaign web applications (live, internal users):** HTML, CSS, JavaScript; KPI tracking, prize management and team performance dashboards, **used by 200+ sales professionals across LATAM**. Gathered requirements from stakeholders in several countries including Brazil. Hardest part: finding, understanding and complying with Amazon's internal rules, using only approved services. Found a supported way to include her own HTML and CSS by reading internal documentation.
- **Multi-agent Generative AI prototype (her own practice project for the internal AWSome Builder program, built alone, not built with Amazon Q):** Python with the AWS CDK, Amazon Bedrock AgentCore, Strands Agents; an orchestrator coordinating specialized agents with tool calling, memory and RAG over a Bedrock Knowledge Base. Prototype, internal code.
  - Multi-agent prototype = Maria's own practice project, built alone, for AWS's internal AWSome Builder program (Solutions Architect path: three internal certifications, each based on a project; you choose a customer scenario, build it and present it as to a customer, practising: explaining technical ideas simply, exploring AWS services and handling customer questions, and presenting the final cost without scaring the customer). Not a team project, not for a client, NOT about email automation (that was the separate Amazon Q Developer CLI tool). Told by Maria 2026-10-07. Scenario she chose: a gym that wanted an AI personal trainer; agents = orchestrator + nutrition agent + training agent (told by Maria 2026-10-07). Confirmed: she passed 2 of the 3 AWSome Builder certifications before joining Amadeus; never say she completed all three.
- **Personal tool with Amazon Q Developer CLI (now Kiro CLI), her own initiative:** generates creative HTML emails formatted to display correctly in Outlook, to make her own work more efficient. Not an AWS team project. Not production. (Corrected by Maria 2026-10-07.)
- Shadowed Solutions Architects in customer engagements; presented existing demos (also at AWS Summit Bogotá). Did not build those demos.
- Self-directed labs: RAG, AWS Glue, AWS CDK, Terraform, serverless.
- **Won the AWS LATAM New Hire Jam Day 2025** (story 4.1).

### Freelance Developer: payment automation for a client company (Mar – Apr 2025)
- Built a **Power Automate / Power Apps workflow that consumes a Colombian bank's existing REST API** and automates **2,000+ weekly payouts** for a client company. Credentials in **Azure Key Vault**; dashboards to monitor successful and reversed transactions.
- She did not build the API. The client was a company, not the bank.

### Freelance Data Analyst: petroleum refining client (Jan – Jun 2023)
- Analysed SCADA process data (40+ operational variables) in Python and delivered ML-based recommendations.

### Teaching Assistant: Programming in Python, Universidad de los Andes (2022 – 2023)
- Reviewed and debugged student code, explained concepts in labs, mentored project groups.

---

## 3. Projects
- **Thesis: protein thermal stability prediction (2024–2025)** — github.com/Malelizarazo/protein-thermostability-predictor. Fetched **20,000+ Meltome Atlas sequences** from the UniProt REST API, generated **ESM-2** protein-language-model embeddings and trained **PyTorch MLP and LSTM** regressors. Best: **LSTM, R² = 0.74, MAE = 4.54 °C**. Baselines: Random Forest, KNN, SVR, Bayesian Ridge, Azure ML AutoML. Deployed as a web app with Docker on a GPU VM. pandas + PyTorch, no PySpark.
- **Real-time computer vision state tracker (2025–2026):** Python, event-driven architecture, JSON config, logging; PyTorch EfficientNet-B0 (99.26% validation accuracy) with OpenCV; de-duplication cut 4,000+ images to 870 clean samples.
- **Full-stack web coursework (2025):** React/JavaScript front ends, TypeScript/NestJS (Node.js) back ends, TypeORM/SQLite, Jest tests.
- **Portfolio website (2026):** Next.js, React, TypeScript, Tailwind CSS, Three.js; GitHub Actions to GitHub Pages.

---

## 4. STAR stories

### 4.1 Challenge: hackathon (best story)
- **Situation:** AWS LATAM New Hire Jam Day 2025, 14 technical challenges. Her team was two interns, one person fewer than the other teams.
- **Task:** she took one of the hardest: connecting two virtual machines through a secure, authenticated tunnel.
- **Action:** the deployment kept failing. Instead of skipping it, she re-read the whole specification and found a key requirement at the very bottom that showed her environment had been misconfigured from the start. She **redeployed once, cleanly**, validating each step. It worked after about three hours.
- **Result:** no other team completed that challenge; hers was the only LATAM team to finish all 14, and they won.
- **Learning:** read the spec fully, question your own setup, rebuild cleanly instead of guessing.

### 4.2 Initiative: Python script at Amadeus
- **Situation:** health checks and incident analysis across several monitoring dashboards.
- **Task:** nobody asked her to change it, but she knew it could be done better.
- **Action:** wrote a small Python script that uses her own authenticated access, read-only, to query the same data the monitoring pages show; it pulls key graphs and incidents into a summary with links and a short explanation.
- **Result:** her analysis starts from the most relevant information, so she finds problems faster, including harder ones. Still a personal tool; next step is to polish it and propose it to the team.

### 4.3 Impact: AWS campaign apps
- **Situation:** LATAM sales teams needed to follow campaign KPIs, prizes and team performance.
- **Task:** she was responsible for building the web applications.
- **Action:** found and understood Amazon's internal rules, worked only with approved services, gathered feedback from stakeholders in several countries including Brazil, and found a supported way to include her own HTML and CSS.
- **Result:** the internal apps went live and were used by 200+ sales professionals across LATAM during each four-week campaign.

### 4.4 Collaboration: Follow-the-Sun at Amadeus
- **Situation:** 24/7 Follow-the-Sun team supporting high-availability travel platforms.
- **Task:** incidents must move quickly between people, shifts and engineering teams.
- **Action:** escalates early with clear written evidence; documents procedures in runbooks so the next shift doesn't start from zero.
- **Result:** the operation as a whole resolves over 90% of ~4,600 weekly incidents at the frontline (team number); clear handoffs are a big part of it. Also at AWS: turned feedback from stakeholders in several countries into features.

### 4.5 Feedback: Python TA
- **Situation:** as TA for Programming in Python, a student was stuck on an exercise.
- **Task:** find why and help her move forward.
- **Action:** checked the required programming concepts one by one (she knew all of them), kept asking questions until finding the real blocker: the exercise needed fairly advanced math and she didn't understand the problem itself. Told her directly that her programming was solid, and advised her not to panic in exams: it's a programming exam, not a math exam, so ask to clarify the problem without fear.
- **Result:** she saw that her programming wasn't the problem. (Maria doesn't remember the exact exercise or later outcome: don't invent one.)
- **Learning:** good feedback starts with finding the real blocker, not the obvious one.

### 4.6 Disagreement: chemical engineering lab (cheese)
- **Situation:** joined a lab group that already knew each other and didn't trust her yet; each brought an ingredient for making cheese, hers was the milk; they told her to buy regular long-life whole milk.
- **Task:** she researched and found UHT milk changes the proteins, so rennet can't form a proper curd.
- **Action:** explained it; they didn't believe her. Instead of fighting, she bought both milks. They tried theirs first.
- **Result:** after three hours it didn't curdle; they switched to hers, losing three hours but not another lab day. The group started trusting her.
- **Learning:** bring evidence and a backup plan instead of arguing; share the source earlier next time.

**Gaps (no story yet):** leading a team, a production outage she personally fixed. Help her build honest stories; never invent them.

---

## 5. Strength and weakness

**Strength:** Problem solving with persistence. If something is possible, she assumes there's a way and likes being the one who finds it. Example: the hackathon. Outside work: LeetCode, puzzles, escape rooms.

**Weakness:** Not much experience with large production codebases yet. She compensates by reading documentation deeply and asking early, with clear evidence of what she tried. She used to keep debugging alone too long; the hackathon taught her to re-read the spec, and Amadeus taught her to escalate early.

---

## 6. Why Docplanner and why this role

**About Docplanner:** company behind Doctoralia (Spain, LatAm), ZnanyLekarz (Poland), MioDottore (Italy); 13 countries; marketplace for patients to find doctors and book appointments plus practice-management software for doctors; engineering hubs in Barcelona and Warsaw; bringing AI into clinical workflows. Stack: Node.js/TypeScript, React, React Native, AWS, Kubernetes, Terraform, CI/CD, observability. AI-assisted development by default. Values: problem solving, builder mindset, ownership, pragmatism, "signals over credentials".

**Why two degrees:** I actually started in Chemical Engineering. Then I took programming, and I liked it so much that I decided to study both, in parallel. What I liked was the idea of understanding chemistry with the logic of computing. Proteins are the clearest example for me. A protein is a sequence of amino acids, written by the genetic code, and to me it's like code we're still learning to read. I like knowing that everything has a pattern, and finding patterns is exactly what software is good at. My thesis brought both together: I used machine learning to predict how stable proteins are with heat. So for me the two degrees aren't separate: software is how I understand science. And that's part of why a healthcare product like Docplanner interests me.

**Why Docplanner (three reasons):**
1. **Impact:** helps millions of patients find a doctor and book appointments every month, in Spain and in Latin America too, where Maria is from.
2. **Engineering culture:** AI-assisted development by default and "signals over credentials" match how she learned at AWS (her own personal tool with Amazon Q Developer CLI, testing and reviewing every change; the hackathon).
3. **Healthcare + AI:** chemical engineering plus a thesis applying ML to protein data; science, health and software is where she wants to grow.

**Why this role:**
- Built for early-career engineers with a strong problem-solving and coding focus: her profile.
- Stack overlap: TypeScript and React (portfolio), NestJS on Node (coursework), Kubernetes/OpenShift (daily at Amadeus), AWS (internship + 3 certifications).
- A step from supporting systems to building them.

**Gaps to handle honestly (Admit → reframe → evidence):**
- Node.js only in coursework (NestJS), not production. No React Native.
- About 6 months full-time after graduating, plus the 10-month AWS internship.
- Leaving Amadeus after ~6 months: wants to build software and a Monday-to-Friday schedule.
- Lives in Colombia: Spanish citizen, no visa, will be living in Spain on the start date.
- Terraform only in self-directed labs. AWS CDK used in Python for the multi-agent prototype (not production).

---

## 7. Logistics answers (Docplanner)

| Question | Answer |
|---|---|
| Salary | "As I mentioned in my application, I'm looking at 40 to 48 thousand euros gross per year, depending on the full package." Then ask for their band and the full package; don't concede on the spot |
| Relocation | Spanish citizen, no visa; already decided to move; leaning Valencia, flexible; will be living in Spain on the start date; happy to align with onboarding dates |
| Notice / start | 2 weeks' notice; available 1 November 2026 |
| Why leaving Amadeus | Learned a lot about production, but the role is support and she wants to build software; also looking for a stable Monday-to-Friday schedule |
| Other processes | Yes, a few at different stages; this one is a top priority; will be open if timelines become an issue. No company names |
| On-call | Acceptable only if compensated; ask frequency and compensation (better in later stages) |

---

## 8. Questions Maria asks the interviewer
1. Could you walk me through the next steps of the process and the timeline? (always)
2. How are early-career engineers matched to teams, like Marketplace and Search, Practice Management or the AI clinical tools?
3. What does onboarding and mentorship look like for junior engineers, and what would success look like after six months?
4. How does AI-assisted development work day to day? Are there shared practices for reviewing AI-generated code?
5. How do fully remote engineers in Spain collaborate with the Barcelona and Warsaw teams?


---

## Motivation background (told by Maria 2026-10-07; use the framed answers, never the raw details)

- AWSome Builder (internal AWS Solutions Architect program, 3 certifications, each based on a project): Maria passed 2 of 3; stopped because she got the Amadeus job. She also practised Professional Services' own version. (Maria, 2026-10-07)
- Why she didn't stay at AWS (Maria, 2026-10-07): in Colombia AWS had 2 technical paths, Solutions Architect and Professional Services. In sales she worked close to SAs and prepared for SA (AWSome Builder). Seeing the role up close: mostly customer calls, repeating ~80% the same content within a chosen specialty, learning things overnight; she saw a colleague's interactive session get dismissive customer comments. She realized she prefers building, time to learn, depth and production. She moved closer to the ProServe junior team (<8 months old; the hackathon was with them; she practised their builder program too). January 2026: global layoffs removed all ProServe juniors (~30 people incl. the manager). Choice became SA with sales metrics vs a role with technical depth -> Amadeus. INTERVIEW: never mention customer comments, the 80% figure, headcount or the manager; frame positively.
- Why leaving Amadeus (Maria, 2026-10-07): joined with good salary and a promised 6-month training; the team is a rebirth of an existing Miami team (same time zone, cheaper labour). From September only 9 juniors remain, with a manager newer than them. She learned a lot (investigation under customer pressure) but stagnated: repetitive and easy work (same links, app dependencies, logs, RTOs, escalate); she automated the investigation. Wants depth, challenges and building. Personal: Spanish passport, always wanted to live in Europe, new experiences, right age. INTERVIEW: never mention salary comparisons, cheaper labour, Miami, the team being left alone, the manager, 'stagnated' or 'easy'; also the earlier schedule reason (10:00-19:00 + unpaid weekends) only if pushed, softly.

**Answer: why leaving Amadeus.** I've learned a lot at Amadeus. I investigate production incidents under pressure, with a customer waiting, and that's a skill I'll keep. But after six months, the work has become quite repetitive. The investigation follows the same steps every time, to the point that I automated part of it with my own Python script. I'm looking for more depth and harder problems, and above all, I want to build software, not only support it. And on a personal level, I'm a Spanish citizen and I'd like to live and work in Spain. This feels like the right moment to do it, in a role where I can keep growing for several years.

**Answer: why didn't you stay at AWS.** In Colombia, AWS had two technical paths for someone like me: Solutions Architect and Professional Services. I was in the sales organization, so I worked close to the Solutions Architects, and I started preparing for that path. I passed two of the three internal AWSome Builder certifications. But being that close to the role, I realized it's mostly customer calls about one specialty, and what I enjoy most is building and going deep. So I got closer to the Professional Services junior team. That's the team I did the hackathon with. Then in January, that junior team was closed as part of global layoffs. So I looked for a technical role where I could see production up close, and that's how I joined Amadeus.

- AWS campaign apps: each campaign lasted four weeks and the apps were used only during that campaign. They are NOT still in use: never say 'still used', 'every day since', 'in production' or that the team keeps using them. (Maria, 2026-10-07)


## Favourite stories by category (Maria, 2026-10-07)
- Proudest experience: the hackathon.
- Initiative: AWS campaign landing pages (backup: Amadeus Python script).
- Impact: the same landing pages.
- Failure / mistake: the failed first thesis.

- Campaign landing pages (AWS, told by Maria 2026-10-07): the plan was to buy them from a third-party vendor (~USD 2,000); she volunteered to build them internally and save that money; at first they doubted her; she built the first one and then all the campaign pages. Unconfirmed: whether the ~USD 2,000 was per page, per campaign or in total (say 'about two thousand dollars' for the vendor, never a total saving).
- Failed first thesis (told by Maria 2026-10-07): a chemical engineering thesis on proteins; days in the lab; she followed her director's recommendations to the letter; those same recommendations were what failed her, and he didn't defend her. Lesson: don't rely on one person's word, research more, ask others, have several sources of truth, trust her own knowledge. INTERVIEW: never blame the director, never say he called it badly done; own the single-source mistake.

**Answer: initiative.** At AWS, the sales team needed landing pages for their campaigns, and the plan was to buy them from an external vendor, for about two thousand dollars. I raised my hand and said I could build them internally, and save that money. At first, they weren't sure an intern could do it. So I built the first one, within Amazon's internal rules and approved services, and I found a supported way to use my own HTML and CSS. It worked, and after that, I built all the campaign pages. More than two hundred sales professionals across Latin America used them during each four-week campaign. What I took from it is that if I can see a better way, I'd rather offer it and prove it than just accept the default.

**Answer: impact.** A good example is the campaign landing pages I built at AWS. The plan was to buy them from an external vendor for about two thousand dollars, and I offered to build them internally instead. At first they weren't sure an intern could do it, so I built the first one, within Amazon's internal rules and approved services. I gathered feedback from teams in several countries, including Brazil, and found a supported way to use my own HTML and CSS so the pages were clear for busy sales teams. The impact: we didn't need the vendor, I ended up building all the campaign pages, and more than two hundred sales professionals across Latin America used them during each four-week campaign.

**Answer: failure.** A real failure for me was my first thesis attempt, in chemical engineering. I chose the topic I loved most, proteins, and I spent days in the lab running experiments. I based my method on my director's recommendations, because I trusted them completely. In the end, the thesis didn't pass. And what I own is this: I relied on a single source. I didn't research enough on my own, and I didn't ask other people to check the approach. So for my final thesis, I worked with two directors and validated my approach with more than one source, and it passed. What I learned is to validate an approach with more than one source.


## Facts confirmed 2026-10-08
- Relocation (Maria, 2026-10-08): she will move to Spain when she gets the job; she is NOT moving if there's no offer. Never say 'I've already decided to move to Spain' or 'settle in Spain long term'; say 'I'd move to Spain for this role'. Never mention other countries (e.g. Switzerland) as alternatives.
- Why Valencia: cost of living vs quality of life; would also accept Barcelona, including hybrid.
- Spanish documents: she doesn't have DNI / Social Security number / NIF yet; she'll get them first thing on arrival. Spanish citizen, no visa or work permit needed.
- Amazon Q tool and scraping: the tool itself didn't scrape; it reused a small script she wrote earlier that collected public event information. Never call it 'web scraping agents' or 'email automation agents'.
- Salary for Docplanner: she stated EUR 40-48k in the application, so her stated floor is 40k.

- Salary floor for Docplanner: EUR 40k is a hard limit (Maria, 2026-10-08).
- Found the role on Docplanner's careers page.
- Campaign apps = the landing pages; the vendor cost ~USD 2,000 PER CAMPAIGN; a campaign about every two months; she built them during her ~8 months there; teams were impressed by what she built with internally approved resources and asked her for recommendations and support for their own external events.
- Theses: the failed attempt was in chemical engineering (lab, burned out); her final thesis was ML on proteins combining both degrees, with two directors who supported her a lot; it passed.
- Amadeus: works in English every day (written records, incident calls, shift handover calls). Her team/manager don't know about the Python script yet (not polished).
- AWS offered her another internship but there were no full-time openings; she didn't see herself as a Solutions Architect.
- Computer-vision tracker: never bring it up (small personal game-automation project). Only if asked directly: 'a small personal project to practise PyTorch and OpenCV'. Never say it was for a video game.
- Live coding language: Python.

- References: her thesis director at Universidad de los Andes (knows her work best). Unconfirmed: whether Amadeus knows she's looking; don't offer the current employer as a reference.
- Code bug story: a UNIVERSITY project (object-oriented design): two classes with almost the same name (like Book / Books), one created automatically by the editor's create-class quick fix; found after about an hour with her professor. Use only for code-level debugging questions.
- No pull requests / team code review experience yet; would like to. Closest: reviewed and debugged student code as a teaching assistant.
- AI tools: not tied to one tool; mainly AI search to find solutions faster; Amazon Q Developer CLI at AWS; her work is based on understanding the problem; always reviews output.
- Timeline: finished courses May 2025, internship full time from June 2025, graduation ceremony October 2025.
- Offers: no offers or deadlines right now (2026-10-08); in other processes.
