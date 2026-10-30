# AI Disclosure

This document states exactly which parts of EduShield AI are rules, which are machine learning, which are
simulated and which are only planned. It applies to the prototype in this repository (engine method
`hybrid: versioned rules + isolation forest + graph analysis`; versions `rules-2026.10.1`,
`iforest-0.1.0-synthetic`, `graph-2026.10.1`).

**In one sentence:** EduShield AI scores records with deterministic rules and graph analysis, adds a small,
capped signal from an unsupervised anomaly model trained only on synthetic data, simulates biometric checks, and
leaves every decision to a person.

## Summary

| Component | Status | Kind | Learns from data? |
|---|---|---|---|
| Fraud rules (17) | **Operational** | Deterministic, hand-written rules | No |
| Graph analysis (linked clusters) | **Operational** | Deterministic graph algorithm (NetworkX connected components) | No |
| Risk scoring and levels | **Operational** | Deterministic formula (noisy-OR) and fixed thresholds | No |
| Anomaly detection | **Operational, synthetic-trained** | Unsupervised machine learning (scikit-learn Isolation Forest) | Yes, synthetic data only, unlabelled |
| Biometric verification (document, face, liveness, presentation attack) | **Simulated** | Deterministic simulation from synthetic test samples | No |
| Supervised fraud models, real biometric models | **Planned** | Not built | — |
| External services (identity vendor, SIS, aid systems) | **Planned** | Not integrated | — |
| Generative AI / large language models | **Not used** | The product makes no calls to any AI service | — |

## 1. Operational: rule-based fraud detection

Seventeen versioned rules, defined in `backend/app/detection/rules/` and catalogued in
`backend/app/detection/catalog.py`, inspect tokenized identity attributes, devices, network addresses,
enrollment, disbursements and verification outcomes. Each emits a signal with a fixed maximum weight and the
evidence that triggered it.

| Category | Rules (maximum weight) |
|---|---|
| Identity | `SSN_IDENTITY_CONFLICT` (0.55), `CONTACT_REUSE` (0.25), `SHARED_HOUSEHOLD_OR_RESIDENCE` (0.04) |
| Application | `DEVICE_BURST` (0.40), `NETWORK_BURST` (0.20), `SHARED_DEVICE_SPREAD` (0.03), `OFF_HOURS_SUBMISSION` (0.05) |
| Enrollment | `NO_ATTENDANCE` (0.35), `CONCURRENT_ENROLLMENT` (0.25) |
| Disbursement | `DESTINATION_SHARED` (0.45), `DESTINATION_CHANGED_BEFORE_PAYOUT` (0.30), `DESTINATION_CHANGE_VERIFIED` (0.02), `AMOUNT_OUTLIER` (0.35), `DISBURSEMENT_BURST` (0.20) |
| Verification outcome | `FACE_MISMATCH` (0.60), `PRESENTATION_ATTACK` (0.50), `DOCUMENT_SUSPICIOUS` (0.35) |

The weights are expert judgements tuned against the synthetic dataset. They are **not** learned and have **not**
been validated on real fraud.

The three verification-outcome rules read the results of the *simulated* provider (section 4). In this prototype,
those three signals are only as meaningful as the simulation behind them.

## 2. Operational: graph analysis and risk scoring

- **Graph analysis.** Applications that share identity tokens, devices or payment destinations are linked in a
  NetworkX graph. Members of a connected cluster of four or more applications receive a `NETWORK_CLUSTER` signal
  (maximum weight 0.40). This is a deterministic algorithm, not machine learning.
- **Score.** Signals combine with a noisy-OR, `score = 100 × (1 − Π(1 − wᵢ))`, and each signal's share is stored
  as its points.
- **Levels.** Low below 30, medium 30–59, high 60–79, critical 80 and above. Each level maps to a fixed, written
  recommendation. High and critical open an alert for a person to review.
- **Reproducibility.** Every assessment stores its signals, points, evidence, method, rule, model and graph
  versions, and a timestamp.

The score is a **prioritization aid**. It is not a probability of fraud and should not be read as one.

## 3. Operational, synthetic-trained: anomaly detection (machine learning)

This is the only machine-learning component in the product.

| | |
|---|---|
| Model | scikit-learn `IsolationForest` (unsupervised; no fraud labels) |
| Purpose | Surface applications whose *combination* of behaviour is unusual, complementing the rules |
| Training data | The current **synthetic** dataset only, retrained on each detection run |
| Features (13) | SSN token shared, contact shared, device burst, network burst, off-hours submission, online-only enrollment, no attendance, credit hours, largest disbursement versus typical, destination shared, destination changed, number of disbursements, failed verification |
| Excluded | Income, Student Aid Index, dependency status, age, and any demographic attribute |
| Output | Flags the most unusual 4% of applications |
| Influence | Capped at a weight of 0.30: it can raise attention but cannot make a record critical on its own |
| Explanation | Occlusion attribution: each feature is replaced by its median, and the change in anomaly score is reported as its contribution |
| Evaluation | **Not evaluated on real-world data. No accuracy, precision, recall or false-positive rate is claimed.** |

The Detection engine page has a **scenario coverage** check. It confirms that each planted synthetic scenario
fires its expected signals and that legitimate look-alike cases stay below high. It is a regression check on the
demo data, **not** an accuracy metric.

## 4. Simulated: biometric identity verification

Document authentication, face matching, liveness detection and presentation-attack detection are **simulated**.

- There is **no camera, no image capture, no face recognition model and no liveness model** in this repository.
- `SimulatedBiometricProvider` (`backend/app/biometrics/simulated.py`) takes the name of a synthetic test sample
  (for example "printed photo of the student"). It derives repeatable scores from fixed ranges for that sample,
  seeded by the student reference.
- It is labelled as a simulation everywhere it appears: `provider_mode: "simulation"` and a "SIMULATED PROVIDER"
  disclaimer in the API, and a "Simulated biometric provider" badge and a "no camera and no images" notice in the
  user interface.
- What *is* real is the **workflow** around it: consent enforcement, the officer-led alternative methods, decision
  rules, re-scoring of the application, alerts, recommendations and audit records.

**EduShield AI does not claim production-grade facial recognition, liveness detection or presentation-attack
detection.** Any real deployment would use an authorized commercial identity-verification vendor through the
provider interface in `backend/app/biometrics/provider.py`. That vendor's accuracy, bias testing and
certifications would need independent review.

## 5. Planned: machine learning capabilities

None of the following exists in this repository:

- Supervised fraud models trained on confirmed, labelled case outcomes.
- Evaluation of any model on real, consented institutional data, with error rates reported overall and across
  student groups.
- Fairness testing and ongoing drift monitoring.
- Learned (rather than hand-set) rule weights.

Any of these would be introduced behind the same rules: capped influence, explanations, versioning and mandatory
human review.

## 6. Planned: external integrations

None of the following is integrated:

- A commercial identity-verification vendor for real document, face and liveness checks.
- Student information systems and financial aid management systems.
- Any connection to Federal Student Aid or FAFSA systems. EduShield AI is not affiliated with, endorsed by or
  connected to Federal Student Aid or the U.S. Department of Education.

Each would require institutional authorization, contracts, a privacy review and legal approval.

## 7. What EduShield AI never does

- It never denies aid, holds a payment, or labels a student fraudulent automatically.
- It never uses income, Student Aid Index, dependency status, age or demographic attributes as signals.
- It never stores face images, document images or biometric templates.
- It never claims a model accuracy figure.

## 8. AI assistance in building this project

The source code, tests and documentation in this repository were written with the help of an AI coding assistant
(Anthropic's Claude), as recorded in the `Co-Authored-By` lines of the commit history. The team directed the work.
Changes were checked with the automated test suites, linting, type checking and manual testing before being
committed.
