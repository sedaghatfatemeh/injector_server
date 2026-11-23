// Capture documentation against a disposable real backend. Never uses the ordinary API.
import { chromium, expect as baseExpect } from '@playwright/test';
import { execFileSync, spawn } from 'node:child_process';
import { createHash, randomBytes } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';

const root = process.cwd();
const expect = baseExpect.configure({ timeout: 30000 });
const output = path.join(root, 'docs/assets/walkthrough-v2');
const work = path.join(root, '.local/walkthrough-v2');
const original = readFileSync('docs/walkthrough.fa.md');
const originalHash = createHash('sha256').update(original).digest('hex');
const suffix = randomBytes(6).toString('hex');
const database = `qa_walkthrough_${suffix}`;
const container = `injector-walkthrough-${suffix}`;
const apiPort = 8007;
const webPort = 5187;
const origin = `http://127.0.0.1:${webPort}`;
const adminPassword = `Admin-${randomBytes(18).toString('hex')}!`;
const supportPassword = `Support-${randomBytes(18).toString('hex')}!`;
const customerPassword = `Customer-${randomBytes(18).toString('hex')}!`;
const secrets = [adminPassword, supportPassword, customerPassword];
const screenshots = [];
const responses = [];
const steps = [];
let createdDatabase = false;
let browser, vite;
let cleanupOk = false;
const docker = (args, input) => execFileSync('docker', args, {
  cwd: root, input, encoding: 'utf8', windowsHide: true,
  stdio: ['pipe', 'pipe', 'pipe'], timeout: 120000,
});
const compose = ['compose', '-f', 'compose.yaml'];
const record = (step) => { steps.push(step); console.log(`PASS: ${step}`); };

async function ready(url) {
  for (let i = 0; i < 90; i++) {
    try { if ((await fetch(url)).ok) return; } catch { /* startup */ }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error(`Readiness timeout: ${url}`);
}

// Use the repository's existing embedded font for reproducible offline captures.
const prototype = readFileSync('prototype/onboarding/index.html', 'utf8');
const fontFace = prototype.match(/@font-face\s*\{[^}]*data:font[^}]*\}/)?.[0];
assert(fontFace, 'Expected the approved prototype embedded font.');

async function context(options = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 },
    locale: 'fa-IR', timezoneId: 'Asia/Tehran', reducedMotion: 'reduce', ...options });
  await ctx.route('**/*', route => {
    const url = new URL(route.request().url());
    if (['127.0.0.1', 'localhost'].includes(url.hostname)) return route.continue();
    if (url.hostname === 'fonts.googleapis.com') {
      return route.fulfill({ contentType: 'text/css', body: fontFace });
    }
    return route.abort();
  });
  ctx.on('page', page => page.on('response', response => {
    const url = new URL(response.url());
    if (url.pathname.startsWith('/api/v1/')) responses.push({ path: url.pathname, status: response.status() });
  }));
  return ctx;
}

async function capture(page, name, caption, role) {
  await page.evaluate(async () => { await document.fonts.ready; });
  await expect(page.locator('.live-app')).toBeVisible();
  const filename = `${name}.png`;
  const masks = [page.locator('.live-secret')];
  const passwordInputs = page.locator('input[type="password"]');
  for (let i = 0; i < await passwordInputs.count(); i++) {
    if (await passwordInputs.nth(i).inputValue()) masks.push(passwordInputs.nth(i));
  }
  await page.screenshot({ path: path.join(output, filename), fullPage: true, animations: 'disabled',
    mask: masks, maskColor: '#8b948f' });
  const data = readFileSync(path.join(output, filename));
  screenshots.push({ filename, caption, role, width: data.readUInt32BE(16), height: data.readUInt32BE(20),
    sha256: createHash('sha256').update(data).digest('hex') });
  console.log(`CAPTURE: ${filename}`);
}

async function goto(page, pathname = '/') {
  await page.goto(`${origin}${pathname}`, { waitUntil: 'domcontentloaded' });
}

async function login(page, email, password, heading) {
  await expect(page.getByRole('heading', { name: 'ورود به سامانه', exact: true })).toBeVisible();
  await page.getByLabel('ایمیل', { exact: true }).fill(email);
  await page.getByLabel('گذرواژه', { exact: true }).fill(password);
  const response = page.waitForResponse(r => r.url().endsWith('/auth/login/') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'ورود', exact: true }).click();
  assert.equal((await response).status(), 200, 'Real browser login must succeed.');
  await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible();
}

async function nav(page, name) {
  await page.getByRole('navigation').getByRole('button', { name, exact: true }).click();
  await expect(page.locator('.live-top h1')).toHaveText(name);
  await expect(page.getByText('در حال دریافت اطلاعات…', { exact: true })).toHaveCount(0);
}

async function saveDialog(page, route, button = 'ذخیره') {
  const result = page.waitForResponse(r => r.url().includes(route) && r.request().method() === 'POST');
  await page.getByRole('dialog').getByRole('button', { name: button, exact: true }).click();
  const response = await result;
  assert.equal(response.status(), 201, `Create ${route} must succeed.`);
  const data = await response.json();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  return data;
}

async function browserMutation(page, endpoint, body) {
  return page.evaluate(async ({ endpoint, body }) => {
    const bootstrap = await fetch('/api/v1/auth/csrf/', { credentials: 'include' });
    const { csrfToken } = await bootstrap.json();
    const response = await fetch(endpoint, { method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }, body: JSON.stringify(body) });
    return { status: response.status, data: await response.json() };
  }, { endpoint, body });
}

try {
  assert(/^qa_walkthrough_[a-f0-9]{12}$/.test(database));
  mkdirSync(output, { recursive: true });
  mkdirSync(work, { recursive: true });
  const dbContainer = docker([...compose, 'ps', '-q', 'db']).trim();
  assert(dbContainer, 'Start local Compose PostgreSQL first.');
  const network = Object.keys(JSON.parse(docker(['inspect', '--format', '{{json .NetworkSettings.Networks}}', dbContainer])))[0];
  const env = ['--network', network, '--env-file', '.env', '-e', 'POSTGRES_HOST=db', '-e', `POSTGRES_DB=${database}`,
    '-e', 'DJANGO_DEBUG=true', '-e', 'DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1', '-e', 'STAFF_LOGIN_RATE=200/minute',
    '-e', 'DEVICE_ONLINE_WINDOW_MINUTES=15', '-e', `CSRF_TRUSTED_ORIGINS=${origin}`, '-e', `CORS_ALLOWED_ORIGINS=${origin}`];
  const source = ['-w', '/workspace', '-v', `${root.replaceAll('\\', '/')}/backend:/workspace:ro`];
  const image = 'injector-api-dev';
  docker([...compose, 'exec', '-T', 'db', 'sh', '-c', 'createdb -U "$POSTGRES_USER" "$1"', '--', database]);
  createdDatabase = true;
  docker(['run', '--rm', ...env, ...source, image, 'python', 'manage.py', 'migrate', '--noinput']);
  const seed = `from django.contrib.auth import get_user_model
from devices.models import Customer, Device
get_user_model().objects.create_superuser(username='walkthrough-admin', email='admin@walkthrough.example.test', password=${JSON.stringify(adminPassword)})
other=Customer.objects.create(organization_name='سازمان آزمایشی ب', contact_name='مسئول نمونه ب', contact_email='owner-b@example.test')
Device.objects.create(customer=other, serial_number='WT-B-001', model_name='PX-320', location='محل آزمایشی ب')
`;
  docker(['run', '--rm', '-i', ...env, ...source, image, 'python', 'manage.py', 'shell', '-v', '0'], seed);
  docker(['run', '-d', '--name', container, '--label', `com.injector.walkthrough.database=${database}`, ...env, ...source,
    '-p', `127.0.0.1:${apiPort}:8000`, image, 'gunicorn', 'config.wsgi:application', '--bind', '0.0.0.0:8000', '--workers', '1']);
  const shell = code => docker(['exec', '-i', container, 'python', 'manage.py', 'shell', '-v', '0'], code);
  await ready(`http://127.0.0.1:${apiPort}/health/ready/`);
  writeFileSync(path.join(work, 'vite.config.mjs'), `import base from '../../vite.config.js';
export default {...base, cacheDir:'.local/walkthrough-v2/vite-cache', server:{host:'127.0.0.1',port:${webPort},strictPort:true,proxy:{'/api':'http://127.0.0.1:${apiPort}'}}};\n`);
  vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--config', '.local/walkthrough-v2/vite.config.mjs'], {
    cwd: root, windowsHide: true, env: { ...process.env, VITE_DEMO_MODE: 'false', VITE_API_BASE_URL: '' }, stdio: 'ignore',
  });
  await ready(origin);
  browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || (process.platform === 'win32' ? 'msedge' : undefined), headless: true });
  const adminContext = await context();
  const admin = await adminContext.newPage();
  admin.setDefaultTimeout(30000);
  await goto(admin);
  await expect(admin.getByRole('heading', { name: 'ورود به سامانه' })).toBeVisible();
  await capture(admin, '01-login', 'صفحه ورود مشترک کارکنان و مشتری؛ ثبت‌نام عمومی وجود ندارد.', 'anonymous');
  await login(admin, 'admin@walkthrough.example.test', adminPassword, 'نمای کلی');
  record('Administrator browser login through real API');
  await capture(admin, '02-overview', 'نمای کلی مدیر کل در محیط آزمایشی متصل به PostgreSQL.', 'super_admin');

  await nav(admin, 'کاربران');
  await admin.getByRole('button', { name: 'افزودن کاربر', exact: true }).click();
  let dialog = admin.getByRole('dialog');
  await dialog.getByLabel('نام', { exact: true }).fill('پشتیبان');
  await dialog.getByLabel('نام خانوادگی', { exact: true }).fill('آزمایشی');
  await dialog.getByLabel('ایمیل', { exact: true }).fill('support@walkthrough.example.test');
  await dialog.getByLabel('گذرواژهٔ اولیه').fill(supportPassword);
  await dialog.locator('select[name="role"]').selectOption('support');
  await capture(admin, '03-staff-form', 'افزودن کارمند با نقش پشتیبان؛ ناحیه گذرواژه در تصویر پوشانده شده است.', 'super_admin');
  await saveDialog(admin, '/staff-users/', 'افزودن کاربر');
  await expect(admin.getByRole('cell', { name: 'support@walkthrough.example.test', exact: true })).toBeVisible();
  await capture(admin, '04-staff-created', 'حساب پشتیبان پس از ایجاد موفق در فهرست کارکنان.', 'super_admin');

  await nav(admin, 'مشتریان');
  await admin.getByRole('button', { name: 'ثبت مشتری', exact: true }).click();
  dialog = admin.getByRole('dialog');
  await dialog.getByLabel('نام سازمان').fill('سازمان آزمایشی الف');
  await dialog.getByLabel('نام مسئول').fill('مسئول نمونه الف');
  await dialog.getByLabel('ایمیل', { exact: true }).fill('owner-a@example.test');
  await dialog.getByLabel('نشانی').fill('نشانی ساختگی برای آموزش پنل');
  await capture(admin, '05-organization-form', 'ثبت سازمان و حداقل اطلاعات تماس؛ این فرم حساب ورود مشتری نمی‌سازد.', 'super_admin');
  const organization = await saveDialog(admin, '/customers/');
  await expect(admin.getByRole('cell', { name: 'سازمان آزمایشی الف', exact: true })).toBeVisible();
  await capture(admin, '06-organizations', 'دو سازمان آزمایشی برای نمایش مالکیت مجزا.', 'super_admin');

  await nav(admin, 'دستگاه‌ها');
  await admin.getByRole('button', { name: 'ثبت دستگاه', exact: true }).click();
  dialog = admin.getByRole('dialog');
  await dialog.getByLabel('شماره سریال').fill('WT-A-001');
  await dialog.getByLabel('مدل', { exact: true }).fill('PX-500');
  await dialog.locator('select[name="customer"]').selectOption(String(organization.id));
  await dialog.getByLabel('نسخه برنامه').fill('2.4.1');
  await dialog.getByLabel('موقعیت').fill('محل نصب آزمایشی الف');
  await capture(admin, '07-device-form', 'ثبت دستگاه با سریال یکتا و تخصیص به سازمان الف.', 'super_admin');
  const device = await saveDialog(admin, '/devices/');
  await expect(admin.getByRole('button', { name: 'WT-A-001', exact: true })).toBeVisible();
  await capture(admin, '08-devices', 'موجودی دستگاه‌های دو سازمان؛ دستگاه تازه هنوز ارتباط ندارد.', 'super_admin');

  const provision = await browserMutation(admin, `/api/v1/devices/${device.id}/provision_credential/`, {});
  assert.equal(provision.status, 201);
  const credential = provision.data.credential;
  secrets.push(credential);
  const deviceHeaders = { Authorization: `Device ${credential}`, 'Content-Type': 'application/json' };
  async function devicePost(endpoint, payload) {
    const result = await fetch(`http://127.0.0.1:${apiPort}/api/v1/device/${endpoint}/`, {
      method: 'POST', headers: deviceHeaders, body: JSON.stringify(payload),
    });
    assert.equal(result.status, 200, `Device ${endpoint} response`);
    return result.json();
  }
  await devicePost('check-in', { software_version: '2.4.1', install_state: 'idle' });
  const now = Date.now();
  const fault = randomBytes(16).toString('hex').replace(/(.{8})(.{4})(.{4})(.{4})(.{12})/, '$1-$2-$3-$4-$5');
  const active = { event_id: crypto.randomUUID(), fault_id: fault, code: 'FUEL_PRESSURE', state: 'active',
    summary: 'هشدار فشار گزارش‌شده توسط دستگاه آزمایشی', occurred_at: new Date(now - 600000).toISOString(), software_version: '2.4.1' };
  const accepted = await devicePost('events', { events: [active,
    { event_id: crypto.randomUUID(), code: 'TEST_COMPLETED', state: 'info', summary: 'گزارش پایان آزمون نمونه', occurred_at: new Date(now - 120000).toISOString() }] });
  assert(accepted.results.every(item => item.status === 'accepted'));
  assert.equal((await devicePost('events', { events: [active] })).results[0].status, 'duplicate');
  assert.equal((await devicePost('events', { events: [{ ...active, summary: 'Conflicting reuse' }] })).results[0].status, 'rejected');
  record('Real credential/check-in/events accepted, duplicate and conflict verified');
  shell(`from devices.models import Device\nDevice.objects.create(customer_id=${organization.id}, serial_number='WT-A-002', model_name='PX-500', location='محل دوم آزمایشی')\n`);
  await admin.getByRole('button', { name: 'بازخوانی', exact: true }).click();
  await expect(admin.getByRole('button', { name: 'WT-A-002', exact: true })).toBeVisible();
  await admin.getByPlaceholder('جست‌وجوی سریال، مشتری یا مدل').fill('WT-A-001');
  await expect(admin.getByRole('button', { name: 'WT-B-001', exact: true })).toHaveCount(0);
  await capture(admin, '09-device-search', 'جست‌وجوی سریال و نمایش ارتباط اخیر و یک خطای فعال گزارش‌شده.', 'super_admin');
  await admin.getByRole('button', { name: 'WT-A-001', exact: true }).click();
  await expect(admin.getByRole('dialog').getByText('هشدار فشار گزارش‌شده توسط دستگاه آزمایشی', { exact: true })).toBeVisible();
  await capture(admin, '10-device-detail', 'جزئیات دستگاه و زمان وقوع/دریافت رویدادهای واقعیِ آزمایشی.', 'super_admin');
  await admin.getByRole('dialog').getByRole('button', { name: 'صدور/چرخش شناسهٔ دستگاه' }).click();
  await expect(admin.locator('.live-secret')).toBeVisible();
  await capture(admin, '11-credential-masked', 'نمایش یک‌باره شناسه دستگاه؛ خود secret عمداً با پوشش تصویری حذف شده است.', 'super_admin');
  await admin.getByRole('dialog').last().getByRole('button', { name: 'بستن', exact: true }).click();
  await admin.getByRole('dialog').getByRole('button', { name: 'بستن', exact: true }).click();

  await nav(admin, 'رویدادها و خطاها');
  await expect(admin.getByText('هشدار فشار گزارش‌شده توسط دستگاه آزمایشی', { exact: true })).toBeVisible();
  await capture(admin, '12-events', 'تاریخچه رویدادها با زمان وقوع، زمان دریافت و برچسب تأخیر.', 'super_admin');
  await admin.getByLabel('سریال دستگاه', { exact: true }).fill('WT-A-001');
  await admin.getByLabel('وضعیت گزارش‌شده').selectOption('active');
  await admin.getByRole('button', { name: 'اعمال فیلترها' }).click();
  await expect(admin.getByText('گزارش پایان آزمون نمونه', { exact: true })).toHaveCount(0);
  await capture(admin, '13-event-filter', 'فیلتر تاریخچه بر اساس سریال و state گزارش‌شده؛ این فیلتر تشخیص سرور نیست.', 'super_admin');

  await nav(admin, 'به‌روزرسانی‌ها');
  await admin.getByRole('button', { name: 'ثبت نسخه', exact: true }).click();
  dialog = admin.getByRole('dialog');
  await dialog.getByLabel('نسخه', { exact: true }).fill('2.5.0');
  await dialog.getByLabel('پیوند بسته HTTPS').fill('https://packages.example.test/injector-2.5.0.whl');
  await dialog.getByLabel('SHA-256', { exact: true }).fill('0123456789abcdef'.repeat(4));
  await dialog.getByLabel('مدل‌های سازگار (با کاما جدا شوند)').fill('PX-500');
  await dialog.getByLabel('حداقل نسخهٔ فعلی').fill('2.0.0');
  await dialog.getByLabel('یادداشت نسخه').fill('metadata ساختگی برای آموزش؛ بسته‌ای دانلود یا نصب نمی‌شود.');
  await dialog.getByLabel('مقصد انتشار').selectOption('selected');
  await dialog.getByLabel('دستگاه‌های انتخابی').selectOption(String(device.id));
  await dialog.evaluate(element => { element.scrollTop = 0; });
  await capture(admin, '14-release-form', 'بخش مشخصات metadata نمونه؛ URL و digest آموزشی‌اند و بسته واقعی ندارند.', 'super_admin');
  await dialog.getByRole('button', { name: 'ذخیره', exact: true }).scrollIntoViewIfNeeded();
  await capture(admin, '32-release-targets', 'ادامه فرم انتشار: انتخاب مدل و حداقل نسخه و مقصد منتخب پیش از ذخیره.', 'super_admin');
  await saveDialog(admin, '/releases/');
  await expect(admin.getByRole('cell', { name: '2.5.0', exact: true })).toBeVisible();
  await capture(admin, '15-releases', 'انتشار خودکار metadata و assignment دستگاه منتخب؛ بدون دانلود یا نصب.', 'super_admin');

  await nav(admin, 'حساب‌های مشتریان');
  await admin.getByRole('button', { name: 'افزودن حساب مشتری', exact: true }).click();
  dialog = admin.getByRole('dialog');
  await dialog.getByLabel('ایمیل', { exact: true }).fill('customer-a@walkthrough.example.test');
  await dialog.getByLabel('گذرواژهٔ اولیه').fill(customerPassword);
  await dialog.getByLabel('سازمان مشتری', { exact: true }).selectOption(String(organization.id));
  await capture(admin, '16-customer-account-form', 'ساخت حساب ورود مشتری و اتصال صریح آن به سازمان الف؛ رمز پوشانده شده است.', 'super_admin');
  await saveDialog(admin, '/customer-users/', 'افزودن حساب مشتری');
  await expect(admin.getByRole('cell', { name: 'customer-a@walkthrough.example.test', exact: true })).toBeVisible();
  await capture(admin, '17-customer-accounts', 'حساب مشتری فعال در فهرست مجزای مدیریت حساب‌های مشتریان.', 'super_admin');
  record('Staff, organization, device, release and customer account created through real UI');

  const customerContext = await context();
  const customer = await customerContext.newPage();
  customer.setDefaultTimeout(30000);
  await goto(customer);
  await expect(customer.getByRole('heading', { name: 'ورود به سامانه', exact: true })).toBeVisible();
  await customer.getByLabel('ایمیل', { exact: true }).fill('customer-a@walkthrough.example.test');
  await customer.getByLabel('گذرواژه', { exact: true }).fill('Intentionally-Incorrect-Password!');
  await customer.getByRole('button', { name: 'ورود', exact: true }).click();
  await expect(customer.getByRole('alert')).toBeVisible();
  await capture(customer, '18-invalid-login', 'رد ورود با رمز اشتباه و پیام عمومی؛ هویت نامعتبر تفکیک نمی‌شود.', 'anonymous');
  await login(customer, 'customer-a@walkthrough.example.test', customerPassword, 'دستگاه‌های من');
  await expect(customer.getByRole('link', { name: 'WT-A-001', exact: true })).toBeVisible();
  await expect(customer.getByRole('link', { name: 'WT-B-001', exact: true })).toHaveCount(0);
  await capture(customer, '19-customer-devices', 'پنل مشتری فقط دو دستگاه سازمان الف را نشان می‌دهد؛ دستگاه ب دیده نمی‌شود.', 'customer');
  const list = await (await customer.request.get(`${origin}/api/v1/customer/devices/`)).json();
  assert.equal(list.count, 2);
  assert(list.results.every(item => Object.keys(item).sort().join(',') === ['id','serial_number','model_name','software_version','location','last_seen_at','is_online'].sort().join(',')));
  assert.equal((await customer.request.get(`${origin}/api/v1/devices/`)).status(), 403);
  await customer.getByRole('link', { name: 'WT-A-001', exact: true }).click();
  await expect(customer.getByRole('heading', { name: 'WT-A-001', exact: true })).toBeVisible();
  await capture(customer, '20-customer-detail', 'جزئیات فقط‌خواندنی مشتری؛ تماس داخلی، رویداد و انتشار در پاسخ وجود ندارند.', 'customer');
  await customer.reload({ waitUntil: 'domcontentloaded' });
  await expect(customer.getByRole('heading', { name: 'WT-A-001', exact: true })).toBeVisible();
  record('Real customer scoped list, safe fields, staff denial and detail reload verified');
  await customer.getByRole('button', { name: 'بازگشت به دستگاه‌ها' }).click();
  await customer.getByRole('link', { name: 'WT-A-002', exact: true }).click();
  await expect(customer.getByRole('heading', { name: 'WT-A-002', exact: true })).toBeVisible();
  await capture(customer, '21-never-connected', 'دستگاه دوم هنوز ارتباطی ندارد؛ آخرین ارتباط یا آنلاین بودن ساختگی نیست.', 'customer');
  await customer.getByRole('button', { name: 'بازگشت به دستگاه‌ها' }).click();
  await customer.getByLabel('جست‌وجوی سریال یا مدل', { exact: true }).fill('NO-MATCH');
  await expect(customer.getByText('دستگاهی با این جست‌وجو یا فیلتر یافت نشد.')).toBeVisible();
  await capture(customer, '22-customer-no-match', 'جست‌وجوی بدون نتیجه و امکان پاک‌کردن فیلتر؛ با خطای API فرق دارد.', 'customer');
  await customer.getByRole('button', { name: 'پاک‌کردن جست‌وجو و فیلتر' }).click();

  const mobileContext = await context({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const mobile = await mobileContext.newPage();
  mobile.setDefaultTimeout(30000);
  await goto(mobile);
  await login(mobile, 'customer-a@walkthrough.example.test', customerPassword, 'دستگاه‌های من');
  await expect(mobile.getByRole('link', { name: 'WT-A-001', exact: true })).toBeVisible();
  await capture(mobile, '23-mobile-customer', 'پنل مشتری در عرض ۳۹۰ پیکسل با ساختار RTL و جدول قابل پیمایش.', 'customer');
  await mobile.getByRole('button', { name: 'باز کردن منو' }).click();
  await expect(mobile.getByRole('dialog')).toBeVisible();
  await capture(mobile, '24-mobile-drawer', 'منوی کشویی موبایل مشتری؛ مسیرهای کارکنان وجود ندارند.', 'customer');
  await mobile.keyboard.press('Escape');
  await mobile.getByRole('button', { name: 'تغییر پوسته' }).click();
  await expect(mobile.locator('html')).toHaveAttribute('data-theme', 'dark');
  await capture(mobile, '25-mobile-dark', 'پوسته تیره همان پنل مشتری؛ داده‌ها از API واقعی آزمایشی هستند.', 'customer');

  await customer.getByRole('link', { name: 'WT-A-001', exact: true }).click();
  await expect(customer.getByRole('heading', { name: 'WT-A-001', exact: true })).toBeVisible();
  await nav(admin, 'دستگاه‌ها');
  const row = admin.getByRole('row').filter({ has: admin.getByRole('button', { name: 'WT-A-001', exact: true }) });
  await row.getByRole('button', { name: 'ویرایش', exact: true }).click();
  dialog = admin.getByRole('dialog');
  await dialog.locator('select[name="customer"]').selectOption({ label: 'سازمان آزمایشی ب' });
  await capture(admin, '26-device-reassignment', 'مدیر در حال انتقال دستگاه از سازمان الف به ب؛ نسخه گزارش‌شده read-only است.', 'super_admin');
  const updated = admin.waitForResponse(r => r.url().includes(`/devices/${device.id}/`) && r.request().method() === 'PATCH');
  await dialog.getByRole('button', { name: 'ذخیره', exact: true }).click();
  assert.equal((await updated).status(), 200);
  await expect(admin.getByRole('dialog')).toHaveCount(0);
  await customer.getByRole('button', { name: 'بازخوانی', exact: true }).click();
  await expect(customer.getByText('دستگاه در دسترس نیست یا دیگر به سازمان شما اختصاص ندارد.')).toBeVisible();
  await capture(customer, '27-reassigned-unavailable', 'پس از انتقال، جزئیات قبلی مشتری پاک و دسترسی از درخواست بعدی رد می‌شود.', 'customer');

  await nav(admin, 'حساب‌های مشتریان');
  await admin.getByRole('button', { name: 'غیرفعال‌کردن customer-a@walkthrough.example.test', exact: true }).click();
  await expect(admin.getByRole('cell', { name: 'غیرفعال', exact: true })).toBeVisible();
  await capture(admin, '28-customer-deactivated', 'غیرفعال‌سازی حساب مشتری توسط مدیر؛ حذف فیزیکی یا تغییر نقش انجام نمی‌شود.', 'super_admin');
  await customer.getByRole('button', { name: 'بازخوانی', exact: true }).click();
  await expect(customer.getByRole('heading', { name: 'ورود به سامانه', exact: true })).toBeVisible();
  await capture(customer, '29-revoked-session', 'بازگشت به ورود پس از لغو دسترسی؛ هیچ جزئیات دستگاه قبلی باقی نیست.', 'anonymous');
  record('Real reassignment and deactivation clear customer access on next request');

  const supportContext = await context();
  const support = await supportContext.newPage();
  support.setDefaultTimeout(30000);
  await goto(support);
  await login(support, 'support@walkthrough.example.test', supportPassword, 'نمای کلی');
  await nav(support, 'دستگاه‌ها');
  await expect(support.getByRole('button', { name: 'ثبت دستگاه', exact: true })).toHaveCount(0);
  await capture(support, '30-support-read-only', 'نمای پشتیبان بدون دکمه ثبت/ویرایش/شناسه و بدون مدیریت کاربران.', 'support');
  assert.equal((await support.request.get(`${origin}/api/v1/staff-users/`)).status(), 403);
  await support.getByRole('button', { name: 'خروج', exact: true }).first().click();
  await expect(support.getByRole('heading', { name: 'ورود به سامانه', exact: true })).toBeVisible();
  await capture(support, '31-logout', 'خروج موفق و بازگشت به صفحه ورود؛ نشست قبلی داده محافظت‌شده نشان نمی‌دهد.', 'anonymous');
  record('Support read-only boundaries and server logout verified');
  assert.equal(createHash('sha256').update(readFileSync('docs/walkthrough.fa.md')).digest('hex'), originalHash);
  record(`Captured ${screenshots.length} real panel screenshots; original guide unchanged`);
} catch (error) {
  let message = String(error.stack || error);
  for (const secret of secrets.filter(Boolean)) message = message.replaceAll(secret, '[redacted]');
  console.error(message);
  console.error(JSON.stringify({ recentApiResponses: responses.slice(-15) }));
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
  if (vite) vite.kill();
  let containerOk = true;
  try {
    const label = docker(['inspect', '--format', '{{index .Config.Labels "com.injector.walkthrough.database"}}', container]).trim();
    assert.equal(label, database);
    docker(['rm', '-f', container]);
  } catch (error) {
    // A nonexistent container is fine; a remaining one with mismatched ownership is not.
    const remaining = docker(['ps', '-a', '--filter', `name=^/${container}$`, '--format', '{{.Names}}']).trim();
    if (remaining) { containerOk = false; console.error('QA container cleanup requires attention.'); }
  }
  let databaseOk = !createdDatabase;
  if (createdDatabase && containerOk) {
    try {
      assert(/^qa_walkthrough_[a-f0-9]{12}$/.test(database));
      docker([...compose, 'exec', '-T', 'db', 'sh', '-c', 'dropdb -U "$POSTGRES_USER" "$1"', '--', database]);
      databaseOk = true;
    } catch { console.error(`QA database cleanup requires attention: ${database}`); }
  }
  cleanupOk = containerOk && databaseOk;
  if (!cleanupOk) process.exitCode = 1;
  const report = { capturedAt: new Date().toISOString(), realBackend: true, browser: 'Playwright Edge/Chromium',
    ordinaryDatabaseModified: false, originalGuideSha256: originalHash,
    captureUsesPrototypeEmbeddedFont: true, secretsMasked: true,
    steps, screenshots, cleanupOk, completed: !process.exitCode };
  writeFileSync(path.join(work, 'result.json'), JSON.stringify(report, null, 2) + '\n');
  if (!process.exitCode) writeFileSync(path.join(output, 'capture-manifest.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(`Cleanup: ${cleanupOk ? 'isolated database and API removed' : 'requires attention'}`);
}
