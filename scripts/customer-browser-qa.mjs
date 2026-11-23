// Real-backend acceptance in a disposable PostgreSQL database. Run from repo root.
import { chromium, expect } from '@playwright/test';
import { execFileSync, spawn } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import assert from 'node:assert/strict';

const suffix = randomBytes(6).toString('hex');
const database = `qa_customer_${suffix}`;
const container = `injector-customer-qa-${suffix}`;
const root = process.cwd();
const artifacts = `${root}/.local/customer-scope/artifacts`;
const adminPassword = `Admin-${randomBytes(18).toString('hex')}!`;
const customerPassword = `Customer-${randomBytes(18).toString('hex')}!`;
const supportPassword = `Support-${randomBytes(18).toString('hex')}!`;
const docker = (args, input) => execFileSync('docker', args, {
  cwd: root, input, encoding: 'utf8', windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'],
});
const compose = ['compose', '-f', 'compose.yaml'];
const steps = [];
const apiResponses = [];
const record = text => { steps.push(text); console.log(`PASS: ${text}`); };
let createdDatabase = false, browser, vite;

async function ready(url) {
  for (let i = 0; i < 60; i++) {
    try { if ((await fetch(url)).ok) return; } catch { /* startup */ }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error(`Readiness timeout: ${url}`);
}
async function login(page, email, password, heading) {
  await expect(page.getByRole('heading', { name: 'ورود به سامانه', exact: true })).toBeVisible();
  await page.getByLabel('ایمیل', { exact: true }).fill(email);
  await page.getByLabel('گذرواژه', { exact: true }).fill(password);
  await page.getByLabel('گذرواژه', { exact: true }).press('Enter');
  await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible();
}

try {
  assert(/^qa_customer_[a-f0-9]{12}$/.test(database));
  assert(/^injector-customer-qa-[a-f0-9]{12}$/.test(container));
  mkdirSync(artifacts, { recursive: true });
  const dbContainer = docker([...compose, 'ps', '-q', 'db']).trim();
  assert(dbContainer, 'Start the local Compose PostgreSQL service first.');
  const network = Object.keys(JSON.parse(docker(['inspect', '--format', '{{json .NetworkSettings.Networks}}', dbContainer])))[0];
  const env = ['--network', network, '--env-file', '.env', '-e', 'POSTGRES_HOST=db', '-e', `POSTGRES_DB=${database}`,
    '-e', 'DJANGO_DEBUG=true', '-e', 'DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1', '-e', 'STAFF_LOGIN_RATE=200/minute',
    '-e', 'CSRF_TRUSTED_ORIGINS=http://127.0.0.1:5186', '-e', 'CORS_ALLOWED_ORIGINS=http://127.0.0.1:5186'];
  const source = ['-w', '/workspace', '-v', `${root.replaceAll('\\', '/')}/backend:/workspace:ro`];
  const image = 'injector-api-dev';
  docker([...compose, 'exec', '-T', 'db', 'sh', '-c', 'createdb -U "$POSTGRES_USER" "$1"', '--', database]);
  createdDatabase = true;
  docker(['run', '--rm', ...env, ...source, image, 'python', 'manage.py', 'migrate', '--noinput']);
  const seed = `import json
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from devices.models import Customer, Device
User = get_user_model()
User.objects.create_superuser(username='qa-admin', email='qa-admin@example.test', password=${JSON.stringify(adminPassword)})
support = User.objects.create_user(username='qa-support', email='qa-support@example.test', password=${JSON.stringify(supportPassword)}, is_staff=True)
support.groups.add(Group.objects.get(name='support'))
own = Customer.objects.create(organization_name='سازمان مشتری آزمایشی', contact_name='Owner')
other = Customer.objects.create(organization_name='سازمان دیگر', contact_name='Other')
device = Device.objects.create(customer=own, serial_number='QA-OWN-001', model_name='PX-500', software_version='2.4.1', last_seen_at=timezone.now(), site_contact_phone='PRIVATE-INTERNAL-CONTACT')
Device.objects.create(customer=own, serial_number='QA-NEVER-002', model_name='PX-500')
foreign = Device.objects.create(customer=other, serial_number='QA-FOREIGN-003', model_name='PX-500')
print(json.dumps({'organization': own.pk, 'other': other.pk, 'device': device.pk, 'foreign': foreign.pk}))
`;
  const data = JSON.parse(docker(['run', '--rm', '-i', ...env, ...source, image, 'python', 'manage.py', 'shell', '-v', '0'], seed).trim().split('\n').at(-1));
  docker(['run', '-d', '--name', container, '--label', `com.injector.qa.database=${database}`, ...env, ...source,
    '-p', '127.0.0.1:8006:8000', image, 'gunicorn', 'config.wsgi:application', '--bind', '0.0.0.0:8000', '--workers', '1']);
  const shell = code => docker(['exec', '-i', container, 'python', 'manage.py', 'shell', '-v', '0'], code);
  await ready('http://127.0.0.1:8006/health/ready/');
  writeFileSync(`${root}/.local/customer-scope/qa-vite.config.mjs`, `import base from '../../vite.config.js';
export default { ...base, cacheDir: '.local/customer-scope/vite-cache', server: { host: '127.0.0.1', port: 5186, strictPort: true, proxy: { '/api': 'http://127.0.0.1:8006' } } };\n`);
  vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--config', '.local/customer-scope/qa-vite.config.mjs'], {
    cwd: root, windowsHide: true, env: { ...process.env, VITE_DEMO_MODE: 'false', VITE_API_BASE_URL: '' }, stdio: 'ignore',
  });
  await ready('http://127.0.0.1:5186/');
  browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || (process.platform === 'win32' ? 'msedge' : undefined), headless: true });
  const errors = [];
  const adminContext = await browser.newContext({ viewport: { width: 1365, height: 900 } });
  const customerContext = await browser.newContext({ viewport: { width: 1365, height: 900 } });
  for (const context of [adminContext, customerContext]) {
    context.on('page', page => {
      page.on('pageerror', error => errors.push(error.message));
      page.on('response', response => {
        if (response.url().includes('/api/v1/')) apiResponses.push({ path: new URL(response.url()).pathname, status: response.status() });
      });
    });
    await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  }
  const admin = await adminContext.newPage();
  await admin.goto('http://127.0.0.1:5186/');
  await login(admin, 'qa-admin@example.test', adminPassword, 'نمای کلی');
  await admin.getByRole('navigation').getByRole('button', { name: 'حساب‌های مشتریان', exact: true }).click();
  await admin.getByRole('button', { name: 'افزودن حساب مشتری', exact: true }).click();
  const dialog = admin.getByRole('dialog');
  await dialog.getByLabel('ایمیل', { exact: true }).fill('qa-customer@example.test');
  await dialog.getByLabel('گذرواژهٔ اولیه').fill(customerPassword);
  await dialog.getByLabel('سازمان مشتری', { exact: true }).selectOption(String(data.organization));
  const created = admin.waitForResponse(response => response.url().includes('/customer-users/') && response.request().method() === 'POST');
  await dialog.getByRole('button', { name: 'افزودن حساب مشتری', exact: true }).click();
  assert.equal((await created).status(), 201);
  await expect(dialog).toHaveCount(0);
  await expect(admin.getByRole('cell', { name: 'qa-customer@example.test', exact: true })).toBeVisible();
  record('Super administrator provisions customer account through the real application');

  const customer = await customerContext.newPage();
  await customer.goto('http://127.0.0.1:5186/');
  await customer.getByLabel('ایمیل', { exact: true }).fill('qa-customer@example.test');
  await customer.getByLabel('گذرواژه', { exact: true }).fill('Incorrect-Password-42!');
  await customer.getByRole('button', { name: 'ورود', exact: true }).click();
  await expect(customer.getByRole('alert')).toContainText('Email or password is incorrect.');
  await login(customer, 'qa-customer@example.test', customerPassword, 'دستگاه‌های من');
  await expect(customer.getByRole('link', { name: 'QA-OWN-001' })).toBeVisible();
  await expect(customer.getByRole('link', { name: 'QA-FOREIGN-003' })).toHaveCount(0);
  await expect(customer.getByText('هنوز ارتباطی ثبت نشده است').first()).toBeVisible();
  record('Invalid credentials denied; customer login shows only own devices and never-connected state');

  const cookie = (await customerContext.cookies()).find(item => item.name === 'sessionid');
  assert(cookie.httpOnly && cookie.sameSite === 'Lax');
  assert.equal(await customer.evaluate(() => Object.keys(localStorage).some(key => /token|password|credential/i.test(key))), false);
  const devices = await (await customer.request.get('http://127.0.0.1:5186/api/v1/customer/devices/')).json();
  assert.equal(devices.count, 2);
  assert(!JSON.stringify(devices).includes('PRIVATE-INTERNAL-CONTACT'));
  assert.equal((await customer.request.get(`http://127.0.0.1:5186/api/v1/customer/devices/${data.foreign}/`)).status(), 404);
  assert.equal((await customer.request.get('http://127.0.0.1:5186/api/v1/devices/')).status(), 403);
  assert.equal((await customer.request.get('http://127.0.0.1:5186/api/v1/staff-users/')).status(), 403);
  record('Real session uses HttpOnly cookies; safe responses and cross-tenant/staff API denial verified');

  await customer.getByRole('link', { name: 'QA-OWN-001' }).click();
  await expect(customer.getByRole('heading', { name: 'QA-OWN-001', exact: true })).toBeVisible();
  await customer.reload();
  await expect(customer.getByRole('heading', { name: 'QA-OWN-001', exact: true })).toBeVisible();
  record('Customer detail direct route survives refresh with server session restoration');

  await admin.getByRole('button', { name: 'غیرفعال‌کردن qa-customer@example.test', exact: true }).click();
  await expect(admin.getByRole('cell', { name: 'غیرفعال', exact: true })).toBeVisible();
  await customer.getByRole('button', { name: 'بازخوانی', exact: true }).click();
  await expect(customer.getByRole('heading', { name: 'ورود به سامانه' })).toBeVisible();
  await expect(customer.getByRole('heading', { name: 'QA-OWN-001' })).toHaveCount(0);
  await admin.getByRole('button', { name: 'فعال‌کردن qa-customer@example.test', exact: true }).click();
  await expect(admin.getByRole('cell', { name: 'فعال', exact: true })).toBeVisible();
  await login(customer, 'qa-customer@example.test', customerPassword, 'جزئیات دستگاه');
  record('Administrator deactivation revokes an existing customer session on next request; reactivation permits login');

  await customer.setViewportSize({ width: 390, height: 844 });
  await customer.getByRole('button', { name: 'باز کردن منو' }).click();
  await expect(customer.getByRole('dialog')).toBeVisible();
  await customer.keyboard.press('Escape');
  await expect(customer.getByRole('dialog')).toHaveCount(0);
  await customer.getByRole('button', { name: 'تغییر پوسته' }).click();
  await customer.reload();
  await expect(customer.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(customer.locator('.customer-panel')).toHaveAttribute('dir', 'rtl');
  await expect(customer.getByRole('heading', { name: 'QA-OWN-001', exact: true })).toBeVisible();
  await customer.screenshot({ path: `${artifacts}/customer-mobile.png`, fullPage: true });
  record('Mobile Persian RTL panel, drawer keyboard dismissal and persistent dark theme verified');

  shell(`from devices.models import Device\nDevice.objects.filter(pk=${data.device}).update(customer_id=${data.other})\n`);
  await customer.getByRole('button', { name: 'بازخوانی' }).click();
  await expect(customer.getByRole('alert')).toContainText('دستگاه در دسترس نیست');
  await expect(customer.getByRole('heading', { name: 'QA-OWN-001', exact: true })).toHaveCount(0);
  assert.equal((await customer.request.get(`http://127.0.0.1:5186/api/v1/customer/devices/${data.device}/`)).status(), 404);
  record('Device reassignment removes previous customer detail/API access and clears displayed data');

  const currentCookie = (await customerContext.cookies()).find(item => item.name === 'sessionid');
  shell(`from django.contrib.sessions.models import Session\nfrom django.utils import timezone\nfrom datetime import timedelta\nSession.objects.filter(session_key=${JSON.stringify(currentCookie.value)}).update(expire_date=timezone.now()-timedelta(seconds=1))\n`);
  await customer.reload();
  await expect(customer.getByRole('heading', { name: 'ورود به سامانه' })).toBeVisible();
  await login(customer, 'qa-customer@example.test', customerPassword, 'جزئیات دستگاه');
  await customer.getByRole('button', { name: 'خروج', exact: true }).click();
  await expect(customer.getByRole('heading', { name: 'ورود به سامانه' })).toBeVisible();
  await customer.reload();
  await expect(customer.getByRole('heading', { name: 'ورود به سامانه' })).toBeVisible();
  record('Actual server-session expiry and logout revocation return to shared login without protected data');

  await admin.getByRole('button', { name: 'خروج', exact: true }).first().click();
  await login(admin, 'qa-support@example.test', supportPassword, 'نمای کلی');
  await expect(admin.getByRole('button', { name: 'حساب‌های مشتریان', exact: true })).toHaveCount(0);
  assert.equal((await admin.request.get('http://127.0.0.1:5186/api/v1/customer-users/')).status(), 403);
  record('Existing staff login remains functional and support cannot provision customers');
  assert.deepEqual(errors, [], 'No uncaught browser exceptions');
  writeFileSync(`${artifacts}/result.json`, JSON.stringify({ browser: 'Playwright Chromium/Edge', steps }, null, 2));
  console.log(`Real-backend customer acceptance: ${steps.length} checks passed.`);
} catch (error) {
  let safe = String(error.stack || error);
  for (const secret of [adminPassword, customerPassword, supportPassword]) safe = safe.replaceAll(secret, '[redacted]');
  console.error(safe);
  console.error(JSON.stringify({ recentApiResponses: apiResponses.slice(-20) }));
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
  if (vite) vite.kill();
  try {
    const label = docker(['inspect', '--format', '{{index .Config.Labels "com.injector.qa.database"}}', container]).trim();
    if (label === database) docker(['rm', '-f', container]);
  } catch { /* No QA service was created. */ }
  if (createdDatabase) {
    try {
      docker([...compose, 'exec', '-T', 'db', 'sh', '-c', 'dropdb -U "$POSTGRES_USER" "$1"', '--', database]);
      console.log('Removed isolated customer QA database and services.');
    } catch {
      console.error(`QA database cleanup needs attention: ${database}`);
      process.exitCode = 1;
    }
  }
}
