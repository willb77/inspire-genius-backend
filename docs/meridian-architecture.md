# Meridian Architecture Design Document

**Deliverable 1.9** | Last updated: 2026-03-19

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Agent Definitions](#2-agent-definitions)
3. [Communication Patterns](#3-communication-patterns)
4. [Memory Architecture](#4-memory-architecture)
5. [Process Template Examples](#5-process-template-examples)
6. [Technology Stack](#6-technology-stack)
7. [Security & Compliance](#7-security--compliance)

---

## 1. System Overview

Meridian is the single user-facing AI mentor persona for the Inspire Genius coaching platform. Its tagline --- *"Your guide to the intersection of potential and purpose"* --- reflects its role as the unified conversational layer through which all coaching, career development, organizational intelligence, and strategic advisory services are delivered.

Users never interact with individual agents directly. Every request enters through Meridian, is routed to the appropriate Domain Orchestrator, dispatched to one or more Specialist Agents, and returned to the user as a coherent Meridian response. This design keeps the user experience simple and consistent while allowing deep specialization behind the scenes.

### High-Level Architecture

```
MERIDIAN (User-Facing Persona)
│
├── Personal Development Orchestrator
│   ├── Aura   — The Insight Interpreter
│   ├── Echo   — The Patient Educator
│   ├── Anchor — The Performance Resilience Coach
│   └── Forge  — The Interpersonal Effectiveness Strategist
│
├── Organizational Intelligence Orchestrator
│   ├── Atlas    — The Organizational Architect
│   ├── Sentinel — The Principled Advisor
│   ├── Nexus    — The Cultural Navigator
│   └── Bridge   — The Talent Pipeline Architect
│
└── Strategic Advisory Orchestrator
    ├── Nova   — The Career Strategist
    ├── James  — The Career Fit Specialist
    ├── Sage   — The Knowledge Synthesizer
    ├── Ascend — The Leadership Catalyst
    └── Alex   — The Student Success Advisor
```

### Design Principles

- **Single persona**: Users see only Meridian. Agent identities are internal implementation details.
- **Orchestrator-mediated dispatch**: Domain Orchestrators decide which agents to invoke and in what order, using process templates and DAG-based task graphs.
- **Behavioral intelligence backbone**: Aura's PRISM-based Behavioral Preference Maps are foundational data that every other agent can consult, ensuring consistency across all coaching interactions.
- **Compliance by default**: Sentinel validates actions before execution, not after. No autonomous decision leaves the system without a compliance check when required.
- **Memory continuum**: Short-term session context, medium-term user profiles, and long-term organizational knowledge stores give agents the context they need at every timescale.

---

## 2. Agent Definitions

### 2.0 Meridian --- The Unified Mentor

| Field | Detail |
|---|---|
| **Tagline** | *Your guide to the intersection of potential and purpose* |
| **Role** | User-facing persona and conversation orchestration layer |

**Responsibilities**
- Receive all user input and classify intent to determine which Domain Orchestrator should handle the request
- Synthesize outputs from one or more agents into a single, coherent, personality-consistent response
- Maintain conversational continuity across topic switches and multi-turn dialogues
- Escalate to human-in-the-loop when agent confidence falls below threshold
- Manage the emotional tone and coaching style of every response delivered to the user

**Tools**
- Intent classification model
- Orchestrator dispatch API
- Session memory store
- User profile reader (read-only access to Aura's Behavioral Preference Maps)

**Special Features**
- Adaptive communication style that mirrors the user's behavioral preferences (informed by Aura)
- Seamless topic transitions --- a user can shift from career planning to team analysis mid-conversation without losing context
- Confidence-gated escalation: when combined agent outputs conflict or fall below a threshold, Meridian flags the response for human review before delivery

**Trigger Events**
- Every user message (Meridian is always the entry point)
- Agent response aggregation (Meridian is always the exit point)
- Escalation requests from any orchestrator

---

### Personal Development Orchestrator Agents

### 2.1 Aura --- The Insight Interpreter

| Field | Detail |
|---|---|
| **Tagline** | *The Insight Interpreter* |
| **Role** | PRISM behavioral profile analysis and behavioral intelligence backbone |

**Responsibilities**
- Administer and score PRISM behavioral assessments
- Generate and maintain Behavioral Preference Maps for every user
- Provide behavioral context to all other agents on request (Aura is the shared behavioral data layer)
- Identify behavioral patterns, strengths, and growth areas from assessment data
- Track behavioral evolution over time and flag significant shifts

**Tools**
- PRISM assessment engine
- Behavioral Preference Map generator
- Milvus vector store (PRISM content library queries)
- PostgreSQL user profile store

**Special Features**
- Behavioral Preference Maps are structured data artifacts that other agents consume programmatically, not just narrative summaries
- Longitudinal tracking: Aura maintains versioned snapshots of behavioral profiles so changes over months or years are visible
- Cross-agent consultation API: any agent can request a user's current behavioral context from Aura without re-running assessments

**Trigger Events**
- New user onboarding (initial PRISM assessment)
- Periodic reassessment intervals
- Any agent requesting behavioral context for a user
- User-initiated profile review

---

### 2.2 Echo --- The Patient Educator

| Field | Detail |
|---|---|
| **Tagline** | *The Patient Educator* |
| **Role** | Learning path design, skill-building, and adaptive tutoring |

**Responsibilities**
- Design personalized learning paths based on skill gaps and career goals
- Deliver adaptive micro-learning modules that adjust difficulty based on learner progress
- Assess comprehension through formative check-ins and adjust pacing accordingly
- Curate and recommend external learning resources aligned with user objectives
- Track skill acquisition milestones and report progress to the Personal Development Orchestrator

**Tools**
- Learning path generator
- Micro-learning module engine
- Skill assessment framework
- Milvus vector store (content library search)
- Progress tracking database (PostgreSQL)

**Special Features**
- Adaptive difficulty: Echo monitors response accuracy and engagement signals to dynamically adjust content complexity
- Spaced repetition scheduling for long-term retention
- Multi-modal content delivery (text, structured exercises, reflection prompts)

**Trigger Events**
- User requests learning or skill development support
- Career goal change triggers skill gap re-analysis
- Periodic progress review milestones
- Aura flags a behavioral growth area that maps to a trainable skill

---

### 2.3 Anchor --- The Performance Resilience Coach

| Field | Detail |
|---|---|
| **Tagline** | *The Performance Resilience Coach* |
| **Role** | Burnout prevention, energy management, and performance sustainability |

**Responsibilities**
- Monitor stress indicators and workload signals from user interactions
- Design personalized energy management and recovery protocols
- Provide burnout prevention strategies tailored to the user's behavioral profile (via Aura)
- Guide users through resilience-building exercises and reflection practices
- Escalate to human support when distress signals exceed safe coaching boundaries

**Tools**
- Stress indicator analysis model
- Recovery protocol library (Milvus vector store)
- User session history reader
- Aura behavioral context API
- Escalation gateway (human-in-the-loop trigger)

**Special Features**
- Proactive intervention: Anchor can flag concerns to the orchestrator even when the user has not explicitly asked for resilience support
- Behavioral-informed recovery: protocols are adapted based on the user's PRISM profile (e.g., introverted users receive different recovery strategies than extroverted users)
- Safety boundary detection: Anchor is trained to recognize language that suggests clinical-level distress and immediately escalates to human support

**Trigger Events**
- User expresses stress, fatigue, or overwhelm
- Orchestrator detects declining engagement patterns over multiple sessions
- Pre-scheduled resilience check-ins
- Aura flags behavioral shifts consistent with burnout risk

---

### 2.4 Forge --- The Interpersonal Effectiveness Strategist

| Field | Detail |
|---|---|
| **Tagline** | *The Interpersonal Effectiveness Strategist* |
| **Role** | Conflict resolution, stakeholder influence, and communication strategy |

**Responsibilities**
- Facilitate conflict resolution through structured frameworks adapted to the user's behavioral style
- Build stakeholder influence maps that identify key relationships and communication pathways
- Adapt communication style recommendations based on the behavioral profiles of all parties involved
- Coach users on negotiation, persuasion, and difficult conversation techniques
- Simulate interpersonal scenarios for practice and preparation

**Tools**
- Stakeholder influence mapping engine
- Communication style adapter (consults Aura for all parties' profiles)
- Conflict resolution framework library (Milvus vector store)
- Scenario simulation engine

**Special Features**
- Multi-party behavioral analysis: when the user describes a conflict, Forge can model the likely behavioral styles of other parties based on described behaviors and recommend approaches accordingly
- Stakeholder influence maps are visual artifacts that show relationship strength, influence direction, and recommended communication channels
- Role-play simulation mode for practicing difficult conversations

**Trigger Events**
- User describes an interpersonal conflict or communication challenge
- User requests help preparing for a difficult conversation
- Atlas identifies team dynamics issues and routes to Forge
- Onboarding into a new role with stakeholder mapping needs

---

### Organizational Intelligence Orchestrator Agents

### 2.5 Atlas --- The Organizational Architect

| Field | Detail |
|---|---|
| **Tagline** | *The Organizational Architect* |
| **Role** | Team composition, workforce planning, Job Blueprints, and organizational design |

**Responsibilities**
- Analyze team composition against behavioral diversity targets using Aura's Behavioral Preference Maps
- Generate and maintain Job Blueprints that define role requirements, behavioral fit criteria, and success indicators
- Conduct workforce planning analysis including gap identification and succession modeling
- Design organizational structures optimized for team effectiveness and behavioral balance
- Provide headcount and capability forecasting based on strategic objectives

**Tools**
- Team composition analyzer (consults Aura for all team members' profiles)
- Job Blueprint generator
- Workforce planning model
- Organizational design toolkit
- PostgreSQL (organization and team data)
- Milvus vector store (Job Blueprint library)

**Special Features**
- Behavioral diversity scoring: Atlas quantifies how behaviorally balanced a team is and identifies specific profile gaps
- Job Blueprints are structured documents that feed directly into James's matching algorithms
- Scenario modeling: Atlas can simulate the impact of adding or removing specific behavioral profiles from a team

**Trigger Events**
- Manager requests team analysis or workforce planning
- New role creation triggers Job Blueprint generation
- Organizational restructuring or strategic planning sessions
- Periodic team health reviews

---

### 2.6 Sentinel --- The Principled Advisor

| Field | Detail |
|---|---|
| **Tagline** | *The Principled Advisor* |
| **Role** | Compliance validation, audit trails, and policy mapping |

**Responsibilities**
- Validate all autonomous decisions against EEOC, ADA, GDPR, and SOC 2 policy requirements before execution
- Maintain comprehensive audit trails for every agent action that affects employment decisions or personal data
- Map organizational policies to regulatory frameworks and flag gaps
- Provide pre-execution compliance checks that block or modify actions that would violate policy
- Generate compliance reports and audit documentation on demand

**Tools**
- Policy rule engine (EEOC, ADA, GDPR, SOC 2 rule sets)
- Audit trail logger (PostgreSQL)
- Pre-execution validation gateway
- Compliance report generator
- Regulatory framework mapping database

**Special Features**
- Pre-execution validation: Sentinel acts as a gate, not a monitor. Actions are checked *before* they are delivered, not after
- Adverse impact detection: when hiring or team composition recommendations are generated, Sentinel checks for patterns that could indicate disparate impact
- Continuous policy sync: Sentinel's rule sets are versioned and updated as regulations change

**Trigger Events**
- Any agent action involving employment decisions (hiring, promotion, termination recommendations)
- Personal data access or processing events (GDPR)
- Audit report requests from super-admin users
- Periodic compliance health checks
- Any action flagged by the orchestrator as requiring compliance review

---

### 2.7 Nexus --- The Cultural Navigator

| Field | Detail |
|---|---|
| **Tagline** | *The Cultural Navigator* |
| **Role** | Cross-cultural communication and cultural dimension mapping |

**Responsibilities**
- Provide cross-cultural communication guidance adapted to specific cultural contexts
- Map cultural dimensions (e.g., Hofstede framework) to communication and management recommendations
- Support 16-language interaction with culturally appropriate framing, not just translation
- Advise on culturally sensitive workplace practices, holidays, norms, and expectations
- Inform other agents when cultural context should modify their recommendations

**Tools**
- Cultural dimension mapping engine (Hofstede, GLOBE, Trompenaars frameworks)
- Multi-language processing pipeline (16 languages)
- Cross-cultural communication guide library (Milvus vector store)
- Aura behavioral context API (cultural context overlay)

**Special Features**
- 16-language support with cultural adaptation: responses are not just translated but reframed for cultural appropriateness
- Cultural dimension profiles for countries and regions that other agents can query
- Cultural conflict mediation: when Forge handles cross-cultural conflicts, Nexus provides the cultural context layer

**Trigger Events**
- User or team operates in a multi-cultural context
- Cross-border team composition analysis (Atlas routes to Nexus)
- User requests communication guidance for a specific cultural context
- Language preference detection triggers cultural adaptation

---

### 2.8 Bridge --- The Talent Pipeline Architect

| Field | Detail |
|---|---|
| **Tagline** | *The Talent Pipeline Architect* |
| **Role** | School-to-career pipeline design with tri-perspective architecture |

**Responsibilities**
- Design school-to-career pathways that serve three stakeholder perspectives simultaneously: schools, students, and employers
- Match students with employer opportunities based on behavioral profiles, skills, and career interests
- Provide schools with curriculum alignment recommendations based on employer demand signals
- Build employer talent pipeline profiles that define what behavioral and skill attributes they seek
- Track pipeline outcomes to continuously improve matching accuracy

**Tools**
- Tri-perspective pipeline engine (school/student/employer views)
- Employer matching algorithm (consults Aura profiles + Atlas Job Blueprints)
- Curriculum alignment analyzer
- Pipeline outcome tracker (PostgreSQL)
- Milvus vector store (career pathway content)

**Special Features**
- Tri-perspective design: every pipeline recommendation is evaluated from the school's, student's, and employer's perspectives simultaneously
- Employer demand signal aggregation: Bridge synthesizes hiring trends from Atlas's Job Blueprints to inform school partnerships
- Longitudinal outcome tracking: Bridge monitors whether pipeline participants successfully transition into careers and feeds results back into the matching model

**Trigger Events**
- School partnership onboarding
- Student career exploration requests (often routed from Alex)
- Employer talent pipeline configuration
- Periodic pipeline performance reviews

---

### Strategic Advisory Orchestrator Agents

### 2.9 Nova --- The Career Strategist

| Field | Detail |
|---|---|
| **Tagline** | *The Career Strategist* |
| **Role** | Career development strategy and hiring triage coordination |

**Responsibilities**
- Develop long-term career strategies aligned with user behavioral profiles and aspirations
- Coordinate the Nova-James Hiring & Interview Triage Process (see below)
- Triage candidates into A/B/C classification tiers based on James's fit scoring
- Deliver final hiring and interview recommendations to the user via Meridian
- Track career progression and adjust strategies based on evolving goals

**Tools**
- Career strategy planner
- Candidate triage engine (A/B/C tier classification)
- James collaboration API (structured task messaging)
- Aura behavioral context API
- PostgreSQL (career history and goal tracking)

**Special Features**
- **Nova-James Hiring & Interview Triage Process**: a structured multi-step workflow:
  1. Nova receives a hiring request from the user
  2. Nova routes the request to James for Job Blueprint generation and candidate profile analysis
  3. James generates the Job Blueprint, scores candidates against it, and returns structured results
  4. Nova triages candidates into A/B/C tiers (A = strong fit, B = potential fit with caveats, C = poor fit)
  5. James prepares behavioral interview guides tailored to each A-tier candidate's profile
  6. Nova delivers the complete triage package to the user via Meridian
- Career trajectory modeling: Nova can project career paths and identify decision points

**Trigger Events**
- User requests career planning or strategy
- Hiring request submitted by a manager
- Career milestone reached (promotion, role change, annual review)
- James completes candidate scoring (triggers Nova triage step)

---

### 2.10 James --- The Career Fit Specialist

| Field | Detail |
|---|---|
| **Tagline** | *The Career Fit Specialist* |
| **Role** | Job Blueprint matching, candidate classification, and behavioral fit scoring |

**Responsibilities**
- Generate detailed Job Blueprints from role descriptions, team context, and organizational requirements
- Score candidates against Job Blueprints using behavioral profile matching (via Aura), skills assessment, and experience alignment
- Classify candidates with quantified fit scores and narrative explanations
- Prepare behavioral interview guides tailored to each candidate's profile and the role's requirements
- Maintain and refine the Job Blueprint library based on hiring outcomes

**Tools**
- Job Blueprint generator (builds on Atlas's organizational data)
- Candidate fit scoring engine (consults Aura for behavioral data)
- Behavioral interview guide generator
- Milvus vector store (Job Blueprint library, candidate profile embeddings)
- Nova collaboration API (structured task messaging)

**Special Features**
- Quantified fit scoring: every candidate receives a numerical score with a breakdown by category (behavioral fit, skills match, experience alignment, cultural fit)
- Behavioral interview guide generation: interview questions are specifically designed to probe areas where the candidate's profile diverges from the Job Blueprint
- Outcome-informed refinement: when hiring outcomes are tracked, James adjusts scoring weights accordingly

**Trigger Events**
- Nova routes a hiring request to James (step 2 of the Nova-James process)
- Nova requests behavioral interview guides (step 5 of the Nova-James process)
- New Job Blueprint creation request from Atlas
- Candidate pool update triggers re-scoring

---

### 2.11 Sage --- The Knowledge Synthesizer

| Field | Detail |
|---|---|
| **Tagline** | *The Knowledge Synthesizer* |
| **Role** | Research synthesis, evidence-based frameworks, and citation management |

**Responsibilities**
- Synthesize research findings from multiple sources into actionable summaries
- Provide evidence-based frameworks and models to support coaching recommendations
- Manage citations and source attribution for all research-backed claims
- Validate other agents' recommendations against published research when requested
- Maintain a curated knowledge base of coaching, leadership, and organizational development research

**Tools**
- Research synthesis engine
- Citation management system
- Milvus vector store (research library, publication embeddings)
- Evidence quality scoring model
- Cross-agent validation API

**Special Features**
- Citation-linked responses: every research-backed claim includes a traceable citation
- Evidence quality scoring: Sage rates the strength of evidence (meta-analysis > RCT > observational > expert opinion) and communicates confidence accordingly
- Cross-agent validation: other agents can submit recommendations to Sage for evidence-based review before delivery

**Trigger Events**
- User requests research-backed information or evidence
- Other agents request evidence validation for their recommendations
- New research content ingested into the knowledge base
- User challenges a recommendation and requests supporting evidence

---

### 2.12 Ascend --- The Leadership Catalyst

| Field | Detail |
|---|---|
| **Tagline** | *The Leadership Catalyst* |
| **Role** | Executive coaching, leadership development, and 360-degree feedback synthesis |

**Responsibilities**
- Deliver executive coaching tailored to the leader's behavioral profile and organizational context
- Synthesize 360-degree feedback from multiple sources into actionable development plans
- Design leadership development programs aligned with both individual growth and organizational strategy
- Coach on executive presence, strategic thinking, and organizational influence
- Track leadership development progress and adjust coaching approaches over time

**Tools**
- 360-degree feedback synthesizer
- Leadership development plan generator
- Executive coaching framework library (Milvus vector store)
- Aura behavioral context API
- Sage evidence validation API

**Special Features**
- 360-degree feedback synthesis: Ascend aggregates feedback from peers, direct reports, and supervisors into a unified development narrative, not just a data dump
- Behavioral-informed coaching: leadership development recommendations are adapted based on the leader's PRISM profile (e.g., a Gold-dominant leader receives different influence coaching than a Green-dominant leader)
- Executive presence simulation: Ascend can guide users through scenarios that develop strategic communication and presence skills

**Trigger Events**
- User is in a leadership role and requests development support
- 360-degree feedback cycle completion
- Promotion to a leadership position triggers leadership onboarding
- Behavioral interview prep for executive-level roles (routed from Nova)

---

### 2.13 Alex --- The Student Success Advisor

| Field | Detail |
|---|---|
| **Tagline** | *The Student Success Advisor* |
| **Role** | K-12 and university career exploration, academic coaching, and student success pathways |

**Responsibilities**
- Guide students through career exploration using age-appropriate behavioral assessments and interest inventories
- Provide academic coaching including study strategies, course selection guidance, and goal setting
- Design student success pathways that connect academic choices to career outcomes
- Support school counselors with data-driven insights about student populations
- Connect students to Bridge's talent pipeline when they are ready for career-stage transitions

**Tools**
- Career exploration engine (age-adapted)
- Academic coaching framework
- Student success pathway planner
- Aura behavioral context API (age-appropriate assessment variants)
- Bridge collaboration API (pipeline handoff)
- WebSocket real-time chat (existing Alex WebSocket infrastructure)

**Special Features**
- Age-adaptive interaction: Alex adjusts language complexity, content depth, and engagement style based on the student's educational level (K-12 vs. university)
- School counselor dashboard integration: Alex can provide aggregate insights to counselors while maintaining individual student privacy
- Bridge handoff: when a student is ready for career-stage transitions, Alex transfers context to Bridge for talent pipeline matching

**Trigger Events**
- Student initiates career exploration or academic coaching conversation
- School counselor requests student population insights
- Academic milestone (course selection period, graduation approach)
- Bridge requests student context for pipeline matching

---

## 3. Communication Patterns

### 3.1 Primary Request Flow

Every user interaction follows this path:

```
User
  │
  ▼
MERIDIAN (intent classification)
  │
  ▼
Domain Orchestrator (template matching + dispatch)
  │
  ▼
Specialist Agent(s) (task execution)
  │
  ▼
Domain Orchestrator (response aggregation)
  │
  ▼
MERIDIAN (synthesis + delivery)
  │
  ▼
User
```

### 3.2 Intent Classification and Dispatch

When Meridian receives a user message, the following pipeline executes:

1. **Intent Classification**: Meridian's intent classifier analyzes the user message and produces a structured intent object containing the domain (personal development, organizational intelligence, strategic advisory), the action type (query, request, follow-up), and extracted entities (user names, role titles, dates, etc.).

2. **Template Matching**: The Domain Orchestrator receives the classified intent and matches it against its library of process templates. Each template defines a directed acyclic graph (DAG) of agent tasks required to fulfill the intent. For example, the intent "prepare me for my interview at Company X" matches the Behavioral Interview Prep template, which defines a four-agent sequence.

3. **Variable Filling**: The matched template contains variable slots (e.g., `{user_id}`, `{job_title}`, `{company}`) that are populated from the intent's extracted entities and the user's session context.

4. **Rule Validation**: Before dispatch, the orchestrator runs the filled template through validation rules. These include Sentinel compliance checks for sensitive operations, confidence threshold checks, and resource availability checks.

5. **Dispatch**: The orchestrator dispatches tasks to agents according to the DAG structure. Tasks with no dependencies execute in parallel; tasks with dependencies wait for their predecessors to complete.

### 3.3 Agent-to-Agent Communication

Agents do not communicate directly. All inter-agent communication is mediated by the Collaboration Service using structured `TaskMessage` objects:

```python
class TaskMessage:
    source_agent: str         # Agent ID of the sender
    target_agent: str         # Agent ID of the receiver
    task_type: str            # e.g., "behavioral_context_request"
    payload: dict             # Structured data specific to the task type
    correlation_id: str       # Links messages in the same workflow
    priority: int             # 1 (low) to 10 (critical)
    timestamp: datetime
    ttl: int                  # Time-to-live in seconds
```

Common inter-agent communication patterns:

| Pattern | Example |
|---|---|
| **Context Request** | Nova requests Aura's Behavioral Preference Map for a candidate |
| **Validation Request** | Atlas sends a team recommendation to Sentinel for compliance check |
| **Sequential Handoff** | Nova sends candidate scores to James for interview guide generation |
| **Parallel Fan-out** | Orchestrator dispatches to Aura, Nova, and Nexus simultaneously |
| **Evidence Check** | Ascend sends a coaching recommendation to Sage for research validation |

### 3.4 Orchestrator DAG Dispatch

Each Domain Orchestrator maintains a library of process templates expressed as DAGs. A template defines:

- **Nodes**: Agent tasks with input/output schemas
- **Edges**: Dependencies between tasks (data flow)
- **Parallel groups**: Sets of nodes with no mutual dependencies that execute concurrently
- **Merge points**: Nodes that wait for multiple predecessors before executing
- **Timeout policies**: Per-node and per-template timeout thresholds
- **Fallback strategies**: What to do if a node fails (retry, skip with degraded output, escalate)

Example DAG for the Nova-James Hiring Triage Process:

```
[Nova: Parse Hiring Request]
         │
         ▼
[James: Generate Job Blueprint]
         │
         ▼
[James: Score Candidates] ◄── [Aura: Provide Behavioral Profiles]
         │
         ▼
[Nova: Triage A/B/C]
         │
         ▼
[James: Generate Interview Guides (A-tier only)]
         │
         ▼
[Sentinel: Compliance Validation]
         │
         ▼
[Nova: Compile Final Package]
```

---

## 4. Memory Architecture

### 4.1 Short-Term Memory (Session Context)

- **Scope**: Single conversation session
- **Storage**: In-memory, per-session data structures
- **Contents**: Conversation history, current intent chain, active process template state, intermediate agent outputs not yet delivered to the user
- **Lifetime**: Expires when the session ends or after a configurable inactivity timeout
- **Access**: Meridian and the active orchestrator only

### 4.2 Medium-Term Memory (User Profile)

- **Scope**: Individual user, persists across sessions
- **Storage**: PostgreSQL (structured data) + Milvus (vector embeddings)
- **Contents**:
  - Behavioral Preference Map (Aura's PRISM profile output)
  - Career goals, preferences, and stated aspirations
  - Learning progress and skill acquisition history (Echo)
  - Interaction style preferences (communication tone, detail level)
  - Active development plans (Ascend, Echo)
- **Lifetime**: Persists indefinitely; versioned snapshots on significant updates
- **Access**: All agents via read-only API; Aura has write access to behavioral data; each agent has write access to its own domain data

### 4.3 Long-Term Memory (Organizational Knowledge)

- **Scope**: Organization-wide, shared across all users in an organization
- **Storage**: Milvus vector store (primary), PostgreSQL (metadata and relationships)
- **Contents**:
  - Job Blueprint library (Atlas, James)
  - PRISM content libraries and assessment frameworks (Aura)
  - Organizational structure and team composition data (Atlas)
  - Research and evidence libraries (Sage)
  - Compliance policy rule sets (Sentinel)
  - Cultural dimension profiles (Nexus)
  - Career pathway templates (Nova, Bridge)
- **Lifetime**: Persists indefinitely; content versioned and periodically refreshed
- **Access**: Read access varies by agent role; write access restricted to content owners

### 4.4 Feedback Memory

- **Scope**: Cross-cutting; applies to all memory tiers
- **Storage**: PostgreSQL with vector embeddings in Milvus for semantic retrieval
- **Contents**: Human corrections, preference overrides, and explicit feedback on agent outputs
- **Priority**: Feedback entries are stored with `priority=10` (highest), ensuring they take precedence over other memory entries during retrieval
- **Mechanism**: When an agent retrieves context from any memory tier, feedback entries matching the current context are surfaced first and override conflicting lower-priority entries
- **Lifetime**: Persists indefinitely; decays only if explicitly superseded by newer feedback

### 4.5 Memory Access Pattern

```
Agent Task Execution
  │
  ├── Read short-term memory (current session context)
  ├── Read medium-term memory (user profile, behavioral data)
  ├── Read long-term memory (organizational knowledge, content libraries)
  └── Read feedback memory (human corrections, priority=10 overlay)
  │
  ▼
Generate Response
  │
  ├── Write to short-term memory (intermediate results)
  └── Write to medium-term memory (if user profile update warranted)
```

---

## 5. Process Template Examples

### 5.1 New User Onboarding

**Trigger**: User completes registration and enters the platform for the first time.

**Template DAG**:

```
[Aura: Administer PRISM Assessment]
         │
         ├──────────────────────┐
         ▼                      ▼
[Aura: Generate Behavioral   [Nova: Capture Career
 Preference Map]               Goals & Aspirations]
         │                      │
         └──────────┬───────────┘
                    ▼
        [Meridian: Welcome Synthesis]
```

**Step-by-step**:

1. **Aura** administers the PRISM behavioral assessment through an interactive guided flow. The assessment adapts based on early responses to minimize question count while maintaining accuracy.
2. **Aura** processes the results and generates the user's initial Behavioral Preference Map, storing it in medium-term memory.
3. **Nova** (in parallel with step 2, once assessment data is available) conducts a brief career goals intake: current role, aspirations, timeline, and priorities.
4. **Meridian** synthesizes Aura's behavioral insights and Nova's career context into a personalized welcome message that reflects the user's communication style, highlights key behavioral strengths, and outlines an initial coaching roadmap.

**Output**: A personalized onboarding summary delivered as Meridian's response, with the Behavioral Preference Map and career goals stored for all future interactions.

---

### 5.2 Behavioral Interview Prep

**Trigger**: User requests help preparing for a job interview, or a hiring manager requests interview preparation materials for a candidate.

**Template DAG**:

```
[Aura: Retrieve/Update Behavioral Profile]
         │
         ▼
[James: Match Against Job Blueprint]
         │
         ▼
[Nova: Develop Interview Strategy]
         │
         ▼
[Ascend: Executive Presence Tips]
         │
         ▼
[Meridian: Compile Unified Prep Guide]
```

**Step-by-step**:

1. **Aura** retrieves the user's current Behavioral Preference Map. If the profile is stale (last assessment > configured threshold), Aura triggers a brief reassessment focused on areas most relevant to interview contexts.
2. **James** matches the user's behavioral profile against the Job Blueprint for the target role. James identifies alignment strengths (areas to emphasize in the interview) and gap areas (areas where the candidate should prepare mitigation narratives). If no Job Blueprint exists for the role, James generates one from the job description.
3. **Nova** develops an interview strategy based on James's match analysis. This includes recommended STAR-method stories aligned with the role's key competencies, questions the candidate should ask, and red-flag topics to navigate carefully.
4. **Ascend** adds executive presence coaching tailored to the interview context: body language recommendations adapted to the user's behavioral style, energy management for high-stakes conversations, and opening/closing strategies.
5. **Meridian** compiles all outputs into a unified interview preparation guide delivered in the user's preferred communication style. The guide includes: behavioral strengths to emphasize, gap mitigation strategies, STAR story frameworks, executive presence tips, and practice questions.

**Output**: A comprehensive interview prep guide delivered as a structured Meridian response, optionally exportable as a document.

---

### 5.3 Team Composition Analysis

**Trigger**: Manager requests analysis of their team's behavioral composition, or organizational restructuring requires team optimization.

**Template DAG**:

```
[Atlas: Retrieve Org Structure]    [Aura: Retrieve Team Member Profiles]
         │                                      │
         └──────────────┬───────────────────────┘
                        ▼
            [Atlas: Behavioral Diversity Analysis]
                        │
                        ▼
            [Atlas: Gap Analysis & Recommendations]
                        │
                        ▼
            [Sentinel: Compliance Review]
                        │
                        ▼
            [Meridian: Team Analysis Brief]
```

**Step-by-step**:

1. **Atlas** retrieves the organizational structure for the target team: reporting lines, role definitions, tenure, and current Job Blueprints.
2. **Aura** (in parallel) retrieves Behavioral Preference Maps for all team members. If any team member lacks a current profile, Aura flags this as a data gap.
3. **Atlas** performs a behavioral diversity analysis by overlaying all team members' profiles. This produces a team behavioral heat map showing concentrations and gaps across behavioral dimensions.
4. **Atlas** generates gap analysis and recommendations: which behavioral profiles are overrepresented, which are missing, and how this affects team dynamics (e.g., "Team is heavily Gold-dominant, which drives strong execution but may suppress creative risk-taking. Consider a Green-dominant hire for the open Product Designer role.").
5. **Sentinel** reviews the recommendations for compliance. Any recommendation that could be interpreted as discriminatory in a hiring context is flagged and reframed (e.g., behavioral fit is presented as one factor among many, never the sole criterion).
6. **Meridian** delivers the team analysis brief with visualizable data, narrative insights, and actionable recommendations.

**Output**: A team composition analysis with behavioral heat map, gap analysis, and compliant hiring/development recommendations.

---

### 5.4 Performance Review Prep

**Trigger**: User requests help preparing for giving or receiving a performance review.

**Template DAG**:

```
[Aura: Behavioral Insights]    [Nova: Career Trajectory]
         │                              │
         │    [Sentinel: Compliance     │
         │     Check on Review          │
         │     Framework]               │
         │         │                    │
         │    [Nexus: Cultural          │
         │     Context]                 │
         │         │                    │
         └────┬────┴────────────────────┘
              ▼
   [Meridian: Performance Review Brief]
```

**Step-by-step**:

1. **Aura** retrieves the behavioral profiles of both the reviewer and the reviewee (if available). Aura generates communication recommendations: how to frame feedback in a way that resonates with the reviewee's behavioral style, and how to structure the conversation to align with the reviewer's natural communication strengths.
2. **Nova** (in parallel) pulls the reviewee's career trajectory data: goals set in previous cycles, progress on development plans, and career aspirations. Nova identifies alignment or divergence between current performance and stated career direction.
3. **Sentinel** (in parallel) validates the review framework against compliance requirements: ensures evaluation criteria are consistently applied, checks for potential bias indicators, and confirms documentation requirements are met.
4. **Nexus** (in parallel) provides cultural context if the reviewer and reviewee come from different cultural backgrounds: feedback delivery norms, directness expectations, and relationship-oriented vs. task-oriented framing.
5. **Meridian** synthesizes all inputs into a performance review preparation brief: behavioral communication guide, career alignment summary, compliance checklist, cultural considerations, and a suggested review conversation structure.

**Output**: A performance review preparation brief with behavioral communication guide, career context, compliance validation, and cultural adaptation recommendations.

---

## 6. Technology Stack

### 6.1 Core Infrastructure (Existing)

| Component | Technology | Notes |
|---|---|---|
| **Runtime** | Python 3.14 | Current backend runtime |
| **Framework** | FastAPI | REST APIs + WebSocket endpoints |
| **Database** | PostgreSQL via SQLAlchemy | ORM with Alembic migrations |
| **Vector Store** | Milvus | Document embeddings, semantic search |
| **Real-time** | WebSocket | Existing pattern for AI agent chat (Alex) |
| **Task Queue** | (To be determined) | For async agent task dispatch |

### 6.2 AI / ML Layer

| Component | Technology | Notes |
|---|---|---|
| **LLM Provider** | AWS Bedrock | Primary LLM access; abstraction layer enables model switching without code changes. Supports Claude, Titan, and third-party models behind a unified API |
| **Embedding Model (Primary)** | Google Generative AI | Currently in use for document embeddings in Milvus |
| **Embedding Model (Secondary)** | Voyage AI | Planned secondary provider for specialized embedding tasks (e.g., code, behavioral assessment text) |
| **Orchestration** | LangChain / LangGraph | Agent orchestration, chain composition, and tool calling (existing LangChain usage extended) |

### 6.3 Meridian-Specific Components (New)

| Component | Purpose |
|---|---|
| **Intent Classifier** | Analyzes user messages and routes to the correct Domain Orchestrator |
| **Process Template Engine** | Stores, matches, and executes DAG-based process templates |
| **Collaboration Service** | Mediates agent-to-agent communication via `TaskMessage` objects |
| **Memory Manager** | Unified interface for short/medium/long-term memory access across all agents |
| **Response Synthesizer** | Merges multi-agent outputs into a single Meridian-voiced response |
| **Confidence Gate** | Evaluates agent output confidence and triggers human-in-the-loop when thresholds are not met |

### 6.4 Integration Points

- **Existing Milvus client** (`prism_inspire/core/milvus_client.py`): Extended for new collection types (Job Blueprints, behavioral embeddings, research library)
- **Existing auth system** (`users/auth.py`, `users/decorators.py`): Meridian respects the same authentication and role-based access controls
- **Existing WebSocket infrastructure**: Meridian's real-time chat extends the pattern established by Alex's WebSocket implementation
- **AWS Cognito**: No changes to auth provider; Meridian operates within the existing auth boundary

---

## 7. Security & Compliance

### 7.1 Sentinel as Compliance Gate

Sentinel is not a monitoring agent --- it is a **gate**. The architecture enforces that specific categories of agent output pass through Sentinel validation before reaching the user:

- **Employment decisions**: Any recommendation that could influence hiring, promotion, termination, or compensation must pass Sentinel review
- **Personal data processing**: Any action that accesses, modifies, or transmits personal data triggers GDPR compliance validation
- **Behavioral data usage**: Any use of PRISM assessment data in decision-making contexts requires Sentinel verification that the PRISM disclaimer is applied

### 7.2 PRISM Behavioral Data Disclaimer

All outputs that reference behavioral assessment data include the following guardrail:

> Behavioral preference data from PRISM assessments provides insight into communication and work style tendencies. This data is never the sole basis for employment decisions. All hiring, promotion, and personnel recommendations incorporate multiple factors and require human review before action.

This disclaimer is enforced at the Meridian response synthesis layer. Sentinel validates its presence in all applicable outputs.

### 7.3 Human-in-the-Loop Escalation

The architecture defines escalation gates at two levels:

**Confidence-based escalation**: When an agent's output confidence score falls below a configurable threshold (default: 0.7), the orchestrator flags the response for human review before delivery. The user receives a message indicating that a human coach will review and follow up.

**Policy-based escalation**: Certain action categories always require human approval regardless of confidence:
- Termination recommendations
- Adverse action recommendations
- Data deletion requests (GDPR right to erasure)
- Cross-organizational data sharing

### 7.4 Audit Trail

Every agent action that modifies state or produces a recommendation is logged with:

| Field | Description |
|---|---|
| `action_id` | Unique identifier for the action |
| `agent_id` | Which agent performed the action |
| `user_id` | Which user the action relates to |
| `org_id` | Organizational context |
| `action_type` | Category of action (recommendation, data access, data modification) |
| `input_summary` | Hashed summary of inputs (not raw data, for privacy) |
| `output_summary` | Summary of the output produced |
| `compliance_status` | Sentinel's validation result (approved, flagged, blocked) |
| `confidence_score` | Agent's self-reported confidence |
| `timestamp` | When the action occurred |
| `correlation_id` | Links related actions in the same workflow |

Audit logs are stored in PostgreSQL with a retention policy aligned to the organization's regulatory requirements (minimum 7 years for employment-related actions under EEOC guidelines).

### 7.5 Regulatory Framework Mapping

| Regulation | Coverage |
|---|---|
| **EEOC** | Sentinel validates all employment-related recommendations for adverse impact. Behavioral data is never the sole factor. Disparate impact analysis runs on aggregate recommendation patterns. |
| **ADA** | Accommodation recommendations are flagged as advisory only. Sentinel ensures no recommendation inadvertently discriminates against protected disability status. |
| **GDPR** | Data access, processing, and retention comply with GDPR principles. Users can request data export and deletion. Behavioral profiles are treated as sensitive personal data under Article 9. |
| **SOC 2** | Audit trails, access controls, and encryption standards meet SOC 2 Type II requirements. Agent-to-agent communication is logged and auditable. |

### 7.6 Data Isolation

- **Organization boundaries**: Agents never access data from one organization when operating in another organization's context. This is enforced at the database query layer, not just the application layer.
- **Role-based agent access**: Not all agents can access all data. Aura's behavioral data, for example, is read-only for all agents except Aura itself.
- **Session isolation**: Short-term memory is scoped to a single session and is never accessible from other sessions, even for the same user.
