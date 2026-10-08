**[00:06] Pregunta:** Hi, Maria. Nice to meet you. Can you hear me okay?

Yes, I can hear you perfectly, Krystyna. Nice to meet you too, thanks for having me.

---

**[00:55] Pregunta:** Sorry. I think the audio cut out for a second there. In all, I only caught the end, but I'm I'm good. Thank you for asking. It's been a busy day. But a good one. How are you? How's your day going over there in Bokta?

I'm doing great, thank you. It's morning here in Bogotá, and I'm excited for this conversation.

No worries about the audio, I could hear you fine. Glad it's been a good busy day for you. I'm ready whenever you'd like to start.

---

**[02:01] Pregunta:** Great. That's so lovely to hear. So just a quick note before we start. We sometimes use AI Which not with note taking during the call. It's only used for the assessment and feedback Nothing else? Is that okay with you? And here's the plan for today. I will tell you a little about Docker and the Rope. Then I love to hear about you. Your journey and some of your experiences. And we will have, we will leave time at the end for your questions. Sounds good? Quick intro from my side. Docker Planner is the company behind doctor... Doctoralia here in Spain and in SLA... And in Latin America. Sini leikarts in Poland, and Myovoter in Italy. We connect patients with doctors, and we also build the software Docker... Docker's and clinics use to run their practice. On the tech side, we have engineering hubs in Barcelona and Warsaw. And this early career role is part of a group of junior engineers. We are hiring to join different product teams. It's a strong coding and problem solving role, so we are looking for people who love to build. So let's start with you. Could you walk me through your background And what body to apply to Docker Planner?

That's totally fine with me, thank you for letting me know.

I have two degrees from Universidad de los Andes, in Systems and Computer Engineering and Chemical Engineering, finished in 2025.

After that I joined AWS as an intern for ten months, from June 2025 to March 2026. I built internal web applications for campaign tracking that went live and were used day to day by more than two hundred sales professionals across Latin America. I also worked on a multi-agent prototype using Amazon Bedrock AgentCore and Strands Agents, with agents built through Amazon Q Developer CLI.

During that time, I was also part of a two-person team that won the AWS LATAM New Hire Jam Day hackathon. We were the only Latin America team to finish all fourteen challenges.

Since April I've been a Junior Cloud Support Engineer at Amadeus, troubleshooting microservices on Kubernetes and OpenShift for platforms that run twenty four seven. That gave me a real sense of what production looks like.

Now I want to go back to building software full time, on a product people depend on. That's exactly why this role at Docplanner caught my attention.

---

**[07:50] Pregunta:** Thank you, Maria. That's really nice journey, and congratulations on the hackathon. Finishing all 14 challenges as a team of two is impressive. I'd like to dig into a couple of things you mentioned. You said you worked on a multiaging prototype at AWS. I'm not an engineer myself. So could you explain it to me, in simple terms? What did it actually do, and what was your part in it?

Sure, happy to explain it simply.

**Think of it as** a small team of AI agents working together instead of one person doing everything. There was an orchestrator agent that split up the work, and specialized agents that handled specific tasks.

**It used tool calling,** so the agents could actually take actions, not just answer questions. It also had memory and could search a knowledge base to find relevant information before responding.

**My part was** building it in Python with the AWS CDK, running on Amazon Bedrock AgentCore. I also used Amazon Q Developer CLI to help build the agents, including ones for email automation.

**It was a prototype,** so the goal was to show how this kind of multi-agent system could work for real tasks, not a finished product.

---

**[10:44] Pregunta:** Oh, I like the small team instead of one person image. That makes it much clearer for me. Thank you. And who was it for? What problem was the prototype meant to solve? Was there a team or a use case behind it?

**It was built within the AWS team I was part of during the internship.** The idea was to explore how a multi-agent setup could help with things like email automation and content generation, tasks that normally take someone a lot of manual time.

**So one of the agents I built, for example, handled an email automation use case.** The orchestrator would break down a request and the specialized agents would handle the actual drafting and actions.

**But to be clear, it was a prototype, not a finished product.** The goal was to demonstrate the approach was workable for real use cases, not to deploy it for end users.

---

**[16:32] Pregunta:** Got it. So it was about saving people manual type on repetitive work, and you were clear it was a prototype. Thanks. That's helpful. Let's let's talk about a bit about motivation. You're currently at Amadeus. I have been there since April. And white And why Docker Planner specifically?

There are three reasons for me.

**First, impact.** Docplanner's product reaches millions of patients across Spain and Latin America. That scale really matters to me.

**Second, the engineering culture.** AI-assisted development by default, and you value signals over credentials. That fits how I already work.

**Third, healthcare and AI together.** I come from chemical engineering, and my thesis applied machine learning to proteins. Docplanner sits right at that intersection of healthcare and technology.

---

**[38:13] Pregunta:** Oh, that's a great answer. I especially, like, you mentioned signals over credentials. It's something we really believe. And They didn't mention Ambarios, though. I'm curious. Six months in, quite short. What were you... Start looking already. Is something not working for you there?

Nothing's wrong there, honestly.

**I've learned a lot** about production systems at Amadeus. But my role there is support, not building.

**And building is what I want to do.** That's what I did at AWS, and it's what I enjoy most.

**I'm also looking for** a stable Monday to Friday schedule. This role gives me both of those things.

---

**[39:57] Pregunta:** Okay. That makes sense. Thank you for being open about it. And just so I understand, what's your schedule like at AWS right now? Imagine wiring. Wanting Monday to Friday.

Right now at Amadeus I'm on a 24/7 Follow-the-Sun rotation, so it's not a fixed Monday-to-Friday schedule.

That rotation is normal for production support work. But it's one more reason I want to move into a building role with a stable schedule.

---

**[43:40] Pregunta:** I understand. Thank you for sharing. Have time for family and friends' matters. And our engineering team, Jenny, will work as time Monday to Friday schedule so that part should fit well. Okay. Let's move to some examples for your experience. Can you tell me about a time you've faced a really difficult challenge and how you overcome... Overcame it?

One that comes to mind is the AWS LATAM New Hire Jam Day hackathon, in 2025.

**The context was** fourteen technical challenges, and my team was just two interns. That's one person fewer than the other teams.

**I took on** one of the hardest challenges. I had to connect two virtual machines through a secure, authenticated tunnel. **But** my deployment kept failing.

**So instead of guessing,** I went back and re-read the whole specification. **And at the very bottom,** I found what was wrong in my own setup.

**So I rebuilt it** once, cleanly, checking every step carefully.

**In the end,** we were the only LATAM team to complete all fourteen challenges, and we won.
