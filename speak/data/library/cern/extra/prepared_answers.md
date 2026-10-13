# Prepared answers - CERN GRAE Computer Security (EN)

## tell_me_about_yourself - Tell me about yourself | Walk me through your background | Who are you
I'm Maria. I studied two degrees at Universidad de los Andes, Systems and Computer
Engineering and Chemical Engineering. Before Amadeus I did a ten-month internship at AWS.
Since April I've been a Junior Cloud Support Engineer at Amadeus, on a 24/7 follow-the-sun
team that keeps high-availability travel platforms running on Linux and Kubernetes/OpenShift.
What I've learned there is that the part I like most is the moment something breaks:
understanding why, and deciding fast whether I can fix it myself or need to escalate it with
the evidence. Security is that same question, but with someone on the other side breaking it
on purpose. That's where I want to grow.

## why_two_degrees - Why two degrees | Why both chemical and computer engineering | Why did you study chemical engineering and computing
Because I liked both, and they fit together. I started in Chemical Engineering, then I took
a programming course and liked it so much that I added Computing, in parallel. Chemistry is
full of patterns, and finding patterns is what software is good at. My thesis joined the
two: I used machine learning to predict how stable a protein is when it's heated.

## chemical_engineering_useful - What did you take from chemical engineering that's useful in IT | What does chemical engineering bring to IT
Mainly how to troubleshoot when you can't just rerun things. In a lab you can't run an
experiment twenty times to find where it broke. You follow a procedure, and when something
fails you reason back with the chemistry: if the protein got contaminated, it's because a
material wasn't autoclaved, or a step wasn't sealed properly. I bring that to incidents: I
think about which step could cause this symptom, and I don't go down paths I know can't be
the cause.

## why_cern - Why CERN | Why do you want to work here | Why are you applying to CERN and to this team in particular
Honestly, my goal has always been to keep growing. At Amadeus I've learned a lot, but the
cases have started to repeat, to the point that I wrote a script to automate how I search
and triage them. For me that's the sign it's time for a bigger challenge. Security is that
challenge, and this team protects an open, international science environment, which is a
harder problem than securing a typical company. And on a personal note, I've always wanted
to work in another country. I'm Spanish, and people often ask me why I'm still in Colombia.
This is the moment to take that step.

## cern_harder_problem - What makes protecting an open science environment harder than one company | Why is CERN a harder security problem | What's different about securing CERN
To be clear, at Amadeus I don't secure the platform: I investigate incidents when something
fails, and I fix it or escalate it. But the difference is clear to me. A company can rely on
control: known users, company devices, closed access. CERN can't work that way. It's open by
design: thousands of scientists from institutes all over the world, many on their own
devices, sharing computing and data across sites, and the science needs that openness. So
you have to protect it without closing it, and it's an attractive target too. That balance
is what makes it harder, and more interesting to me.

## cern_publication - What publication or task stood out to you | Which of our articles did you read | What did you read about our team's work | What did it tell you about the team
The one that stuck with me was "One click to many", from July. A phishing email asked people
to type a verification code, and that used Microsoft's device code login, so even with CERN's
two-factor authentication the attacker got a valid token, good for 90 days. Then it used the
mailbox to send itself on to more than five thousand people at CERN, and 108 clicked, so the
team had to revoke their tokens.
What it told me is that the team doesn't stop at "we have 2FA, we're safe": the attackers
moved to the token, and you followed them there. And you published it openly, so the whole
lab learns from it. Since the role includes reviewing Microsoft 365, that's exactly the kind
of problem I'd like to work on.
If they ask how to prevent it: block or limit device code login for people who don't need
it, shorten how long those tokens last, and alert on device code sign-ins in the logs. The
article itself says the team is looking at disabling it and reducing the 90 days.
If the talk goes to control systems or my chemical engineering: I also read your ICALEPCS
paper, "20 years (trying to) securing controls". What struck me is the closing idea that
the question is not if a facility falls for an attack, but when. And that recent pentests
still found basic problems, like default passwords stored unprotected in cameras, or shared
passwords sent in clear text. Coming from chemical engineering, where plants run on control
systems, that made that side of CERN's work very concrete for me.

## why_security - Why security | Why do you want to move into security | Why security if your experience is in cloud and operations
Because the part of my job I enjoy most is when something breaks: understanding why, and
deciding fast whether I can fix it myself or need to escalate it with the evidence. Security is that same question, but with someone
on the other side breaking it on purpose, and that makes it harder and more interesting to
me. Cloud and operations are a good base for it, because you can't protect a system you
don't know how to run. That's why I want to make the jump now.

## incident_hard_amadeus - Tell me about a difficult incident you handled
A recent one: users at one airport couldn't log in to their backup environment in another
region. In Splunk, on that region's gateway logs, I saw their logins went from normal to only
failures after one night, all with the same reason: the authentication server denied access.
I ruled out the network and the application, and then found the cause: a migration of those
accounts to a new authentication mechanism that the backup region didn't support yet. I
documented it with the evidence and the SRE team confirmed it (details in
login_failure_case). Because the first steps of every investigation repeat, I also wrote a
personal read-only Python script that gathers the ticket's dashboards for me.

## recent_changes_how - What recent changes were you looking for | How did you find the recent changes | How do you check recent changes | What kind of changes do you look for
Changes on the affected service or on the affected users, in the window right before the
failures started. But first I narrow down in the logs where it fails, because that tells me
what kind of change to look for. Last week, for example, the logs showed one group of users
being rejected by authentication, so I looked for changes touching those users, and found a
user migration that started about 30 minutes after their last successful login.

## login_failure_case - Tell me about a recent incident | Give me a concrete example | How did you correlate the logs | What did the logs or timestamps show | What was the change that caused it | How did you rule out the network | Who fixed it
Last week, users at one airport couldn't log in to their backup environment in another
region. I went to Splunk, to the logs of that region's Citrix NetScaler gateways.
First the timeline: those users had between 18 and 52 successful logins a day, and after one
night, only failures. Every failure had the same reason, "External authentication server
denied access", across 25 different users, and the authentication messages showed that
region's LDAP policy rejecting them. The failures also clustered at the times the customer
reported.
Then I ruled things out. The requests reached the gateway, so it wasn't the site's network.
The region was healthy for everyone else: normal login numbers compared to the day before.
The same users still logged in fine in their main region. And a support test with a different
account opened the application in the backup region. So it was authentication, for those
users only.
Then the change: a migration of those user accounts had started about 30 minutes after their
last successful login, and every attempt after it failed. I documented that as the candidate
cause, and the SRE team confirmed it: the accounts had moved to Keycloak, a new
authentication mechanism, and the backup region didn't support it yet. Workaround: another
region. The fix for that region is planned.
How I knew the requests reached the gateway: the failures themselves were logged by the
gateway. In Splunk I searched the NetScaler events named LOGIN_FAILED for those users, and
each had a Failure_reason field, "External authentication server denied access", plus the
user and the client IP. The gateway can only log that if the request arrived and it tried to
authenticate the user against LDAP. If it were the site's network, there'd be nothing from
those users in those logs. For the before-and-after, I counted the LOGIN and LOGIN_FAILED
events per day for those users.
Have I seen both patterns, a denial versus no response at all, in real incidents? Yes. The
denial side is this case: every failure was an answer from the authentication server, just a
negative one. The no-response side I saw in the payment link case: there the external
provider didn't answer at all, so the card authorizations timed out.
A detail I was careful with: the failure counts were indexed events that looked duplicated,
so I didn't report them as unique attempts.

## third_party_link_down - How do you know if a problem is on your side or a third party's | Tell me about an incident caused by an external provider | What do you check first in an outage
A recent one: an automatic alert said the payment link to one external payment provider was
down, and card authorizations were timing out. My part was to check our side. In Splunk, the
card authorization dashboard showed a spike of failed authorizations starting at 15:00 GMT,
already going down. I checked our payment dashboards in Grafana, and the maintenance calendar,
to see if anything planned on our side could explain it: nothing was. The payments team then
confirmed in the logs that the provider simply hadn't responded for about 40 minutes. The link
recovered on its own, and support followed up with the provider for the root cause.

## logging_facility_alf - Was that through a GitOps tool, deployment annotations or CI/CD history | What logging tool do you use | What is the name of that logging facility | How do you go deeper than the dashboards
Day to day I start with Grafana and Prometheus dashboards for the symptom. When I need to go
deeper, I go to the logging facility. It's an internal tool called ALF, literally the Amadeus
Logging Facility. There I can follow the path the request or the message went through and see
exactly where it failed.

## searching_alf - How do you query or search ALF | How do you search the logs when troubleshooting | How do you correlate IDs | How do you trace a request across log entries
I start from what the customer reports. For example, if they say they can't log in to an
application, I look for that same error in ALF. That entry gives me the message ID and other
IDs, and with those I can follow the specific applications and path the message took, until I
see where it fails. Then I trace it back to what failed.

## triage_script_details - How does your triage script work | How was authentication handled in the script | Did it use a token, a key, or something else | How do you make sure the script is read-only | What exactly does the script do | Did your team ask you to build it | Does the team use it
It's one Python script, and a personal tool: nobody asked for it, I built it to do my own
triage faster, because the investigation follows the same steps every time. I want to polish
it before I propose it to the team. I give it an incident number, it reads the ticket through the
ticketing system's REST API, pulls out the monitoring links, and opens the first metrics and
log dashboards it finds, Thanos, Grafana and Splunk, with a recent time window. Then it saves
screenshots and a JSON and Markdown summary. For authentication there's no stored key or
password: it uses Playwright to drive Chrome with my own SSO session, and I sign in with MFA
myself. The only token involved is the session's anti-CSRF token, which it reads from the page
for the ticket API call; it's never saved in files or in the output. It's read-only by what it does: only GET
requests, reading pages and taking screenshots. That isn't enforced by a read-only role yet,
which is what I'd add next. I always validate the findings manually.

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

## landing_pages_tech - What service did you use to host the landing pages | How did you build the landing pages technically | Which tools did you use for the dashboards
The pages lived on Amazon's internal wiki: that was the approved place to host the HTML. I
found out how to add my own formatting there with HTML and CSS. I couldn't use JavaScript,
but I managed well without it. For the charts I used Amazon QuickSight, and I also used it
to store and organize the campaign data.

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

## key_vault_details - How was the secret retrieved at runtime from Key Vault | What identity or authentication method was used | How was access to the Key Vault controlled | Did you rotate or monitor the credentials | Which vault solution did you use
It was Azure Key Vault, and I built that flow end to end: the vault didn't exist before, I
created it for this flow. It held the bank API credential and the API key. At runtime the
flow read them from the vault and made one request to the bank's API, which returned a
temporary token that expired after about three hours. The payment calls used that token,
not the stored credentials. Access to the vault was meant for that flow only. I didn't set
up rotation or monitoring on the vault itself; what we did keep was a log of every change
in our database against the payments: paid, not paid, a phone number changed. Today I'd
add RBAC scoped to the flow's identity, expiry dates and rotation on the stored secrets,
and the vault's access logs wired to alerts.

## python_and_scripting - What is your experience with Python and scripting | Have you done shell scripting | Do you know PowerShell or bash
Python is my live-coding language. I built the read-only triage script, the AWS CDK
multi-agent prototype (Bedrock AgentCore, Strands, Knowledge Base with RAG), and my thesis
pipeline (20k+ protein sequences from UniProt, ESM-2 embeddings, PyTorch LSTM, served with
Docker). At Amadeus I use the Linux command line daily for troubleshooting; when I work with
pods I pipe kubectl into grep to find the specific pods I need. I also wrote a small
PowerShell script that refreshes the incident queue page, so I always see the queue up to
date instead of refreshing it by hand. At AWS I wrote a small script that collected public
event information.

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

## hardened_in_production - Give me a concrete example of something you've hardened in production | What have you hardened in production
I haven't hardened anything in production yet. The closest I've done is on access and
secrets. In a freelance payments flow, I kept the credentials in Azure Key Vault, not in the
code. At Amadeus, my one triage script is read-only and uses only my own access. Real
hardening, like RBAC and network policies, is what I want to build here.

## cert_lifecycle_live - Have you ever rotated or revoked a certificate in a live environment | Have you ever had to rotate a certificate or revoke one in a live environment
Not in a live environment yet. I know the flow: revoke it, publish that through CRL or OCSP,
then reissue with a new key pair, never the old one. That's something I'd want to learn here
with the team's own tooling.

## on_call_night_shifts - Are you okay with on-call and night shifts
Yes. At Amadeus I'm already in a 24/7 follow-the-sun team, and some weeks that includes
weekend shifts. That's part of operating real systems, and I'm open to the on-call rota
this role needs.

## large_international_teams - Have you worked in large international teams
At AWS I gathered feedback from teams across LATAM (including Brazil). At Amadeus I work
daily in English: incident notes, escalations, runbooks, incident calls and shift handovers.
I am used to large, multilingual, distributed teams.

## non_native_communication - How do you handle communication when team members are not native English speakers | How do you communicate across languages
I'm not a native English speaker either, so I know both sides of it. I speak more slowly,
and I put things in writing. At AWS I worked closely with a colleague from Brazil: she
didn't speak much Spanish, I didn't speak Portuguese, and English wasn't easy for her
either. So after every meeting we wrote down what we had agreed, and that way we were both
sure we were on the same page.

## where_do_you_see_yourself - Where do you see yourself in five years
Growing into a security engineer: detection, cloud security and pentesting, ideally staying
in a research/scientific environment where the work has real impact.

## salary_and_availability - When could you start | Are you willing to relocate to Geneva
Available from 1 November 2026 (2-week notice). Spanish national (EU citizen), no visa
needed. I'd relocate to Geneva or the French border area for this role.
(Note: CERN start was 1 Oct 2026, so ask the real date.)
