---
framework_version: 1.0.0
---

# Interview Preparation Guide

<!-- SETUP: STAR examples are personalized by running /setup based on your actual experience -->

## STAR Format

Structure answers as: **Situation** (context), **Task** (your responsibility), **Action** (what you did), **Result** (outcome).

Keep answers to 1-2 minutes. Be specific. End with what you learned or would do differently.

## Ready-Made STAR Examples

Grounded in the CV, LinkedIn, and the Rootstrap bios page. Numbers appear only where they are real (62%→86%, −54%); a result without a figure is phrased honestly and can be strengthened later with a number recovered from git history / PR descriptions.

### 1. PostgreSQL & API performance optimization (Problem-solving / Performance)
**S:** At Rootstrap, the Rails apps we shipped for clients (Special Olympics, Go! Coaching) had slow endpoints and inefficient database access that degraded the user experience.
**T:** Diagnose and fix the performance problems in PostgreSQL and the REST APIs without breaking existing functionality.
**A:** Detected N+1 queries with Prosopite, added missing indexes, profiled slow queries with EXPLAIN/ANALYZE, applied query preloading and batching, and added pagination, caching, and rate limiting to the REST APIs. Kept query logic clean with Service Objects and Query Objects.
**R:** Eliminated the N+1 queries and cut the number of SQL queries per request, with a measurable drop in response times and a database that scaled to more load.
**Use for:** "tell me about a hard technical problem you solved", "how do you optimize performance"

### 2. Test coverage 62% → 86% with CI/CD (Reliability / Process improvement)
**S:** The codebase had roughly 62% test coverage, and production regressions were a recurring problem.
**T:** Raise coverage and cut regressions by building out the RSpec suite and wiring it into CI/CD.
**A:** Wrote comprehensive RSpec suites (unit, request, system) using FactoryBot and Shoulda Matchers, integrated them into CI/CD so failing tests block merges, and prioritized the critical paths.
**R:** Raised coverage from 62% to 86% in 2 quarters and cut production regressions by 54%.
**Use for:** "how do you ensure code quality", "tell me about improving a process"

### 3. Football Club Admin — sports management API (Full-stack delivery / Initiative)
**S:** Snappler needed a backend API for a sports/football club management system, paired with a React + TypeScript frontend.
**T:** Build the Ruby on Rails backend API and integrate it with the frontend.
**A:** Developed the backend API in Ruby on Rails (RESTful, MVC) and integrated it with the React + TypeScript frontend, collaborating with design and QA.
**R:** Delivered the system end to end for the client, from API design through to a working frontend.
**Use for:** "tell me about a feature you built end to end", "describe a project you're proud of"

### 4. Aero Admin / Aero Tarifario — legacy airline system (Adaptability / Legacy)
**S:** Snappler maintained a legacy airline system (Aero Admin, plus Aero Tarifario for fares) built on CoffeeScript, jQuery, and legacy Ruby.
**T:** Maintain, fix, and extend the legacy codebase without introducing regressions.
**A:** Worked across the legacy CoffeeScript/jQuery/Ruby stack to add new functionality, support the product, and resolve issues.
**R:** Kept the system running reliably for a major airline client while shipping new features and improvements.
**Use for:** "tell me about working with legacy code", "how do you handle unfamiliar or old systems"

## Common Tough Questions

### "Why did you leave [previous company]?"
> [PREPARE YOUR ANSWER - be honest, forward-looking, no negativity about former employer]

### "You don't have [specific skill/experience]."
> [PREPARE YOUR ANSWER - acknowledge the gap, bridge to adjacent experience, show willingness to learn]

### "Where do you see yourself in 5 years?"
> [PREPARE YOUR ANSWER - show ambition aligned with the role's growth path]

### "What's your biggest weakness?"
> [PREPARE YOUR ANSWER - genuine weakness with concrete mitigation strategy]

### "Why this company specifically?"
> Customize per company. Must reference: specific projects, company values, market position, or team structure. Never give a generic answer.

## Questions You Should Ask Interviewers

### About the Role
- "What does a typical week look like in this role?"
- "What would success look like in the first 6 months?"
- "What's the biggest challenge the team is facing right now?"

### About the Team
- "How big is the team, and how do you divide work?"
- "What does the development/project lifecycle look like, from idea to production?"
- "How do you onboard new team members?"

### About Tech & Growth
- "What's your current tech stack for [relevant area]?"
- "Is there room to grow into more architectural or strategic decisions?"
- "How does the team stay current with new tools and methods?"

### About Culture (use these to prevent disappointment)
- "How would you describe the team culture?"
- "What does professional development look like here?"
- "Is there flexibility for remote/hybrid work?"
- "What's the balance between development/new projects and maintenance work?"
- "How would you describe the leadership style in this team?"
- "What do people who thrive here have in common?"

## Phone/Video Interview Tips
- Have STAR examples written out (use this file)
- Keep a glass of water nearby
- Smile when speaking (it changes your tone)
- Ask for clarification if a question is vague
- It's OK to take 5 seconds to think before answering
- End with: "Is there anything else you'd like to know about my background?"

## After the Application (Best Practice)

### Follow-Up Etiquette
- **Don't call to "stand out"** or to learn more about the role post-submission - this risks a negative impression
- If the employer specified a timeline, respect it and wait
- If no timeline was given and significant time has passed (2+ weeks), a brief call to ask about status is acceptable
- If you have genuinely new, relevant information to share, a short follow-up is fine

### Thank-You Notes
- When you receive any update (interview invitation, rejection, or status update), send a brief thank-you message
- Express appreciation for their time and the process
- Keep it short (2-3 sentences)

## Roleplay Guidelines
When the user asks for interview practice:
1. Ask which role/company to simulate
2. Start with easy warm-up questions ("Tell me about yourself")
3. Progress to role-specific technical questions
4. Include 1-2 behavioral questions using the competencies from the job posting
5. End with a tough question or curveball
6. After each answer, give brief feedback: what worked, what to sharpen
7. Suggest which STAR example would work best for each question
