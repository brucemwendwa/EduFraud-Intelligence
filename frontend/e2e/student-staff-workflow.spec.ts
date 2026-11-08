import { expect, test, type Browser, type Page } from '@playwright/test';

/**
 * The core product journey against a running stack (synthetic demo data):
 * student drafts and submits → staff request information → student responds → staff decide,
 * with role separation, dashboards and audit checked along the way.
 *
 * The evidence test also needs document storage and a malware scanner, and is skipped unless
 * E2E_DOCUMENTS=1. EICAR_STRING must hold the harmless EICAR test string for its infected-file step.
 */
const PASSWORD = 'EduShield!Demo2026';
const STUDENT = 'student@northbridge.demo';
const OFFICER = 'officer@northbridge.demo';
const ADMIN = 'inst.admin@northbridge.demo';
const OTHER_TENANT = 'investigator@lakeshore.demo';
const shots = process.env.E2E_SCREENSHOTS;

async function signIn(page: Page, email: string, landing: string) {
  await page.goto('/login');
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: /^Sign in/ }).click();
  await page.waitForURL(`**${landing}`);
}

async function asUser(browser: Browser, email: string, landing: string) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  await signIn(page, email, landing);
  return page;
}

async function snap(page: Page, name: string) {
  if (shots) await page.screenshot({ path: `${shots}/${name}.png`, fullPage: true });
}

async function fillApplication(page: Page, program: string) {
  await page.getByLabel('Award year').fill('2026-2027');
  await page.getByLabel('Program').fill(program);
  await page.getByLabel('Dependency status').selectOption('independent');
  await page.getByLabel('Enrollment intensity').selectOption('full_time');
  await page.getByLabel('Requested amount').fill('6500');
  await page.getByLabel('Student aid index').fill('1200');
}

async function startDraft(student: Page, program: string) {
  await student.goto('/student/applications/new');
  await fillApplication(student, program);
  await student.getByRole('button', { name: 'Save draft' }).click();
  await student.waitForURL(/\/student\/applications\/[0-9a-f-]{36}$/);
  return student.url().split('/').pop()!;
}

async function record(staff: Page, id: string, decision: string, note: string, message?: string) {
  await staff.goto(`/app/applications/${id}`);
  await staff.getByRole('button', { name: 'Record review' }).click();
  const dialog = staff.getByRole('dialog');
  await dialog.getByLabel('Application decision').selectOption(decision);
  await dialog.getByLabel('Internal review note').fill(note);
  if (message) await dialog.getByLabel(/Message to the student/).fill(message);
  await dialog.getByRole('button', { name: 'Save decision' }).click();
  await expect(dialog).toBeHidden();
}

test('a student application moves through staff review to an audited decision', async ({ browser }) => {
  const student = await asUser(browser, STUDENT, '/student');
  await expect(student.getByRole('heading', { name: /^Welcome/ })).toBeVisible();
  const program = `E2E Nursing ${Date.now()}`;

  // Student: a blank submission is refused and names what is missing.
  await student.goto('/student/applications/new');
  await student.getByRole('button', { name: 'Submit application' }).click();
  await expect(student.getByRole('alert')).toContainText('Complete the required information');
  await student.waitForURL(/\/student\/applications\/[0-9a-f-]{36}$/);
  const id = student.url().split('/').pop()!;

  // Student: completing the form and submitting saves the typed values first.
  await fillApplication(student, program);
  await student.getByRole('button', { name: 'Submit application' }).click();
  await expect(student.getByText('Current status').locator('..').getByText('Submitted', { exact: true })).toBeVisible();
  await expect(student.getByLabel('Program')).toBeDisabled();
  const reference = (await student.getByRole('heading', { level: 1 }).textContent())!.trim();
  await expect(student.locator('body')).not.toContainText(/risk/i);

  // Staff: it is in the awaiting-review queue, with an explainable, advisory assessment.
  const officer = await asUser(browser, OFFICER, '/app');
  await expect(officer.getByRole('heading', { name: 'Application pipeline' })).toBeVisible();
  await expect(officer.getByRole('link', { name: reference }).first()).toBeVisible();
  await snap(officer, 'staff-dashboard');
  await officer.goto(`/app/applications?queue=awaiting_review&q=${reference}`);
  await officer.getByRole('link', { name: reference }).click();
  await expect(officer.getByText('Explainable risk assessment')).toBeVisible();
  await expect(officer.getByText(/No external fraud database or government identity system was consulted/)).toBeVisible();
  await snap(officer, 'staff-application');

  // Staff: an information request needs a message for the student, separate from the internal note.
  await officer.getByRole('button', { name: 'Record review' }).click();
  const dialog = officer.getByRole('dialog');
  await dialog.getByLabel('Application decision').selectOption('additional_information_required');
  await dialog.getByLabel('Internal review note').fill('Internal: enrollment term mismatch.');
  await expect(dialog.getByRole('button', { name: 'Save decision' })).toBeDisabled();
  await dialog.getByLabel('Message to the student').fill('Please upload your enrollment letter.');
  await dialog.getByRole('button', { name: 'Save decision' }).click();
  await expect(dialog).toBeHidden();

  // Student: sees the request on the dashboard, never the internal note, and responds.
  await student.goto('/student');
  const request = student.locator('section', { hasText: 'needs more information' }).locator('li', { hasText: reference });
  await expect(request.getByText('Please upload your enrollment letter.')).toBeVisible();
  await snap(student, 'student-dashboard');
  await request.getByRole('link', { name: /Respond/ }).click();
  await student.waitForURL(`**/student/applications/${id}`);
  await expect(student.locator('body')).not.toContainText('enrollment term mismatch');
  await student.getByLabel(/Note to your financial aid office/).fill('My enrollment letter is attached.');
  await student.getByRole('button', { name: 'Resubmit application' }).click();
  await expect(student.getByLabel('Program')).toBeDisabled();

  // Staff: the response is on the timeline; rejection requires a reason and is final.
  await officer.goto(`/app/applications/${id}`);
  await officer.getByRole('tab', { name: /History/ }).click();
  await expect(officer.getByText('My enrollment letter is attached.')).toBeVisible();
  await expect(officer.getByText('Internal: enrollment term mismatch.')).toBeVisible();
  await record(officer, id, 'rejected', 'Enrollment could not be confirmed with the registrar.', 'Your enrollment could not be confirmed for this term.');

  // Student: sees the decision and reason, and can no longer change the application.
  await student.goto(`/student/applications/${id}`);
  await expect(student.getByText('Your application was not approved')).toBeVisible();
  await expect(student.getByText('Your enrollment could not be confirmed for this term.').first()).toBeVisible();
  await expect(student.getByRole('button', { name: 'Withdraw application' })).toHaveCount(0);
  await snap(student, 'student-decision');

  // Audit: an authorized administrator can see who did what.
  const admin = await asUser(browser, ADMIN, '/app');
  const events = await (await admin.request.get(`/api/v1/audit/events?q=${reference}&page_size=50`)).json();
  const actions = events.items.map((e: { action: string }) => e.action);
  for (const action of ['application.draft_create', 'application.submit', 'application.status_change', 'application.review']) {
    expect(actions).toContain(action);
  }
  expect((await (await admin.request.get('/api/v1/audit/verify')).json()).valid).toBe(true);
  await Promise.all([student.context().close(), officer.context().close(), admin.context().close()]);
});

test('each role stays in its own area and institution', async ({ browser }) => {
  const student = await asUser(browser, STUDENT, '/student');
  const id = await startDraft(student, 'E2E Access Control');

  // A student is sent away from staff pages, and the API refuses staff data regardless of the UI.
  await student.goto('/app/applications');
  await student.waitForURL('**/student');
  expect((await student.request.get('/api/v1/applications')).status()).toBe(403);
  expect((await student.request.get('/api/v1/operations/overview')).status()).toBe(403);

  // A student cannot open another student's application by changing the URL.
  const officer = await asUser(browser, OFFICER, '/app');
  const others = await (await officer.request.get('/api/v1/applications?page_size=1')).json();
  await student.goto(`/student/applications/${others.items[0].id}`);
  await expect(student.getByText('Application unavailable')).toBeVisible();
  expect((await student.request.get(`/api/v1/student-applications/${others.items[0].id}`)).status()).toBe(404);

  // Staff cannot see an unsubmitted draft, and the operations page is permission-gated.
  expect((await officer.request.get(`/api/v1/applications/${id}`)).status()).toBe(404);
  await expect(officer.getByRole('link', { name: 'Operations' })).toHaveCount(0);
  expect((await officer.request.get('/api/v1/operations/overview')).status()).toBe(403);

  // Another institution's staff get a 404 for this institution's record.
  const other = await asUser(browser, OTHER_TENANT, '/app');
  expect((await other.request.get(`/api/v1/applications/${others.items[0].id}`)).status()).toBe(404);

  // Sessions survive a reload and end at sign-out.
  await student.goto('/student');
  await student.reload();
  await expect(student.getByRole('heading', { name: /^Welcome/ })).toBeVisible();
  await student.getByRole('button', { name: 'Sign out' }).click();
  await student.waitForURL('**/login');
  await student.goto('/student');
  await student.waitForURL('**/login');
  expect((await student.request.get('/api/v1/auth/me')).status()).toBe(401);

  // A write without the client header, as a cross-site form would send it, is refused by the CSRF check.
  const csrf = await officer.request.post('/api/v1/auth/logout');
  expect(csrf.status()).toBe(403);
  expect((await csrf.json()).error.code).toBe('csrf_check_failed');
  await Promise.all([student.context().close(), officer.context().close(), other.context().close()]);
});

test('an institution-issued invitation activates a student account', async ({ browser }) => {
  const admin = await asUser(browser, ADMIN, '/app');
  const queue = await (await admin.request.get('/api/v1/applications?page_size=100')).json();
  const application = queue.items[Date.now() % queue.items.length];
  const email = `invited.${Date.now()}@students.northbridge.demo`;

  await admin.goto(`/app/applications/${application.id}`);
  await admin.getByRole('button', { name: 'Invite to student portal' }).click();
  const dialog = admin.getByRole('dialog');
  await dialog.getByLabel("Student's email address").fill(email);
  await dialog.getByRole('button', { name: 'Send invitation' }).click();
  await expect(dialog.getByText('Development mode: no email was sent.')).toBeVisible();
  const link = (await dialog.locator('code').textContent())!;

  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const student = await context.newPage();
  await student.goto(link);
  await student.getByLabel('Create password').fill('Correct-Horse-2026!');
  await student.getByLabel('Confirm password').fill('Correct-Horse-2026!');
  await student.getByRole('button', { name: 'Activate account' }).click();
  await expect(student.getByRole('heading', { name: 'Account activated' })).toBeVisible();

  // The link is single use.
  await student.goto(link);
  await student.getByLabel('Create password').fill('Correct-Horse-2026!');
  await student.getByLabel('Confirm password').fill('Correct-Horse-2026!');
  await student.getByRole('button', { name: 'Activate account' }).click();
  await expect(student.getByRole('alert')).toContainText('invalid or has expired');

  await student.goto('/login');
  await student.getByLabel('Email address').fill(email);
  await student.getByLabel('Password').fill('Correct-Horse-2026!');
  await student.getByRole('button', { name: /^Sign in/ }).click();
  await student.waitForURL('**/student');
  await expect(student.getByText(application.student.student_ref)).toBeVisible();
  await Promise.all([admin.context().close(), context.close()]);
});

test('the operations page reports live service state to administrators', async ({ browser }) => {
  const admin = await asUser(browser, ADMIN, '/app');
  await admin.getByRole('link', { name: 'Operations' }).click();
  await admin.waitForURL('**/app/operations');
  await expect(admin.getByRole('heading', { name: 'Service health' })).toBeVisible();
  const main = admin.locator('#main');
  await expect(main.getByText('Database', { exact: true })).toBeVisible();
  await expect(main.getByText('Malware scanner', { exact: true })).toBeVisible();
  await expect(main.getByText('Identity verification', { exact: true })).toBeVisible();
  await expect(admin.getByRole('heading', { name: 'Processing activity' })).toBeVisible();
  await expect(admin.getByText('Recent audit events')).toBeVisible();
  await snap(admin, 'operations');
  await admin.context().close();
});

test('evidence stays quarantined until scanned, then flows to staff review', async ({ browser }) => {
  test.skip(!process.env.E2E_DOCUMENTS, 'Requires object storage and a malware scanner (E2E_DOCUMENTS=1).');
  const student = await asUser(browser, STUDENT, '/student');
  const id = await startDraft(student, 'E2E Evidence');
  const pdf = (body: string) => Buffer.from(`%PDF-1.7\n${body}\n%%EOF\n`);

  // A clean upload passes a real scan and becomes downloadable.
  const chooser = student.getByLabel('Choose a file');
  await chooser.setInputFiles({ name: 'enrollment-letter.pdf', mimeType: 'application/pdf', buffer: pdf('synthetic enrollment letter') });
  await student.getByRole('button', { name: 'Upload', exact: true }).click();
  const row = student.locator('li', { hasText: 'enrollment-letter.pdf' });
  await expect(row.getByText('Security checks passed')).toBeVisible({ timeout: 30_000 });
  await expect(row.getByRole('button', { name: 'Download' })).toBeEnabled();
  const documents = await (await student.request.get(`/api/v1/student-applications/${id}/documents`)).json();
  const headers = { 'X-EduShield-Client': 'web' };
  const link = await (await student.request.post(`/api/v1/student-documents/${documents[0].id}/download`, { headers })).json();
  const stored = await student.request.get(link.url);
  expect(stored.ok()).toBeTruthy();
  expect(stored.headers()['content-disposition']).toContain('attachment');
  expect(await stored.text()).toContain('synthetic enrollment letter');

  // A file containing the EICAR test string is rejected and cannot be downloaded.
  if (process.env.EICAR_STRING) {
    await chooser.setInputFiles({ name: 'infected.pdf', mimeType: 'application/pdf', buffer: pdf(process.env.EICAR_STRING) });
    await student.getByRole('button', { name: 'Upload', exact: true }).click();
    const infected = student.locator('li', { hasText: 'infected.pdf' });
    await expect(infected.getByText('Security checks rejected this document.')).toBeVisible({ timeout: 30_000 });
    await expect(infected.getByRole('button', { name: 'Download' })).toBeDisabled();
    const listed = await (await student.request.get(`/api/v1/student-applications/${id}/documents`)).json();
    const rejected = listed.find((d: { original_filename: string }) => d.original_filename === 'infected.pdf');
    expect((await student.request.post(`/api/v1/student-documents/${rejected.id}/download`, { headers })).status()).toBe(409);
  }
  await fillApplication(student, 'E2E Evidence');
  await student.getByRole('button', { name: 'Submit application' }).click();
  await expect(student.getByLabel('Program')).toBeDisabled();
  await snap(student, 'student-evidence');

  // Staff can review only the clean document, and the student sees the decision.
  const officer = await asUser(browser, OFFICER, '/app');
  await officer.goto(`/app/applications/${id}`);
  await officer.getByRole('tab', { name: 'Evidence' }).click();
  const staffRow = officer.locator('li', { hasText: 'enrollment-letter.pdf' });
  await staffRow.getByRole('button', { name: 'Review evidence' }).click();
  const dialog = officer.getByRole('dialog');
  await dialog.getByLabel('Decision').selectOption('replacement_requested');
  await dialog.getByLabel('Reason').fill('The letter is missing the registrar signature.');
  await dialog.getByRole('button', { name: 'Record review' }).click();
  await expect(staffRow.getByText('Review: Replacement requested')).toBeVisible();
  if (process.env.EICAR_STRING) {
    await expect(officer.locator('li', { hasText: 'infected.pdf' }).getByRole('button', { name: 'Review evidence' })).toHaveCount(0);
  }
  await snap(officer, 'staff-evidence');

  // The student replaces it after submission because staff asked; the original stays until the new file clears.
  await student.reload();
  await expect(student.getByText('Staff note: The letter is missing the registrar signature.')).toBeVisible();
  await student.locator('li', { hasText: 'enrollment-letter.pdf' }).getByRole('button', { name: 'Replace document' }).click();
  await student.getByLabel(/Replacement file for enrollment-letter.pdf/).setInputFiles({ name: 'enrollment-letter-signed.pdf', mimeType: 'application/pdf', buffer: pdf('signed letter') });
  await student.getByRole('button', { name: 'Upload replacement' }).click();
  await expect(student.locator('li', { hasText: 'enrollment-letter-signed.pdf' }).getByText('Security checks passed')).toBeVisible({ timeout: 30_000 });
  await student.reload();
  await expect(student.locator('li', { hasText: 'enrollment-letter.pdf' }).getByText('A verified replacement is now on record.')).toBeVisible();
  await Promise.all([student.context().close(), officer.context().close()]);
});
