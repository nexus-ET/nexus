/**
 * Prints a concise pass/fail/skip summary from Playwright JSON report.
 * Usage: npm run summary  (after npm test)
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const resultsPath = path.resolve(__dirname, '../reports/results.json');
const summaryPath = path.resolve(__dirname, '../reports/summary.md');

function walkSuites(suite, rows = []) {
  if (suite.specs) {
    for (const spec of suite.specs) {
      for (const t of spec.tests || []) {
        const result = (t.results && t.results[0]) || {};
        rows.push({
          title: `${suite.title ? suite.title + ' › ' : ''}${spec.title}`,
          status: result.status || t.status || 'unknown',
          project: t.projectName || '',
          error: result.error?.message || '',
        });
      }
    }
  }
  for (const child of suite.suites || []) {
    walkSuites(child, rows);
  }
  return rows;
}

if (!fs.existsSync(resultsPath)) {
  console.error(`Missing ${resultsPath}. Run: npm test`);
  process.exit(1);
}

const report = JSON.parse(fs.readFileSync(resultsPath, 'utf8'));
const rows = [];
for (const suite of report.suites || []) {
  walkSuites(suite, rows);
}

const counts = { passed: 0, failed: 0, skipped: 0, timedOut: 0, interrupted: 0, unknown: 0 };
for (const r of rows) {
  const key = counts[r.status] !== undefined ? r.status : 'unknown';
  counts[key] += 1;
}

const lines = [
  '# Nexus UAT — Playwright execution summary',
  '',
  `Generated: ${new Date().toISOString()}`,
  '',
  '## Totals',
  '',
  `| Status | Count |`,
  `| --- | ---: |`,
  `| Passed | ${counts.passed} |`,
  `| Failed | ${counts.failed} |`,
  `| Skipped | ${counts.skipped} |`,
  `| Timed out | ${counts.timedOut} |`,
  `| Interrupted | ${counts.interrupted} |`,
  `| Other | ${counts.unknown} |`,
  `| **Total** | **${rows.length}** |`,
  '',
  '## Cases',
  '',
];

for (const r of rows) {
  lines.push(`- **${r.status.toUpperCase()}** — ${r.title}${r.project ? ` (${r.project})` : ''}`);
  if (r.error) {
    lines.push(`  - ${String(r.error).split('\n')[0]}`);
  }
}

fs.mkdirSync(path.dirname(summaryPath), { recursive: true });
fs.writeFileSync(summaryPath, lines.join('\n') + '\n', 'utf8');
console.log(lines.join('\n'));
console.log(`\nWrote ${summaryPath}`);
console.log(`HTML report: reports/html/index.html`);
console.log(`JSON report: reports/results.json`);
