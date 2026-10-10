# Prepared answers - CERN GRAE Computer Security (EN)

## tell_me_about_yourself - Tell me about yourself | Walk me through your background
CS engineer (double degree with Chemical Engineering), currently a Junior Cloud Support
Engineer at Amadeus since April 2026, in a 24/7 follow-the-sun team supporting
high-availability travel platforms on Linux and Kubernetes/OpenShift. Before that, a
10-month internship at AWS in the LATAM sales org. Spanish national (EU citizen), ready to
relocate to Geneva or the French border area for this role, available from 1 November 2026.
I want to move into security: operating real systems is what I enjoy most, and hardening is
where I want to grow.

## why_cern - Why CERN | Why do you want to work here
Three reasons. One: it is real science with global impact, not another product. Two: the
role is exactly where I want to grow - SOC, cloud security and pentesting, using open
source tools like Zeek, Kafka and MISP. Three: the international, multilingual environment
is where I do my best work, and I already work in English daily. I am also committed to
learning French.

## why_security - Why security | Why do you want to move into security
My path has been systems and cloud, and security is the natural next step. From the
operations side I already do incident triage, I wrote a read-only script that uses only my
own authenticated access, and in a freelance payments flow I kept the credentials in Azure
Key Vault. I want to go deeper into detection, hardening and pentesting.

## incident_hard_amadeus - Tell me about a difficult incident you handled
Situation: connection drops in one of the applications. Task: find root cause fast.
Action: reviewed the monitoring dashboards one by one to isolate whether it was the app,
the network or something else; checked recent changes; escalated with written evidence
when it needed engineering. Because the steps always repeat, I automated part of it with a
read-only Python script that pulls the relevant graphs and incidents using my own
authenticated access. Result: faster triage, start from the most relevant signal, catch
hard problems sooner.

## hackathon_secure_tunnel - Tell me about a hard technical challenge
(Strongest story for a security team.)
Situation: AWS LATAM New Hire Jam 2025, 14 challenges, my team was one person short. Task:
connect two VMs with a secure, authenticated tunnel - one of the hardest challenges.
Action: deployment kept failing; instead of guessing I re-read the whole spec and found a
key requirement at the end showing my environment was misconfigured from the start.
Redeployed once, clean, validating each step. Result: no other team completed it; we were
the only LATAM team to finish all 14 and we won. Learning: read the full spec, question
your own config, rebuild clean.

## proud_project_landing_pages - What project are you most proud of
Situation: campaign landing pages were going to cost about 2,000 USD per campaign from an
external vendor. Task: offer to build them in-house. Action: built the first in ~4 days
using only Amazon's approved services and internal rules; read internal docs until I found
a supported way to use my own HTML/CSS; gathered feedback from teams across LATAM. Result:
built them all, used by 200+ sales professionals during each four-week campaign, with KPI
tracking and dashboards. It is where I proved I can deliver when people doubted an intern.

## conflict_lab_cheese - Tell me about a time you disagreed with your team | A conflict with a teammate
Situation: chem engineering project, group did not trust me. Task: I was in charge of the
milk for cheese. Action: they wanted UHT whole milk; I researched that the heat changes
proteins so it does not curdle well. They did not believe me, so instead of arguing I
bought both. Result: theirs did not curdle after 3 hours, mine worked - we lost no lab day.
Learning: bring evidence and a plan B; next time share the source first.

## kubernetes_openshift - What is your experience with Kubernetes | Have you worked with OpenShift
At Amadeus I troubleshoot microservices on Linux and Kubernetes/OpenShift: pod recycling,
health and performance checks with Grafana and Prometheus, escalating to engineering with
written evidence, documenting runbooks. On hardening, I know the angle - RBAC, resource
limits, restart behaviour, and how misconfigurations surface as incidents - but I haven't
done hardening work myself yet; that's where I want to grow.

## cloud_security_aws - What is your experience with AWS and cloud security
10-month AWS internship plus certs (Solutions Architect Associate, ML Engineer Associate,
GenAI Developer Professional). I built only with Amazon's approved services, and used the
AWS CDK in Python for my multi-agent prototype. On cloud security, I know the angle - IAM
least privilege (roles over wildcards), avoiding public S3 buckets, reviewing
M365/Workspace-style misconfigurations - but I haven't done that work hands-on yet. What I
have done in practice: a read-only script that uses only my own access at Amadeus, and
credentials kept in Azure Key Vault in a freelance flow.

## secrets_and_least_privilege - How do you handle secrets and least privilege
Freelance payments flow: Power Automate/Power Apps over a Colombian bank's existing REST
API, 2,000+ weekly payments, credentials stored in Azure Key Vault, dashboards for
successful and reversed transactions. My Amadeus script is read-only by design and uses my
own authenticated access. Those are the same principles, applied at a small scale.

## python_and_scripting - What is your experience with Python and scripting
Python is my live-coding language. I built the read-only triage script, the AWS CDK
multi-agent prototype (Bedrock AgentCore, Strands, Knowledge Base with RAG), and my thesis
pipeline (20k+ protein sequences from UniProt, ESM-2 embeddings, PyTorch LSTM, served with
Docker). Linux daily for troubleshooting at Amadeus, and some shell.

## monitoring_and_detection - What is your experience with monitoring and detection | Have you worked in a SOC
At Amadeus: Grafana and Prometheus in a 24/7 follow-the-sun team; the team manages its
dashboards and alerts as code.
SOC angle: Zeek is network monitoring/IDS (passive, not inline); logs would flow to
OpenSearch via Kafka; MISP is threat intel. I have not used these three directly but I know
what each does and how they fit.

## authn_vs_authz - What is the difference between authentication and authorization
Authentication proves who you are (passwords, MFA, certificates, SSO). Authorization
decides what you can do (roles, policies, scopes). The hackathon tunnel was authentication;
IAM policies and RBAC are authorization. Common failure: confusing the two and giving broad
permissions.

## tls_and_pki - How does TLS work | Explain PKI and certificates
TLS secures transport with a handshake that authenticates the server via an X.509
certificate signed by a trusted CA (PKI). Key points: cert validation, expiry, and that PKI
is only as strong as its key management. Ties to my hackathon tunnel (secure, authenticated
channel).

## learning_security_gaps - Do you have pentesting or CTF experience | What are your security gaps
I have no formal pentesting or CTF record yet. But the tunnel, least-privilege scripting and
Key Vault work are the same principles. To fill the gap I would: practice on CTFs, study
Zeek/Kafka/MISP, and go deep on Kubernetes hardening and AWS IAM.

## on_call_night_shifts - Are you okay with on-call and night shifts
Yes. At Amadeus I'm already in a 24/7 follow-the-sun team, and some weeks that includes
weekend shifts. That's part of operating real systems, and I'm open to the on-call rota
this role needs.

## large_international_teams - Have you worked in large international teams
At AWS I gathered feedback from teams across LATAM (including Brazil). At Amadeus I work
daily in English: incident notes, escalations, runbooks, incident calls and shift handovers.
I am used to large, multilingual, distributed teams.

## where_do_you_see_yourself - Where do you see yourself in five years
Growing into a security engineer: detection, cloud security and pentesting, ideally staying
in a research/scientific environment where the work has real impact.

## salary_and_availability - When could you start | Are you willing to relocate to Geneva
Available from 1 November 2026 (2-week notice). Spanish national (EU citizen), no visa
needed. I'd relocate to Geneva or the French border area for this role.
(Note: CERN start was 1 Oct 2026, so ask the real date.)
