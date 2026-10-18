# Prepared answers - Optiver (copied 2026-10-15 from the CERN library: Maria's own stories only)

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

## why_optiver - Why Optiver | Why do you want to work at Optiver | Why do you want to join Optiver | What attracts you to Optiver | Why this company | Why trading
(Lead with the problem, not with agentic AI: that's only one line of the posting. The father line only as written here; whether he trades himself is not in the notes.)
Three things.
First, the problems. In trading, a system has to be fast and correct at the same time.
And you see the result of your code right away, not months later. That direct feedback is what I enjoy most.
Second, the people and the training. The Academy and a mentor would give me the trading side, on top of my engineering base.
And third, the role asks for building agents and agentic workflows, and I already built a multi-agent prototype at AWS with Bedrock.
And on a personal level, markets have been a topic at home, because of my father.

## why_two_degrees - Why two degrees | Chemical and computing why both | Why both and what does any of it have to do with security | Why both chemical and computer engineering | Why did you study chemical engineering and computing
Everyone asks me that, and I love answering it.
I started in Chemical Engineering.
Then I took a programming course, and I liked it so much that I added Computing in parallel.
For me, both connect in one idea.
A protein is code, written in the genetic code, and science is still learning to read it.
My thesis joined the two.
I used machine learning to predict how stable a protein is when it's heated.

## why_software_engineering - Why software engineering | Why software engineering and not machine learning or research | What did the thesis teach you about what you want | Why do you want to build software | Why move from support to software engineering
(At Amadeus I debug production systems; I do NOT build or ship them there. Never say "what I do now at Amadeus" about building. Puzzles and escape rooms are real interests from my CV.)
Because I love hunting for what's wrong.
When something breaks, in the code or in the environment, I want to find out why.
And the hard ones are my favourite, because you have to get creative to find them.
It's the same feeling I get with puzzles and escape rooms.
At Amadeus I do that every day with production incidents.
Now I want to do it while I build the systems too, not only after they break.

## chemical_engineering_useful - What did you take from chemical engineering that's useful in IT | What does chemical engineering bring to IT
Mainly, how to troubleshoot when you can't just run things again.
In a lab, you can't repeat an experiment twenty times to find where it broke.
So when something fails, you reason back with the chemistry.
For example, if the protein got contaminated, maybe a material wasn't autoclaved.
Or maybe a step wasn't sealed properly.
I bring that to incidents.
I think about which step could cause this symptom.
And I don't go down paths that I know can't be the cause.

## incident_hard_amadeus - Tell me about a difficult incident you handled
The situation was that users at one airport couldn't log in to their backup environment in another region.
My job was to find the cause.
So what I did was go first to that region's gateway logs in Splunk.
Their logins went from normal to only failures after one night, all with the same reason: the authentication server denied access.
So I ruled out the network and the application.
Then I looked for recent changes on those users.
The result was that I found the cause: those accounts had been migrated to a new authentication mechanism, and the backup region didn't support it yet.
I documented it with the evidence, and the SRE team confirmed it and owned the fix.
What I learned is to let the logs tell me what kind of change to look for.

## recent_changes_how - What recent changes were you looking for | How did you find the recent changes | How do you check recent changes | What kind of changes do you look for
I look for changes on the affected service or users, right before the failures started.
But first, I narrow down in the logs where it fails.
That tells me what kind of change to look for.
For example, last week the logs showed one group of users rejected by authentication.
So I looked for changes on those users.
That's how I found a user migration.
The failures started about five minutes after it was deployed.

## login_failure_case - Tell me about a recent incident | Give me a concrete example of an incident | How did you correlate the logs | What did the logs or timestamps show | What was the change that caused it | Who fixed it
Last week, users at one airport couldn't log in to their backup environment in another region.
I went to Splunk, to the logs of that region's Citrix NetScaler gateways.
First, I checked the timeline.
Before that, those users logged in normally every day.
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
A migration of those accounts was deployed, and about five minutes later the failures started.
After it, every attempt failed.
I documented that as the likely cause, and the SRE team confirmed it.
The accounts had moved to Keycloak, and the backup region didn't support it yet.
(One more detail if they push on numbers: the failure counts were indexed events that looked duplicated, so I didn't report them as unique attempts. The only timing number to say is "about five minutes" between the deploy and the failures.)

## do_differently - Looking back, is there anything you would do differently | Looking back, is there anything you would do differently if that happened again | Is there anything you would do differently | Anything you would do differently if it happened again | What would you do differently if that happened again | What would you change next time | What did you learn from that incident
(About the investigation itself. Never answer with the triage script, and never say it was built after this incident: that timing is not in the notes.)
Yes, one thing: I would look for recent changes earlier.
That time, I first ruled out the network and the application, and only then searched for changes.
But the logs already showed one group of users failing with the same reason.
That pattern usually means something changed for those users.
So next time, as soon as I see a pattern like that, I would check recent changes in parallel.
That would have pointed to the migration sooner.

## login_contribution - What was your concrete contribution | What was your own part, not the team's | What did you do yourself in that incident
(Maria's own account, 2026-10-13. The change search tool's name is not in the notes: never name it.)
My part was the diagnosis.
First I ruled out infrastructure, network and the client side, from the logs I can see.
Then I searched for recent changes in an internal tool.
I saw that a user migration was deployed, and the failures started about five minutes later.
I documented the timing, the error and the affected users.
Then I handed it to the SRE team, and they confirmed it and owned the fix.
That configuration is theirs, not mine.

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
But no read-only role enforces that yet, and that's what I would add next.
And I always check the findings myself.

## hackathon_secure_tunnel - Tell me about a hard technical challenge
The situation was the AWS LATAM New Hire Jam in 2025, with 14 challenges, and my team was one person short.
My job was one of the hardest challenges: connecting two VMs with a secure, authenticated tunnel.
The deployment kept failing.
So what I did was, instead of guessing, read the whole spec again.
I found a key requirement that showed my environment was wrong from the start.
Then I redeployed once, clean, and checked each step.
The result was that no other team completed that challenge.
We were the only LATAM team to finish all 14, and we won.
What I learned is to read the full spec, question my own setup, and rebuild clean.

## proud_project_landing_pages - What project are you most proud of
The situation was that at AWS, the sales team ran internal campaigns of four weeks, about every two months, and each one needed a page where the sales people could follow their KPIs, prizes and team results.
Those landing pages were going to cost about 2,000 dollars per campaign from an outside vendor.
So I offered to build them in-house, and that became my job.
So what I did was build the first one in about four days.
I used only Amazon's approved services and followed the internal rules.
I read the internal docs until I found a supported way to use my own HTML and CSS.
I also collected feedback from teams across LATAM.
The result was that I built all of them.
More than 200 sales people used them in each four-week campaign, with KPI tracking and dashboards.
That's where I proved I can deliver, even when people doubted an intern.

## landing_pages_tech - What service did you use to host the landing pages | How did you build the landing pages technically | Which tools did you use for the dashboards
The pages lived on Amazon's internal wiki, because that was the approved place for the HTML.
I found out how to add my own formatting there with HTML and CSS.
I couldn't use JavaScript, but I managed well without it.
For the charts, I used Amazon QuickSight.
I also used it to store and organize the campaign data.

## conflict_lab_cheese - Tell me about a time you disagreed with your team | A conflict with a teammate
The situation was a chemical engineering lab, and my group didn't trust me at first.
My job was to get the milk for making cheese.
They wanted UHT whole milk.
But I had read that the heat changes the proteins, so it doesn't curdle well.
They didn't believe me, so what I did was, instead of arguing, buy both.
The result was that after three hours, theirs didn't curdle, and mine worked.
So we didn't lose a lab day.
What I learned is to bring evidence and a plan B, and next time to share the source first.

## kubernetes_openshift - What is your experience with Kubernetes | Have you worked with OpenShift
At Amadeus, I troubleshoot microservices on Linux and Kubernetes, including OpenShift.
That means recycling pods, and checking health and performance in Grafana and Prometheus.
When it needs engineering, I escalate with written evidence, and I document runbooks.
On hardening, I know the main ideas: RBAC, resource limits and restart behaviour.
I also see how bad configurations show up as incidents.
But I haven't done hardening work myself yet, and that's where I want to grow.

## python_and_scripting - What is your experience with Python and scripting | Have you done shell scripting | Do you know PowerShell or bash | What programming languages do you like using | What kind of projects have you been doing | Software development experience | What kind of programming languages do you like using or projects you've been doing
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
Today, I would add RBAC for the flow's identity, plus expiry dates and rotation on the secrets.
And I would send the vault's access logs to alerts.

## aws_internship_technical - What did you do at AWS | Tell me about your internship at AWS | What did you do technically at AWS | What was your role at AWS | Share a bit more about what you did at AWS
(Interview 2026-10-14: Maria said "I was nothing in particular" here. Never play it down: say the technical work.)
At AWS, I was in the sales organization for Latin America, but my work there was technical.
I built the campaign landing pages in-house, instead of paying an outside vendor.
I wrote them in HTML and CSS, and built the dashboards in Amazon QuickSight.
More than two hundred sales people used them in each campaign.
I also built a multi-agent prototype in Python, with the AWS CDK and Bedrock.
And at a hackathon, I connected two VMs with a secure, authenticated tunnel, and we won.
So I was in sales, but I always went for the technical side.

## aws_how_technical - How technical was your work at AWS really | What did you personally build at AWS | You were in a sales organization rather than a software engineering team, how technical was your work | How technical was your work really, what did you personally build | Was your AWS internship technical
(Maria's own words, practice 2026-10-15: the landing pages were NOT her assigned task at first; she was only going to organize them. She proposed building them to her manager. The multi-agent prototype was her own initiative, to learn more as a solutions architect.)
Yes, it was technical, even though I sat in a sales organization.
They gave me a path towards sales, but I always looked for the technical side, and if a task wasn't technical, I found a way to make it technical.
For example, the sales team ran internal campaigns of four weeks, about every two months, and each one needed a page where the sales people could follow their KPIs, prizes and team results.
Those landing pages were going to cost about two thousand dollars per campaign from an outside vendor.
At first, my task was only to organize them, not to build them.
So I told my manager: I can build them, you save the money, and I learn.
I wrote them in HTML and CSS on Amazon's internal wiki, and built the dashboards in Amazon QuickSight.
More than two hundred sales people used them in each campaign.
I also built a multi-agent prototype in Python with the AWS CDK and Bedrock, on my own initiative, to learn more as a solutions architect.

## vm_experience - Any deployment of virtual machines | Have you deployed virtual machines | What is your experience with virtual machines
(Interview 2026-10-14: Maria said no here; the hackathon is the answer.)
Yes, partly.
At an AWS hackathon, I had to connect two VMs with a secure, authenticated tunnel.
The deployment kept failing, so I read the whole spec again.
I found my environment was wrong from the start, so I redeployed it clean.
No other team completed that challenge.
At Amadeus, I work more with containers on Kubernetes than with VMs.

## config_management - Do you use any configuration management | Are you familiar with Puppet or Ansible or Chef | Configuration management systems for Linux | Whether you use any kind of configuration management systems | Maybe Puppet or Ansible you're not familiar with either Chef
Not Puppet or Ansible directly.
The closest I've done is infrastructure as code with the AWS CDK, in Python.
There, the setup is defined in code, so it's applied the same way every time.
That's the same idea behind Puppet and Ansible: nobody changes servers by hand.
So I would need to learn your tool, but the idea is already familiar to me.

## personal_incident_volume - How many incidents do you handle per day | Roughly how many incidents do you personally handle | How many incidents do you handle yourself | How many tickets do you handle per day | How many incidents per week do you handle | Your operation handles a large volume of incidents, how many do you handle
(Maria, 2026-10-15: it varies a lot; some days only about ten, and it has gone up to hundreds; the team organized itself. The ~4,600/week is the whole operation. Never say she alone handled hundreds; no exact personal average is in the notes.)
The 4,600 a week is the whole operation, not just me.
For me, it varies a lot from day to day.
On a quiet day, it can be around ten incidents.
But it has gone up to hundreds, and on those days we organized as a team to split them.
So I'm used to both: going deep on one case, and prioritizing fast when the queue explodes.

## finance_interest - Do you have any personal experience with trading or investing or an interest in finance beyond the technology | Not much about financial markets themselves | Do you have any personal experience with trading or investing | Do you have an interest in finance beyond the technology | Why are you interested in financial markets | What is your interest in finance | Any interest in trading or investing
(Maria, 2026-10-15: her father is an industrial engineer; he has always taught her to value trading and motivated her to learn it; he shows her and explains it. Whether she trades or invests herself is NOT in the notes: never claim she does, and never say "I have no experience".)
Yes, and for me it's personal. It started at home.
My father is an industrial engineer, and he has always followed the markets.
Since I was young, he has shown me how trading works and explained it to me, and he always motivated me to learn it.
So talking about markets feels a bit like being at home.
What I add now is the engineering side. In trading, a system has to be correct and fast at the same time.
That's why Optiver feels like the place where both of those things meet.

## father_lesson - Can you give me one concrete thing you learned from him that stuck | What did you learn from your father about markets | One concrete thing you learned from him | What is one lesson from your father that stuck
(Maria, 2026-10-15: she used to think markets were random and recently argued with him about it; he made her realize it isn't pure chance: there are patterns, and you don't win every time, but in the long run the edge wins, like the casino.)
The biggest one is that markets are not as random as I thought.
I used to think it was just luck, and recently we actually argued about it.
But he made me realize that there are patterns, and a way to reason about them.
You won't be right every time, but with a small edge, you win in the long run.
He compared it to a casino: each game looks random, but the house sets the rules so that it always wins over time.
That changed how I see it. It's about the edge and the long run, not about one single bet.

## market_making - What is market making | What exactly is market making | How does a firm like Optiver make money from it | In your own words, what exactly is market making, and how does a firm like Optiver make money from it | How does Optiver make money | What does a market maker do | What is an edge
(General market knowledge, not Maria's experience. Keep it simple; never claim she has traded. Vocabulary: the bid-ask gap is the SPREAD; the EDGE is the small statistical advantage. No casino here: the casino belongs only to 'father_lesson', once per call.)
A market maker quotes a price to buy and a price to sell the same asset, at the same time.
The difference between those two prices is the spread.
The firm makes money from that spread, NOT by betting on direction.
Each trade can go either way, but with a small positive edge repeated thousands of times, the expected value adds up, as long as you manage the risk.
The main risk is a stale quote: if my price is old, a faster trader picks me off.
That's why speed and correct systems matter so much: they protect that small edge.
And by always being there to buy and sell, market makers also give liquidity to the market.

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

## on_call_night_shifts - Are you okay with on-call and night shifts
Yes.
At Amadeus, I'm already in a 24/7 follow-the-sun team.
Some weeks, that includes weekend shifts.
That's part of running real systems, so I'm open to the on-call rota here.

