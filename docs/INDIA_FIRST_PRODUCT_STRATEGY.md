# Warik AI — India-first product strategy

**Working thesis:** Warik is a personal action assistant for the everyday work people do not want to forget. It turns conversations into pending commitments, helps users take supported next steps, and keeps an outcome visible until the user records that it is complete.

This is a product hypothesis, not a claim that every Indian consumer has the same problem. Validate it with observed behaviour and retention.

## 1. The problem to investigate

A large part of personal administration is not a single complex task. It is the repeated follow-up around small tasks: a refund that has not arrived, a delivery issue, a form waiting for submission, a booking to confirm, a document to send, or a person who owes a response.

Three public signals make this worth investigating:

- **Consumer resolution is a recurring burden.** The Government reported that the National Consumer Helpline facilitated refunds of more than ₹105 crore across 1,66,189 refund-related grievances in 35 sectors between 25 April 2025 and 31 July 2026; e-commerce accounted for more than ₹74 crore of those facilitated refunds. Separately, NCH recorded 511,196 e-commerce grievances in 2025. These are signals of repeated resolution and follow-up workflows, not proof that every complaint remains unresolved or that Warik can retrieve refund status or resolve claims automatically.
- **Time is constrained.** India's 2024 Time Use Survey reported that 53.9% of urban residents participated in unpaid domestic services and 24.5% in unpaid caregiving. This is a better framing than calling customers lazy: many people are balancing paid work with household and care responsibilities.
- **Language affects accessibility.** The IAMAI–Kantar Internet in India 2024 report estimated that 870 million users accessed the internet in Indic languages; 57% of urban internet users preferred Indic-language content. Treat this as support for testing local-language experiences, not as proof that every user wants voice.

### Sources

- Government of India, National Consumer Helpline refund update, 9 September 2026: https://www.pib.gov.in/PressReleasePage.aspx?PRID=2308386&lang=2&reg=48
- Government of India, National Consumer Helpline update, 17 February 2026: https://www.pib.gov.in/PressReleasePage.aspx?PRID=2229099&lang=1&reg=1
- Government of India, Time Use Survey 2024 release: https://www.pib.gov.in/Pressreleaseshare.aspx?PRID=2106113&lang=2&reg=48
- Department of Consumer Affairs / Lok Sabha response on e-commerce complaints (2025 figure): https://fcainfoweb.nic.in/PMS/writereaddata/2026_LS_B_361.pdf
- IAMAI–Kantar, Internet in India 2024 report: https://www.iamai.in/sites/default/files/research/Kantar_%20IAMAI%20report_2024_.pdf

These sources support problem discovery. They are not a market-size calculation, willingness-to-pay study, or proof of product-market fit.

## 2. The wedge: make follow-through reliable

Do not begin by trying to automate every app a person uses. Start with one repeated job:

**“Remember what I am waiting for, tell me what needs attention, and help me follow it through.”**

Examples to validate:

- A customer is waiting for a refund after cancelling an order.
- A student is waiting for a certificate, approval, or assignment feedback.
- A renter is waiting for a repair or deposit update.
- A working professional needs to chase a reimbursement, invoice, or response.
- A household member needs to track a recurring service issue or appointment.

The common job is follow-through, not the specific merchant or institution.

## 3. Product promise

Warik should:

1. Capture a request through text or a supported Indian language.
2. Extract the commitment, counterparty, useful context, and due date when possible.
3. Ask the user to save or correct the proposed commitment.
4. Show open, in-progress, waiting, and blocked items in one Action Ledger.
5. Suggest the next step or create a reminder when the user approves.
6. Require a user-entered outcome note before marking a commitment complete.

Use precise language: the current ledger records user-provided status and outcome notes. It does not independently verify a merchant's back-end state.

## 4. Why this is different from a generic chatbot

A chatbot gives an answer and expects the user to remember what happens next. Warik's product loop is:

**Capture → structure → approval → supported action → follow-up → user-recorded outcome.**

The moat will not be a prompt or a glowing orb. It must come from:
- Reliable capture of context and dates across real conversations.
- A history of commitments and outcomes that users actually return to.
- India-relevant workflows and languages that work in noisy, mixed-language use.
- Trustworthy permissions, confirmations, auditability, and deletion controls.
- Integrations that are official, reliable, and demonstrably used.

## 5. Initial customer hypothesis

Start with digitally active people who coordinate many small commitments, rather than claiming to serve everyone:

- Salaried professionals in large and mid-sized Indian cities.
- Students and early-career workers managing education, travel, and paperwork.
- Renters and young households coordinating services, deliveries, and appointments.
- Independent professionals tracking client responses, invoices, and reimbursements.

These are hypotheses. Interview users before choosing a primary segment.

## 6. Current product foundation

The advanced workspace branch contains:
- A general conversational path for ordinary questions plus a live-registry, capability-driven workflow planner for supported actions.
- Multi-step planning with schema validation, dependency/input bindings, optional steps, partial-failure handling, retries, approval gates, and persisted workflow state.
- Contextual follow-up reasoning after completed workflows: Warik can offer one relevant next step from the user's goal, allowlisted outcome data, and currently registered tools. The suggestion is a question, not an automatic action.
- User profile defaults for preferred language, currency, timezone, and monthly budget, combined with relevant explicitly saved memories. These are advisory and the latest request always overrides them.
- User approval checkpoints and action logs.
- Action Ledger with counterparty, due date, status, and completion note.
- Personal memory controls.
- Tasks, reminders, expenses, travel and food discovery.
- Document upload and document question-answering.
- Browser voice capture with an editable transcript and ten speech-language options, when voice is configured.

Important limitations to disclose:
- Voice requires a server-side speech provider and is off by default.
- Restaurant listings are candidates, not confirmed menu, price, or dietary matches.
- Travel inventory and prices are not guaranteed live data.
- No WhatsApp/iMessage control or dedicated cloud desktop is implemented.
- Warik does not yet autonomously submit consumer complaints, retrieve merchant refund state, pay bills, or use UPI.

## 7. A narrow first workflow to prove

Use a refund follow-up as a demonstration of the product loop, without pretending to integrate with a merchant:

1. User says: “My cancelled order refund is still pending. Remind me to follow up with the store on Friday.”
2. Warik proposes a commitment with the store as counterparty and Friday as the due date.
3. User reviews and saves it.
4. The item appears as waiting in the Action Ledger.
5. Warik surfaces it when due and offers the next step or a reminder.
6. The user records the response and outcome; only then can it be marked complete.

This demonstrates memory, structure, user control, and follow-through. Merchant contact and refund verification remain manual until official integrations exist.

### General goal-oriented journeys

Warik should not encode a fixed sequence of add-ons. For a request such as a point-to-point flight search, it should identify the required origin, destination, date and time flexibility, then choose only relevant registered capabilities. It should compare actual returned options when a provider returns structured offers; otherwise it should expose an external search handoff and say that live fares were not retrieved.

After showing options, Warik should ask for a selection before using that selection as an input to another workflow. A later optional step might be ground transport, a hotel, calendar coordination, expense tracking or nothing at all. The decision depends on the user's goal, context, saved preferences, search results and tool availability—not a mandatory flight → cab → hotel template.

The current flight tool can return structured offers only when its configured provider is available. The fallback Google Flights link is a handoff, not a live quote. Uber/Ola links open their apps and do not return a live fare or book a ride. Hotel search depends on the configured provider and returns booking options, not a reservation. A real booking integration must be separately added and must return a confirmed provider booking reference before Warik claims success.

## 8. Discovery plan

Run 25–30 interviews in one initial segment. Do not ask “Would you use an AI assistant?” Ask people to reconstruct the last real incident.

Useful questions:
1. Tell me about the last refund, delivery, booking, or service issue you had to follow up on.
2. How many messages, calls, or apps did it take?
3. What did you have to remember yourself?
4. Where did you keep the order ID, receipt, or proof?
5. What happened when you forgot to follow up?
6. How do you currently track waiting-for replies?
7. Which language do you use when giving yourself a reminder?
8. Would you trust an assistant to draft a follow-up? What would it need to show first?
9. Which actions must always require your approval?
10. What have you already tried to solve this problem?

Ask to see the current workaround (screenshots with private details hidden, a notes app, a spreadsheet, or a WhatsApp thread). Record repeated pain, not just positive reactions.

## 9. Pilot metrics

Track real usage from the first cohort:
- Activated users who save at least one commitment.
- Weekly active users and 7-day / 30-day retention.
- Commitments created per active user.
- Percentage of due commitments revisited or updated.
- User-reported completion rate and time from capture to outcome.
- Reminder usefulness and snooze/ignore rate.
- Incorrectly extracted dates, counterparties, or commitment proposals.
- Tool success, failure, retry, and confirmation rates.
- Voice transcription corrections by language.

Never present target metrics as achieved metrics. A useful early goal is a small cohort that repeatedly uses the product without founder prompting; report the actual count, cohort period, and definitions.

## 10. Product roadmap

### Next: prove the loop
- Make Action Ledger capture and corrections frictionless.
- Improve date, counterparty, and waiting-state extraction.
- Add notification delivery and dependable reminder scheduling.
- Collect explicit user feedback on wrong proposals and missed follow-ups.
- Measure retention and completed outcomes.

### Then: reduce manual work
- Add user-authorized email or document import using supported connectors.
- Generate follow-up drafts from the user's actual case context.
- Add official consumer-resolution or merchant integrations only where access and terms permit.
- Consider WhatsApp Business Platform integration after proving the workflow and handling consent, delivery, and retention correctly.

### Later: controlled app execution
- Use a sandboxed browser executor for specific tested workflows.
- Show the planned steps, requested permissions, and evidence before execution.
- Require confirmation before messages are sent, bookings are committed, or money moves.
- Keep credentials, OTPs, and payment authorization out of the general LLM context.

## 11. Demo for a YC conversation

Show one live sequence, not a tour of every menu:

1. Speak or type a pending refund issue.
2. Review the extracted commitment and correct the due date.
3. Save it to the Action Ledger.
4. Show the waiting state and next-step prompt.
5. Complete the commitment with a user-entered outcome note.
6. Open the audit/action history to show which step required user approval.

Then show a real user using the workflow again a week later. That repeat use is more meaningful than a polished mock screen.

## 12. YC narrative

A concise framing:

> Warik is building an India-first personal action assistant. People already use chat apps to coordinate everyday work, but they still have to remember what is pending and chase every loose end themselves. Warik turns conversations into structured commitments, helps users take supported actions with approval, and tracks each item until the user records the outcome. We are starting with personal follow-through and local-language capture before expanding into deeper integrations.

Replace this narrative with measured customer evidence as soon as it exists. Do not imply that Instinct's scale, funding, or product capabilities transfer to Warik. The goal is to prove a narrow behaviour first.

## 13. Trust and safety principles

- Default to least privilege and explain what data leaves the device.
- Never ask for UPI PINs, passwords, OTPs, or card security codes.
- Require explicit confirmation before external or irreversible actions.
- Keep human review between speech transcription and agent execution.
- Make memory and personal records viewable, editable, and deletable.
- Distinguish provider-verified data from user-provided information and estimates.
- Log meaningful actions without retaining unnecessary sensitive content.
- Provide a clear recovery path when an action fails or only partially completes.
