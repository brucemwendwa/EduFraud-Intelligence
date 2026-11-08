/// <reference lib="dom" />
import { createRequire } from 'node:module';
import { expect, test, type Browser, type Page } from '@playwright/test';

/** Automated WCAG A/AA checks plus layout and keyboard behaviour on the main screens. */
const require = createRequire(import.meta.url);
const axePath = process.env.AXE_CORE_PATH ?? require.resolve('axe-core/axe.min.js');
const PASSWORD = 'EduShield!Demo2026';
const STUDENT = 'student@northbridge.demo';
const OFFICER = 'officer@northbridge.demo';
const ADMIN = 'inst.admin@northbridge.demo';
const WIDTHS = [
  { name: 'phone', width: 390, height: 844 },
  { name: 'tablet', width: 820, height: 1180 },
] as const;

type Violation = { id: string; impact: string | null; help: string; nodes: { target: string[]; failureSummary?: string }[] };

async function violations(page: Page): Promise<Violation[]> {
  await page.addScriptTag({ path: axePath });
  return page.evaluate(async () => {
    const axe = (window as unknown as { axe: { run: (c: unknown, o: unknown) => Promise<{ violations: Violation[] }> } }).axe;
    return (await axe.run(document, { runOnly: ['wcag2a', 'wcag2aa'] })).violations;
  });
}

async function expectAccessible(page: Page, screen: string) {
  const found = await violations(page);
  const summary = found.map((v) => `${screen}: ${v.id} (${v.impact}) ${v.help}\n   ${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join('\n   ')}`);
  expect(summary, summary.join('\n')).toEqual([]);
}

async function signedIn(browser: Browser, email: string, landing: string, viewport = { width: 1440, height: 900 }) {
  const context = await browser.newContext({ viewport, bypassCSP: true });
  const page = await context.newPage();
  await page.goto('/login');
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: /^Sign in/ }).click();
  await page.waitForURL(`**${landing}`);
  return page;
}

async function settled(page: Page) {
  await page.waitForLoadState('networkidle');
  await expect(page.locator('[data-sonner-toast]')).toHaveCount(0, { timeout: 8000 }).catch(() => undefined);
}

async function expectNoHorizontalOverflow(page: Page, screen: string) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `${screen} scrolls sideways by ${overflow}px`).toBeLessThanOrEqual(1);
}

test('sign-in pages meet WCAG A and AA', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, bypassCSP: true });
  const page = await context.newPage();
  for (const path of ['/login', '/forgot-password', '/reset-password?token=x', '/activate?token=x']) {
    await page.goto(path);
    await settled(page);
    await expectAccessible(page, path);
  }
  await context.close();
});

test('student screens meet WCAG A and AA', async ({ browser }) => {
  const page = await signedIn(browser, STUDENT, '/student');
  for (const path of ['/student', '/student/applications', '/student/applications/new', '/student/profile']) {
    await page.goto(path);
    await settled(page);
    await expectAccessible(page, path);
  }
  await page.context().close();
});

test('staff screens meet WCAG A and AA', async ({ browser }) => {
  const page = await signedIn(browser, ADMIN, '/app');
  for (const path of ['/app', '/app/applications', '/app/operations', '/app/institutions']) {
    await page.goto(path);
    await settled(page);
    await expectAccessible(page, path);
  }
  await page.goto('/app/applications');
  await page.getByRole('link', { name: /^FA-/ }).first().click();
  await expect(page.getByText('Explainable risk assessment')).toBeVisible();
  await settled(page);
  await expectAccessible(page, 'application detail');
  await page.getByRole('tab', { name: 'Evidence' }).click();
  await expectAccessible(page, 'evidence tab');
  await page.getByRole('tab', { name: /History/ }).click();
  await expectAccessible(page, 'history tab');
  await page.getByRole('button', { name: 'Record review' }).click();
  await expectAccessible(page, 'review dialog');
  await page.context().close();
});

for (const { name, width, height } of WIDTHS) {
  test(`student screens fit a ${name}`, async ({ browser }) => {
    const page = await signedIn(browser, STUDENT, '/student', { width, height });
    for (const path of ['/student', '/student/applications', '/student/applications/new', '/student/profile']) {
      await page.goto(path);
      await settled(page);
      await expectNoHorizontalOverflow(page, `${path} on ${name}`);
    }
    await page.context().close();
  });

  test(`staff screens fit a ${name}`, async ({ browser }) => {
    const page = await signedIn(browser, ADMIN, '/app', { width, height });
    for (const path of ['/app', '/app/applications', '/app/operations', '/app/institutions']) {
      await page.goto(path);
      await settled(page);
      await expectNoHorizontalOverflow(page, `${path} on ${name}`);
    }
    await page.goto('/app/applications');
    await page.getByRole('link', { name: /^FA-/ }).first().click();
    await expect(page.getByText('Explainable risk assessment')).toBeVisible();
    await settled(page);
    await expectNoHorizontalOverflow(page, `application detail on ${name}`);
    await page.context().close();
  });
}

test('the sign-in form works from the keyboard', async ({ page }) => {
  await page.goto('/login');
  await settled(page);
  await page.getByLabel('Email address').focus();
  await page.keyboard.type(OFFICER);
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('Password')).toBeFocused();
  await page.keyboard.type(PASSWORD);
  await page.keyboard.press('Enter');
  await page.waitForURL('**/app');
});

test('dialogs trap focus, close on Escape and return focus', async ({ browser }) => {
  const page = await signedIn(browser, OFFICER, '/app');
  await page.goto('/app/applications');
  await page.getByRole('link', { name: /^FA-/ }).first().click();
  const opener = page.getByRole('button', { name: 'Record review' });
  await opener.click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  for (let step = 0; step < 12; step += 1) {
    await page.keyboard.press('Tab');
    expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true);
  }
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(opener).toBeFocused();
  await page.context().close();
});
