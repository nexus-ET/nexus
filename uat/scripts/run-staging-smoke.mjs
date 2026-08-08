import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import dotenv from 'dotenv';

const here = path.dirname(fileURLToPath(import.meta.url));
const uatRoot = path.resolve(here, '..');
const backendRoot = path.resolve(uatRoot, '../backend');
dotenv.config({ path: path.join(uatRoot, '.env') });

const baseUrl = (
  process.env.STAGING_SMOKE_BASE_URL ||
  process.env.UAT_BASE_URL ||
  'https://nexus-dev.edutrust.in'
).replace(/\/$/, '');

const pyCandidates = [
  path.join(backendRoot, '.venv', 'Scripts', 'python.exe'),
  path.join(backendRoot, '.venv', 'bin', 'python'),
  'python',
];
const python = pyCandidates.find((candidate) => candidate === 'python' || fs.existsSync(candidate));
if (!python) {
  console.error('No Python interpreter found for staging smoke.');
  process.exit(1);
}

const script = path.join(backendRoot, 'scripts', 'staging_post_deploy_smoke.py');
const env = {
  ...process.env,
  UAT_EMAIL: process.env.UAT_EMAIL || process.env.STAGING_SMOKE_EMAIL || '',
  UAT_PASSWORD: process.env.UAT_PASSWORD || process.env.STAGING_SMOKE_PASSWORD || '',
  STAGING_SMOKE_BASE_URL: baseUrl,
};

const result = spawnSync(python, [script, '--base-url', baseUrl], {
  cwd: backendRoot,
  env,
  stdio: 'inherit',
});
process.exit(result.status ?? 1);
