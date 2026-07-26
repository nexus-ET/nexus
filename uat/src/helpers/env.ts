import fs from 'fs';
import path from 'path';

export type UatEnv = {
  baseUrl: string;
  email: string;
  password: string;
  leadId: string;
};

export function loadUatEnv(): UatEnv {
  const baseUrl = (process.env.UAT_BASE_URL || 'http://127.0.0.1:5175').replace(/\/$/, '');
  const email = (process.env.UAT_EMAIL || '').trim();
  const password = (process.env.UAT_PASSWORD || '').trim();
  const leadId = (process.env.UAT_LEAD_ID || '27').trim();

  return { baseUrl, email, password, leadId };
}

export function requireCredentials(): UatEnv {
  const env = loadUatEnv();
  if (!env.email || !env.password) {
    throw new Error(
      'UAT_EMAIL and UAT_PASSWORD must be set in uat/.env (see .env.example).'
    );
  }
  return env;
}

export function ensureAuthDir(): string {
  const dir = path.resolve(__dirname, '../../playwright/.auth');
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}
