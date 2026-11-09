import { execSync } from 'node:child_process';
import { expect, test, type Browser, type Page } from '@playwright/test';

/**
 * Acceptance scenarios for the full application lifecycle, run against a live stack.
 *
 * Evidence steps need storage and a scanner, so they run with E2E_DOCUMENTS=1.
 * The scanner-outage scenario also needs E2E_SCANNER_STOP and E2E_SCANNER_START commands.
 */
const PASSWORD = 'EduShield!Demo2026';
const STUDENT_PASSWORD = 'Correct-Horse-2026!';
const DEMO_STUDENT = 'student@northbridge.demo';
const OFFICER = 'officer@northbridge.demo';
const AUDITOR = 'auditor@northbridge.demo';
const ADMIN = 'inst.admin@northbridge.demo';
const OTHER_INSTITUTION = 'investigator@lakeshore.demo';
const CLIENT = { 'X-EduShield-Client': 'web' };
const documents = Boolean(process.env.E2E_DOCUMENTS);
const pdf = (body: string) => Buffer.from(`%PDF-1.7\n${body}\n%%EOF\n`);

async function login(page: Page, email: string, password: string, landing: string) {
  await page.goto('/login');
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: /^Sign in/ }).click();
  await page.waitForURL(`**${landing}`);
}

async function open(browser: Browser, email: string, landing: string, password = PASSWORD) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  await login(page, email, password, landing);
  return page;
}

async function inviteFreshStudent(browser: Browser) {
  const admin = await open(browser, ADMIN, '/app');
  const queue = await (await admin.request.get('/api/v1/applications?page_size=100')).json();
  const candidates = queue.items.filter((a: { student: { student_ref: string } }) => a.student.student_ref !== 'STU-00001');
  const application = candidates[Date.now() % candidates.length];
  const email = `accept.${Date.now()}@students.northbridge.demo`;
  await admin.goto(`/app/applications/${application.id}`);
  await admin.getByRole('button', { name: 'Invite to student portal' }).click();
  const dialog = admin.getByRole('dialog');
  await dialog.getByLabel("Student's email address").fill(email);
  await dialog.getByRole('button', { name: 'Send invitation' }).click();
  await expect(dialog.getByText(/no email was sent/)).toBeVisible();
  const link = (await dialog.locator('code').textContent())!;
  await admin.context().close();
  return { email, link };
}

async function fillApplication(page: Page, program: string) {
  await page.getByLabel('Award year').fill('2026-2027');
  await page.getByLabel('Program').fill(program);
  await page.getByLabel('Dependency status').selectOption('independent');
  await page.getByLabel('Enrollment intensity').selectOption('full_time');
  await page.getByLabel('Requested amount').fill('6500');
  await page.getByLabel('Student aid index').fill('1200');
}

async function decide(staff: Page, id: string, decision: string, note: string, message?: string) {
  await staff.goto(`/app/applications/${id}`);
  await staff.getByRole('button', { name: 'Record review' }).click();
  const dialog = staff.getByRole('dialog');
  await dialog.getByLabel('Application decision').selectOption(decision);
  await dialog.getByLabel('Internal review note').fill(note);
  if (message) await dialog.getByLabel(/Message to the student/).fill(message);
  await dialog.getByRole('button', { name: 'Save decision' }).click();
  await expect(dialog).toBeHidden();
}

async function apiDraft(student: Page, program: string) {
  const body = { award_year: '2026-2027', dependency_status: 'independent', enrollment_intensity: 'full_time', program, requested_amount: '6500.00', student_aid_index: 1200 };
  const created = await student.request.post('/api/v1/student-applications', { data: body, headers: CLIENT });
  expect(created.status()).toBe(201);
  return (await created.json()) as { id: string; reference: string };
}

test.describe('student and staff lifecycle', () => {
  test('an invited student applies and staff reach an audited decision', async ({ browser }) => {
    test.setTimeout(240_000);
    // Student steps 1-4: invitation, activation, sign-in, dashboard.
    const { email, link } = await inviteFreshStudent(browser);
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const student = await context.newPage();
    await student.goto(link);
    await student.getByLabel('Create password').fill(STUDENT_PASSWORD);
    await student.getByLabel('Confirm password').fill(STUDENT_PASSWORD);
    await student.getByRole('button', { name: 'Activate account' }).click();
    await expect(student.getByRole('heading', { name: 'Account activated' })).toBeVisible();
    await login(student, email, STUDENT_PASSWORD, '/student');
    await expect(student.getByRole('heading', { name: /^Welcome/ })).toBeVisible();

    // Student steps 5-7: create, save a draft, submit.
    const program = `Acceptance Nursing ${Date.now()}`;
    await student.goto('/student/applications/new');
    await fillApplication(student, program);
    await student.getByRole('button', { name: 'Save draft' }).click();
    await student.waitForURL(/\/student\/applications\/[0-9a-f-]{36}$/);
    const id = student.url().split('/').pop()!;
    await expect(student.getByText('Current status').locator('..').getByText('Draft', { exact: true })).toBeVisible();
    await student.getByRole('button', { name: 'Submit application' }).click();
    await expect(student.getByText('Current status').locator('..').getByText('Submitted', { exact: true })).toBeVisible();
    const reference = (await student.getByRole('heading', { level: 1 }).textContent())!.trim();

    // Staff steps 1-7: institution dashboard, open, review, explainable risk, request information.
    const officer = await open(browser, OFFICER, '/app');
    await expect(officer.getByRole('heading', { name: 'Application pipeline' })).toBeVisible();
    await officer.goto(`/app/applications?queue=awaiting_review&q=${reference}`);
    await officer.getByRole('link', { name: reference }).click();
    await expect(officer.getByText(program)).toBeVisible();
    await expect(officer.getByText('Explainable risk assessment')).toBeVisible();
    await expect(officer.getByText('Limitations of this result')).toBeVisible();
    await decide(officer, id, 'additional_information_required', 'Internal: term mismatch to check.', 'Please upload your enrollment letter.');

    // Student steps 8-11: the request arrives; evidence is uploaded and scanned; the student responds.
    await student.goto('/student');
    const request = student.locator('section', { hasText: 'needs more information' }).locator('li', { hasText: reference });
    await expect(request.getByText('Please upload your enrollment letter.')).toBeVisible();
    await request.getByRole('link', { name: /Respond/ }).click();
    await student.waitForURL(`**/student/applications/${id}`);
    await expect(student.locator('body')).not.toContainText('term mismatch');
    if (documents) {
      await student.getByLabel('Choose a file').setInputFiles({ name: 'enrollment-letter.pdf', mimeType: 'application/pdf', buffer: pdf('synthetic letter') });
      await student.getByRole('button', { name: 'Upload', exact: true }).click();
      await expect(student.locator('li', { hasText: 'enrollment-letter.pdf' }).getByText('Security checks passed')).toBeVisible({ timeout: 45_000 });
    }
    await student.getByLabel(/Note to your financial aid office/).fill('My enrollment letter is attached.');
    await student.getByRole('button', { name: 'Resubmit application' }).click();
    await expect(student.getByLabel('Program')).toBeDisabled();

    // Staff steps 5, 8-9: eligible evidence, the response, an authorized decision.
    await officer.goto(`/app/applications/${id}`);
    await officer.getByRole('tab', { name: /History/ }).click();
    await expect(officer.getByText('My enrollment letter is attached.')).toBeVisible();
    if (documents) {
      await officer.getByRole('tab', { name: 'Evidence' }).click();
      await expect(officer.locator('li', { hasText: 'enrollment-letter.pdf' }).getByRole('button', { name: 'Download' })).toBeEnabled();
    }
    await decide(officer, id, 'approved', 'Enrollment confirmed against the registrar record.');

    // Student step 12: the decision is visible.
    await student.goto(`/student/applications/${id}`);
    await expect(student.getByText('Your application was approved')).toBeVisible();

    // Staff step 10: audit events are recorded and the chain is intact.
    const admin = await open(browser, ADMIN, '/app');
    const events = await (await admin.request.get(`/api/v1/audit/events?q=${reference}&page_size=50`)).json();
    const actions = events.items.map((e: { action: string }) => e.action);
    for (const action of ['application.draft_create', 'application.submit', 'application.status_change', 'application.review']) expect(actions).toContain(action);
    expect((await (await admin.request.get('/api/v1/audit/verify')).json()).valid).toBe(true);
    await Promise.all([context.close(), officer.context().close(), admin.context().close()]);
  });
});

test.describe('administrator', () => {
  test('sees institution-scoped operations and manages staff within limits', async ({ browser }) => {
    const admin = await open(browser, ADMIN, '/app');
    await admin.getByRole('link', { name: 'Operations' }).click();
    await expect(admin.getByRole('heading', { name: 'Service health' })).toBeVisible();
    await expect(admin.getByRole('heading', { name: 'Processing activity' })).toBeVisible();
    await expect(admin.getByText('Background jobs')).toBeVisible();

    await admin.getByRole('link', { name: 'Institutions & users' }).click();
    await admin.waitForURL('**/app/institutions');
    await admin.getByRole('button', { name: 'Invite staff' }).click();
    const dialog = admin.getByRole('dialog');
    const email = `new.staff.${Date.now()}@northbridge.example`;
    await dialog.getByLabel('Email address').fill(email);
    await dialog.getByLabel('Full name').fill('New Staff Member');
    await dialog.getByLabel('Role').selectOption('auditor');
    await dialog.getByRole('button', { name: 'Send invitation' }).click();
    const link = (await dialog.locator('code').textContent())!;
    await dialog.getByRole('button', { name: 'Done' }).click();

    const context = await browser.newContext();
    const staff = await context.newPage();
    await staff.goto(link);
    await staff.getByLabel('Create password').fill(STUDENT_PASSWORD);
    await staff.getByLabel('Confirm password').fill(STUDENT_PASSWORD);
    await staff.getByRole('button', { name: 'Activate account' }).click();
    await expect(staff.getByRole('heading', { name: 'Account activated' })).toBeVisible();
    await login(staff, email, STUDENT_PASSWORD, '/app');
    await context.close();

    // Unauthorized administrative actions are refused by the API.
    const me = await (await admin.request.get('/api/v1/auth/me')).json();
    const own = await admin.request.patch(`/api/v1/users/${me.id}`, { data: { role_key: 'auditor' }, headers: CLIENT });
    expect(own.status()).toBe(403);
    const grant = await admin.request.post('/api/v1/staff-invitations', { data: { email: `x${Date.now()}@northbridge.example`, full_name: 'Escalation Attempt', role_key: 'platform_admin' }, headers: CLIENT });
    expect(grant.status()).toBe(403);
    const officer = await open(browser, OFFICER, '/app');
    expect((await officer.request.get('/api/v1/users')).status()).toBe(403);
    expect((await officer.request.get('/api/v1/operations/overview')).status()).toBe(403);
    await Promise.all([admin.context().close(), officer.context().close()]);
  });
});

test.describe('negative scenarios', () => {
  test('access stays within the owner and the institution', async ({ browser }) => {
    const student = await open(browser, DEMO_STUDENT, '/student');
    const officer = await open(browser, OFFICER, '/app');
    const queue = await (await officer.request.get('/api/v1/applications?page_size=1')).json();
    const target = queue.items[0].id;
    expect((await student.request.get(`/api/v1/student-applications/${target}`)).status()).toBe(404);
    expect((await student.request.get(`/api/v1/student-applications/${target}/documents`)).status()).toBe(404);
    expect((await student.request.get('/api/v1/applications')).status()).toBe(403);
    const other = await open(browser, OTHER_INSTITUTION, '/app');
    expect((await other.request.get(`/api/v1/applications/${target}`)).status()).toBe(404);
    expect((await other.request.get(`/api/v1/applications/${target}/documents`)).status()).toBe(404);
    await Promise.all([student.context().close(), officer.context().close(), other.context().close()]);
  });

  test('an invalid or signed-out session cannot be reused', async ({ browser }) => {
    const student = await open(browser, DEMO_STUDENT, '/student');
    const [session] = (await student.context().cookies()).filter((c) => c.name === 'edushield_session');
    await student.getByRole('button', { name: 'Sign out' }).click();
    await student.waitForURL('**/login');

    const replay = await browser.newContext();
    await replay.addCookies([session!]);
    const copied = await replay.newPage();
    expect((await copied.request.get('/api/v1/auth/me')).status()).toBe(401);
    await copied.goto('/student');
    await copied.waitForURL('**/login');

    const invalid = await browser.newContext();
    await invalid.addCookies([{ ...session!, value: 'not-a-valid-session' }]);
    const page = await invalid.newPage();
    expect((await page.request.get('/api/v1/auth/me')).status()).toBe(401);
    await Promise.all([student.context().close(), replay.close(), invalid.close()]);
  });

  test('a revoked invitation cannot activate an account', async ({ browser }) => {
    const admin = await open(browser, ADMIN, '/app');
    const created = await admin.request.post('/api/v1/staff-invitations', { data: { email: `revoked.${Date.now()}@northbridge.example`, full_name: 'Revoked Person', role_key: 'auditor' }, headers: CLIENT });
    const invitation = await created.json();
    expect((await admin.request.post(`/api/v1/staff-invitations/${invitation.id}/revoke`, { headers: CLIENT })).status()).toBe(200);
    const token = new URL(invitation.activation_url).searchParams.get('token');
    const refused = await admin.request.post('/api/v1/staff-activation', { data: { token, password: STUDENT_PASSWORD }, headers: CLIENT });
    expect(refused.status()).toBe(401);
    await admin.context().close();
  });

  test('read-only staff, repeated submissions and invalid transitions are refused', async ({ browser }) => {
    const student = await open(browser, DEMO_STUDENT, '/student');
    const officer = await open(browser, OFFICER, '/app');
    const auditor = await open(browser, AUDITOR, '/app');
    const draft = await apiDraft(student, 'Acceptance Negative');
    const submit = () => student.request.post(`/api/v1/student-applications/${draft.id}/submit`, { headers: CLIENT });
    expect((await submit()).status()).toBe(200);
    expect((await submit()).status()).toBe(409);

    const review = (client: Page, status: string, extra = {}) => client.request.patch(`/api/v1/applications/${draft.id}/review`, { data: { review_status: 'in_review', application_status: status, note: 'Acceptance decision.', ...extra }, headers: CLIENT });
    expect((await review(auditor, 'approved')).status()).toBe(403);
    expect((await review(officer, 'rejected')).status()).toBe(422);
    expect((await review(officer, 'approved')).status()).toBe(200);
    expect((await review(officer, 'in_review')).status()).toBe(409);
    await Promise.all([student.context().close(), officer.context().close(), auditor.context().close()]);
  });

  test('unscanned and infected evidence cannot be downloaded', async ({ browser }) => {
    test.skip(!documents, 'Requires object storage and a malware scanner (E2E_DOCUMENTS=1).');
    test.skip(!process.env.EICAR_STRING, 'Requires the EICAR test string.');
    test.setTimeout(120_000);
    const student = await open(browser, DEMO_STUDENT, '/student');
    const draft = await apiDraft(student, 'Acceptance Infected');
    await student.goto(`/student/applications/${draft.id}`);
    await student.getByLabel('Choose a file').setInputFiles({ name: 'infected.pdf', mimeType: 'application/pdf', buffer: pdf(process.env.EICAR_STRING!) });
    await student.getByRole('button', { name: 'Upload', exact: true }).click();
    const row = student.locator('li', { hasText: 'infected.pdf' });
    await expect(row.getByText('Security checks rejected this document.')).toBeVisible({ timeout: 45_000 });
    await expect(row.getByRole('button', { name: 'Download' })).toBeDisabled();
    const listed = await (await student.request.get(`/api/v1/student-applications/${draft.id}/documents`)).json();
    expect((await student.request.post(`/api/v1/student-documents/${listed[0].id}/download`, { headers: CLIENT })).status()).toBe(409);
    await student.context().close();
  });

  test('a scanner outage quarantines evidence without blocking the student', async ({ browser }) => {
    test.skip(!documents || !process.env.E2E_SCANNER_STOP || !process.env.E2E_SCANNER_START, 'Requires control of a live scanner.');
    test.setTimeout(300_000);
    const student = await open(browser, DEMO_STUDENT, '/student');
    const admin = await open(browser, ADMIN, '/app');
    const draft = await apiDraft(student, 'Acceptance Outage');
    execSync(process.env.E2E_SCANNER_STOP!, { stdio: 'ignore' });
    try {
      await student.goto(`/student/applications/${draft.id}`);
      await student.getByLabel('Choose a file').setInputFiles({ name: 'during-outage.pdf', mimeType: 'application/pdf', buffer: pdf('synthetic evidence') });
      await student.getByRole('button', { name: 'Upload', exact: true }).click();
      const row = student.locator('li', { hasText: 'during-outage.pdf' });
      await expect(row).toBeVisible({ timeout: 20_000 });
      await expect(row.getByRole('button', { name: 'Download' })).toBeDisabled();
      const listed = await (await student.request.get(`/api/v1/student-applications/${draft.id}/documents`)).json();
      expect(listed[0].status).not.toBe('available');
      expect((await student.request.post(`/api/v1/student-documents/${listed[0].id}/download`, { headers: CLIENT })).status()).toBe(409);
      expect((await student.request.post(`/api/v1/student-applications/${draft.id}/submit`, { headers: CLIENT })).status()).toBe(200);
      const overview = await (await admin.request.get('/api/v1/operations/overview')).json();
      expect(overview.health.find((c: { key: string }) => c.key === 'scanner').status).toBe('down');
      expect(overview.overall_health).toBe('down');
    } finally {
      execSync(process.env.E2E_SCANNER_START!, { stdio: 'ignore' });
    }
    // The durable job retries on the scheduler and clears the document once the scanner is back.
    await expect(async () => {
      const listed = await (await student.request.get(`/api/v1/student-applications/${draft.id}/documents`)).json();
      expect(listed[0].status).toBe('available');
    }).toPass({ timeout: 200_000, intervals: [5_000] });
    await Promise.all([student.context().close(), admin.context().close()]);
  });
});
