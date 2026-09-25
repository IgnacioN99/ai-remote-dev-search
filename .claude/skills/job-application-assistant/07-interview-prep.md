---
framework_version: 1.0.0
---

# Interview Preparation Guide

<!-- SETUP: STAR examples are personalized by running /setup based on your actual experience -->

## STAR Format

Structure answers as: **Situation** (context), **Task** (your responsibility), **Action** (what you did), **Result** (outcome).

Keep answers to 1-2 minutes. Be specific. End with what you learned or would do differently.

## Ready-Made STAR Framework Examples

Tailor these STAR patterns to your verified background documented in `CLAUDE.md` and `01-candidate-profile.md`. Numbers appear only where they are real and verifiable; a result without a figure is phrased honestly and can be strengthened later with data recovered from pull requests or monitoring dashboards.

### 1. Database & API Performance Optimization (Problem-solving / Performance)
**S:** At [PREVIOUS_COMPANY], high traffic and unoptimized database queries led to latency spikes and slow API responses during peak hours.
**T:** Diagnose and resolve the performance bottlenecks in the database and API endpoints without regression.
**A:** Profiled slow queries using query explain plans and profiling tools, identified missing database indexes, implemented batch loading and caching, and eliminated N+1 query patterns. Refactored query logic using modular service/query abstractions.
**R:** Reduced average endpoint response latency significantly and decreased database CPU utilization, enabling the system to scale smoothly under higher concurrent loads.
**Use for:** "tell me about a hard technical problem you solved", "how do you optimize system performance"

### 2. Automated Test Coverage & CI/CD Pipeline (Reliability / Quality Improvement)
**S:** A critical codebase suffered from low automated test coverage, resulting in recurring regressions in production.
**T:** Raise code quality and prevent production regressions by building out automated test suites and integrating them into continuous integration.
**A:** Wrote comprehensive unit, integration, and end-to-end tests for critical business paths. Configured the CI/CD pipeline to gate pull requests and block merges on test failures.
**R:** Increased test coverage across the application and drastically reduced defect rates and regression rollbacks in production.
**Use for:** "how do you ensure code quality", "tell me about improving an engineering process"

### 3. End-to-End Feature Delivery & Integration (Architecture / Initiative)
**S:** The team needed a new customer-facing system with complex data flows between backend services and a modern web frontend.
**T:** Architect and implement the backend APIs, establish clean schema contracts, and integrate seamlessly with the frontend application.
**A:** Designed modular REST/gRPC endpoints, implemented robust validation and error handling, and collaborated closely with product and frontend engineers during integration and QA.
**R:** Shipped the feature on schedule, meeting all user acceptance criteria and providing an intuitive, performant user experience.
**Use for:** "tell me about a feature you built end to end", "describe a project you're proud of"

### 4. Legacy Codebase Modernization (Adaptability / Refactoring)
**S:** The company relied on a legacy service with aging dependencies and outdated architectural patterns that was difficult to extend.
**T:** Maintain system reliability while incrementally refactoring and modernizing components to enable new capabilities.
**A:** Added automated regression tests around critical paths before touching legacy code, followed the strangler pattern to isolate legacy modules, and introduced modern libraries and patterns gradually.
**R:** Kept existing operations stable without downtime while dramatically improving developer velocity and reducing technical debt.
**Use for:** "tell me about working with legacy code", "how do you handle unfamiliar or old systems"

## Common Tough Questions

### "Why did you leave [previous company]?"
> [PREPARE YOUR ANSWER - be honest, forward-looking, focus on growth, no negativity about former employer]

### "You don't have [specific skill/experience]."
> [PREPARE YOUR ANSWER - acknowledge the gap, bridge to adjacent experience, show track record of fast learning]

### "Where do you see yourself in 5 years?"
> [PREPARE YOUR ANSWER - show ambition aligned with the role's growth path]

### "What's your biggest weakness?"
> [PREPARE YOUR ANSWER - genuine weakness with concrete mitigation and improvement strategy]

### "Why this company specifically?"
> Customize per company. Must reference: specific engineering challenges, company mission, market position, or team structure. Never give a generic answer.

## Questions You Should Ask Interviewers

### About the Role & Engineering Culture
- "What does a typical sprint or release cycle look like for this team?"
- "What would success look like in the first 6 months?"
- "What's the biggest technical challenge the engineering team is currently tackling?"
- "How does the team approach code reviews, testing, and managing technical debt?"
