import { expect, test, type Page } from '@playwright/test';

/**
 * Acceptance workflow for investigation cases (synthetic demo data):
 * open a suspicious application → open a case → assign → examine evidence → add a note →
 * record justified decisions (escalate, then resolve) → verify the audit history.
 */
const PASSWORD = 'EduShield!Demo2026';
const shots = process.env.E2E_SCREENSHOTS;

async function signIn(page: Page, email: string) {
  await page.goto('/login');
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: /^Sign in/ }).click();
  await page.waitForURL('**/app');
}

async function snap(page: Page, name: string) {
  if (shots) await page.screenshot({ path: `${shots}/${name}.png`, fullPage: true });
}

test('investigator works a case from suspicious application to audited decision', async ({ page, browser }) => {
  await signIn(page, 'investigator@northbridge.demo');

  // 1. Open a suspicious application.
  await page.goto('/app/applications?scenario=unusual_disbursement');
  await page.getByRole('link', { name: /^FA-/ }).first().click();
  await expect(page.getByText('Explainable risk assessment')).toBeVisible();
  await expect(page.getByText('Disbursement amount far above typical').first()).toBeVisible();

  // 2. Create an investigation case.
  await page.getByRole('button', { name: 'Open investigation' }).click();
  await page.waitForURL(/\/app\/cases\/[0-9a-f-]{36}$/);
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Unusual disbursement activity');
  const reference = (await page.getByText(/^CASE-\d{5}/).first().textContent())!.match(/CASE-\d{5}/)![0];
  await expect(page.getByText('Suspicious activity').first()).toBeVisible();

  // 3. Assign an investigator.
  await page.getByRole('button', { name: /^(Assign|Reassign)$/ }).click();
  const investigator = page.getByLabel('Investigator');
  const danaId = await investigator.locator('option', { hasText: 'Dana Whitfield' }).getAttribute('value');
  await investigator.selectOption(danaId!);
  await page.getByLabel(/Handover note/).fill('Dana has the bank-change history for this student.');
  await page.getByRole('button', { name: 'Save assignment' }).click();
  await expect(page.getByText('Assigned to Dana Whitfield')).toBeVisible();

  // 4. Examine supporting evidence (attached automatically from the triggering records).
  await expect(page.getByRole('tab', { name: /Evidence/ })).toBeVisible();
  await expect(page.getByText(/^Alert ALT-\d+/).first()).toBeVisible();
  await expect(page.getByText(/^Risk assessment: \d+\/100/)).toBeVisible();
  await page.getByRole('tab', { name: 'Risk explanation' }).click();
  await expect(page.getByText(/prioritisation aid, not a finding/)).toBeVisible();
  await snap(page, 'case-1-evidence');

  // 5. Add an investigation note.
  await page.getByRole('tab', { name: /Notes/ }).click();
  const note = 'Called the student on the number on file; they did not request a destination change.';
  await page.getByLabel('Internal note').fill(note);
  await page.getByRole('button', { name: 'Add note' }).click();
  await expect(page.getByText(note)).toBeVisible();

  // 6–7. Record justified decisions: escalate, then resolve without labelling the student.
  await page.getByRole('button', { name: 'Record decision' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: /^Escalate/ }).click();
  await dialog.getByLabel('Justification').fill('Outsized refund to a destination changed two days earlier, plus a payment burst.');
  await expect(dialog.getByRole('button', { name: 'Record decision' })).toBeDisabled();
  await dialog.getByRole('checkbox').check();
  await dialog.getByRole('button', { name: 'Record decision' }).click();
  await expect(page.getByText('An investigator judged the evidence serious enough')).toBeVisible();
  await expect(page.getByText('Outsized refund to a destination changed two days earlier', { exact: false })).toBeVisible();

  await page.getByRole('button', { name: 'Record decision' }).click();
  await dialog.getByRole('button', { name: /^Resolve/ }).click();
  await dialog.getByRole('button', { name: /No fraud found/ }).click();
  await dialog
    .getByLabel('Justification')
    .fill('Student confirmed by phone and in person that the new account is theirs; refund explained by a scholarship.');
  await dialog.getByRole('checkbox').check();
  await dialog.getByRole('button', { name: 'Record decision' }).click();
  await expect(page.getByText('Not substantiated').first()).toBeVisible();
  await expect(page.getByText('Marcus Bell ·').first()).toBeVisible(); // decision records who decided
  await snap(page, 'case-2-decided');

  // 8. Verify the audit history: on the case timeline, and independently as the auditor.
  await page.getByRole('tab', { name: /Timeline/ }).click();
  for (const entry of ['Case opened', 'Assignment changed', 'Note added', 'Escalated: suspected fraud', 'Resolved: no fraud found']) {
    await expect(page.getByText(entry, { exact: true }).first()).toBeVisible();
  }
  await snap(page, 'case-3-timeline');

  const auditorContext = await browser.newContext();
  const auditor = await auditorContext.newPage();
  await signIn(auditor, 'auditor@northbridge.demo');
  const events = await auditor.request.get(`/api/v1/audit/events?q=${reference}&page_size=50`);
  expect(events.ok()).toBeTruthy();
  const actions = (await events.json()).items.map((e: { action: string }) => e.action);
  for (const action of ['case.create', 'case.assign', 'case.note_add', 'case.decision.escalate', 'case.decision.resolve']) {
    expect(actions).toContain(action);
  }
  const chain = await (await auditor.request.get('/api/v1/audit/verify')).json();
  expect(chain.valid).toBe(true);
  await auditorContext.close();
});
