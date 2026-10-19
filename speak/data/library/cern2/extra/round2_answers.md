# Round 2 answers - CERN panel (2026-10-19). Technical answers are "how I would", never claimed experience.

## why_hire_limited_security - You have limited security experience, why should we hire you | Why should we hire you | Why should we hire you with limited security experience | Why should we pick you | Why should we choose you | What makes you a good fit for this role | Why should we choose you over the other candidates | Why you and not another candidate | Why should we pick you
(No weaknesses in this answer: they asked for reasons. Hackathon only in one line if it was not told yet.)
Three reasons.
First, I already investigate real production systems every day, I build a timeline from the logs and escalate with evidence.
Second, I learn fast, and I've proven I can reach the level of people I consider really strong, like when we won the AWS hackathon.
Third, the mission, science and computing together is exactly what I studied for, and protecting it is what I want to do.

## operations_to_security - Why do you want to move from operations into security | Why move from operations to security | Why leave operations for security
Because security is the part of operations I find most interesting.
In operations, something fails, and I find out why.
In security, someone is actively trying to hide, so the investigation is harder.
I already have the habits: logs, timelines, evidence.
Now I want to use them where they matter most.

## puppet_since_last_time - Last time you hadn't used Puppet, have you looked at it | Have you looked at Puppet since | What do you know about Puppet now | Puppet Ansible Chef difference | What is the difference between Puppet and Ansible
(Maria confirmed on 2026-10-16 that she reviewed Puppet. She has NOT written Puppet code or used it in production. Never claim she did.)
Yes, I went back over it after our first interview, but I haven't used it in production yet.
Puppet and Chef describe in code how a machine should be, and an agent on each node keeps it that way.
The Puppet agent asks the server for its catalog, compares it with the machine, and fixes what differs.
Ansible has no agent. It pushes the changes over SSH, usually when someone runs a playbook.
For security, that means the same baseline on every node, reviewed changes in git, and a report of every correction.

## puppet_manual_change - What happens if someone changes a managed service by hand | Someone changes a managed setting by hand | What if someone edits a file that Puppet manages | Does Puppet correct manual changes
On the next agent run, Puppet puts it back to the state declared in the code.
By default the agent runs about every thirty minutes, so the change can live until then.
It only corrects what the code manages. A setting that isn't declared stays as it was.
And the run report records the correction, so a change nobody expected becomes a signal to look at.
If the change is really needed, it has to go through the Puppet code, reviewed in git.

## puppet_when_corrected - When exactly does Puppet correct it | Is it corrected immediately | How fast does Puppet fix it
Not immediately. It is corrected on the next agent run.
By default that is about every thirty minutes, and an admin can also trigger a run by hand.
Between runs, the manual change is live, so Puppet reduces drift but it is not a real-time control.

## puppet_noop - How would you test a Puppet change without applying it | What is noop mode | How do you try a change safely
I would run the agent in noop mode first.
It compares the machine with the catalog and reports what it would change, without changing anything.
Then I would apply it on a test node or a small group, and only then to everything.

## puppet_compromised_node - How would you use Puppet to spot a compromised node | Can Puppet help detect an attacker | Puppet and security monitoring | How do you know if a node has silently stopped applying the security configuration | How do you notice a node that stopped applying its configuration
It can give a useful signal, but it is not a detection tool by itself.
If the reports show Puppet correcting the same file or service again and again, someone or something keeps changing it.
And a node that stops reporting is also worth checking.
I've been reading about the Puppet run reports since our first interview, and this is where they help most.
But an attacker with root can change things Puppet doesn't manage, or stop the agent, so I would combine it with host and network logs.

## container_compromise_trace - A pod looks compromised, what do you do | Last time your answer on containers was only about the network, what would you do differently now | Your container answer was only network, what would you add | How do you trace what happened inside the container | How would you investigate a compromised container | A pod is compromised, how do you trace what happened inside it | For that container traceability gap what would you collect beyond network logs | What would you log inside a container
(From FRASES_LO_QUE_ESTUDIE.md, 2026-10-17: Maria asked to use it as something she read since round 1.) Facts from Liviu's HTCondor workshop slides (30/09/2026). Collection must already be enabled to reconstruct past activity.
Last time I only covered the network side, so I looked into runtime monitoring.
A tool like Falco watches system calls through eBPF.
So you see which process started, from which parent, which files changed and which connections opened.
And in Liviu's HTCondor workshop slides, I saw you log uid, euid, pid, ppid, the binary, the arguments and the tty for every command.
That's exactly what lets you rebuild the chain from the web server process to the shell.
And it works even after the container is gone, because the events were already sent centrally.

## falco_vs_zeek - Falco vs Zeek | What is the difference between Falco and Zeek | How do Falco and Zeek compare
Falco looks inside the host, at system calls.
Zeek looks at the network traffic.
So Falco tells you what a process did, and Zeek tells you who it talked to.
They complement each other.

## m365_review_method - How would you review hundreds of Microsoft 365 settings | How would you review M365 or Google Workspace settings | How would you approach the M365 review | How would you approach the Microsoft 365 review | Where would you start with the Microsoft 365 review | How do you decide which M365 settings to change
(From FRASES_LO_QUE_ESTUDIE.md, 2026-10-17: Maria asked to use it as something she read since round 1.) Never assume CERN uses Conditional Access: say "if you use Conditional Access".
I read your Bulletin article, One click to many, about the device code phishing in July.
Then I read Microsoft's documentation on blocking authentication flows.
I also found CISA's SCuBA project, secure configuration baselines for Microsoft 365 and Google Workspace.
It comes with a tool, ScubaGear, that checks a tenant against them.
I would use a baseline like that as the starting list.
Then, for each setting, the impact analysis.
Report-only mode where it exists, the sign-in logs to see who would be affected, a pilot group, and a staged rollout.

## collateral_damage - How do you assess collateral damage before enabling a setting | How do you know what a setting will break | How do you evaluate the impact on users before deploying a setting
First, I would look at the logs to see who actually uses the feature today.
Then I would turn the setting on in report-only mode, to see what it would block without blocking it.
After that, a small pilot group, and only then a rollout in phases.
And I would always keep a way to roll back, and tell people before, not after.

## m365_motivation - Reviewing M365 settings one by one is not glamorous, how do you stay motivated | How do you stay motivated with repetitive review work | That's not glamorous, how do you stay motivated
For me, it's like an investigation.
Each setting is a question: who uses this, and what could go wrong?
And every setting I close reduces a real risk, like the device code phishing your team wrote about in July.
If I document it well, it also helps the next person for years.

## explain_to_physicist - How do you explain to a physicist why we are taking something away | A physicist says it slows them down | They say the control slows them down, what do you do | How do you explain a security change to a user | How do you convince a scientist to accept a security restriction
First I would ask what exactly slows them down, because sometimes it's one setting we can adjust.
Then I would explain why: the concrete risk, with a real example, not a policy.
Then I would offer an alternative, so they can still do their work.
I would give them a clear date, and tell them who to contact if something breaks.
If they really need an exception, it's small, with an owner and an expiry date.
People accept a change much better when they understand it and still have a way to work.

## security_exception - Exceptions kill cyber security, when would you still grant one | When would you grant a security exception | A physicist needs 2FA off or a port open for an experiment | A research group refuses a security control | A group rejects a control because it breaks their work | Who accepts the risk of an exception
(Shared responsibility: from Liviu's HTCondor slides, which Maria read. Risk is accepted by the service owner together with the security team, never by Maria or the scientists alone.)
Only as a last resort.
First, I would understand the real need, because often there's an alternative, like network limits, strong authentication or more monitoring.
Liviu's HTCondor slides describe security as a shared responsibility between service managers and the security team, so I wouldn't just impose it.
If there really is no alternative, the exception should be as small as possible, with an owner and an expiry date.
It's signed off by the service owner together with your team, not by me or the scientists alone.
And while it exists, I would add more monitoring on it.

## bank_vs_cern - What is the difference between security in a bank and at CERN | How is security at CERN different from a company
A bank can control almost everything: the devices, the users, the software.
CERN can't, because of academic freedom.
There are about two hundred thousand personal devices and thousands of institutes.
So you can't install software everywhere. You watch the network, and you build defense in depth.

## prioritise_urgent - How do you prioritise when everything is urgent | How do you prioritise | How do you decide what to fix first
I look at impact, how likely it is, and how exposed it is.
Anything facing the internet goes first.
At Amadeus I do this every day in a 24/7 team: impact and urgency first, and I escalate with evidence.

## raise_team_misconfiguration - If you found that one of our own team's services was misconfigured, how would you raise it | How would you raise a problem with a colleague's service
Privately first, with the person who owns it.
I would bring the evidence and a proposal, not just the problem.
And without blaming anyone: the goal is to fix it, not to find who did it.

## biggest_risk_cern - What is the biggest security risk to CERN right now | What is the biggest risk for CERN in your opinion
In my opinion, stolen identities and credentials.
Your team's July article, "One click to many", showed how one click on a device code phish gives an attacker a valid token.
And AI makes phishing much more convincing.
After that, I would say suppliers and the software supply chain.

## cut_attack_surface - If you had to cut the attack surface of CERN by 20 percent in one year, where would you start | How would you reduce the attack surface
I would start with an inventory of everything exposed to the internet.
Then close what nobody uses anymore.
And put the rest behind the SSO, with two-factor authentication.

## measure_security_team - How would you measure if the security team is doing a good job | How do you measure security
I would measure how long it takes to detect and to contain an incident.
How many services follow the security baseline.
How many users have two-factor authentication.
And how many critical patches are applied within the deadline.

## first_week_no_task - What would you do in your first week if nobody gave you a task | Your first week with no task
I would learn the environment first.
Read the team's documentation, sit with the SOC to see a normal day, and look at the open tasks.
Then I would ask which one I could take, starting with something small, so I learn the tools with a real case.

## learn_fast_example - How do you learn a completely new technology fast, give an example | How do you learn new technology fast | Tell me about a time you had to learn something new quickly | A time you had to learn something new very quickly | Something you learned quickly
(Only facts in the notes: the hackathon, and five AWS certifications (Solutions Architect Associate, Machine Learning Engineer Associate, Generative AI Developer Professional, Cloud Practitioner and AI Practitioner). No dates, study method or "while working full time" for the certifications: never invent how or when she studied.)
I learn by doing, with a real goal.
The situation was the AWS LATAM New Hire Jam in 2025, with 14 challenges, and my team was one person short.
My job was one of the hardest challenges, connecting two VMs with a secure, authenticated tunnel, and I had to learn it on the spot.
So what I did was, when the deployment kept failing, read the whole specification again instead of guessing.
I found a key requirement that showed my environment was wrong from the start, and I redeployed once, clean.
The result was that no other team completed that challenge, and we won.
And a recent example: Puppet was my weak spot in our first interview, so since then I've been reading about it.

## other_offers_start - Do you have other interviews or offers | When could you start | What is your notice period
(Notice period at Amadeus: NOT in the notes; never invent a date.)
Yes, I'm in other processes, and I would be very happy to join CERN.
For the start date, I would give notice at Amadeus and take about two weeks to settle in, and I can agree the exact date with HR.

## what_is_soc - What's a SOC and what does a SOC analyst do all day | What is a SOC
A SOC is the security operations center: the team that watches for attacks and responds to them.
An analyst reviews alerts, decides which ones are real, and investigates them.
Then they contain the threat, or escalate it, and improve the detection rules so there's less noise next time.

## what_is_zeek - What is Zeek | Zeek vs Suricata | Zeek vs Snort | How is Zeek different from Suricata
Zeek is a network monitor that turns traffic into structured logs: connections, DNS, HTTP and TLS.
Suricata and Snort are mainly signature-based: a rule matches, and they fire an alert.
So Zeek gives you rich logs to investigate, and Suricata gives you alerts on known patterns.
Zeek also has an intelligence framework, where you can load indicators from MISP.

## ioc_examples - What's an IoC | Give three examples of IoCs | What is an indicator of compromise | What's the difference between an IoC and a detection rule | IoC versus rule
An indicator of compromise is a single piece of evidence: an IP, a domain, or the hash of a file.
A detection rule is the logic that searches the data and raises an alert.
IoCs change fast, so behaviour based rules last longer.
At CERN, MISP brings in the shared indicators, as in Liviu's Zeek Workshop talk.

## why_kafka - Why put Kafka between sensors and storage | Why Kafka
Kafka decouples the sensors from the storage.
If there's a peak of traffic, or the storage is slow, Kafka absorbs it and nothing is lost.
And several consumers can read the same data, like OpenSearch for search and Spark for analytics.

## alert_reduction - We see billions of connections and tens of thousands of raw alerts, how do you get to a few dozen | How do you reduce alert noise | How do you get from thousands of alerts to a few dozen
First, remove the false positives I know about.
Then aggregate: many alerts about the same host become one.
Then correlate with other sources, and enrich with context, like who owns the machine.
And I would review each tuning rule regularly, so I don't hide a real attack.

## encrypted_traffic - Traffic is encrypted and we don't decrypt it, what can you still detect | What can you detect in encrypted traffic
A lot, from the metadata.
Who talks to whom, how much, and when.
DNS queries, the server name in the TLS handshake, the certificates, and TLS fingerprints like JA3.
And patterns like beaconing: regular connections to the same destination.

## command_logging_fields - Which fields would you log for every command executed on a host | What fields would you log for every command
I would record the user and effective user IDs, process and parent process IDs, executable, arguments, terminal and timestamp.
I would add the host, container ID, pod UID, namespace and image identity when available.
User IDs show the identity and effective privileges, while parent links help reconstruct the process chain.
I would protect the logs and redact secrets in arguments, because command lines can contain credentials.
(These are desired telemetry fields, not a claim that every Falco event contains them. Prefer host process identifiers and retain namespace/container context.)

## container_audit_limits - Can Kubernetes audit logs show every command typed in an interactive shell | Can audit logs replace runtime monitoring | What do Kubernetes audit logs tell you about exec
No. Kubernetes audit logs record API requests according to the configured audit policy.
They can show an exec request and the identity that made it.
They do not record every command subsequently typed inside an interactive shell.
For that activity I need runtime process telemetry, and even process events do not capture every shell builtin.

## container_process_identity - How do you avoid mixing up reused process IDs | Is the PID enough to reconstruct a process tree | What if two containers have the same PID
I would not use the process ID alone, because IDs can be reused or repeat across namespaces.
I would combine it with the host, container identity and process start time.
Then I would link parent and child events within that same context and time range.
If events are missing, I would mark the gap rather than invent the chain.

## container_missing_history - The pod is already gone and Falco was not running can you reconstruct everything | Can you recover commands after the container is deleted | What if runtime monitoring was not enabled
No. Starting monitoring now cannot recover process events that were never collected.
I would look for retained application logs, API audit logs, node evidence and network records.
I would build the timeline those sources support and state where evidence is missing.
For future incidents, I would collect runtime events centrally and monitor collection failures.

## container_isolation_limits - Is adding a deny egress NetworkPolicy enough to isolate the compromised pod | Does a deny policy override existing allow policies
No. Network policies are additive, so another policy may still allow traffic.
I would check both ingress and egress, plugin enforcement and existing connections.
I would verify containment and preserve evidence, escalating to node or infrastructure controls if needed.

## kernel_modules - How do you see which kernel modules are loaded and why does security care | Which kernel modules are loaded
With lsmod, and modinfo for the details.
Security cares because a malicious kernel module is a rootkit.
It runs with full privileges and can hide processes, files and connections.

## kernel_allowlist - Blocklist vs allowlist of kernel modules, pros and cons | Allowlist or blocklist of kernel modules | How would you make sure a vulnerable module stays blocked on every node
An allowlist is safer, because only known modules can load.
But it can break rare hardware or drivers.
So I would roll it out carefully: first only report, collect data, and only then block.
A blocklist is easier, but it only stops what you already know is bad.
To apply it on every node and keep it there, I would declare it in Puppet, by host group.
Puppet was my weak spot last time, so I've been reading about it, and this is exactly where it fits.

## what_is_ebpf - What is eBPF and why is it useful for security | What is eBPF
eBPF lets you run small, verified programs inside the kernel, without writing a kernel module.
For security, you can watch system calls, network activity and process executions, with very low cost.
Tools like Falco and Tetragon are built on it.

## priv_esc_cve_response - A new Linux local privilege escalation CVE comes out, walk me through the response | How do you respond to a Linux privilege escalation | A new Linux local privilege escalation comes out, what do you do | New kernel vulnerability, what do you do
(From FRASES_LO_QUE_ESTUDIE.md, 2026-10-17: Maria asked to use it as something she read since round 1.) Facts from Liviu's HTCondor workshop slides (30/09/2026).
In Liviu's slides from September, there's a five-step process I found useful.
Identify, determine exposure, mitigate, remediate, verify.
Mitigation comes first, like blocking the vulnerable kernel module, because the patch and the reboot take longer.
To block it on every node and keep it blocked, I would declare it in Puppet, which I've been reading about.
I also saw you're moving from a blocklist to an allowlist of kernel modules.
How is the delayed blocking going?

## uid_vs_euid - What's the difference between uid and euid | uid vs euid | Real UID versus effective UID | A process runs as a regular user but its effective UID is zero | How can a process end up with euid zero | Which commands to check a uid euid privilege escalation
(Liviu's HTCondor slides, which Maria read: CERN's traceability logs uid and euid, gid and egid, pid and ppid, binary, arguments and tty for every command. Cite it here, it is the clearest fit.)
The real uid is who started the process.
The effective uid is the permissions it actually uses.
The normal reason is a setuid binary, like passwd or sudo, which runs with the owner's permissions.
That's exactly why I liked that your SOC logs both uid and euid for every command, as I saw in Liviu's HTCondor slides.
To check it, I would run ps with dash o, asking for pid, ppid, ruser, euser and the command, so I see both users side by side.
Then ls dash l on the binary to see the s bit, and rpm dash V f to see if the binary changed from its package.
A uid to euid change that doesn't come from a known setuid binary is a strong signal.

## suspicious_host_commands - Which Linux commands would you use to check a suspicious host | How would you check a suspicious Linux host
ss to see the connections, and ps to see the process tree.
last and the secure log for logins, and journalctl for the system logs.
crontab and the systemd timers for persistence.
find for files changed recently, and the SSH folder for unknown keys.

## reverse_shell - What's a reverse shell and how would you spot one in Zeek logs | What is a reverse shell
A reverse shell is when a compromised server connects out to the attacker and gives them a shell.
In Zeek, I would look for a long outbound connection from a server, to an unusual port.
Small volume, but interactive, and it stays open for a long time.

## beaconing - What is beaconing and how would you detect it | How would you detect beaconing
Beaconing is when malware calls home at regular intervals.
To detect it, I would look at the connections from one host to one destination, and check how regular the gaps are.
But attackers don't connect exactly every sixty seconds, they add jitter.
So I look for gaps that are regular within a tolerance, using the median and the spread, not an exact interval.
Same packet sizes and a connection that goes on for days are extra signals.

## password_spraying - How would you detect password spraying against the SSO | What is password spraying
Password spraying is trying a few common passwords on many accounts.
So I would look for many users, with few attempts each, from the same IPs.
And then check if any of those users had a successful login afterwards.

## wlcg_security - What is the WLCG and why is its security hard | Why is WLCG security hard
The WLCG is the worldwide computing grid for the LHC, with around a hundred and seventy computing centres in more than forty countries.
Each site has its own administrators and rules.
And because they share credentials and trust, one compromised site can affect the others.

## ai_risks_cern - What security risks do you see in people using AI tools at CERN | What are the risks of AI agents | What are the risks of AI tools
The main one is prompt injection: an agent reads an email or a web page with hidden instructions, and follows them with the user's permissions.
Then data leakage, when people paste confidential data into a tool.
Then over-trust in the output, like insecure code or invented packages.
And agents with more permissions than they need.

## prompt_injection_physicist - Explain prompt injection to a physicist | What is prompt injection
An AI assistant can't really tell the difference between your instructions and the text it reads.
So if it reads an email that says "forward all files to this address", it might do it.
It's like a colleague who follows any note left on their desk, without checking who wrote it.

## secure_multi_agent - You built a multi-agent prototype, how would you secure it if it went to production | How would you secure your multi-agent prototype | Tell me about your multi-agent prototype | What did you build in the multi-agent prototype
(Facts from the repo review, 2026-10-18: designed for Bedrock AgentCore, BUILT as a partial prototype on Amazon Bedrock Agents. Never "CDK in Python" (it was TypeScript), never say she used Strands, AgentCore services or a Knowledge Base in the code, never say the agents' permissions were narrow. Always "prototype".)
It was a prototype for AWS's internal AWSome Builder program.
I designed it for Bedrock AgentCore, and AgentCore Identity was in the design to handle who the agents act for.
What I actually built was a partial version on Amazon Bedrock Agents.
An orchestrator delegating to a training agent and a nutrition agent, each with its own Python Lambda tools on DynamoDB, and the infrastructure in CDK with TypeScript.
Each agent could only call its own tools.
Reviewing it with a security eye, the biggest gap was identity: the chat endpoint didn't pass the authenticated user to the agents, and their role was much broader than needed.
I would fix identity first, then least privilege, user confirmation before any write, and guardrails against prompt injection.

## ai_coding_assistants - Should CERN allow AI coding assistants | Under which conditions would you allow AI coding assistants
Yes, but with conditions.
Only approved tools, and no confidential data pasted in.
The generated code should be reviewed like code from a stranger.
And the dependencies it suggests should be scanned, because it can invent packages.

## agent_mailbox - An AI agent has access to a user's mailbox, what could go wrong
An email with hidden instructions could make the agent forward data, or send phishing to colleagues.
It's like the device code phishing your team wrote about in July, but automatic, and from a trusted account.
So I would limit what it can send, and require a human to approve it.

## llm_crawlers - LLM crawlers are hammering our websites, what can we do | How do you stop AI crawlers
Rate limiting and caching first, so the servers don't fall over.
robots.txt helps, but crawlers can ignore it.
Then detect them by behaviour, add challenges like proof of work, or block known ranges.
And always check that we don't block real users.

## rootkit - What is a rootkit | User mode vs kernel mode rootkit
A rootkit is malware that hides itself and keeps access.
A user-mode rootkit replaces programs or libraries, like ps or ls.
A kernel-mode rootkit runs inside the kernel, so it can hide almost anything, and it's much harder to find.

## trust_compromised_machine - Can you trust a compromised machine to investigate itself | Can you trust a compromised host
Not fully.
A rootkit can hide processes, files and connections from tools on that same machine.
So I would also look from outside: the network logs, logs already shipped centrally, or the disk analysed from another system.
And usually you rebuild the machine instead of cleaning it.

## forensic_order - What do you collect first in a forensic investigation, and in which order | How do you preserve evidence
From the most volatile to the least.
First memory, then connections and processes, then the disk and the logs.
To preserve evidence, I would work on copies, take hashes, never touch the original, and write notes with the time of each step.

## stolen_ssh_key - What would you look for in auth logs after a stolen SSH key
Logins from new IPs, or at unusual hours.
Jumps from that host to other hosts, which would be lateral movement.
And the same key being used on several machines.

## tier2_cryptomining - A Tier-2 site in the WLCG is mining cryptocurrency, your steps | One of the WLCG sites reports ransomware on their worker nodes, what do you do | A WLCG site has ransomware | A WLCG site is compromised, what do you do | Ransomware at a WLCG site, what do you do | A grid site is hit by ransomware | Ransomware hits a Tier-2 WLCG site, what do you do in the first hour to protect CERN and preserve evidence
(A WLCG site belongs to another institute: CERN never isolates it, it restricts traffic on ITS OWN side. When asked to protect CERN AND preserve evidence, protect CERN comes FIRST. Facts from Luna's HEPiX slides, spring 2025. Pau leads EGI's incident response task force.)
First, protect CERN.
I would restrict traffic from that site on our side, because we can't trust its servers now.
And I would revoke any credentials or grid tokens used there, then search our logs for their use at CERN.
That's how an attack jumps from one site to another.
The site isn't ours, so I coordinate with their security team, following the EGI incident procedure.
I would share the indicators through MISP with the other sites.
And I would help them preserve evidence: memory first, then disk and logs, working on hashed copies.
In the Tier-2 case from your HEPiX slides, the attacker came in through a BMC exposed with default credentials, so I would also ask how they got in.

## responsible_disclosure - What is responsible vulnerability disclosure
You tell the owner privately first, and give them time to patch.
Only after that, it's published.
And you never exploit more than you need to prove it.

## cve_cvss - What is a CVE and a CVSS score | Why isn't CVSS enough to prioritise
A CVE is the public ID of a known vulnerability, and CVSS is a score of how severe it is.
But CVSS alone isn't enough, because it doesn't know your exposure, or if the vulnerability is being exploited right now.
So I would also check lists like CISA's known exploited vulnerabilities, and EPSS.

## negative_time_to_exploit - Time to exploit is now negative with AI, what does that change | Exploits come out before the patch
It means we can't wait for the patch.
We need fast mitigations, like blocking or isolating.
An inventory that is always up to date, so we know where we are exposed.
And less exposed surface in the first place.

## owasp_top10 - Name some of the OWASP Top 10 | What is the OWASP Top 10
Injection, like SQL injection.
Broken access control, cross-site scripting, and insecure configuration.
Vulnerable or outdated components, server-side request forgery, and authentication failures.

## sql_injection - Explain SQL injection and how to prevent it | What is SQL injection
SQL injection is when user input ends up inside a database query, and changes what the query does.
To prevent it, I would use parameterized queries, or an ORM like Django's.
And the database account should have the minimum privileges.

## xss - Explain XSS | Stored vs reflected XSS | What is cross-site scripting
Cross-site scripting is when an attacker gets their script to run in another user's browser.
Stored means it's saved on the server, like in a comment. Reflected means it comes back from the request, like in a link.
To prevent it, escape the output, which Django does by default, and use a content security policy.

## ssrf - What is SSRF and why is it dangerous in a cloud | What is server-side request forgery | What is SSRF and why can it be dangerous in a cloud environment, give me one example
(Public, well-known case: Capital One, 2019.)
SSRF is when an attacker tricks a server into making requests for them.
In the cloud it's dangerous because the server can reach the metadata service, and get the credentials of its role.
A concrete example is Capital One in 2019.
The attacker used SSRF through a misconfigured web application firewall, reached the metadata service, took the role's credentials, and read data from S3.
To prevent it: IMDSv2, an allowlist of URLs the server may call, block internal ranges, and a role with least privilege.

## csrf - What is CSRF and how does Django protect against it | What is CSRF
CSRF is when another site makes your browser send a request to a site where you're logged in.
Django protects against it with a CSRF token in each form, and SameSite cookies help too.

## http_vs_https - HTTP vs HTTPS | What is the difference between HTTP and HTTPS
HTTPS is HTTP over TLS.
TLS gives encryption, integrity, and authentication of the server with a certificate.

## url_in_browser - What happens when you type a URL in the browser
First a DNS lookup to find the IP.
Then a TCP connection, and the TLS handshake for HTTPS.
Then the browser sends the HTTP request, gets the response, and renders the page.

## find_web_servers - How would you find all web servers on CERN's network and what they run | How would you find exposed or insecure services
I would scan the network regularly, and fingerprint what's running and its version, from banners and headers.
Then store it in a searchable index.
When a new CVE comes out, I query the index, find who's affected, and notify the owners.

## cve_in_one_hour - A new CVE in a web framework is published, how do you find every affected server in an hour
I would query the service index by product and version.
Then prioritise the ones exposed to the internet.
Notify the owners, and mitigate with a WAF rule while they patch.

## opensearch_vs_postgres - Why OpenSearch for this and not just PostgreSQL | What is Redis used for
OpenSearch is built for full-text search and fast aggregations over millions of documents.
PostgreSQL is better for relational data and state.
And Redis is usually the cache, or the task queue, for example with Celery.

## scan_responsibly - How do you scan responsibly without breaking fragile devices
Limit the speed, and exclude control systems and other fragile devices.
Agree on time windows, and tell the owners first.
And start with a light scan, before anything more intrusive.

## insecure_iot - What is an insecure IoT device and why does CERN care
Cameras, printers or sensors that still have default passwords or old firmware.
They are easy to find and easy to take over.
Once an attacker controls one, it's a way into the network.
So CERN needs to find them and get them fixed or isolated.

## store_passwords - How do you store passwords in a web app
With a slow hash and a salt, like bcrypt or argon2.
Never with reversible encryption.

## security_code_review - What would you check in a code review for security
Inputs that aren't validated, and queries built with strings.
Secrets in the code, permissions, and dependencies.
And logs that contain sensitive data.

## vm_vs_container - What's the difference between a VM and a container | VM vs container
A container shares the kernel of the host. A VM has its own kernel.
So a VM gives stronger isolation, and a container is lighter and faster to start.

## harden_kubernetes - How would you harden a Kubernetes cluster | How would you harden a Kubernetes cluster without blocking research work | How would you harden OpenShift | How would you harden a Kubernetes or OpenShift cluster | How would you secure a Kubernetes cluster | What would you put in a Pod Security standard
(From FRASES_LO_QUE_ESTUDIE.md, 2026-10-17: Maria asked to use it as something she read since round 1.)
I went through the Kubernetes Pod Security Standards.
There are three levels, Privileged, Baseline and Restricted, applied per namespace with labels.
Restricted means no root, no privileged containers, dropped capabilities, no host paths and a seccomp profile.
OpenShift's restricted SCC does something similar by default.
To avoid blocking research, I would apply them first in warn and audit mode, so we see what would break without breaking anything, and only then enforce.
Together with RBAC least privilege and default-deny network policies, that's where I would start.
I would rather use that standard than invent my own list.

## k8s_secrets - Why are Kubernetes Secrets not really secret
Because by default they're only base64-encoded in etcd, not encrypted.
So you encrypt etcd, limit who can read them with RBAC, or use a vault.

## network_policy_deny_egress - What is a NetworkPolicy | Write one that denies all egress from a namespace
A NetworkPolicy is a firewall rule for pods.
To deny all egress, I would select all pods with an empty pod selector, set the policy type to Egress, and add no egress rules.

## kubectl_exec_3am - Someone ran kubectl exec into a production pod at 3 am, what do you do
First, check the audit logs: who, from where, and what they ran.
Then ask that person or their team if it was planned.
If nobody can explain it, I treat it as an incident: isolate the pod, keep the evidence, and revoke the credentials.

## first_in_cloud_account - What would you secure first in a new cloud account | CERN is starting to use AWS GCP Azure and Oracle
The root or admin account with MFA and no access keys.
Single sign-on for people, and audit logs like CloudTrail turned on.
Billing alerts, storage private by default, and least privilege for everyone.

## public_bucket - How do you prevent a public S3 bucket or storage bucket
Turn on Block Public Access at the account level.
Add organization policies that forbid it.
And scan the configuration regularly.

## iac_security - Infrastructure as code, why is it good for security
Everything is reviewed in git, so you know who changed what and when.
It's repeatable, and you can scan it before it's deployed.

## ssh_key_auth - How does SSH key authentication work
The server has my public key.
When I connect, it sends a challenge, and I sign it with my private key.
The private key never leaves my machine.

## ssh_2fa - Why would we want 2FA on SSH, and what breaks if we enforce it
Because SSH keys get stolen.
What breaks is automation and service accounts.
So I would give those service accounts without interactive login, or use SSH certificates.

## mfa_old_portal - How would you add MFA to an old internal portal that doesn't support it
I would put it behind a proxy that uses the SSO with two-factor authentication.
And until then, more monitoring on it.

## rotate_secret_50 - How do you rotate a secret used by 50 services without downtime | A credential is shared by forty services, how do you rotate it | Rotate a leaked credential used by many services
Support two secrets at the same time.
Update the services one by one to the new one, and check in the logs who still uses the old one.
While I rotate, I watch the old credential: if something outside those services uses it, that's the attacker.
If a pod reads the secret from an environment variable, it does not pick up the new one alone, so I restart it with kubectl rollout restart.
Only at the end I revoke the old one.
But the real problem is many services sharing one credential.
Afterwards, I would give each service its own, so next time we revoke one, not forty.

## waf_limits - What is a WAF and what are its limits
A WAF is a web application firewall: it filters HTTP requests and blocks known attack patterns.
But attackers can bypass it, and it doesn't fix the bug underneath.
So it buys time, but the code still needs the fix.

## mistake_made - Tell me about a mistake you made | Tell me about a time you failed | A time you made a mistake | Tell me about a time you were wrong about a root cause | A time you were wrong about the cause
(First thesis. Never blame the director, never say his recommendations caused the failure. Details of the topic beyond proteins: not in the notes.)
The situation was my first thesis attempt, in chemical engineering, on proteins.
My job was to design the method and run the lab experiments.
So what I did was base the method on my director's recommendations, because I trusted them completely.
The result was that the thesis didn't pass.
What I own is that I relied on a single source, and I didn't ask anyone else to check the approach.
For my final thesis I worked with two directors, and it passed.
What I learned is to validate a cause or an approach with more than one source, and I do the same with incidents now.

## prototype_security_done - Did you do any of that in your prototype | Did you secure your prototype | Was your prototype secure
(From the repo review: each agent only had its own tools; the chat endpoint did not pass the user to the agents; the chat role was broad. Human approval and guardrails were not there.)
Partly.
Each agent could only call its own tools, so the training agent couldn't touch the meals.
But identity was the gap: the chat endpoint didn't pass the authenticated user to the agents, and the role was broader than needed.
And there was no human confirmation or guardrails yet, it was a prototype.
That's what I would fix first.

## role_excites_worries - What part of this role excites you most, and what part worries you | What excites you and what worries you about this role
What excites me most is the SOC work and the Microsoft 365 review, because both are real investigations with real impact.
What worries me a bit is Puppet and the scale, about fifteen thousand nodes.
I haven't used Puppet in production yet, but I didn't wait: since our first conversation I've been reading about it.
And my plan is to start with small changes on a test node, and learn from the team's existing code.

## deal_with_worry - And how would you deal with that part that worries you | How would you deal with that
Step by step, with a real case, and I already started.
Since our first conversation, I've been reading about Puppet, especially how declared configuration corrects drift.
Here, I would first read the team's existing Puppet code, to learn how things are done.
Then make small changes on a test node, with reviews from someone on the team.
That's how I learned Splunk and Grafana at Amadeus, by using them on real incidents.

## introduce_to_team - Could you introduce yourself to the rest of the team | Introduce yourself to the team | Most of them haven't met you | Introduce yourself to the team in two minutes | Could you introduce yourself to the team, most of them haven't met you | Introduce yourself to the panel
(Memorized intro, about 50 seconds: give it exactly as written, never shorten or rephrase it.)
I'm Maria. I have two degrees from Universidad de los Andes, in Systems and Computer Engineering and in Chemical Engineering.
After finishing my studies, I did a ten-month internship at AWS.
There, I built internal web tools used by more than 200 people.
I also hold five AWS certifications, including Solutions Architect Associate.
Since April, I've been a Junior Cloud Support Engineer at Amadeus, on a 24/7 team.
I investigate production incidents on Linux, Kubernetes and OpenShift.
I build the timeline from logs and metrics, find what changed, and escalate with evidence.
I also wrote my own Python script to speed up the first checks.
What matters for this role is that investigation habit.
Since our first conversation, I've been closing my gaps, especially Puppet and tracing activity inside containers.
Security asks the same question I answer every day: why did this break?
Except that someone is breaking it on purpose.

## code_conn_log_top - Given a Zeek conn.log print the top ten source IPs by number of connections | Top ten source IPs in a conn.log
I would read the file line by line.
I skip the lines that start with a hash, except the fields line, which tells me the column names.
For each connection, I take the source IP from that column and add one to a Counter.
At the end, I print the ten most common.

## code_huge_file - The file is one point two terabytes, what changes | The file is huge, what changes
I would stream the file, so I never load all of it into memory.
The counter grows with the number of distinct IPs, so I would check whether that fits too.
If it does not, I would partition counts on disk or use distributed processing.
For parallel workers, I would split on complete lines and give each worker the column names.
Then I would merge the counts before choosing the top ten.

## code_intel_hits - You have a set of malicious IPs from MISP, return every connection whose destination is in that set | And for domains
I would load the malicious IPs into a set, so each lookup is instant.
Then go through the connections and keep the ones whose destination IP is in the set.
For domains, the same idea with the DNS log, using the query field.
I would lowercase the domains and remove a trailing dot first, so they match.

## code_beacon - Given the timestamps of connections from one host to one destination, how would you decide in code if it looks like beaconing
I would sort the timestamps and compute the gaps between them.
If the gaps are almost all the same, it looks like beaconing.
I would measure that with the standard deviation divided by the mean, and flag it when it's very small.
And I would require a minimum number of connections, so a few random ones don't trigger it.

## code_kernel_allowlist - Write a script that compares the loaded kernel modules to an allowlist | Compare loaded kernel modules to an allowlist
I would read the allowlist file into a set, skipping empty lines and comments.
Then read the loaded modules from proc modules, which is what lsmod shows, and take the first word of each line.
The result is the loaded modules minus the allowed ones, sorted.
To roll it out to many nodes, I would only report first, collect data per host group, and block later.
Once the allowlist is solid, I would push it with Puppet per host group, which I've been reading about.

## code_process_tree - Given events with pid, ppid and command, print the chain of parents for a suspicious pid
I would put the events in a dictionary, from pid to event.
Then start from the suspicious pid and follow the parent pid, step by step, printing each command.
I stop when the parent isn't in the dictionary or it's pid one.
And I keep a set of the pids I've seen, so a loop can't make it run forever.

## code_secret_scan - How would you scan a repository for things that look like AWS keys or private keys | Lots of false positives
I would walk through every file in the repository and check each line with a few regular expressions.
For example, AWS access keys start with A K I A, and private keys start with a BEGIN PRIVATE KEY line.
I would scan the Git history too, because deleting a file does not remove old secrets.
For false positives, I would review each match and allow only specific, documented exceptions.
Test files can contain real secrets too, so I would not exclude them automatically.
And if one is real, the important part is to rotate the secret, not only delete it, because it stays in the git history.

## code_failed_logins - From the secure log, count failed logins per source IP and flag the ones with more than twenty | One-liner for the five IPs with most failed SSH logins
I would read the log line by line and match the failed password lines with a regular expression.
From each match, I take the source IP and count it with a Counter.
Then I return the IPs with more than twenty.
As a shell one-liner, the steps are filter the failed logins, extract the IP, count, sort, and take the top five, with grep, sort, uniq, sort again and head.

## code_rate_per_minute - Given web access logs, find clients making more than a hundred requests per minute
I would group the requests by IP and by minute, and count them with a Counter.
Any pair above a hundred is flagged.
For a sliding window instead of fixed minutes, I would keep a deque of timestamps per IP and drop the ones older than sixty seconds.

## code_vulnerable_versions - Given a list of services with host, product and version and a vulnerable range, return the affected hosts | Versions like 2.4.58-ubuntu1
I would identify the package ecosystem and use its version comparison rules, keeping the complete version.
I would match the product and check the affected ranges, including whether each boundary is included.
For Ubuntu packages, I would use the advisory for that package and Ubuntu release, including backported fixes.
I would return affected hosts and separately report versions I cannot assess.
(Do not use numeric tuples, string sorting or suffix removal as a universal comparator. A single lower-inclusive, upper-exclusive range is only valid when specified by the question or advisory. Keep distinct affected branches. Do not claim an example package is fixed without its advisory.)

## ubuntu_version_suffix - What about versions like two point four point fifty-eight dash ubuntu one | Should you strip the Ubuntu suffix | How do you handle backported security fixes
I would keep the full package version, including the Ubuntu revision.
I would use Debian package comparison rules and the security advisory for that Ubuntu release.
A backported fix can leave the upstream version unchanged, so the upstream number alone cannot tell me whether it is vulnerable.

## version_comparator_choice - Can packaging.version handle every version | Can you use the Python packaging library for Debian packages | Which version comparison library would you use
No. I would choose the comparator for the package ecosystem.
Python packaging versions use PEP four forty, while Debian packages use Debian ordering rules.
For a SemVer product, I would use a SemVer implementation.
If the ecosystem or version is unknown, I would report it for review rather than force it into another format.

## version_prerelease - In SemVer is a release candidate older than the final release | Does build metadata change SemVer precedence
Under SemVer, a release candidate has lower precedence than the final release with the same core version.
Build metadata does not change precedence.
That ordering alone does not tell me whether either version is affected by a particular vulnerability.
I would apply the advisory's affected ranges and prerelease rules.

## version_range_boundaries - Is the fixed version itself vulnerable | What about inclusive and exclusive range boundaries | How would you test the version comparison
I would test the exact lower and upper boundaries, plus versions immediately outside them.
If the lower bound is inclusive, it is affected.
If the upper bound is the first fixed release and is exclusive, that release is not affected by that range.
I would also test separate affected branches, prereleases and invalid input.

## version_unknown - The version is unknown or only a server banner is available | Does failing to parse a version mean it is safe | What if the version is missing or malformed
No. An unknown version is not evidence that the service is safe.
I would report it as needing verification and check the installed package or image inventory.
A network banner is a clue, not proof of the installed patch level.
I would keep unknown results separate from confirmed affected and confirmed unaffected results.

## version_multiple_ranges - The advisory lists two separate affected branches | Should you merge affected ranges into one minimum and maximum
I would keep the affected ranges separate and test whether the version falls within any of them.
Combining them into one large range could incorrectly flag versions in the gap.
Each branch must keep its own boundaries and applicable package context.

## code_security_headers - Write a function that checks a website for missing security headers | And for ten thousand sites
I would make one request to the site, with a timeout.
Then check a list of headers, like Strict Transport Security, Content Security Policy, X Content Type Options and X Frame Options, and return the missing ones.
For ten thousand sites, I would run the checks in parallel with a thread pool, with timeouts and retries, and save the results.

## default_password_check - How would you check safely if a device still uses a default password
With permission first.
I would check the account lockout policy and agree on a safe attempt limit with the owner first.
Even one attempt per password can lock the same account, so I would not assume that is safe.
Where possible, I would check the configuration without attempting a login.
And I would log every attempt.

## code_port_check - Write a minimal TCP port check | Why would you use nmap or masscan instead
For each port, I would open a TCP socket with a short timeout and try to connect.
If the connection succeeds, the port is open.
In practice I would use nmap, because it also detects the service and its version.
Masscan is for very fast port discovery at large scale, but it doesn't detect versions.
And only scan with authorization.

## code_pod_spec - Given a pod spec as a dictionary, flag privileged containers, root users and hostPath volumes | How would you enforce this instead of just reporting
I would check regular, init and ephemeral containers, including security settings inherited from the pod.
Container settings override pod settings where they overlap.
I would flag privileged mode, an explicit root user, missing non-root enforcement and allowed privilege escalation.
Missing user information is a risk to review, not proof that the process runs as root.
Then I would check the volumes and flag any hostPath.
To enforce it instead of reporting, I would use Pod Security Admission in restricted mode, or a policy engine like Kyverno or Gatekeeper.

## code_ci_gate - Fail a CI build if an image scanner reports any critical vulnerability
I would read the scanner's JSON report and keep the findings with severity critical.
I print each one, so the developer sees what to fix.
Then exit with code one if there's any, so the pipeline fails, and zero if not.

## code_baseline_drift - You have the current settings and a baseline, how would you report what differs | Which drift would you fix first
I would go through every setting in the baseline and compare it with the current value.
Every difference goes into a report, with the current value and the expected one.
To decide what to fix first, I would look at the risk and how many users it affects.
And I would use report-only mode before changing anything.

## security_vs_usability - Security versus usability, tell me about a decision where you had to balance them | Tell me about a decision where you had to balance security and usability | Security versus usability, give me an example | A trade-off between security and convenience | A time you balanced security and usability | Security vs usability
(Maria confirmed 2026-10-18: she chose this on purpose, and it is her only example. Personal script, small scale: never inflate it, no invented outcome.)
A small one, from my own triage script at Amadeus.
I needed it to read data from internal tools.
I chose to use my own signed-in browser session, with MFA, instead of storing a password in the script.
The cost is usability, it only works while I'm signed in.
But no credential sits in a file, and that was worth it to me.

## misp_to_zeek - How would indicators from MISP reach Zeek | How does MISP feed Zeek | How do MISP indicators get into Zeek
MISP exports its indicators as a feed, like IPs, domains and file hashes.
A small job pulls that feed regularly and turns it into Zeek's intel file format.
Zeek's intelligence framework loads those files, and checks live traffic against them.
When something matches, Zeek writes it to the intel log.
I would configure a notice policy or a downstream rule to turn the matches into alerts.

## beacon_jitter - Malware adds jitter, does your method still work | What if the malware adds jitter
Partly, so I would adapt it.
Jitter makes the gaps less regular, so the ratio of standard deviation to mean goes up.
So I would allow a higher threshold, and use the median gap, which is less sensitive to outliers.
I would also look at other signals, like connections of the same size, or a connection that keeps going for days.

## live_coding_approach - Can you write some code | Let's do a small coding exercise | How would you write that in Python
(Live coding: say the approach first, ask one assumption, write the simple version, test with a small example, then improvements.)
Sure. Let me first say the approach.
Can I assume the file fits in memory, or should I read it line by line?

## preparation_since_round_one - Since we last spoke what have you done to prepare | How did you prepare for this second interview
(Maria confirmed on 2026-10-16 and 2026-10-17: Puppet, container traceability, and the readings listed in the brief. Maria 2026-10-18: keep it about studying CERN topics; NEVER mention the triage script here.)
I went back over the topics I struggled with in our first interview, especially Puppet and tracing activity inside containers.
For containers, I looked into runtime monitoring, like Falco, not only the network traffic.
I also read your Bulletin articles, One click to many and The road to SBOM.
And I went through Liviu's slides from the HTCondor workshop, and his Zeek Workshop talk.

## code_kubectl_restarts - Write me a one-liner that finds all pods in all namespaces that restarted more than five times | Find all pods in all namespaces that restarted more than five times | One-liner for pods that restarted more than five times with kubectl | kubectl and grep pods restarted more than five times
I would list the pods in all namespaces without the header, and filter on the restarts column with awk.
With all namespaces, the columns are namespace, name, ready, status, restarts, so restarts is the fifth one.
So it's kubectl get pods, dash A, no headers, piped to awk, keeping lines where the fifth column is above five.
Newer kubectl shows restarts like three, then five minutes ago in brackets, but the number is still the fifth column.

## kubectl_restarts_format - What if the restarts column shows something like three five minutes ago | The restarts column has a time in brackets
That's the normal output of newer kubectl, the last restart time in brackets.
Awk splits on spaces, so the count stays in the fifth column and the bracket part moves to the next one.
So the filter still works. For something more robust, I would read the restart count from the JSON output instead.

## least_privilege_example - What's least privilege, give an example from your work | Least privilege example from your work | What is least privilege
(The triage script's read-only behaviour is by design, NOT enforced by a role or scope: never say a compromised script could not write.)
Least privilege means each person or service gets only the access its task needs, nothing more.
In AWS, that's an IAM role scoped to one task instead of a wildcard permission, which I studied for my certifications.
In my own work, my triage script at Amadeus only reads, it does GET requests and screenshots and never changes anything.
But that's how I wrote it, not enforced by a role, so the next step would be a read-only scope.

## vm_fleet_openstack - At CERN VMs run on OpenStack, how would you secure a fleet of VMs you don't own | How would you secure a fleet of VMs you don't own | Secure VMs on OpenStack
I would start from what can be controlled centrally.
Maintained base images, patched regularly, so every new VM starts clean.
Security groups that open only the ports each VM needs.
SSH with keys only, no passwords and no direct root login.
Configuration managed with Puppet, so the baseline is the same everywhere and drift gets corrected.
And an inventory with regular scanning, plus the SOC's network monitoring for what we can't see inside.

## m365_first_setting - Give me one Microsoft 365 setting you'd check first and why | Which M365 setting would you check first | One Microsoft 365 setting to check first
I would check that legacy authentication is blocked.
Old protocols, like basic authentication for mail clients, don't support MFA, so a stolen password is enough to get in.
I would look at the sign-in logs first to see who still uses them, then block it in report-only mode before enforcing.
A close second is user consent to OAuth apps, because a malicious app can read mail without any password.

## configured_controls - Give me two specific controls you've actually configured before | You said compensating controls, give me two specific controls you've actually configured before and how you'd verify they're effective here | Compensating controls you've configured | Two specific controls you've actually configured and how you'd verify they're effective | Which security controls have you configured yourself | Controls you have actually configured
(Only the real ones: the Azure Key Vault flow and the hackathon tunnel. Never Puppet, firewalls, network policies or monitoring rules: she has not configured those. Never claim she set up rotation or monitoring on the vault.)
Two I built myself are small, but real.
First, in a freelance payments flow, I created an Azure Key Vault and kept the bank API credentials out of the code.
The payment calls used a temporary token from the bank, which expired after about three hours.
Second, at an AWS hackathon, I connected two VMs with a secure, authenticated tunnel.
Here, I would roll a control out with Puppet, which I've been reading about since our first conversation.
And I would verify it two ways.
The Puppet run reports show if a node drifted from the setting and got corrected.
And I would test that it really blocks, for example that a login without the right key gets refused.

## verify_baseline_fleet - How would you verify that a hardening baseline is really applied across the whole fleet | How do you verify a baseline is applied on every machine | How do you know a setting is applied everywhere
(If she already said in this interview that she has been reading about Puppet, skip that line and just apply it.)
I would verify it from two sides, the config and the behaviour.
For the config, Puppet, which I've been reading about since our first interview, since it was my weak spot.
Its run reports show every node that drifted and got corrected, and any node that stopped reporting.
For the behaviour, I would test the control on a sample of hosts, for example that a password login is refused.
A report saying a setting is applied isn't proof that it actually blocks something.

## ca_device_code_policy - How would you configure a Conditional Access policy to control device code authentication | Configure a Microsoft Entra Conditional Access policy for device code flow | How would you target the policy and enforce the restriction for device code
(Targeting only the group that needs device code does NOT restrict anything for everyone else: the block applies to all users, the approved group is excluded.)
I would use the Authentication flows condition, which can target the device code flow.
The policy blocks device code flow for all users.
The approved group, with a confirmed business need, is excluded from that block.
For that group, a second policy requires a compliant device or a trusted location.
And both start in report-only mode, so I see who would be affected before enforcing.

## sbom_affected_systems - How do you know which systems are affected by a new vulnerability | Which systems are affected by a new CVE | How do you find which images contain a vulnerable package | What do you think about SBOMs | What did you think of the SBOM article
(From FRASES_LO_QUE_ESTUDIE.md, 2026-10-17: Maria asked to use it as something she read since round 1.) Article "The road to SBOM" (Bulletin, 30/09/2026).
I read your recent article, The road to SBOM.
I liked the idea that an SBOM answers exactly that question, which images contain this package and version.
I saw CERN already has pieces, like GitLab's dependency scanning and the component listing for OpenStack-managed containers.
And you're looking at a software gateway with a quarantine of twelve to forty-eight hours for new packages.
I would be curious how you would combine the two.

## malicious_dependencies - How do you deal with malicious dependencies from PyPI or npm | Malicious packages from PyPI or npm | How do you protect against malicious open source packages | What did you think of the Copied committed KO article
(From FRASES_LO_QUE_ESTUDIE.md, 2026-10-17: Maria asked to use it as something she read since round 1.) Article "Copied, committed, KO" (Bulletin, 17/06/2026).
I read the article Copied, committed, KO, from June.
What stayed with me is that the problem is visibility.
You can't notify owners about a malicious package if you don't know who uses it.
So a central proxy that logs every download makes a lot of sense.
And it can hold new packages for a cooldown period before they're used, because most malicious packages get caught within days.

## cern_soc_zeek_talk - What do you know about our SOC | What do you know about how our SOC works | What do you know about our security operations | What did you think of Liviu's Zeek talk
(From FRASES_LO_QUE_ESTUDIE.md, 2026-10-17: Maria asked to use it as something she read since round 1.) Liviu's talk at Zeek Workshop 2026, "Zeek and the Balance between Academic Freedom, Industrial Operations & Security". The connection count comes from his HTCondor slides (verified 2026-10-18), never "two and a half billion connections" (2.5 billion is the DNS requests).
I went through Liviu's Zeek Workshop talk.
What impressed me is the scale.
Zeek sensors feed Kafka, then Spark and OpenSearch.
And in Liviu's HTCondor slides, the SOC sees around three and a half billion network connections a day.
And MISP for indicators shared with other sites.
The part I found most interesting was the balance in the title, between academic freedom and security.
You can't control the devices, so the network becomes the main place to see what's happening.

## liviu_slides_opinion - What did you think of Liviu's slides | What did you think of the HTCondor workshop slides | What stood out in the security landscape slides
(From FRASES_LO_QUE_ESTUDIE.md, 2026-10-17: Maria asked to use it as something she read since round 1.)
Two things stood out to me.
The five steps for a privilege escalation, with mitigation first, because the patch and the reboot take longer.
And the command logging fields, uid, euid, pid, ppid, which let you rebuild a process chain after the fact.
I'm curious how the move to a kernel module allowlist is going.

## aws_undersold - I'd like to correct something from last time about AWS | You said you were nothing at AWS | Last time you said your AWS role was not technical
(Maria said "I was nothing in particular" in round 1. FIVE AWS certifications, Maria 2026-10-17: Solutions Architect Associate, Machine Learning Engineer Associate, Generative AI Developer Professional, Cloud Practitioner and AI Practitioner.)
I'd like to correct something from last time, I undersold my AWS internship.
I was in the sales organization, but I built the web apps for the internal sales campaigns.
More than two hundred people used them, instead of buying them from a vendor.
And I earned five AWS certifications, including Solutions Architect Associate and Generative AI Developer Professional.

## base_image_cve_300_projects - A critical vulnerability is discovered in a base container image used by 300 projects, how would you determine which deployed workloads are affected | A critical vulnerability in a base image used by 300 projects, how do you find which ones are affected | Which deployed workloads use a vulnerable base image | How do you find which containers are built on a vulnerable base image
(SBOM article: the per-image SBOM and OpenStack component listing fit here; the 12-48 h quarantine does NOT, it is for new packages.)
I would match on the image digest, not the tag.
I would check it across everything that is deployed, because a tag like latest can point to different images.
That's where your article on the road to SBOM fits, an SBOM per image tells you which ones contain the vulnerable package.
And the article mentions that OpenStack-managed containers already list their components.
So the output is a list of workloads, with the owner and whether it's exposed.

## base_image_owners_not_reacting - Some affected projects have not rebuilt their images after a week | What do you do if the owners don't react after a week and one project cannot stop its workload | Owners don't rebuild their images, what do you do | What do you do if owners don't react | How would you prioritize and manage the remaining risk | One project cannot stop its workload, what do you do
I would rank what is left by exposure first.
Internet facing or sensitive data goes to the top of the list.
For the one that cannot stop, compensating controls, a tighter network policy and extra monitoring, while the rebuild is pushed.
And a fixed deadline, agreed with their management.
Accepting that risk needs an owner, not an open-ended exception.

## ransomware_first_hour - Walk me through the first hour of a ransomware incident on a Linux server | First hour of a ransomware incident | A server is hit by ransomware, what do you do | How do you respond to ransomware
(General incident response, NOT Maria's experience: she never handled a ransomware case. Pau leads incident response.)
First, isolate it from the network, but keep it running.
Memory and running processes are evidence, and a shutdown loses them.
Then I would find the scope, which other hosts it talks to, and how they got in.
I would preserve the logs centrally before anything gets cleaned up.
Credentials used on that host get rotated, because they may be stolen.
And I would tell the incident response team right away, so one person owns the decisions.
Paying isn't my decision, but I would advise against it, the way back is restoring from backups we have checked are clean.

## ransomware_entry - How do ransomware groups usually get in | How do ransomware attackers get initial access | What are the main ransomware entry points
(General knowledge, not Maria's experience.)
Mostly stolen credentials or phishing.
The other big one is exposed services that are not patched, like a VPN, RDP or a management interface.
And often the group that encrypts didn't break in itself.
Access brokers sell that first foothold to the ransomware affiliates.
So MFA, patching what faces the internet, and watching for unusual logins cover most of it.

## ransomware_affiliate - What is a ransomware affiliate program | What is ransomware as a service | Explain ransomware affiliates
(General knowledge. Pau gave a talk on the "Black Hole Locker" affiliate program; Maria did NOT watch it: never claim she did.)
It's ransomware as a service.
One core group builds the malware, the infrastructure and the leak site.
Affiliates rent it, break into victims, and deploy it.
Then they split the ransom between them.
That's why the same ransomware shows up with very different ways of getting in, it depends on the affiliate.

## monitoring_rule_no_flood - How would you write a monitoring rule for a suspicious login without drowning the SOC in false positives | How do you write a detection rule without too many false positives | How do you avoid alert fatigue with a new rule
(General method, no reading cited.)
I would start from one concrete signal.
For example, a successful login right after many failures, or from a new country for that account.
Before turning it on, I would run it over past logs, to see how many alerts it would have given.
Then I would add context, like the type of account and the usual hours, to cut the noise.
And I would review it after a few weeks, because a rule nobody tunes ends up ignored.

## explain_security_newcomers - How would you explain to new CERN users why they should care about security | How would you convince new users to care about security | Security awareness for newcomers
Start with something real that happened here.
In July, your team wrote about a device code phishing campaign, and 108 people clicked.
One click gave the attacker a valid token for three months, even with two-factor authentication.
Then what they could lose themselves, their account, their data, their experiment's access.
And two or three simple actions, like pausing before typing a code into a sign-in page.


## biggest_achievement_hackathon - What is your biggest achievement so far | What are you most proud of | Your biggest accomplishment | What achievement are you proudest of
(Maria, 2026-10-18: her biggest achievement is the hackathon, because it showed her she can be as good as people she considers very strong, she just has to put in the effort. Facts only from learn_fast_example. If the hackathon was already told, give only the meaning, with a short back-reference.)
Winning the AWS LATAM New Hire Jam, in 2025.
My team was one person short, and I took one of the hardest challenges, a secure, authenticated tunnel between two VMs.
I had never done it before, and when it kept failing, I read the whole specification again.
I found what was wrong from the start, redeployed it clean, and no other team completed that challenge.
What it meant to me is bigger than the prize.
I was next to people I consider really strong, and I saw I can be at that level.
I just have to put in the effort.

## why_leaving_amadeus - Why are you leaving Amadeus after only a few months | Why do you want to leave your current job | Why change jobs so soon | Why leave Amadeus | You just started at Amadeus, why move already
(Maria, 2026-10-18: the main reason is growing in another country and exploring new things; she feels she has learned the core of the junior role. There is also a private team-culture reason: NEVER give any detail of it, never criticise Amadeus or colleagues, never hint at "a story for another time".)
It's less about leaving Amadeus and more about where I want to grow.
I've learned a lot there, real production incidents on Linux and Kubernetes, and a global 24/7 team.
I've covered the core of what that junior role can teach me.
Now I want a bigger challenge, in security, and I want to grow in another country.
CERN is exactly that, the field I want, in an international place with a mission I care about.

## why_not_grow_at_amadeus - Why not grow into security at Amadeus | Couldn't you grow into security at Amadeus | Could you not grow into security there | Couldn't you grow at Amadeus | Is something wrong at Amadeus | Why not stay and grow there | Is there a problem with your current team
(Private reason exists; never give details, never criticise anyone. One neutral line about culture at most, then back to the positive.)
I probably could grow there, if I stayed.
But I want that growth abroad, in an international environment.
And for the long term, I'm looking for a team culture where I feel at home, respectful and collaborative.
From what I've seen of your team, how openly you explain incidents to the whole lab, that's what I'm looking for.

## real_reason_leaving - Be honest with us what's the real reason | Is there something about your current team you don't like | What's the real reason you're leaving | Is there anything else behind it
(Private reason exists. Honest but neutral: never "it's a good team, no problem" (not true), never details, never criticise anyone.)
Growth is the main reason, honestly.
There is also a culture side, it's not the team where I see myself long term.
I prefer not to go into details about colleagues.
What I'm looking for is a respectful, collaborative team, and that's what I've seen from yours.

## weakness_hard_on_myself - What are your main weaknesses | What is your biggest weakness | What would you like to improve about yourself | What do you struggle with | Tell me a weakness
(Maria, 2026-10-18: failing frustrates her and she can be very hard on herself. Mention the thesis lightly, no details unless asked; if they ask for more, tell mistake_made. Never list technical gaps of the job (Zeek, MISP, Kubernetes) as THE weakness. Facts: the first thesis only.)
I can be very hard on myself when I fail.
For example, my first thesis didn't pass, and of course it hit me hard.
But I kept going, and my final thesis passed.
I'm happy to tell you more about what happened, if you like.
What I've learned is to take a failure as a lesson, not as a verdict on me.

## handle_pressure - How do you handle pressure or tight deadlines | How do you deal with stress | How do you work under pressure | What do you do when you're under pressure
(Maria, 2026-10-18: under pressure she isolates and goes 100% focused, she acts instead of freezing, and prioritises what causes the pressure. She can come across short if interrupted: NOT in this answer unless she confirms a way she handles it.)
I go into full focus.
I step away from distractions, and I start with whatever is causing the pressure, instead of freezing.
At Amadeus, in a 24/7 team, that means impact and urgency first, and I escalate with evidence.
Once the most urgent thing is under control, I go to the next one.

## different_from_experienced - What makes you different from someone with more security experience | Why you over someone with more security experience | Someone more experienced also applied, why you
Someone with more experience brings the tools already.
I bring fresh eyes from production operations, where I see every day how real systems break.
And the drive to close the gap fast, I've already gone back over my weak spots from the first round.
In a graduate role, that combination grows into exactly the engineer you need.

## anything_else_to_add - Is there anything else you'd like to tell us that we haven't asked | Anything else you want to add | Is there anything we didn't ask that you want us to know
(Close on motivation, never on M365 being her strongest area: her cloud experience is AWS.)
Just that I really want this.
I'm ready to move from Colombia for it, because protecting open science is the work I want to do.
And I'm happy to take on-call and night shifts, they're part of owning real systems.
Thank you for your time, across both rounds.

## priorities_changed - Tell me about a time priorities changed suddenly | A time your priorities changed | Tell me about a time you had to adapt quickly | A time you had to take over someone else's work | Tell me about a time you helped a teammate under pressure
(Maria, 2026-10-18: university team project, a web application. Grade scale in Colombia is out of 5. No names.)
The situation was a university team project, a web application, and we had split all the work between us.
In the middle of the holidays, one teammate, who was abroad, burned his computer, and he couldn't work anymore.
He was the strongest of us, he had years of web experience, and he was the one who had organised the whole team.
So my priority changed, from finishing my part to finishing his part too.
It wouldn't have been fair for him to get a bad grade after everything he had done for the team.
So what I did was build both parts in less than a day.
It wasn't the perfect solution, but it worked, and we got 4.5 out of 5.
I'm proud of it, because I didn't let him down.

## bug_own_code - Tell me about a bug in your own code | Tell me about a bug in your own code that was hard to find | A hard bug you found in your code | A bug you couldn't find | Tell me about a time you debugged something hard | A time you were stuck on a bug
(Maria, 2026-10-18: the course was DPOO, Diseño y Programación Orientada a Objetos, at Universidad de los Andes; a Book class. In English: Object-Oriented Design and Programming.)
The situation was my Object-Oriented Design and Programming course at university, and my Book class just didn't work.
I iterated again and again, and I couldn't find why.
So I went to the professor, and he showed me how to step through it properly.
After about an hour, we found it.
There were two classes with the same name, one I had written, and one that had been created automatically by accident.
What I learned is that I can't just accept whatever my tools generate, I have to check it.
That was before AI, and it matters even more now, I review what an AI suggests before I use it.

## barad_dur_exposed_services - How would you find exposed or insecure services across CERN | How would you find all web servers on CERN's network and what they run | How would you build an inventory of web services | What did you think of Barad-Dûr | What did you think of Dawid's slides
(Maria read Dawid's Barad-Dûr slides, confirmed 2026-10-18. Facts only from the brief section. Cite it at most once in the interview.)
I read your slides on Barad-Dûr, and that's the approach I would take.
Start from DNS, not from IPs, because with virtual hosts one IP can serve many sites.
Collect what each site runs, its certificate and its headers, and keep it searchable, with history.
Then, when something like the Magento vulnerability comes out, it's one query to find every instance and tell the owners.
What I liked most is the perceptual hashing of screenshots, it groups sites that look the same, even when the hostnames tell you nothing.

## takeaway_first_interview - What did you take away from our first interview | What did you learn from the first round | What did you take from last time | What stayed with you from our first conversation
(Confirmed: weak spots in round 1 were Puppet and tracing activity inside containers; she went back over both and read the items in the brief.)
Two things.
First, where my gaps were, Puppet, and what happens inside a container, not only on the network.
So I went back over both, and I read your slides and Bulletin articles on those topics.
Second, how your team works, you explain incidents openly to the whole lab.
That made me want to be part of it even more.

## cern_same_symptom_what_changes - Same symptom at CERN, what changes | What would be different at CERN | And if the same thing happened at CERN | Same login failures at CERN, what changes
Two things change.
First, the users are all over the world, and some log in through their home institute's account.
So before assuming it's our change, I would check if the failure is limited to one identity provider or one service.
Second, at CERN a sudden wave of login failures can also be an attack, like password spraying.
So I'd look at the SSO logs.
Many accounts failing from the same few IPs points to security, not to a bad change.
And since services belong to many different owners, I'd go to the owner of the change instead of rolling it back myself.

## lock_or_log_credential - What would you lock | What would you lock down | What would you log | What would you lock or log after rotating the credential
(If the word is unclear, the first line is: "Sorry, did you say lock or log?")
To lock it down, I'd allow the account only one access path.
For example, only from the experiment's own servers, so a stolen copy doesn't work from anywhere else.
To log it, I'd record every use of the new credential, with the source IP and the time.
Then I'd alert on any use from outside that path.

## rootkit_investigate - How would you investigate a suspected rootkit on a Linux server | We suspect a rootkit on a server, what do you do | How do you investigate a rootkit
The key idea is that the machine can lie to me.
A rootkit changes what ps, ls or netstat show, so I don't trust the tools on that server.
So I compare what the machine says with evidence from outside it.
First I isolate it from the network side, at the switch or firewall, and keep it running.
Then I capture the memory and the disk before touching anything.
I analyse both on another, clean machine.
And the network logs, like Zeek, are an independent source the rootkit can't edit.
If Zeek sees a connection but ss on the host doesn't, something is hiding it.
Anything the network or the memory shows, but the machine hides, is the rootkit.
In the end, I rebuild it from a clean image, I don't try to clean it.

## memory_tool - Which tool would you use to capture the memory | How do you dump memory on Linux | What tool for memory acquisition | Which tool for the memory | How would you analyse the memory
If it's a VM, I would take the memory snapshot from the hypervisor, so nothing runs inside the compromised kernel.
On a physical machine, I would use AVML or LiME, from trusted external media.
AVML is a single static program, so I don't install anything on the suspicious machine.
LiME is a kernel module, so it has to match that exact kernel, and loading it changes the machine a little.
I write the dump to external storage or over the network, never to the local disk.
Then I analyse it on another machine with Volatility 3.
It needs the symbols for that exact kernel version, so I note the kernel version first.
Then I compare the process list in memory with what ps showed. A process that's only in memory is what the rootkit hides.

## telemetry_gap - The telemetry from a host suddenly disappears | A host stopped sending logs, what do you do | The agent on a server went silent
The gap itself is evidence. Attackers stop the logging before they do something.
I wouldn't shut the machine down, because memory is evidence too.
I would isolate it from the network side, at the switch port or the firewall, not from the host.
On the host, a rootkit could fake the result of my commands.
Then I look at the last logs before the gap, and at the network logs for that IP during the gap.

## beacon_detection_rule - How would you write a rule to detect beaconing | How would you turn beacon detection into a rule that doesn't flood the SOC | A beaconing rule without too many alerts | How would you turn the beacon detection into a rule | How do you avoid false positives with beaconing
I would group connections by source, destination and port, and look for intervals with little variation.
I would test it first on past data, to see how many alerts it would give.
Many legitimate processes repeat too, like NTP, updates, monitoring and backups, so I exclude the known ones.
Attackers add jitter, so I don't look for exactly sixty seconds, but for gaps that are regular within a tolerance.
And if the destination IP is in MISP, the priority goes up.

## triage_script_improved - How do you investigate an incident | How do you approach a new investigation | How do you learn a new environment | How would you get up to speed here | How would you get up to speed in a new environment like ours | How do you ramp up in a new team | How do you keep learning on the job | Have you improved your script | What's new with your script
(Maria confirmed 2026-10-18. Call it a "script", never an "agent". "Since we last spoke" counts towards the 1-2 uses of "since our first interview": if already used, say "I've recently improved".)
I've recently improved the triage script I mentioned last time.
Now it also looks for similar past incidents, and reuses the searches that worked.
It's the same idea as a SOC: learn from the cases you already solved.
And it keeps a list of the parts of the architecture I don't understand yet.
On quiet days, that list is my study plan.

## ai_governance_own_use - Do you use AI tools in your work | How do you use AI at work | How should people use AI safely | What is the first control for AI use | How would you govern AI use
(Maria confirmed 2026-10-18: Copilot was the only AI tool Amadeus fully approved for internal data.)
At Amadeus, I extended my triage script with Copilot, because it was the only AI tool the company had fully approved for internal data.
I think that's the first control for AI use: deciding which tools are allowed to see which data.
And I review every query it drafts before I run it.

## triage_script_safe - Is your tool safe | Is the script secure | Would you share the script with the team | What access does the script have
It only reads, using my own login.
Before sharing it with the team, I'd have it reviewed and switch to whatever access the team approves.
And I'd document exactly what it does.

## why_cern_not_private - Why not continue that cybersecurity path at a private company like AWS or Amadeus | Why not do security at a private tech company | Why CERN and not a private company | Why not stay in industry | Why not a security role at AWS or Amadeus | Why specifically CERN and not a tech company
(Maria, 2026-10-18: her Amadeus incidents are production incidents, NOT security incidents. If the question assumes she already does security, correct it first in one line. WLCG: "around a hundred and seventy computing centres", never "thousands of institutes".)
Just to clarify, the incidents I handle at Amadeus are production incidents, not security incidents.
Security is the path I want to start now, and I would rather start it here.
What draws me is the openness.
Liviu's Zeek Workshop talk says it in the title: the balance between academic freedom and security.
At a company, you control the devices. Here you can't, so security has to work with people, not against them.
And with the WLCG, around a hundred and seventy computing centres in more than forty countries depend on each other.
That's a harder and more interesting problem.

## payments_flow_ownership - Which parts of the payments flow did you personally design and implement | What was the most difficult technical decision in the payments project | What was the hardest decision in that project | What did you build yourself in the payments flow | Which parts did you personally design
(Maria, mock 2026-10-18. Token lifetime: say "about three hours", never another number. HOW she handled the token expiring mid-batch is NOT in the notes: never invent a mechanism like refresh timers or retries.)
I designed the Power Automate flow logic, and I set up the Key Vault.
I created the vault myself, and it held the bank API credential and the API key.
I also built the dashboards on top, for successful and reversed payments.
The hardest decision was how to handle the bank's temporary token.
It expired after about three hours, so the flow requested it fresh and never stored it with the static credentials.
And since there were many payments, a long batch could outlive the token.
So I had to organise the batches so they never kept running with an expired token.

## proc_pid_inspect - What would you look at in /proc for a suspicious process | What do you check in /proc/4321 | Which files in proc for a process | How do you check the binary of a running process
In status, the Uid line has four values: real, effective, saved and filesystem.
The exe link points to the binary. If it says deleted, the binary was removed while it was still running, and that's a red flag.
I would also read cmdline, and the open connections of that process.
To check the binary, I wouldn't trust its date, because an attacker can change it with touch.
I would hash it with sha256sum, and compare it with the packaged version, rpm dash V checks the file against its package.
Timestamps can be faked, hashes can't.

## puppet_auditd - How would you deploy auditd with Puppet | Write a Puppet class for auditd | Where do the audit rules go | How do you load the audit rules with Puppet
(OpenVox: CERN is migrating its Puppet fleet to OpenVox, public VoxConf talk of 16/07/2026. Maria didn't read those slides: say "since you're migrating to OpenVox", never "I read".)
A package resource for audit, the config file from a template, and the service with subscribe on the config.
The rules go in a file under etc audit rules dot d, and they're loaded with augenrules dash dash load.
So the rules file notifies an exec that runs augenrules, only when the file changes.
On RHEL, auditd refuses a restart through systemctl, so the service resource uses service auditd restart.
And since you're migrating to OpenVox, the same manifest works, because it's a community fork of Puppet.

## kafka_consumer_down - The Kafka consumer that writes to OpenSearch is down, what happens | A consumer was down, what do you lose | Retention is sixty minutes and the consumer was down ninety | How do you recover the missing events
(SOC numbers from Liviu's HTCondor slides: around three and a half billion network connections a day. Ninety minutes is a couple of hundred million connections.)
Kafka keeps the events, so the consumer group's lag grows while it's down.
When it comes back, it continues from its last committed offset.
If retention is shorter than the outage, I compare that committed offset with the oldest offset Kafka still has.
With sixty minutes of retention and ninety down, about thirty minutes are lost.
I would replay them from the logs Zeek keeps on disk, if it keeps them, and mark them as reconstructed.
Then I re-run the detections over that window, because old data doesn't always trigger alerts on its own.
At the scale in Liviu's slides, ninety minutes is a couple of hundred million connections.
So I would want an alert on consumer lag long before retention runs out, and a retention longer than our reaction time.

## m365_app_consent - A user consented to a malicious app in Microsoft 365, what do you do | Illicit consent grant | An OAuth app got access to a mailbox | How do you investigate an app consent
(SCuBA: the Entra ID baseline says only administrators should consent to applications. Maria read the SCuBA page.)
First, the Entra ID audit logs, to see who consented, when, and to which permissions.
Then I check if it was user consent or admin consent, and if the permissions are delegated or application.
Application permissions work without any user, across the whole tenant, so they're the most dangerous.
I would revoke its permissions, or disable the service principal, without touching the user's account.
To know the damage, I check what it read in the unified audit log, events like MailItemsAccessed and FileAccessed.
And I look for other users who consented to the same app.
To prevent it, I would restrict user consent, and send everything else through an admin consent workflow.
The SCuBA baseline for Entra ID says only administrators should consent to applications, so I would check that early.

## payments_idempotency - How did you avoid paying twice | What if the bank call times out | How do you make the payment calls safe to retry | Idempotency in the payments flow
(Maria confirmed 2026-10-18: the bank's API let her query a payment's status, and she described this design as hers in the mock. Say it as something she did.)
The key was idempotency.
Each payment got a unique ID before the call, and its state was saved before sending it.
If a call timed out, the flow asked the bank for that payment's status before retrying.
That way, a payment was never sent twice.

## ransom_pay - Do we pay the ransom | Should we pay | Would you pay the ransom | They ask if they should pay
(Never "No, I would not pay" as if it were her decision: the decision belongs to the institute's management with legal.)
It's not my decision, it's the institute's management, with their legal team.
My advice would be not to pay.
It doesn't guarantee recovery, and the data has probably been stolen already, so paying doesn't stop them publishing it.
And it funds the next attack.
I would focus on restoring from clean, offline backups and rebuilding.

## rce_open_source_library - A critical RCE in a widely used open source library, how do you find what is actually vulnerable | An RCE in an open source library used across thousands of apps, how do you prioritise | Which running services are actually vulnerable to a new library CVE
(Barad-Dûr only sees EXPOSED web services found from DNS: product, headers, certificate. It never sees libraries inside an app: those come from the SBOM. "Time-to-Exploit has gone negative" is a slide title in Liviu's HTCondor slides. Puppet: only "with a fact that reports installed packages", never claim Puppet collects them by default.)
First, the exact version, not just the package name.
Distributions like RHEL backport fixes without changing the upstream version, so I would check the distro's advisory, not only the number.
For containers, the SBOM, as in your article The road to SBOM, tells me which images contain the library.
For VMs without an inventory, Puppet helps: with a fact that reports installed packages, one query covers the whole fleet.
Barad-Dûr would tell me which exposed web services run the affected product.
Then I check if the vulnerable code is reachable, and I start with internet facing and high privilege systems.
As Liviu's slides say, time to exploit has gone negative, so I mitigate before the patch, disabling the feature or filtering the traffic.
At the end, I verify the new version is installed and that running processes were restarted, because they keep the old library loaded.

## strands_why_not - Why didn't you use Strands | Did you use Strands | Strands or Bedrock Agents
(Maria, 2026-10-18: she designed it with Strands; the built version was a prototype. That is the only reason: never add another, like time or speed.)
I designed it with Strands.
But it was a prototype, so the version I built ran on Bedrock Agents.
Moving to Strands would put the agents' logic in code, versioned and testable, which also makes security review easier.

## puppet_sshd - How would you manage the SSH configuration with Puppet | Write a Puppet class for sshd | How do you avoid breaking SSH with Puppet
A package resource for openssh server, then the config file from a template.
The file has validate_cmd, running sshd dash t dash f on the new file, so a broken config is never written.
And the service with subscribe on the file, so it restarts only when the config changes.

## scheduled_task_check - How do you check scheduled tasks on Linux | Where would you look for persistence in scheduled jobs | A suspicious scheduled task
I would check crontab for every user, and the files in etc cron dot d.
Then the systemd timers, and atq for one-off at jobs.
For anything odd, I look at what the script actually does, and who owns it.

## first_three_months - What would you do in your first three months | How would you spend your first ninety days | What would your first months look like
(Stefan said in round 1 that the cloud review is about a third of the time at the start.)
I would start with the Microsoft 365 review, since you said it's about a third of the time at the start.
Going through the settings one by one, understanding what each does, and checking who uses it in the logs.
In parallel, I would learn the SOC pipeline, from Zeek to Kafka and OpenSearch, by following real alerts.
And I would read the team's Puppet code, starting with small changes on a test node.

## stability_vs_security_change - Walk me through a situation where you had to balance operational stability with a security related change | A time you balanced stability and security | A security change that could break production | Balance operational stability with a security change
(No exact case at Amadeus: say so, then the freelance flow. Power Automate has no repository: never "repo history". The bank API let her query a payment's status (Maria, 2026-10-18).)
I don't have an exact case at Amadeus, so let me give you the closest real one, from a freelance project.
I built a Power Automate flow that called a bank's REST API for more than 2,000 payouts a week.
The credential lived in Azure Key Vault, not in the flow.
The risk was breaking payments, so the key was idempotency.
Every payment got a unique ID before the call, and before any retry the flow checked whether the bank had already processed it.
That way, security never cost us stability.

## payments_alternatives - What alternatives did you consider and why did you reject them | Which alternatives did you reject in the payments flow | Why not keep the credential in the flow
(Power Automate: the flow is a definition on the platform, there is no repo. Token: she never stored it; each batch requested a fresh one, and she organised the batches so a long batch never kept running with an expired token. The exact mechanism beyond that is not in the notes: never invent one like "it requested a new one when it expired".)
I rejected keeping the credential in the flow, because anyone who could edit or export the flow would see it.
I also rejected storing the bank's token.
It expired after about three hours, so the flow requested a fresh one.
And since a large batch could outlive it, I organised the batches so none kept running with an expired token.
Combined with the unique payment ID, a retry could never pay twice.

## copilot_safety - How do you ensure Copilot doesn't leak sensitive information or introduce something unsafe | How do you make sure the AI suggestions are safe | Can Copilot leak data or break production
(Copilot is APPROVED for internal data: never "nothing confidential goes into Copilot". The script is read-only by design (GETs, pages, screenshots), not enforced by a role. It's a personal tool, never in production. Checking suggested dependencies is NOT in the notes: never claim it.)
For the data, Copilot is the tool Amadeus approved for internal data, so nothing leaves the approved boundary.
For safety, Copilot never runs anything. It drafts queries, and I review each one before I run it.
And the script only reads: GET requests, pages and screenshots, so even a bad query can't change anything.
It's also a personal tool, so nothing it does goes to production.
The read-only part is by design, not enforced by a role yet, so a read-only scope would be the next step.

## token_expiry_practice - What happened when the bank token ran out halfway through | Did you ever see failures because the bank token timed out | Was the token ever a problem | Did the token ever expire on you | Did you ever see failures because the bank token expired | Was the token lifetime ever a problem in practice | How long did the bank's token last | What if the token expired mid batch
(Maria's own words: a long run could outlive the token, so she had to organise the batches. Whether it ever actually failed is NOT in the notes: never "it never happened", "it was never a problem", "it did expire" or "it didn't come up", and never a mechanism like checking the token's status.)
I organised the batches precisely so that wouldn't happen.
The token lasted about three hours, and with many payments a long batch could outlive it.
I never stored the token, the flow requested a fresh one.
And I organised the batches so none kept running with an expired token.
