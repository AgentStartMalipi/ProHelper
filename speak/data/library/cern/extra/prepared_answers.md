# Prepared answers - CERN GRAE Computer Security (EN)

(Format: one spoken sentence per line, subject first, linked with simple words. Lines in
parentheses are notes for the copilot and are never shown to read.)

## tell_me_about_yourself - Tell me about yourself | Walk me through your background | Who are you
I'm Maria, and I studied two degrees at Universidad de los Andes.
They were Systems and Computer Engineering, and Chemical Engineering.
Before Amadeus, I did a ten-month internship at AWS.
Since April, I've been a Junior Cloud Support Engineer at Amadeus.
I'm on a 24/7 follow-the-sun team that keeps travel platforms running on Linux and Kubernetes.
What I like most there is the moment something breaks.
I want to understand why, and decide fast if I can fix it or need to escalate it.
Security is that same question, but with someone breaking it on purpose.
That's where I want to grow.

## why_two_degrees - Why two degrees | Why both chemical and computer engineering | Why did you study chemical engineering and computing
Everyone asks me that, and I love answering it.
I started in Chemical Engineering.
Then I took a programming course, and I liked it so much that I added Computing in parallel.
For me, both connect in one idea.
A protein is code, written in the genetic code, and science is still learning to read it.
My thesis joined the two.
I used machine learning to predict how stable a protein is when it's heated.

## chemical_engineering_useful - What did you take from chemical engineering that's useful in IT | What does chemical engineering bring to IT
Mainly, how to troubleshoot when you can't just run things again.
In a lab, you can't repeat an experiment twenty times to find where it broke.
So when something fails, you reason back with the chemistry.
For example, if the protein got contaminated, maybe a material wasn't autoclaved.
Or maybe a step wasn't sealed properly.
I bring that to incidents.
I think about which step could cause this symptom.
And I don't go down paths that I know can't be the cause.

## why_cern - Why CERN | Why do you want to work here | Why are you applying to CERN and to this team in particular
My goal has always been to keep growing.
At Amadeus I've learned a lot, but the cases have started to repeat.
In fact, I wrote a script to automate the first checks I do on them.
For me, that's the sign it's time for a bigger challenge, and security is that challenge.
I chose this team because it protects an open science environment.
That's harder than securing a typical company.
I also like how you work.
When something happens, like the phishing in "One click to many", you explain it openly.
That way, the whole lab learns from it, and that's the kind of team I want to learn from.
And on a personal note, I've always wanted to work in an international environment.
CERN is where I want to take that step.

## cern_harder_problem - What makes protecting an open science environment harder than one company | Why is CERN a harder security problem | What's different about securing CERN
To be clear, at Amadeus I don't secure the platform.
I investigate incidents, and then I fix them or escalate them.
But the difference is clear to me.
A company can rely on control: known users, company devices and closed access.
CERN can't work that way, because it's open by design.
You have thousands of scientists from institutes all over the world.
And from what I read, there are about two hundred thousand personal devices on your network that you don't manage.
They share computing and data across sites, and the science needs that openness.
So you have to protect it without closing it.
It's also an attractive target.
That balance is what makes it harder, and more interesting to me.

## academic_freedom - Security versus academic freedom | How would you balance security and academic freedom here | How do you keep science open and still secure
(Maria's own structure, 2026-10-13.)
I wouldn't lock things down by default, because the science needs openness to work.
I'd put the controls on identity instead, with strong authentication on who gets in.
Then I'd watch the network, because you can't manage two hundred thousand personal devices.
That way scientists keep sharing data and computing across sites.
And where you do own the assets, like control systems, I'd segment them.

## open_environment_priority - How would you secure an environment where you can't control the users and devices | What would your first priority be, detection or segmentation | How do you protect an open environment
For me, it's layers, not one choice.
If I have to pick a first priority, it's strong authentication.
That's because identity is the one thing you control, even on devices you don't own.
But your July article shows that attackers then go after the token.
So you also need to watch the sign-ins and the tokens.
Second, I'd put detection.
You can't install anything on two hundred thousand personal devices, so you watch the network and the logs.
That's how you catch the accounts that get compromised anyway.
And third, segmentation where you do own the assets, like servers and control systems.
That's defense in depth.

## cern_publication - What publication or task stood out to you | Which of our articles did you read | What did you read about our team's work | What did it tell you about the team
The one that stuck with me was "One click to many", from July.
A phishing email asked people to type a verification code.
That code used Microsoft's device code login.
So even with two-factor authentication, the attacker got a valid token for 90 days.
Then the attack used the mailbox to send itself to more than five thousand people at CERN.
In the end, 108 people clicked, and the team had to revoke their tokens.
What it told me is that the team doesn't stop at "we have 2FA, so we're safe".
The attackers moved to the token, and you followed them there.
And you published it openly, so the whole lab learns from it.
That's exactly the kind of problem I'd like to work on.

## prevent_device_code_phishing - How would you prevent that attack | How would you stop device code phishing | What would you do about the device code login
First, I'd block or limit device code login for people who don't need it.
Then I'd shorten how long those tokens last.
And I'd alert on device code sign-ins in the logs.
In fact, the article says the team is looking at disabling it and reducing the 90 days.

## icalepcs_paper - Did you read anything about control systems | What do you know about control system security | Have you read my paper
(Only if the talk goes to control systems, chemical engineering or his own work.)
I also read your ICALEPCS paper, "20 years (trying to) securing controls".
What struck me is the closing idea.
The question is not if a facility falls for an attack, but when.
I was also surprised that recent pentests still found basic problems.
For example, default passwords stored unprotected in cameras, or shared passwords sent in clear text.
I come from chemical engineering, where plants run on control systems.
So that made that side of CERN's work very concrete for me.

## what_challenges_you - What actually challenges you | What inherently interests you in IT | What really challenges you, not the rehearsed line
(Maria's own words, 2026-10-13.)
What really pulls me in is not knowing why something broke.
I want to trace it back step by step, until the cause is certain and not just likely.
Security makes that sharper, because someone is actively hiding what they did.
That's what challenges me.

## why_security - Why security | Why do you want to move into security | Why security if your experience is in cloud and operations
The part of my job I enjoy most is when something breaks.
I want to understand why, and decide fast if I can fix it or need to escalate it.
Security is that same question, but with someone breaking it on purpose.
That makes it harder, and more interesting to me.
Cloud and operations are a good base for it.
That's because you can't protect a system you don't know how to run.
That's why I want to make the jump now.

## incident_hard_amadeus - Tell me about a difficult incident you handled
A recent one was a login problem.
Users at one airport couldn't log in to their backup environment in another region.
I went to Splunk and looked at that region's gateway logs.
Their logins went from normal to only failures after one night.
And all the failures had the same reason: the authentication server denied access.
So I ruled out the network and the application.
Then I found the cause.
Those accounts had been migrated to a new authentication mechanism, and the backup region didn't support it yet.
I documented it with the evidence, and the SRE team confirmed it.
Because the first steps of every investigation repeat, I also wrote a personal script for them.
It's read-only, and it gathers the ticket's dashboards for me.

## recent_changes_how - What recent changes were you looking for | How did you find the recent changes | How do you check recent changes | What kind of changes do you look for
I look for changes on the affected service or users, right before the failures started.
But first, I narrow down in the logs where it fails.
That tells me what kind of change to look for.
For example, last week the logs showed one group of users rejected by authentication.
So I looked for changes on those users.
That's how I found a user migration.
It started about 30 minutes after their last successful login.

## login_failure_case - Tell me about a recent incident | Give me a concrete example | How did you correlate the logs | What did the logs or timestamps show | What was the change that caused it | Who fixed it
Last week, users at one airport couldn't log in to their backup environment in another region.
I went to Splunk, to the logs of that region's Citrix NetScaler gateways.
First, I checked the timeline.
Those users had between 18 and 52 successful logins a day.
After one night, there were only failures.
Every failure had the same reason: "External authentication server denied access".
That was true for 25 different users.
The authentication messages showed that region's LDAP policy rejecting them.
Then I ruled things out.
The requests reached the gateway, so it wasn't the site's network.
The region was fine for everyone else, with normal login numbers.
The same users still logged in fine in their main region.
And a test with a different account opened the application in the backup region.
So it was authentication, only for those users.
Then I looked for the change.
A migration of those accounts started about 30 minutes after their last successful login.
After it, every attempt failed.
I documented that as the likely cause, and the SRE team confirmed it.
The accounts had moved to Keycloak, and the backup region didn't support it yet.
(One more detail if they push on numbers: the failure counts were indexed events that looked
duplicated, so I didn't report them as unique attempts.)

## login_gateway_evidence - How did you confirm the requests reached the gateway | What field or log entry showed the request arriving | How did you rule out the network | What exactly was in the gateway logs
The failures themselves were logged by the gateway.
In Splunk, I searched the NetScaler events called LOGIN_FAILED for those users.
Each one had a Failure_reason field: "External authentication server denied access".
Each entry also had the user name, and that's how I counted 25 different users.
The gateway can only log that if the request arrived and it asked LDAP.
If it were the network, those users wouldn't be in the logs at all.
For the before and after, I counted the logins and failed logins per day.
(The entries also show the client IP, but I didn't analyse the IPs: never claim I did. If
asked: "Each entry had the client IP too, but I focused on the users and the failure reason.")

## login_contribution - What was your concrete contribution | What was your own part, not the team's | What did you do yourself in that incident
(Maria's own account, 2026-10-13. The change search tool's name is not in the notes: never name it.)
My part was the diagnosis.
First I ruled out infrastructure, network and the client side, from the logs I can see.
Then I searched for recent changes in an internal tool.
I saw that a user migration was deployed, and the failures started about five minutes later.
I documented the timing, the error and the affected users.
Then I handed it to the SRE team, and they confirmed it and owned the fix.
That configuration is theirs, not mine.

## login_again_tonight - Suppose the same thing happens again tonight | What would you check first | What would make you change your mind | If it happened again what would you do | What if it happens again tonight
(Maria's own account, 2026-10-13.)
First I'd check Splunk for the same failure reason on the gateway.
Then I'd check if it only hits users from that same airport, or other users too.
That tells me if it's the same cause again or a new one.
I'd also check if the migration or any other change touched those accounts again.
What would change my mind is a different error reason.
The same goes if it hits users outside the migrated group.
For example, users at other airports or other customers complaining about the same issue.

## login_evidence_short - Summarize the evidence | What were the key signals | Give me the evidence in short
There were three things in the logs.
One, every failure was a LOGIN_FAILED event, so the gateway had received the request.
Two, the reason was the same for all 25 users: a clear denial, not a timeout.
Three, it started with the user migration.
Same error, same group and same moment.
So it was an authentication policy problem, not the network and not wrong passwords.

## login_both_patterns - Have you seen a denial versus no response at all | Have you observed both patterns in a real incident | Denial or timeout
Yes, I've seen both.
The denial side is the login case.
Every failure was an answer from the authentication server, just a negative one.
The no-response side was a payment link incident.
There, the external provider didn't answer at all, so the card payments timed out.

## login_afterwards - What changed afterwards | What happened after you found the cause | What was the lesson | What would you suggest
The customer got a workaround right away: another region they already had access to.
The backup region is planned to support the new mechanism within 30 days.
I don't know if any process changed after it.
But what I'd suggest is simple.
Before migrating accounts, check every region and entry point those users rely on, including the backups.
And it connects to security.
Authentication logs are exactly where you'd also see an attacker.
It's the same skill, with a different intent.

## third_party_link_down - How do you know if a problem is on your side or a third party's | Tell me about an incident caused by an external provider | What do you check first in an outage
A recent one was a payment alert.
It said the link to one external payment provider was down, and card payments were timing out.
My part was to check our side.
In Splunk, the card payment dashboard showed a spike of failures starting at 15:00 GMT.
By then, it was already going down.
I also checked our payment dashboards in Grafana and the maintenance calendar.
Nothing planned on our side could explain it.
Then the payments team confirmed in the logs that the provider hadn't answered for about 40 minutes.
The link recovered on its own, and support followed up with the provider.

## logging_facility_alf - Was that through a GitOps tool, deployment annotations or CI/CD history | What logging tool do you use | What is the name of that logging facility | How do you go deeper than the dashboards
Day to day, I start with Grafana and Prometheus dashboards for the symptom.
When I need to go deeper, I go to the logging facility.
It's an internal tool called ALF, which means Amadeus Logging Facility.
There, I can follow the path a request took and see exactly where it failed.

## searching_alf - How do you query or search ALF | How do you search the logs when troubleshooting | How do you correlate IDs | How do you trace a request across log entries
I start from what the customer reports.
For example, they say they can't log in to an application.
So I look for that same error in ALF.
That entry gives me the message ID and other IDs.
With those IDs, I follow the path the message took, application by application.
That's how I see where it fails, and then I trace it back to the cause.

## triage_script_details - How does your triage script work | How was authentication handled in the script | Did it use a token, a key, or something else | How do you make sure the script is read-only | What exactly does the script do | Did your team ask you to build it | Does the team use it
It's one Python script, and it's a personal tool.
Nobody asked for it.
I built it to do my own investigations faster, because they follow the same steps every time.
I want to improve it before I propose it to the team.
I give it an incident number, and it reads the ticket through the ticketing system's REST API.
Then it takes the monitoring links and opens the first dashboards it finds in Thanos, Grafana and Splunk.
At the end, it saves screenshots and a short summary in JSON and Markdown.
For authentication, there's no stored key or password.
It uses Playwright to drive Chrome with my own SSO session, and I sign in with MFA myself.
The only token is the page's anti-CSRF token, which it reads for the ticket API call.
That token is never saved in files or in the output.
The script is read-only because it only does GET requests, reads pages and takes screenshots.
But no read-only role enforces that yet, and that's what I'd add next.
And I always check the findings myself.

## hackathon_secure_tunnel - Tell me about a hard technical challenge
(Strongest story for a security team.)
It was the AWS LATAM New Hire Jam in 2025, with 14 challenges.
My team was one person short.
I took one of the hardest challenges: connecting two VMs with a secure, authenticated tunnel.
The deployment kept failing.
So instead of guessing, I read the whole spec again.
At the end, I found a key requirement that showed my environment was wrong from the start.
I redeployed once, clean, and checked each step.
No other team completed that challenge.
We were the only LATAM team to finish all 14, and we won.
What I learned is to read the full spec, question my own setup, and rebuild clean.

## proud_project_landing_pages - What project are you most proud of
At AWS, campaign landing pages were going to cost about 2,000 dollars per campaign from an outside vendor.
So I offered to build them in-house.
I built the first one in about four days.
I used only Amazon's approved services and followed the internal rules.
I read the internal docs until I found a supported way to use my own HTML and CSS.
I also collected feedback from teams across LATAM.
In the end, I built all of them.
More than 200 sales people used them in each four-week campaign, with KPI tracking and dashboards.
That's where I proved I can deliver, even when people doubted an intern.

## landing_pages_tech - What service did you use to host the landing pages | How did you build the landing pages technically | Which tools did you use for the dashboards
The pages lived on Amazon's internal wiki, because that was the approved place for the HTML.
I found out how to add my own formatting there with HTML and CSS.
I couldn't use JavaScript, but I managed well without it.
For the charts, I used Amazon QuickSight.
I also used it to store and organize the campaign data.

## conflict_lab_cheese - Tell me about a time you disagreed with your team | A conflict with a teammate
It was a chemical engineering project, and my group didn't trust me at first.
I was in charge of the milk for making cheese.
They wanted UHT whole milk.
But I had read that the heat changes the proteins, so it doesn't curdle well.
They didn't believe me, so instead of arguing, I bought both.
After three hours, theirs didn't curdle, and mine worked.
So we didn't lose a lab day.
What I learned is to bring evidence and a plan B, and next time to share the source first.

## kubernetes_openshift - What is your experience with Kubernetes | Have you worked with OpenShift
At Amadeus, I troubleshoot microservices on Linux and Kubernetes, including OpenShift.
That means recycling pods, and checking health and performance in Grafana and Prometheus.
When it needs engineering, I escalate with written evidence, and I document runbooks.
On hardening, I know the main ideas: RBAC, resource limits and restart behaviour.
I also see how bad configurations show up as incidents.
But I haven't done hardening work myself yet, and that's where I want to grow.

## cloud_security_aws - What is your experience with AWS and cloud security
I did a ten-month internship at AWS.
I also have three certifications: Solutions Architect Associate, ML Engineer Associate and GenAI Developer Professional.
At AWS, I built only with Amazon's approved services.
For my multi-agent prototype, I used the AWS CDK in Python.
On cloud security, I know the main ideas.
For example, least privilege in IAM, using roles instead of wildcards, and no public S3 buckets.
But I haven't done that work hands-on yet.
What I have done is a read-only script at Amadeus that uses only my own access.
And in a freelance payments flow, I kept the credentials in Azure Key Vault.

## secrets_and_least_privilege - How do you handle secrets and least privilege
In a freelance project, I built a payments flow with Power Automate and Power Apps.
It used a Colombian bank's REST API and handled more than 2,000 payments a week.
I kept the credentials in Azure Key Vault, not in the code.
I also built dashboards for successful and reversed payments.
At Amadeus, my script is read-only and uses only my own access.
They're the same ideas, just at a small scale.

## key_vault_details - How was the secret retrieved at runtime from Key Vault | What identity or authentication method was used | How was access to the Key Vault controlled | Did you rotate or monitor the credentials | Which vault solution did you use
It was Azure Key Vault, and I built that flow end to end.
The vault didn't exist before, so I created it for this flow.
It held the bank API credential and the API key.
At runtime, the flow read them from the vault and made one request to the bank's API.
The bank returned a temporary token that expired after about three hours.
The payment calls used that token, not the stored credentials.
Access to the vault was meant for that flow only.
I didn't set up rotation or monitoring on the vault itself.
But we did keep a log of every change against the payments in our database.
For example, paid, not paid, or a phone number changed.
Today, I'd add RBAC for the flow's identity, plus expiry dates and rotation on the secrets.
And I'd send the vault's access logs to alerts.

## python_and_scripting - What is your experience with Python and scripting | Have you done shell scripting | Do you know PowerShell or bash
Python is my main language for coding.
I built my investigation script in Python, and also an AWS multi-agent prototype with the CDK.
My thesis pipeline was in Python too.
It used more than 20,000 protein sequences, ESM-2 embeddings and a PyTorch LSTM, served with Docker.
At Amadeus, I use the Linux command line every day for troubleshooting.
For example, I pipe kubectl into grep to find the pods I need.
I also wrote a small PowerShell script that refreshes the incident queue page for me.
And at AWS, I wrote a small script that collected public event information.
(Details if asked: the prototype used Bedrock AgentCore, Strands and a Knowledge Base with
RAG; the thesis sequences came from UniProt.)

## monitoring_and_detection - What is your experience with monitoring and detection | Have you worked in a SOC
At Amadeus, I use Grafana and Prometheus in a 24/7 follow-the-sun team.
The team manages its dashboards and alerts as code.
I haven't worked in a SOC, and I haven't used Zeek, Kafka or MISP directly.
But I know what each one does.
Zeek watches network traffic, and Kafka carries the logs into OpenSearch.
And MISP is the threat intelligence: the list of known bad IPs and domains.

## detection_pipeline - How would you build or wire the detection pipeline | How would you correlate network and authentication data | How would you use Zeek, Kafka, OpenSearch and MISP together
I'd send Zeek's network data and the authentication logs into Kafka.
From Kafka, they'd go into OpenSearch.
There, I'd connect the events by user and by time.
Then I'd check them against MISP, to see if an IP or domain is already known as bad.
The idea is that two weak signals together are stronger than one alone.
For example, a strange login and strange traffic from the same user at the same time.
To be clear, I haven't run Zeek or MISP in production yet.
This is how I'd build it, based on what I've read and how I work with logs today.

## misp_feed_down - What happens if MISP is down | What if the threat intel feed fails | What if the feed stops updating
The logs keep flowing and being stored, because Kafka holds them.
They only miss the threat tags for a while.
When MISP is back, they get them.
The worse case is a feed that stops updating without anyone noticing.
Everything looks fine, but new attackers aren't on the list, so you miss them.
So I'd also alert when the feed hasn't updated for too long.

## log_retention - How long would you keep the logs | What retention would you set | If you ingest three terabytes a day how long do you keep it
I'd keep the recent data in OpenSearch for about two or three weeks.
That's what you search during an investigation.
For older data, I'd move it to cheaper storage and keep it longer.
That's for going back later, when new threat information comes in.
I'd also set the time per log source, because not all logs have the same value.
(General knowledge, not experience: never say I've set retention before.)

## explain_2fa_simple - Explain two factor authentication to a physicist who hates it | Explain 2FA in simple words | How would you explain 2FA simply | Why should I use two factor authentication | Convince someone to use MFA
(General knowledge, not Maria's experience. 2FA did NOT stop the "One click to many" attack: the attacker got around it.)
Your password is something you know, and it can be stolen without you noticing.
Two-factor adds something you have, like your phone.
So a stolen password alone isn't enough.
Think of it like two independent measurements: when both agree, you trust the result.
Yes, it's an extra step, and it isn't perfect.
In July, your team wrote about attackers who tricked people into approving a login for them.
But it stops most attacks with a stolen password, and that's the most common way in.

## authn_vs_authz - What is the difference between authentication and authorization
Authentication proves who you are, with passwords, MFA, certificates or SSO.
Authorization decides what you can do, with roles, policies or scopes.
For example, my hackathon tunnel was about authentication.
IAM policies and RBAC are about authorization.
A common mistake is to mix the two and give very broad permissions.

## tls_and_pki - How does TLS work | Explain PKI and certificates
TLS protects the connection with a handshake.
In that handshake, the server proves who it is with an X.509 certificate.
That certificate is signed by a trusted CA, and that's the PKI.
The key points are checking the certificate, its expiry date, and protecting the keys.
PKI is only as strong as how you manage those keys.

## learning_security_gaps - Do you have pentesting or CTF experience | What are your security gaps
I don't have a formal pentesting or CTF record yet.
But the tunnel, the read-only script and the Key Vault work use the same ideas.
To close that gap, I'd practice on CTFs and study Zeek, Kafka and MISP.
I'd also go deep on Kubernetes hardening and AWS IAM.

## hardened_in_production - Give me a concrete example of something you've hardened in production | What have you hardened in production
I haven't hardened anything in production yet.
The closest I've done is on access and secrets.
In a freelance payments flow, I kept the credentials in Azure Key Vault, not in the code.
At Amadeus, my investigation script is read-only and uses only my own access.
Real hardening, like RBAC and network policies, is what I want to build here.

## cert_lifecycle_live - Have you ever rotated or revoked a certificate in a live environment | Have you ever had to rotate a certificate or revoke one in a live environment
Not in a live environment yet.
But I know the steps.
First, you revoke it, and you publish that through CRL or OCSP.
Then you issue a new one with a new key pair, never the old one.
I'd like to learn that here with the team's own tools.

## typical_day - Describe a typical day at Amadeus | What does a normal day look like | Walk me through a normal day at work | What do you do day to day
(Maria's own account, 2026-10-13. Never add overnight Grafana checks, Kubernetes "acting up" or timezone talk.)
It starts at 8:30 with a handover call from the team in Germany.
They're finishing their shift, so they pass us what's still open.
Then I work the incident queue.
For each alert, I first check the graph that triggered it.
If it has recovered, I update the ticket and keep watching it.
If it's still ongoing, I check if it's a pod, a node or a recent change, like a traffic switch.
For that I use Grafana, our logging tool ALF and Splunk.
If it's not on our side, I hand it to the team that owns it, with the evidence I found.

## on_call_night_shifts - Are you okay with on-call and night shifts
Yes.
At Amadeus, I'm already in a 24/7 follow-the-sun team.
Some weeks, that includes weekend shifts.
That's part of running real systems, so I'm open to the on-call rota here.

## large_international_teams - Have you worked in large international teams
Yes.
At AWS, I collected feedback from teams across LATAM, including Brazil.
At Amadeus, I work in English every day.
That means incident notes, escalations, runbooks, incident calls and shift handovers.
So I'm used to large teams spread across countries and languages.

## non_native_communication - How do you handle communication when team members are not native English speakers | How do you communicate across languages
I'm not a native English speaker either, so I know both sides.
I speak more slowly, and I put things in writing.
At AWS, I worked closely with a colleague from Brazil.
She didn't speak much Spanish, and I didn't speak Portuguese.
English wasn't easy for her either.
So after every meeting, we wrote down what we had agreed.
That way, we were both sure we were on the same page.

## where_do_you_see_yourself - Where do you see yourself in five years
I see myself as a security engineer.
I'd like to work on detection, cloud security and pentesting.
And ideally, I'd stay in a scientific environment where the work has real impact.

## salary_and_availability - When could you start | Are you willing to relocate to Geneva
I could start on the 1st of November 2026, with two weeks' notice.
I'm Spanish, so I'm an EU citizen and I don't need a visa.
And yes, I'd move to Geneva or the French border area for this role.
(Note: CERN start was 1 Oct 2026, so ask the real date.)
