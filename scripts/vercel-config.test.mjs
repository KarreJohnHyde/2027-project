import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import test from 'node:test';

const root = fileURLToPath(new URL('../', import.meta.url));
const config = JSON.parse(readFileSync(path.join(root, 'vercel.json'), 'utf8'));
const exclusions = readFileSync(path.join(root, '.vercelignore'), 'utf8').split(/\r?\n/).filter(line => line && !line.startsWith('#'));

// Vercel matches rewrite sources as anchored path patterns; these sources are plain regular expressions.
const matches = (source, urlPath) => new RegExp(`^${source}$`).test(urlPath);
const serviceFor = urlPath => config.rewrites.find(rule => matches(rule.source, urlPath))?.destination.service;

test('the Vite app and the FastAPI backend are the only services, with no bindings', () => {
  assert.deepEqual(Object.keys(config.services).sort(), ['app', 'backend']);
  assert.equal(config.experimentalServices, undefined);
  assert.equal(config.daemons, undefined);
  for (const service of Object.values(config.services)) {
    assert.equal(service.bindings, undefined, 'the static app calls /api/v1 publicly; the backend calls no service');
  }
  for (const key of ['buildCommand', 'installCommand', 'framework', 'outputDirectory', 'functions']) {
    assert.equal(config[key], undefined, `${key} belongs to a service in services mode`);
  }
});

test('the app builds the Vite bundle with the npm lockfile', () => {
  const app = config.services.app;
  assert.deepEqual([app.root, app.framework, app.installCommand, app.buildCommand, app.outputDirectory], ['.', 'vite', 'npm ci', 'npm run build', 'dist']);
  assert.ok(existsSync(path.join(root, 'package-lock.json')));
});

test('the backend runs on the Python runtime with its evidence staged at build time', () => {
  const backend = config.services.backend;
  assert.deepEqual([backend.root, backend.framework, backend.entrypoint, backend.buildCommand], ['backend', 'fastapi', 'app.main:app', 'python3 vercel_build.py']);
  assert.ok(existsSync(path.join(root, 'backend/app/main.py')));
  assert.ok(existsSync(path.join(root, 'backend/vercel_build.py')));
  for (const manifest of ['backend/pyproject.toml', 'backend/uv.lock']) assert.ok(existsSync(path.join(root, manifest)), manifest);
  assert.ok(backend.functions['app/main.py'].maxDuration <= 300, 'Hobby functions stop at 300 seconds');
});

test('API and health requests reach the backend unchanged; everything else is the app', () => {
  for (const route of ['/api/v1/cases/7', '/api/v1/system/health', '/health']) assert.equal(serviceFor(route), 'backend', route);
  for (const route of ['/', '/cases/7', '/upload', '/assets/index-abc.js', '/apiary', '/models/medtwin_l1_heart.glb']) assert.equal(serviceFor(route), 'app', route);
  assert.deepEqual(config.rewrites.at(-1), { source: '/(.*)', destination: { service: 'app' } });
});

test('client-side routes fall back to the app shell, missing files stay 404', () => {
  const [fallback] = config.services.app.rewrites;
  assert.equal(fallback.destination, '/index.html');
  for (const route of ['/cases/7', '/anatomy-studio', '/research/analytics']) assert.ok(matches(fallback.source, route), route);
  for (const route of ['/assets/missing.js', '/models/missing.glb', '/anatomy/derived/brain.glb']) assert.ok(!matches(fallback.source, route), route);
});

test('the app keeps the security headers the nginx image sends', () => {
  const headers = Object.fromEntries(config.services.app.headers[0].headers.map(({ key, value }) => [key, value]));
  const nginx = readFileSync(path.join(root, 'nginx-security-headers.conf'), 'utf8');
  for (const [key, value] of Object.entries(headers)) assert.ok(nginx.includes(`add_header ${key} "${value}" always;`), key);
  assert.equal(Object.keys(headers).length, 6);
});

test('the frontend default remains same-origin /api/v1', () => {
  const api = readFileSync(path.join(root, 'src/services/api.ts'), 'utf8');
  assert.match(api, /export const API_V1_BASE = configuredOrigin \? .* : '\/api\/v1';/);
});

test('the upload allowlist starts closed and admits build inputs and evidence, not datasets', () => {
  assert.equal(exclusions[0], '**');
  for (const required of ['!vercel.json', '!backend/app/**', '!backend/pyproject.toml', '!backend/uv.lock', '!backend/vercel_build.py',
    '!dataset_registry/tasks.json', '!docs/validation/models/*.json', '!public/models/medtwin_l1_*.glb', '!scripts/start-vite.mjs']) {
    assert.ok(exclusions.includes(required), required);
  }
  for (const forbidden of ['!artifacts/**', '!backend/uploads/**', '!public/**', '!benchmarks/**', '!data/**', '!docs/**']) {
    assert.ok(!exclusions.includes(forbidden), forbidden);
  }
});

test('credentials, local clinical state, weights and unreleased models stay excluded', () => {
  for (const rule of ['**/.env', '**/.env.*', '**/*.db', '**/*.key', '**/*.pt', 'public/anatomy/derived/**', 'backend/uploads/**', 'backend/deployment_files/**']) {
    assert.ok(exclusions.includes(rule), rule);
  }
  assert.doesNotMatch(JSON.stringify(config), /token|secret|password|key=/i);
});
