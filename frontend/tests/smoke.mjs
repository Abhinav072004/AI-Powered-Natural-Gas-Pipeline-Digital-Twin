import assert from 'node:assert/strict'
import { chromium } from 'playwright-core'

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium' })
const base = process.env.TWIN_BASE || 'http://127.0.0.1:8080'
const pages = process.env.TWIN_MODE === 'pages'
const errors = []
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  page.on('pageerror', error => errors.push(error.message))
  if (pages) page.on('request', request => {
    if (new URL(request.url()).pathname.startsWith('/api/')) errors.push(`Unexpected request ${request.url()}`)
  })
  await page.goto(base)
  await page.getByRole('heading', { name: 'Operations overview' }).waitFor()
  if (pages) {
    await page.getByText('Published simulation', { exact: true }).waitFor()
    assert.equal(await page.locator('option[value=live]').count(), 0)
  }
  if (process.env.TWIN_SCREENSHOT) await page.screenshot({ path: process.env.TWIN_SCREENSHOT, fullPage: true })
  await page.getByRole('button', { name: /^S4\b/ }).click()
  await page.getByText('Segment 4', { exact: true }).waitFor()
  await page.getByLabel('Telemetry source').selectOption('communication_failure')
  await page.getByRole('link', { name: 'Leak detection' }).click()
  await page.getByText('Communication fault', { exact: true }).first().waitFor()
  await page.getByLabel('Telemetry source').selectOption('normal')
  await page.getByRole('link', { name: 'Digital twin' }).click()
  await page.getByRole('heading', { name: 'Sensor readings' }).waitFor()
  await page.getByText('PT-101', { exact: true }).waitFor()
  await page.getByRole('link', { name: 'Energy optimization' }).click()
  await page.getByRole('button', { name: 'Compare operating points' }).click()
  await page.getByRole('heading', { name: 'Simulated comparison' }).waitFor()
  if (pages) {
    assert.equal(await page.locator('select[name=flow]').inputValue(), '60')
    await page.locator('select[name=delivery_bar]').selectOption('80')
    await page.getByRole('button', { name: 'Compare operating points' }).click()
    await page.getByText('No feasible operating point with the selected limits').waitFor()
  }
  await page.getByRole('link', { name: 'Maintenance', exact: true }).click()
  await page.getByRole('heading', { name: 'Equipment priority' }).waitFor()
  await page.getByRole('link', { name: 'Safety & risk' }).click()
  await page.getByRole('button', { name: 'Probability 5, severity 5: critical' }).click()
  await page.getByRole('button', { name: 'Evaluate risk' }).click()
  await page.getByText('Critical · 25/25', { exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Save review' }).count(), pages ? 0 : 1)
  await page.getByRole('link', { name: 'Engineering copilot' }).click()
  await page.getByRole('button', { name: 'What is linepack and why does it matter?' }).click()
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await page.getByRole('heading', { name: 'Sources' }).waitFor()
  await page.getByText('Simulation context', { exact: true }).waitFor()
  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 } })
  await mobile.goto(base)
  await mobile.getByRole('heading', { name: 'Operations overview' }).waitFor()
  assert.equal(await mobile.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true)
  assert.deepEqual(errors, [])
  console.log('All seven views, segment selection, scenario switching, engineering forms, copilot citations and mobile layout passed.')
} finally {
  await browser.close()
}
