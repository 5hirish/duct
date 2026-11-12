// The CLI and the skill must agree on every id, area and weight. The skill's
// files live outside the package, so these run only in the repository.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { CHECKS, AREAS, BANDS } from '../src/catalog.js';
import { SCHEMA } from '../src/schema.js';
import { VERSION } from '../src/version.js';

const SKILL = new URL('../../skills/launch-check/', import.meta.url);
const inRepo = existsSync(new URL('references/checklist.md', SKILL));

test('the schema lists exactly the catalog ids', () => {
  assert.deepEqual(SCHEMA.properties.checks.items.properties.id.enum, Object.keys(CHECKS));
  assert.deepEqual(SCHEMA.properties.band.enum, BANDS.map((b) => b.name));
});

test('every catalog id is in the checklist, and the other way round', { skip: !inRepo && 'not in the repository' }, () => {
  const md = readFileSync(new URL('references/checklist.md', SKILL), 'utf8');
  const ids = [...md.matchAll(/^\| ([MKSCAF]\d{1,2}) /gm)].map((m) => m[1]);
  assert.deepEqual([...ids].sort(), Object.keys(CHECKS).sort());
});

test('area weights match the skill', { skip: !inRepo && 'not in the repository' }, () => {
  const md = readFileSync(new URL('SKILL.md', SKILL), 'utf8');
  for (const a of AREAS) {
    const m = new RegExp(`^\\| ${a.name} \\| (\\d+) \\|`, 'mi').exec(md);
    assert.ok(m, `SKILL.md has no weight row for ${a.name}`);
    assert.equal(Number(m[1]), a.weight, a.name);
  }
});

// The skill runs `npx getduct@<version>`, pinned because the Claude and OpenAI
// plugin directories refuse a launcher that can change after review. A CLI
// release that forgets the pin would leave every installed skill on the old
// version, so the bump and the pin land in the same change or this fails.
test('the skill and the plugin README pin this release', { skip: !inRepo && 'not in the repository' }, () => {
  for (const file of ['launch-check/SKILL.md', 'README.md']) {
    const md = readFileSync(new URL(`../${file}`, SKILL), 'utf8');
    const pins = new Set([...md.matchAll(/getduct@([\w.-]+)/g)].map((m) => m[1]));
    assert.deepEqual([...pins], [VERSION], `${file} pins getduct@${[...pins].join(', ')}, the CLI is ${VERSION}`);
  }
});
