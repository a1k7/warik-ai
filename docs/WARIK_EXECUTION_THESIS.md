# Warik AI — Product Thesis: The Personal Execution System

**Updated:** 17 November 2026

## The category we should build

Warik should not compete as another general-purpose chatbot. It should be an **India-first personal execution system**: a persistent assistant that turns a person's objectives into tracked missions, uses connected capabilities, obtains permission for consequential actions, and reports only outcomes supported by evidence.

The product promise:

> **Every mission has a plan, a permission boundary, an evidence trail, and a follow-through state.**

A fluent answer is not a completed task. A tool call is not proof of success. A search snippet is not a verified fact. Warik must make these distinctions visible in the product itself.

## Why a generic assistant is not a defensible wedge

As of November 2026, general-purpose assistants are moving beyond chat:
- Instinct presents itself as a personal assistant that thinks, plans and acts through connected services and user-granted access. Its product concept is a low-friction messaging/calling interface. See [Instinct's privacy policy](https://instinct.com/privacy-policy) and [TechCrunch's reporting on its launch and security concerns](https://techcrunch.com/2026/08/24/instincts-powerful-ai-assistant-is-raising-privacy-and-security-concerns/).
- Claude Cowork can plan multi-step tasks, use connectors, browse, interact with the computer, and let users steer work in progress. See [Claude Cowork](https://claude.com/product/cowork) and [computer-use documentation](https://support.claude.com/en/articles/14128542-let-claude-use-your-computer-in-cowork).
- OpenAI's product direction has also moved toward longer multi-step tasks and finished deliverables through ChatGPT Work. See the [ChatGPT agent / Work help page](https://help-lb.openai.com/en/articles/11752874-chatgpt-agent).

Therefore, "chat + tools", "AI that takes actions", "voice input", and "a beautiful dashboard" are not unique differentiators. Warik should not claim that these alone make it better.

## The differentiated loop: Capture → Understand → Plan → Act → Prove → Follow through

### 1. Capture
Accept natural language, voice, documents and supported connected services. The user should not need to know which integration or workflow to invoke.

### 2. Understand
Convert the request into a structured mission:
- desired outcome
- explicit constraints and preferences
- known facts and their provenance
- missing inputs
- deadline or time sensitivity
- actions that require user approval

Ask only for information that blocks safe progress.

### 3. Plan
Discover capabilities from the live registry. Create a dependency-aware plan. Independent read-only work can run independently; dependent actions must wait for their required inputs. Do not add a fixed sequence of flight, hotel, cab, food or other tools to every request.

### 4. Act
Use direct integrations before browser handoffs. Distinguish:
- search / discovery
- external handoff
- prepared action
- approved action
- executed action

Never infer that a provider accepted an action from a generated link or a successful local function call.

### 5. Prove
Every result should carry an evidence state:
- **Verified:** independent evidence confirms the outcome.
- **Provider-returned:** a connected provider returned the record, price or status; this is not necessarily a completed transaction.
- **Estimated:** calculated from declared assumptions, not quoted by a provider.
- **Unverified:** the action ran, but Warik cannot independently confirm the outcome.
- **Unavailable:** the required source, integration or evidence is missing.

The UI must not collapse these states into a single green "done" label.

### 6. Follow through
A mission remains open while required steps, approvals or user decisions remain. Keep the original objective when asking for clarification. Resume from the last durable checkpoint. Never replay an uncertain external side effect automatically.

## The product surface: Mission Control

The primary interface should make the state of work visible, not just display a transcript.

Each mission should have:
1. **Objective** — what the user asked Warik to achieve.
2. **Constraints** — budget, dates, location, people, preferences and exclusions.
3. **Plan** — ordered steps with dependencies.
4. **Evidence** — sources, retrieval status, timestamps, provider and verification method.
5. **Approval queue** — exactly what Warik wants permission to do and the consequence.
6. **Open loops** — missing information, failed steps, pending selection and follow-up.
7. **Outcome receipt** — what actually happened, what was independently checked and what remains unresolved.

The chat is an input surface and a way to steer the mission. It should not be the only place the mission exists.

## Initial India-first wedge

Start with repeatable personal operations where local context and follow-through matter:
- travel planning that separates live inventory from external search handoffs and estimated budgets
- personal deadlines, reminders and open commitments
- everyday expense capture and budget reconciliation
- food and local discovery with visible data provenance
- student and early-career life administration: applications, forms, deadlines, interview preparation and follow-ups

Do not pretend to have live access to IRCTC, hotel inventory, payments, ride dispatch or messaging until a real provider connection is configured and tested. Where no integration exists, provide an honest handoff and retain the unresolved mission state.

A focused first market (for example, students and early-career professionals) is more testable than claiming to be a universal assistant for everyone. Expand only after one cohort repeats the core mission loop.

## Defensibility

Potential compounding assets are not the base language model:
- a permissioned, user-controlled memory of preferences and constraints
- durable mission history and verified outcome receipts
- India-specific workflow coverage and provider reliability metadata
- failure recovery and idempotency for real integrations
- user trust created by accurate evidence states and honest limitations

The data advantage must come from useful, user-authorized context—not hidden collection or indiscriminate retention. Provide controls to view, correct, export and delete user-owned memory and mission history.

## Metrics that matter

Track the following before vanity metrics such as message volume:
- mission completion rate
- independently verified outcome rate
- time from request to verified outcome
- percentage of missions blocked by missing inputs
- recovery rate after provider/tool failure
- duplicate or unintended side-effect rate (target: zero)
- user correction rate for dates, prices, entities and preferences
- 7-day repeat mission rate and weekly retained users

A successful demo should show a complete mission moving through real evidence, approvals and follow-through—not merely a long answer.

## Build sequence

### Phase A — Trust boundary (in progress)
- Block action-relevant requests from silently falling back to ungrounded chat.
- Add explicit reality-check checkpoints when planning cannot proceed.
- Label estimates, provider results, unavailable categories and verified outcomes separately.
- Show mission progress and verification states in Mission Control.

### Phase B — Persistent mission continuity
- Store the original goal and outstanding questions when a mission needs clarification.
- Resume the same mission when the user supplies the missing detail.
- Persist user decisions and selected options as mission events.
- Add a user-visible open-missions view with due dates, blockers and next actions.

### Phase C — One exceptional workflow
Choose one high-frequency Indian workflow and deliver it end-to-end with real integrations, verified outcomes, receipts and failure recovery. Do not build a broad catalogue of mock integrations.

### Phase D — Proactive entry points
Add messaging and scheduled follow-through only after consent, reliability and provider access are in place. Notifications must be opt-in and every proactive action must have a clear reason and a way to stop it.

## The standard

Warik should be able to say:

- "I have not checked that yet."
- "This is an estimate, not a quote."
- "The provider returned these options; none is booked."
- "I need your approval for this exact action."
- "The action was attempted, but the outcome is not verified."
- "This mission is complete; here is the evidence."

That discipline is not a disclaimer around the product. It is the product.
