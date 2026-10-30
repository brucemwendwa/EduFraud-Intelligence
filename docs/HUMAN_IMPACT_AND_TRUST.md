# Human Impact and Trust Statement

Financial aid is often the difference between a student staying in school or leaving. Fraud hurts students twice.
Stolen aid drains the funds that legitimate students depend on, and an account takeover can redirect a real
student's refund to someone else. A badly designed fraud system can hurt them a third time, by delaying or
denying aid to honest students who happen to look unusual.

EduShield AI is designed so the first two harms are caught early without causing the third. Its principle is
**People First, AI Second**: the software finds and explains patterns; trained people make every decision that
affects a student.

This statement describes how the prototype in this repository behaves today and is explicit about what it does not
yet do. For the technical breakdown of rules, models and simulations, see [AI_DISCLOSURE.md](AI_DISCLOSURE.md).

## 1. Protecting legitimate students

- **Account takeover is treated as harm to the student.** The flagship scenario is a refund-destination change
  requested on another student's account. Step-up verification fails, and the system recommends **not** applying the
  change and contacting the student through a known-good channel. The legitimate student is protected, not
  suspected.
- **Ordinary life is not suspicious.** Siblings sharing a household, students in the same residence hall, shared
  campus kiosks and a verified bank-account change carry near-zero weight (0.02–0.04). Only combinations of strong
  signals escalate.
- **Look-alike controls are tested continuously.** The synthetic dataset includes legitimate cases designed to
  resemble fraud: siblings, a residence hall, a transfer student, a verified bank change and a high-need independent
  student. The Detection engine page checks live that every one of them stays below "high".
- **A person's judgement sticks.** When an investigator dismisses an alert, the same alert is not raised again
  unless the risk becomes more severe.

## 2. AI as decision support, not automatic denial

- The engine produces a score, a level, an explanation and a **recommendation**. It never changes an
  application's status, holds a disbursement or labels a student fraudulent.
- Holding or releasing a disbursement, and recording a review decision (in review, cleared or escalated), are
  actions only a person with the right permission can take. Each one is recorded in the audit trail.
- The highest recommendation reads: *"Hold pending disbursements and open an investigation. No adverse action may
  be taken without human review."*
- A failed identity verification **never denies aid by itself**. It raises or upgrades an alert and recommends
  what a person should do next.

## 3. Human investigation of suspicious activity

- High and critical risk open an **alert** in a review queue. A person acknowledges, dismisses or reopens it.
- Every alert opens onto an **explained assessment**: each signal, its points, the evidence behind it, the method
  that produced it, and the rule and model versions. Investigators can see *why* and challenge it.
- Roles separate duties. Financial aid officers handle day-to-day review. Fraud investigators can also re-run
  assessments and detection. Auditors can see the work and the audit trail but cannot change anything or see
  unmasked names.
- The investigation-case API supports evidence, notes, assignment and resolution, with tenant scoping, permissions
  and audit records. The full investigator workspace UI and a visual timeline are not yet built; today, staff use
  the alert, application and disbursement screens alongside the API workflow.

## 4. False positives and potential bias

**What the design does about them:**

- **No demographic or financial-need inputs.** No signal uses income, Student Aid Index, dependency status, age or
  any demographic attribute.
- **Combination over coincidence.** Scores combine signals, so one weak coincidence cannot make a record high risk.
- **Capped machine learning.** The anomaly model's influence is capped (weight 0.30). It can draw attention but
  cannot make a record critical on its own.
- **Explanations everywhere.** Every score can be inspected signal by signal, so an unfair driver is visible rather
  than hidden inside a model.
- **Versioned and reproducible.** Every assessment records the rule and model versions, so a disputed result can be
  traced and re-examined.

**Known risks we have not yet eliminated:**

- **Proxy features.** Some behavioural inputs can correlate with protected or vulnerable groups:
  - Online-only enrollment and credit hours (anomaly-model features) can reflect working adults, caregivers,
    part-time students or students with disabilities.
  - Off-hours submission (weight 0.05, context only) can reflect shift workers.
  - Missing attendance data (`NO_ATTENDANCE`, 0.35) can be a record-keeping gap rather than fraud.

  Their weights are limited, but they need measurement on real data.
- **Synthetic tuning.** Weights and the anomaly model were tuned on synthetic data. Real false-positive rates are
  unknown, and **no accuracy is claimed**.
- **Face matching bias.** Real face-recognition systems have documented accuracy differences across demographic
  groups. This prototype simulates face matching, so it neither has nor fixes that problem. Any real vendor would
  need independent bias testing. In the meantime, alternatives are always available and a failure never decides an
  outcome.

**Before any real deployment:** measure false-positive rates overall and across student groups on consented
institutional data, review proxy features, set and publish acceptable error thresholds, and re-test after every
rule or model version change.

## 5. Alternative identity verification

- **Consent first.** Biometric verification runs only for students who have explicitly consented. For anyone else,
  the API refuses the request (`409 biometric_consent_required`), and the refusal is recorded in the audit trail.
- **Equal alternatives.** Staff can verify a student by **in-person ID check, officer video call or mailed code**,
  recorded with mandatory notes. These are full verification methods, not second-class options.
- **Inconclusive is not failure.** Poor image quality (for example, glare on a document) produces "manual review",
  with a recommendation to retry or use an alternative method.
- **Real-world reasons for failure are expected.** A failed check prompts contact through a known-good channel and
  an officer-assisted verification, not an automatic consequence.

## 6. Protecting sensitive information

- **Tokenized identifiers.** SSNs, full dates of birth, contact details, device and network identifiers are stored
  only as keyed HMAC-SHA256 pseudonyms. Payment destinations keep only a token and a two-digit display label.
- **Encrypted, masked names.** Student names are encrypted at rest and masked on screen. Revealing a name requires
  the `pii:reveal` permission and a written reason, and the reveal is audited. Auditors cannot reveal names.
- **No biometric vault.** Only scores, outcomes and reason codes are stored. There are no image or template
  columns, and an automated test checks that.
- **Least privilege and isolation.** Five roles with explicit permissions, enforced by the API on every request.
  Each institution sees only its own records. A cross-institution match reveals only that a match exists, never the
  other school's data.
- **Tamper-evident accountability.** Sign-ins, reviews, holds, verifications (including refusals), name reveals and
  permission denials go to an append-only, hash-chained audit trail. Database triggers block updates and deletes.
- **Careful logging.** Logs redact passwords, tokens and SSN-shaped values, and never record request bodies.
- **Safe defaults for production.** In production mode the API refuses to start with development secrets, without
  an encryption key, or on SQLite.

## 7. Synthetic data in the demonstration

- **Every** student, application, enrollment, disbursement and verification in the demo is generated. The three
  institutions are fictional, and all eight staff accounts are fictional people.
- Synthetic SSNs use area number `000`, which is never issued to a real person, and are discarded after
  tokenization.
- Records are flagged `is_synthetic`, and the app permanently shows a "Synthetic demonstration data" notice.
- No real student data, Federal Student Aid data or FAFSA systems are used or connected. EduShield AI is not
  affiliated with, endorsed by or connected to Federal Student Aid or the U.S. Department of Education.

## 8. What a real deployment would still need

The prototype demonstrates the safeguards in software. A real institution would also need:

- A legal and privacy review covering student-records and biometric-privacy law in its jurisdictions.
- Clear notice to students, documented consent, and a way for students to **see and contest** a decision. The
  prototype has no student-facing portal or appeal workflow yet.
- Written policies on who may act on an alert, and on what evidence.
- The evaluation and bias testing described in section 4, repeated over time.

We would rather show these gaps plainly than let a prototype be mistaken for a finished, validated system.
