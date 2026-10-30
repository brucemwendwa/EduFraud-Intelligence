import {
  ArrowRight,
  Banknote,
  BrainCircuit,
  CheckCircle2,
  ClipboardCheck,
  Database,
  Eye,
  FileSearch,
  FolderKanban,
  Fingerprint,
  KeyRound,
  LayoutDashboard,
  Lock,
  Network,
  ScanFace,
  ScrollText,
  ShieldCheck,
  UserCheck,
  UserX,
  Users,
  type LucideIcon,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { Logo } from '@/components/layout/Logo';
import { cn } from '@/lib/cn';
import { HeroPreview } from './HeroPreview';

const problems: { icon: LucideIcon; title: string; body: string }[] = [
  {
    icon: UserX,
    title: 'Identity impersonation',
    body: 'Stolen credentials are used to take over a real student’s account and redirect their aid refund.',
  },
  {
    icon: Users,
    title: 'Synthetic & duplicate identities',
    body: 'One identity attribute appears across several applications with conflicting names or dates of birth.',
  },
  {
    icon: Banknote,
    title: 'Refund redirection',
    body: 'Unrelated students’ disbursements quietly converge on the same payment destination.',
  },
  {
    icon: Network,
    title: 'Coordinated rings',
    body: 'Groups of online-only enrollments share devices and contact details, but none of them ever attends class.',
  },
];

const steps: { icon: LucideIcon; title: string; body: string }[] = [
  { icon: Database, title: 'Ingest', body: 'Application, enrollment and disbursement records arrive with identity attributes tokenized.' },
  { icon: ScanFace, title: 'Verify', body: 'Document, face, liveness and presentation-attack checks run when the risk calls for it.' },
  { icon: BrainCircuit, title: 'Detect', body: 'Rules, an anomaly model and graph analysis score every record.' },
  { icon: Eye, title: 'Explain', body: 'Each score lists its signals, their weight, the method used and the rule version.' },
  { icon: FolderKanban, title: 'Investigate', body: 'People review the evidence, record a decision, and every action is logged.' },
];

// `status` marks capabilities whose screens are not built yet, so the page never overstates the prototype.
const features: { icon: LucideIcon; title: string; body: string; status?: string }[] = [
  { icon: LayoutDashboard, title: 'Fraud intelligence dashboard', body: 'Alerts, risk distribution, verification outcomes and case progress in one view.', status: 'Planned' },
  { icon: Fingerprint, title: 'Biometric identity protection', body: 'Step-up verification with liveness and anti-spoofing behind a vendor-neutral provider interface.' },
  { icon: FileSearch, title: 'Application fraud detection', body: 'Search, filter and triage applications with risk explanations attached.' },
  { icon: BrainCircuit, title: 'Explainable AI engine', body: 'Rule signals combine with an Isolation Forest, with attributions you can inspect.' },
  { icon: Network, title: 'Fraud network intelligence', body: 'An interactive graph links identities, devices and payment destinations; cluster membership raises risk scores.' },
  { icon: Banknote, title: 'Disbursement monitoring', body: 'Catches repeated destinations, unusual amounts and bursts of payments before funds move.' },
  { icon: FolderKanban, title: 'Investigation workspace', body: 'Cases hold evidence, timelines, notes and resolutions, with role-based assignment.', status: 'Planned' },
  { icon: ScrollText, title: 'Audit & security center', body: 'Tamper-evident, hash-chained audit trail covering every sensitive action.', status: 'UI planned' },
];

const safeguards: { icon: LucideIcon; title: string; body: string }[] = [
  { icon: UserCheck, title: 'Human decisions', body: 'The AI recommends; investigators decide. Aid is never denied on a score alone.' },
  { icon: KeyRound, title: 'Tokenized identities', body: 'SSNs and bank details are never stored, only keyed HMAC pseudonyms.' },
  { icon: Fingerprint, title: 'No biometric vault', body: 'The system keeps scores and reason codes only. It never stores face images or templates.' },
  { icon: Lock, title: 'Tenant isolation', body: 'Each institution sees only its own records. Cross-campus matches reveal nothing about the other school.' },
  { icon: ShieldCheck, title: 'Least-privilege roles', body: 'Five roles with explicit permissions, enforced by the API on every request.' },
  { icon: ScrollText, title: 'Tamper-evident audit', body: 'Append-only events, hash-chained and protected from update or delete by database triggers.' },
  { icon: Eye, title: 'Masked by default', body: 'Student names stay masked until an authorized user enters a reason, and the reveal is logged.' },
  { icon: ClipboardCheck, title: 'Alternative verification', body: 'In-person and officer-assisted paths for students who decline biometrics.' },
];

type Status = 'Operational' | 'Simulated' | 'Planned';
const capabilities: { name: string; status: Status; note: string }[] = [
  { name: 'Rule-based detection & explainable risk scoring', status: 'Operational', note: 'Versioned rules with per-signal contributions' },
  { name: 'Anomaly detection (Isolation Forest)', status: 'Operational', note: 'Trained on synthetic data only, so accuracy is not claimed' },
  { name: 'Fraud network graph analysis', status: 'Operational', note: 'NetworkX clustering feeds risk scores; interactive explorer with anonymised cross-institution links' },
  { name: 'Audit trail, RBAC, tenant isolation', status: 'Operational', note: 'Enforced by the API and covered by automated tests' },
  { name: 'Biometric document, face, liveness & PAD checks', status: 'Simulated', note: 'Deterministic mock provider, labelled throughout' },
  { name: 'Student records & financial data', status: 'Simulated', note: 'Synthetic generator. No real students or FSA data' },
  { name: 'Commercial identity-verification vendor', status: 'Planned', note: 'Provider interface ready; requires institutional contract' },
  { name: 'Investigation cases, dashboard analytics, audit center UI', status: 'Planned', note: 'Data model and permissions exist; screens not built yet' },
  { name: 'SIS / aid-system integrations', status: 'Planned', note: 'Requires institutional authorization and legal approval' },
];

const statusStyle: Record<Status, string> = {
  Operational: 'bg-green-50 text-green-700 ring-green-100',
  Simulated: 'bg-blue-50 text-blue-700 ring-blue-100',
  Planned: 'bg-slate-100 text-slate-600 ring-slate-200',
};

export function LandingPage() {
  return (
    <div className="bg-white text-slate-900">
      <SiteHeader />
      <Hero />
      <TrustStrip />
      <Section id="problem" eyebrow="The problem" title="Financial aid fraud no longer looks like one bad application">
        <p className="mx-auto -mt-4 mb-12 max-w-2xl text-center text-slate-600">
          Modern schemes spread across identities, devices and payment accounts. When each record is reviewed alone,
          it can look legitimate, so manual verification misses the pattern.
        </p>
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {problems.map((p) => (
            <IconCard key={p.title} {...p} />
          ))}
        </div>
      </Section>

      <Section id="how" eyebrow="How it works" title="From raw records to defensible decisions" className="bg-canvas">
        <ol className="grid gap-4 md:grid-cols-5">
          {steps.map((s, i) => (
            <li key={s.title} className="relative rounded-xl border border-slate-200 bg-white p-5 shadow-card">
              <div className="flex items-center gap-3">
                <span className="flex size-9 items-center justify-center rounded-lg bg-navy-900 text-white">
                  <s.icon className="size-4" aria-hidden />
                </span>
                <span className="text-xs font-semibold text-slate-400 tabular">0{i + 1}</span>
              </div>
              <h3 className="mt-4 text-sm font-semibold">{s.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{s.body}</p>
              {i < steps.length - 1 && (
                <ArrowRight aria-hidden className="absolute top-1/2 -right-3.5 z-10 hidden size-5 -translate-y-1/2 rounded-full bg-canvas text-slate-400 md:block" />
              )}
            </li>
          ))}
        </ol>
      </Section>

      <Section id="features" eyebrow="Platform" title="Every module an aid office needs to stop fraud early">
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {features.map((f) => (
            <IconCard key={f.title} {...f} />
          ))}
        </div>
      </Section>

      <Spotlight
        eyebrow="Biometric identity protection"
        title="Stop account takeover at the moment it matters"
        body="When someone tries to change a refund destination, recover an account or sign in from a new device, EduShield AI asks for step-up verification. It checks the ID document, compares the face to the enrolled student, tests liveness and detects presentation attacks. The result is scored and explained, and it raises an alert. The face image itself is never stored. In this prototype those checks are simulated with synthetic test samples: no camera and no real biometrics."
        points={[
          'Vendor-neutral provider interface, with a clearly labelled simulation in this prototype',
          'Detects printed-photo and screen-replay attacks',
          'Alternative in-person verification for students who decline biometrics',
        ]}
        visual={<VerificationVisual />}
      />
      <Spotlight
        reverse
        eyebrow="Fraud network intelligence"
        title="See the ring, not just the record"
        body="Graph analysis links applications that share identity tokens, devices or payment destinations. Membership in a linked cluster raises every member's risk score and is explained like any other signal. Investigators explore each cluster interactively and inspect any node's connected records."
        points={[
          'Clusters of four or more linked applications are flagged',
          'Cross-institution matches without exposing another school’s data',
          'Click any graph node to inspect its details and connected records',
        ]}
        visual={<NetworkVisual />}
        className="bg-canvas"
      />

      <section id="privacy" className="bg-navy-950 py-20 text-white sm:py-24">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <p className="text-center text-xs font-semibold tracking-wider text-blue-300 uppercase">Privacy & security</p>
          <h2 className="mx-auto mt-3 max-w-2xl text-center text-3xl font-semibold tracking-tight sm:text-4xl">
            Trust is part of the architecture
          </h2>
          <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {safeguards.map((s) => (
              <div key={s.title} className="rounded-xl border border-white/10 bg-white/5 p-5">
                <s.icon className="size-5 text-blue-300" aria-hidden />
                <h3 className="mt-4 text-sm font-semibold">{s.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-navy-200/80">{s.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <Section id="status" eyebrow="Transparency" title="What is real, what is simulated, what is next">
        <div className="mx-auto max-w-4xl overflow-hidden rounded-xl border border-slate-200 shadow-card">
          <ul className="divide-y divide-slate-100">
            {capabilities.map((c) => (
              <li key={c.name} className="flex flex-col gap-2 px-5 py-4 sm:flex-row sm:items-center sm:gap-6">
                <span className={cn('w-28 shrink-0 rounded-md px-2 py-0.5 text-center text-xs font-medium ring-1 ring-inset', statusStyle[c.status])}>
                  {c.status}
                </span>
                <span className="flex-1 text-sm font-medium text-slate-900">{c.name}</span>
                <span className="text-sm text-slate-500 sm:w-80">{c.note}</span>
              </li>
            ))}
          </ul>
        </div>
      </Section>

      <Section eyebrow="Expected impact" title="Protect the funding without slowing down legitimate students" className="bg-canvas">
        <div className="grid gap-5 md:grid-cols-3">
          {[
            ['Catch it before money moves', 'Signals fire at application and pre-disbursement, while funds can still be held for review.'],
            ['Fewer false alarms', 'A single shared address stays low risk. Risk escalates only when independent signals combine.'],
            ['Defensible decisions', 'Every score is explained and every action is audited, giving reviewers and auditors a clear record.'],
          ].map(([title, body]) => (
            <div key={title} className="rounded-xl border border-slate-200 bg-white p-6 shadow-card">
              <CheckCircle2 className="size-5 text-risk-low" aria-hidden />
              <h3 className="mt-4 font-semibold">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">{body}</p>
            </div>
          ))}
        </div>
      </Section>

      <section className="py-20 sm:py-24">
        <div className="mx-auto max-w-4xl px-4 text-center sm:px-6">
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">See EduShield AI in action</h2>
          <p className="mx-auto mt-4 max-w-xl text-slate-600">
            Sign in with a demo role and walk through five synthetic fraud scenarios, from impersonation to a
            coordinated ring. Legitimate students are included to show what should not be flagged.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link
              to="/login"
              className="inline-flex h-11 items-center gap-2 rounded-lg bg-navy-900 px-5 text-sm font-medium text-white shadow-sm hover:bg-navy-800"
            >
              Launch the live demo <ArrowRight className="size-4" aria-hidden />
            </Link>
            <a
              href="/api/docs"
              className="inline-flex h-11 items-center rounded-lg border border-slate-200 px-5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Explore the API
            </a>
          </div>
        </div>
      </section>
      <SiteFooter />
    </div>
  );
}

function SiteHeader() {
  return (
    <header className="absolute inset-x-0 top-0 z-20">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
        <Link to="/" aria-label="EduShield AI home">
          <Logo tone="light" />
        </Link>
        <nav aria-label="Main" className="hidden items-center gap-7 text-sm text-navy-100/80 md:flex">
          <a href="#problem" className="hover:text-white">Problem</a>
          <a href="#how" className="hover:text-white">How it works</a>
          <a href="#features" className="hover:text-white">Platform</a>
          <a href="#privacy" className="hover:text-white">Privacy</a>
        </nav>
        <Link
          to="/login"
          className="inline-flex h-9 items-center rounded-lg bg-white px-3.5 text-sm font-medium text-navy-900 hover:bg-navy-50"
        >
          Sign in
        </Link>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden bg-navy-950 pt-28 pb-24 text-white sm:pt-36 sm:pb-32">
      <div
        aria-hidden
        className="absolute inset-0 opacity-[0.07] [background-image:linear-gradient(to_right,white_1px,transparent_1px),linear-gradient(to_bottom,white_1px,transparent_1px)] [background-size:44px_44px] [mask-image:radial-gradient(ellipse_at_top,black,transparent_70%)]"
      />
      <div aria-hidden className="absolute -top-40 right-0 size-[36rem] rounded-full bg-brand-blue/20 blur-3xl" />
      <div className="relative mx-auto grid max-w-6xl items-center gap-16 px-4 sm:px-6 lg:grid-cols-[1.05fr_1fr]">
        <div>
          <p className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs font-medium text-navy-100">
            <span className="size-1.5 rounded-full bg-flag-red" aria-hidden />
            Fraud intelligence for U.S. financial aid offices
          </p>
          <h1 className="mt-6 text-4xl leading-[1.08] font-semibold tracking-tight sm:text-5xl lg:text-[3.25rem]">
            Protecting Student Financial Aid Through Intelligence.
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-relaxed text-navy-100/80">
            Detect identity impersonation, uncover suspicious financial aid patterns and empower institutions with
            explainable AI-driven fraud intelligence.
          </p>
          <div className="mt-9 flex flex-wrap gap-3">
            <Link
              to="/login"
              className="inline-flex h-11 items-center gap-2 rounded-lg bg-white px-5 text-sm font-semibold text-navy-900 hover:bg-navy-50"
            >
              Explore the live demo <ArrowRight className="size-4" aria-hidden />
            </Link>
            <a
              href="#how"
              className="inline-flex h-11 items-center rounded-lg border border-white/20 px-5 text-sm font-medium text-white hover:bg-white/10"
            >
              See how it works
            </a>
          </div>
        </div>
        <HeroPreview />
      </div>
    </section>
  );
}

function TrustStrip() {
  const items = ['Synthetic data only', 'Human review for every high-risk case', 'Explainable, versioned signals', 'Institution-level isolation'];
  return (
    <div className="border-b border-slate-100 bg-white">
      <ul className="mx-auto flex max-w-6xl flex-wrap justify-center gap-x-10 gap-y-3 px-4 py-6 text-sm text-slate-600 sm:px-6">
        {items.map((i) => (
          <li key={i} className="flex items-center gap-2">
            <CheckCircle2 className="size-4 text-navy-600" aria-hidden />
            {i}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Section({
  id,
  eyebrow,
  title,
  children,
  className,
}: {
  id?: string;
  eyebrow: string;
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section id={id} className={cn('py-20 sm:py-24', className)}>
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <p className="text-center text-xs font-semibold tracking-wider text-brand-blue uppercase">{eyebrow}</p>
        <h2 className="mx-auto mt-3 mb-12 max-w-3xl text-center text-3xl font-semibold tracking-tight sm:text-4xl">{title}</h2>
        {children}
      </div>
    </section>
  );
}

function IconCard({ icon: Icon, title, body, status }: { icon: LucideIcon; title: string; body: string; status?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <span className="flex size-10 items-center justify-center rounded-lg bg-navy-50 text-navy-700">
          <Icon className="size-5" aria-hidden />
        </span>
        {status && (
          <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 ring-1 ring-slate-200 ring-inset">
            {status}
          </span>
        )}
      </div>
      <h3 className="mt-5 font-semibold">{title}</h3>
      <p className="mt-2 text-sm leading-relaxed text-slate-600">{body}</p>
    </div>
  );
}

function Spotlight({
  eyebrow,
  title,
  body,
  points,
  visual,
  reverse,
  className,
}: {
  eyebrow: string;
  title: string;
  body: string;
  points: string[];
  visual: ReactNode;
  reverse?: boolean;
  className?: string;
}) {
  return (
    <section className={cn('py-20 sm:py-24', className)}>
      <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 sm:px-6 lg:grid-cols-2">
        <div className={cn(reverse && 'lg:order-2')}>
          <p className="text-xs font-semibold tracking-wider text-brand-blue uppercase">{eyebrow}</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight">{title}</h2>
          <p className="mt-4 leading-relaxed text-slate-600">{body}</p>
          <ul className="mt-6 space-y-3">
            {points.map((p) => (
              <li key={p} className="flex gap-3 text-sm text-slate-700">
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-navy-600" aria-hidden />
                {p}
              </li>
            ))}
          </ul>
        </div>
        <div>{visual}</div>
      </div>
    </section>
  );
}

function VerificationVisual() {
  const stages = [
    { label: 'Identity document', result: 'Authentic · data consistent', ok: true },
    { label: 'Face comparison', result: 'Similarity 0.21 · mismatch', ok: false },
    { label: 'Liveness', result: 'Score 0.18 · not live', ok: false },
    { label: 'Presentation attack', result: 'Screen replay detected', ok: false },
  ];
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-raised" role="img" aria-label="Illustration of a failed step-up verification">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">Step-up verification · refund destination change</p>
        <span className="rounded-md bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-700 ring-1 ring-blue-100">Simulation</span>
      </div>
      <ol className="mt-5 space-y-3">
        {stages.map((s) => (
          <li key={s.label} className="flex items-center gap-3 rounded-lg border border-slate-100 px-3.5 py-3">
            <span className={cn('size-2 rounded-full', s.ok ? 'bg-risk-low' : 'bg-risk-critical')} aria-hidden />
            <span className="flex-1 text-sm font-medium text-slate-800">{s.label}</span>
            <span className={cn('text-xs', s.ok ? 'text-green-700' : 'text-red-700')}>{s.result}</span>
          </li>
        ))}
      </ol>
      <p className="mt-5 rounded-lg bg-red-50 px-3.5 py-2.5 text-xs font-medium text-red-800 ring-1 ring-red-100">
        Change blocked. Critical alert raised. Recommended next step: in-person identity check.
      </p>
    </div>
  );
}

function NetworkVisual() {
  const nodes = [
    { x: 160, y: 120, r: 16, kind: 'dest' },
    { x: 80, y: 60, r: 10, kind: 'app' },
    { x: 60, y: 150, r: 10, kind: 'app' },
    { x: 120, y: 220, r: 10, kind: 'app' },
    { x: 250, y: 60, r: 10, kind: 'app' },
    { x: 270, y: 170, r: 10, kind: 'app' },
    { x: 210, y: 240, r: 10, kind: 'app' },
    { x: 340, y: 110, r: 13, kind: 'device' },
    { x: 380, y: 210, r: 10, kind: 'app' },
    { x: 420, y: 70, r: 10, kind: 'app' },
  ];
  const edges = [
    [0, 1], [0, 2], [0, 3], [0, 4], [0, 5], [0, 6], [7, 4], [7, 5], [7, 8], [7, 9],
  ];
  const fill = { dest: '#B22234', device: '#2563EB', app: '#102A4C' } as const;
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-raised">
      <svg viewBox="0 0 480 290" className="w-full" role="img" aria-label="Illustration of a fraud network cluster">
        {edges.map(([a, b]) => (
          <line key={`${a}-${b}`} x1={nodes[a]!.x} y1={nodes[a]!.y} x2={nodes[b]!.x} y2={nodes[b]!.y} stroke="#CBD5E1" strokeWidth="1.5" />
        ))}
        {nodes.map((n, i) => (
          <circle key={i} cx={n.x} cy={n.y} r={n.r} fill={fill[n.kind as keyof typeof fill]} stroke="#fff" strokeWidth="2" />
        ))}
      </svg>
      <div className="flex flex-wrap gap-4 border-t border-slate-100 px-2 pt-3 text-xs text-slate-600">
        <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-full bg-navy-800" />Application</span>
        <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-full bg-flag-red" />Shared payment destination</span>
        <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-full bg-brand-blue" />Shared device</span>
      </div>
    </div>
  );
}

function SiteFooter() {
  return (
    <footer className="border-t border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 sm:px-6 md:flex-row md:items-start md:justify-between">
        <div className="max-w-sm">
          <Logo />
          <p className="mt-3 text-sm text-slate-500">Protecting Education Funding Through Intelligence.</p>
        </div>
        <p className="max-w-lg text-xs leading-relaxed text-slate-500">
          EduShield AI is a prototype decision-support system. It is not affiliated with, endorsed by or connected
          to the U.S. Department of Education, Federal Student Aid or FAFSA systems. All students, institutions and
          records shown are synthetic. Any future integration requires institutional authorization and legal review.
        </p>
      </div>
    </footer>
  );
}
