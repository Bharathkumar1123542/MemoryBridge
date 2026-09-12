# MemoryBridge — Project Overview

**Document type:** Product source of truth
**Version:** 1.0
**Date:** 2026-09-10
**Status:** Approved for hackathon build
**Owner:** Bharath
**Companion documents:** [`architecture.md`](./architecture.md) (system design) · [`implementation.md`](./implementation.md) (build plan)

---

## 1. Executive Summary

MemoryBridge is a safety-first, multi-agent prototype that turns a caregiver's plain-English request ("Remind Maria to water the plants at 10:00") into a calm, low-cognitive-load daily routine for a person living with early-stage dementia or cognitive decline. It is built on the **Strands Agents SDK** and deployed on **AWS Fargate**, with **Neon PostgreSQL** as the system of record and **Amazon Bedrock** as the model provider.

The product is deliberately narrow. It does not manage medication, does not diagnose, does not move money, does not call emergency services, and does not control physical devices. Every routine an agent proposes is a **draft**; only a caregiver's explicit approval turns a draft into something the assisted user sees. This document defines *what* MemoryBridge is and *why* it is scoped the way it is. [`architecture.md`](./architecture.md) defines *how* it is built; [`implementation.md`](./implementation.md) defines the *step-by-step build plan*.

---

## 2. Hackathon Context

MemoryBridge is submitted to the **Agents for Humans Hackathon** (sponsor: Amazon Web Services; administrator: Devpost; `agentsforhumans.devpost.com`).

| Item | Value |
|---|---|
| Submission deadline | September 14, 2026, 5:00 PM Pacific Time |
| Required SDK | Strands Agents SDK (Python) — mandatory for every submission |
| Recommended (not required) | Amazon Bedrock AgentCore Runtime deployment — strengthens the Technical Implementation score |
| Track entered | **Everyday Agents** |
| Prize pool | $40,000 across a Grand Prize and three per-track prizes (Everyday, Professional, Good Neighbor) |

### 2.1 Track rationale

The hackathon defines **Everyday Agents** as agents that take a recurring, easy-to-forget piece of daily/family life off someone's plate, run in the background, and surface only when a human decision is genuinely needed. MemoryBridge fits this precisely: the "customer" of the routine (the caregiver) types one sentence and steps away; the agent pipeline does the decomposition, safety screening, and rewriting; the caregiver is pulled back in only for the single decision that must remain human — approval. Maria's day-to-day experience requires no app management from her at all. This is distinct from **Professional Agents** (a paid specialist's workload) and **Good Neighbor Agents** (many-to-many community/volunteer coordination) — MemoryBridge is a one-caregiver-to-one-assisted-person daily-life tool, which is the Everyday track's defining shape.

### 2.2 Judging-criteria alignment

| Judging criterion (equally weighted) | How MemoryBridge addresses it |
|---|---|
| Technical Implementation | Non-trivial, genuinely multi-agent use of Strands Agents: a `Graph`-orchestrated pipeline with a coded conditional safety gate, plus a fifth deployment path documented for Amazon Bedrock AgentCore Runtime (see `architecture.md §17`, ADR-003). |
| Design | A complete product experience, not a tech demo: a caregiver console with an approval queue, and a distinct, accessibility-first `/today` interface for the assisted user — two different UIs for two different cognitive needs. |
| Potential Impact | Addresses a specific, named, high-stakes population (early-stage dementia / cognitive decline) and a specific, named caregiver pain point (the exhausting choice between over-checking and under-supporting). |
| Creativity & Originality | The system's originality is architectural, not cosmetic: "Safety First, AI Second" is enforced as a structural property (a deterministic gate that runs *before* any model call, and agents that are structurally unable to write to the database — see `architecture.md §7` ADR-002) rather than as a prompt-level promise. |
| Presentation | The demo script in `implementation.md §15` is built directly around the required pitch structure: problem, audience, why it matters, end-to-end working demo. |

---

## 3. Problem Statement

For someone in early-stage dementia or cognitive decline, the activities that structure a day — watering plants, taking a walk, calling a friend, checking the mail — do not disappear all at once. They become harder to *start*, harder to *sequence*, and harder to *remember having done*. The person is often still capable of the activity itself; what has eroded is the scaffolding around it.

Caregivers are the ones who feel this erosion first, and they face a specific, recurring trade-off:

- **Under-support** — a missed reminder becomes a missed meal, an unwatered garden, or a forgotten call, and the caregiver finds out too late to help.
- **Over-support** — constant check-ins ("Did you take your walk? Did you eat? Are you okay?") are exhausting for the caregiver to sustain and can feel infantilizing or intrusive to the assisted person, eroding the independence the caregiver is trying to preserve.

Generic reminder apps do not resolve this trade-off because they operate at the wrong layer. They can fire a notification at 10:00, but they cannot: (a) understand a caregiver's natural-language intent, which is often shorthand, incomplete, or several activities bundled into one sentence; (b) judge whether the requested activity is something an unsupervised, cognitively-impaired person should be doing alone; or (c) translate "water the plants" into the single-action, plain-language, no-jargon phrasing that a person with cognitive decline can actually follow in the moment.

MemoryBridge is built specifically to close that gap — and only that gap. It is explicitly **not** an attempt to replace clinical judgment, caregiving relationships, or emergency response systems (see §9, Out of Scope).

---

## 4. Users and Personas

### 4.1 The Caregiver (primary account holder)

A family member or informal caregiver — adult child, spouse, or close relative — who is not a clinician and typically has limited time. They know the assisted person's routines and risk tolerances intimately but do not want to author a structured daily schedule by hand, and they want a review step they can trust before anything reaches their loved one.

**Representative need:** "I want to say what I want in my own words, see exactly what will be shown to Maria before it goes live, and get told immediately if I've asked for something I shouldn't be automating."

### 4.2 The Assisted User — "Maria" (example persona used throughout this document set)

A person with early-stage dementia or mild cognitive decline who lives independently or semi-independently. Maria can still read, tap a button, and complete a well-framed single-step task, but she is easily overwhelmed by multi-step instructions, small text, or ambiguous phrasing, and she does not manage settings, accounts, or technical configuration herself.

**Representative need:** "Tell me one thing to do, in words I understand, and make it easy for me to say I've done it — or to ask for help without having to explain myself."

### 4.3 Non-users (explicitly out of scope for v1)

Clinicians, professional home-care agencies, multi-caregiver households, and emergency responders are not users of the v1 product. See §9.

---

## 5. Product Principles

1. **Safety First, AI Second.** Every caregiver request passes a deterministic, non-AI safety gate *before* any model is invoked. A model is never the first or only line of defense against a prohibited request.
2. **Draft, never deploy.** No AI-authored output reaches the assisted user without an explicit, logged, human approval action from the caregiver. Agents can produce drafts; only application code — acting on a caregiver's click — can activate one.
3. **Calm over comprehensive.** The assisted-user interface favors fewer words, one action at a time, and generous whitespace over feature density. If a choice must be made between showing more information and showing it calmly, MemoryBridge shows it calmly.
4. **Narrow by design, not by accident.** The prohibited-category list (§9.1) is not a placeholder to expand later inside this prototype — it defines the boundary of what MemoryBridge is allowed to reason about at all, independent of how capable the underlying model is.
5. **No silent autonomy.** MemoryBridge does not place calls, send messages, move money, or operate devices, under any circumstance, regardless of what a caregiver's request or a model's output implies. This is a hard architectural constraint (see `architecture.md §13`), not a policy the model is asked to follow.

---

## 6. Solution Overview

A caregiver enters a natural-language request in the caregiver console. MemoryBridge processes it through six stages before anything is visible to the assisted user, and a seventh stage that only a human can trigger:

| Stage | What happens | Performed by |
|---|---|---|
| 0 — Deterministic gate | The raw request is checked against seven named prohibited categories using rule-based matching, with zero model calls. A match halts the pipeline immediately. | Application code |
| 1 — Routine planning | The caregiver's intent, activity, and schedule are extracted and decomposed into an ordered list of steps. | Routine Planning Agent |
| 2 — Semantic safety review | The *planned* routine is independently judged for unsafe or prohibited intent that keyword matching alone could miss — including intent implied by combinations of otherwise-benign steps. | Semantic Safety Reviewer |
| 3 — Communication rewrite | Approved steps are rewritten into short, one-action-at-a-time, respectful language suited to cognitive decline. | Dementia-Friendly Communication Agent |
| 4 — Caregiver review | The rewritten routine is presented to the caregiver exactly as Maria would see it, alongside the original request, for explicit approval or rejection. | Caregiver (human) |
| 5 — Activation | On approval, the routine becomes visible in Maria's `/today` interface at its scheduled time. | Application code |
| — Escalation (parallel, always available) | From `/today`, Maria can mark a routine complete, or tap **Help me**, which creates an in-app alert in the caregiver console. MemoryBridge never places a call or contacts anyone outside the app. | Escalation Agent + application code |

Full technical detail for each stage — including exact prompts, the deterministic gate's rule table, and the multi-agent orchestration graph — is in `architecture.md §7` and `implementation.md §7–§9`.

---

## 7. Core User Journeys

### 7.1 Journey A — Caregiver creates a routine

1. Caregiver logs into the caregiver console and types: *"Remind Maria to water the plants at 10:00."*
2. The request passes the deterministic gate instantly (no prohibited terms).
3. The Routine Planning Agent extracts: activity = watering plants; time = 10:00 daily; steps = [find the watering can, fill it with water, water each plant on the windowsill].
4. The Semantic Safety Reviewer confirms the routine contains no unsafe intent and returns an approval verdict.
5. The Dementia-Friendly Communication Agent rewrites the steps into three short, first-person-addressed instructions with one action each.
6. The caregiver sees the rewritten routine next to their original request, with a visible **Approve** and **Reject** action. Nothing has been shown to Maria yet.
7. The caregiver taps **Approve**. The routine becomes active and will appear in Maria's `/today` view at 10:00.

### 7.2 Journey B — Caregiver requests something out of scope

1. Caregiver types: *"Remind Maria to take her blood pressure medication at 8am and double the dose if her ankles are swollen."*
2. The deterministic gate matches the `medication_or_dosage` category on the first clause alone and halts the pipeline before any model is called.
3. The caregiver immediately sees a plain-language rejection: the category matched, and a one-line explanation that medication reminders and dosage decisions are outside what MemoryBridge is able to safely automate, with a suggestion to use a dedicated medication-management tool or speak with a pharmacist/clinician.
4. No draft is created, no model call is made, and the attempt is recorded in the audit log (`architecture.md §9`) so the caregiver's request history is transparent.

### 7.3 Journey C — Maria's day

1. At 10:00, Maria's tablet shows one instruction in large, plain text: *"Time to water the plants. Tap the play button to hear it read aloud."*
2. Maria can tap **Listen** to hear the instruction spoken, then **Done** when finished.
3. If Maria is unsure or distressed, she taps **Help me**, optionally records a short note, and the app confirms: *"Your caregiver has been notified."* No call is placed by MemoryBridge.
4. The caregiver sees a new alert in their console within seconds, with Maria's note (if any) and the routine she was on at the time.

---

## 8. Design System Summary

The two interfaces are deliberately built to different standards:

| | Caregiver console | Maria's `/today` interface |
|---|---|---|
| Density | Dashboard-standard information density | One instruction on screen at a time |
| Reading level | Standard | Short sentences, one action per sentence, no jargon |
| Primary interactions | Type, review, approve, reject, browse history | Tap to listen, tap to mark done, tap for help |
| Navigation | Multi-page (routines, approvals, alerts, history) | Effectively navigation-free — a single view that changes with the clock |
| Accessibility floor | WCAG 2.1 AA | WCAG 2.1 AA plus: minimum 24px body text, minimum 44×44px tap targets, audio playback for every instruction, no more than one primary action visible at a time |

Full UI/route detail is in `implementation.md §11`.

---

## 9. Scope

### 9.1 In scope for v1 (this hackathon build)

- Natural-language routine creation from a single caregiver request.
- The four named agents (Routine Planning, Semantic Safety Reviewer, Dementia-Friendly Communication, Escalation) coordinated by a deterministic Strands Agents `Graph`.
- Deterministic pre-model screening against seven named prohibited categories:
  1. **Medication or dosage** — any request that mentions administering, timing, refilling, or adjusting medication, *including plain reminders to take an already-prescribed medication.* MemoryBridge deliberately does not distinguish "reminder" from "dosage change" for this category — that distinction itself requires clinical judgment the prototype does not have, so the entire category is excluded rather than partially supported.
  2. **Medical diagnosis or advice** — symptom interpretation, diagnostic questions, or clinical recommendations.
  3. **Financial transactions** — payments, transfers, purchases, subscriptions, donations.
  4. **Emergency-service actions** — anything implying MemoryBridge should contact emergency services on the assisted user's behalf.
  5. **Unlocking doors** — any request to unlock, disarm, or grant physical access.
  6. **Controlling appliances** — any request to operate a stove, oven, thermostat, smart lock, or other connected device. (MemoryBridge has no device-control integration of any kind; this category also blocks the *instructional* framing of such a routine, since surfacing "turn off the stove" as a routine step could itself be unsafe guidance for an unsupervised, cognitively-impaired user.)
  7. **Other high-risk actions outside prototype scope** — a bounded catch-all for content involving violence, self-harm, or contacting third parties outside the approved caregiver relationship.
- A human-in-the-loop approval checkpoint that is structurally required, not optional, before any routine is visible to the assisted user.
- Maria's `/today` interface: listen, mark complete, request help.
- The Escalation Agent's "Help me" flow, which creates an **in-app, caregiver-facing alert only**.
- Single caregiver, single assisted user, single language (English), single time zone per household.

### 9.2 Explicitly out of scope for v1

- Any medication reminder, tracking, or dosage functionality of any kind.
- Any clinical, diagnostic, or medical-advice functionality.
- Real phone calls, SMS, push notifications to third parties, or any contact with emergency services. **Help me** creates an in-app alert and nothing else, under any circumstance.
- Financial actions of any kind.
- Smart-home or IoT device control of any kind.
- Multiple caregivers per assisted user, or multiple assisted users sharing one device.
- Languages other than English.
- Offline operation (the assisted-user device requires connectivity; there is no offline fallback in v1).
- Caregiver-side editing of an agent-produced draft (v1 supports Approve or Reject only; edit-and-resubmit is future work).
- Voice input for routine creation (v1 accepts typed caregiver requests only).

---

## 10. Success Metrics

Because this is a hackathon prototype rather than a deployed clinical product, success is measured against demonstrable, testable behavior rather than longitudinal outcomes:

| Metric | Target for demo/submission | How it is verified |
|---|---|---|
| Deterministic-gate recall on the seven named categories | 100% on the adversarial test set in `implementation.md §13` | Automated unit tests, run in CI |
| Deterministic-gate false-positive rate on benign daily-living requests | 0% on the benign test set | Automated unit tests |
| End-to-end latency, benign request (Stage 0 → Stage 4 ready for review) | Under 12 seconds at the 95th percentile | Manual timing during demo rehearsal + logged `accumulated_usage`/timing from the Graph result |
| Zero unapproved routines ever reach `/today` | 100% — structurally guaranteed, not just tested | Code review of the activation path (`architecture.md §7`, ADR-002) plus an integration test that asserts a `pending_caregiver_approval` routine is unreachable from the `/today` endpoint |
| Help-me alert delivered even if the Escalation Agent fails | 100% — alert is created by a deterministic fallback path | Integration test that forces an LLM timeout and asserts an alert row is still created |

---

## 11. Why Existing Tools Fall Short

Generic reminder and to-do apps (calendar reminders, smart-speaker routines, medication-reminder apps) share a common limitation relevant here: they require the caregiver to already have translated their intent into a structured schedule, and they have no mechanism to evaluate whether a given automated instruction is appropriate to hand to a cognitively-impaired person unsupervised. MemoryBridge's contribution is not "another reminder app" — it is the reasoning and safety layer that sits between an unstructured caregiver request and a structured, screened, human-approved instruction. This is also why the product is intentionally narrow: the value is in doing the caregiver-intent-to-safe-instruction translation well for a bounded set of daily activities, not in becoming a general-purpose home assistant.

---

## 12. Risks and Assumptions

| # | Risk / assumption | Mitigation / disposition |
|---|---|---|
| R1 | A caregiver may phrase a prohibited request in a way the deterministic keyword gate misses (paraphrase, misspelling, indirection). | Addressed by design: the Semantic Safety Reviewer is a second, independent, meaning-based check specifically because the deterministic gate is known to be evadable by paraphrase. Neither layer is assumed sufficient alone. |
| R2 | A caregiver may over-trust the system and approve a routine without reading it. | The approval screen shows the rewritten routine in full, requires an explicit tap (no default/pre-checked approval), and cannot be bypassed or batch-approved in v1. |
| R3 | "Help me" could be mistaken by Maria or a caregiver for an emergency-calling feature. | The `/today` UI copy explicitly states what happens ("Your caregiver has been notified in the app") at the moment of use, and product marketing/README language never uses "emergency," "call," or "alarm" to describe this feature. |
| R4 | Bedrock model latency could make Stage 1–3 feel slow to a caregiver mid-conversation with a distressed family member. | Latency budget and model-tiering strategy are defined in `architecture.md §12`; the 12-second target in §10 is treated as a hard product requirement, not an aspiration. |
| R5 | Hackathon timeline (4 days from this document's date to submission) constrains scope. | The v1 scope in §9 is deliberately the smallest set that still exercises all four agents and the full safety architecture; see `implementation.md §4` for the day-by-day build plan. |

---

## 13. Glossary

| Term | Meaning |
|---|---|
| Caregiver | The human account holder who creates and approves routines. |
| Assisted user | The person the routines are created for (example: Maria). |
| Routine | A single scheduled activity with an ordered list of steps. |
| Draft | A routine that has passed or failed safety review but has not yet been approved or rejected by a caregiver. |
| Deterministic gate | The non-AI, rule-based screen that runs before any model call. |
| Semantic safety review | The AI-based, meaning-level safety check that runs after routine planning. |
| Human-in-the-loop checkpoint | The mandatory caregiver approval step; the only path by which a routine becomes visible to the assisted user. |
| `/today` | The assisted user's simplified, single-view interface. |
