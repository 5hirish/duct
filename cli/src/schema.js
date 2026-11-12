// Validate a result against schema/launch-check.schema.json.
//
// The schema file is the one definition: agents read it (`getduct schema`),
// and this interprets the subset of JSON Schema it uses rather than carrying
// a validator dependency or a second, hand-written copy of the rules.

import { readFileSync } from 'node:fs';

export const SCHEMA = JSON.parse(readFileSync(new URL('../schema/launch-check.schema.json', import.meta.url), 'utf8'));

function typeOf(v) {
  if (v === null) return 'null';
  if (Array.isArray(v)) return 'array';
  if (typeof v === 'number') return Number.isInteger(v) ? 'integer' : 'number';
  return typeof v;
}

function check(value, rule, path, errors) {
  if (rule.const !== undefined && value !== rule.const) {
    errors.push(`${path} must be ${JSON.stringify(rule.const)}`);
    return;
  }
  if (rule.enum && !rule.enum.includes(value)) {
    errors.push(`${path} must be one of ${rule.enum.join(', ')} (got ${JSON.stringify(value)})`);
    return;
  }
  if (rule.type) {
    const types = [].concat(rule.type);
    const t = typeOf(value);
    if (!types.includes(t) && !(t === 'integer' && types.includes('number'))) {
      errors.push(`${path} must be ${types.join(' or ')} (got ${t})`);
      return;
    }
  }
  if (typeof value === 'string') {
    if (rule.minLength !== undefined && value.length < rule.minLength) errors.push(`${path} is shorter than ${rule.minLength} characters`);
    if (rule.maxLength !== undefined && value.length > rule.maxLength) errors.push(`${path} is longer than ${rule.maxLength} characters`);
    if (rule.pattern && !new RegExp(rule.pattern).test(value)) errors.push(`${path} does not match ${rule.pattern}`);
  }
  if (typeof value === 'number') {
    if (rule.minimum !== undefined && value < rule.minimum) errors.push(`${path} is below ${rule.minimum}`);
    if (rule.maximum !== undefined && value > rule.maximum) errors.push(`${path} is above ${rule.maximum}`);
  }
  if (Array.isArray(value)) {
    if (rule.maxItems !== undefined && value.length > rule.maxItems) errors.push(`${path} has more than ${rule.maxItems} items`);
    if (rule.items) value.forEach((v, i) => check(v, rule.items, `${path}[${i}]`, errors));
  }
  if (typeOf(value) === 'object') {
    for (const key of rule.required ?? []) {
      if (value[key] === undefined) errors.push(`${path}.${key} is required`);
    }
    for (const [key, sub] of Object.entries(rule.properties ?? {})) {
      if (value[key] !== undefined) check(value[key], sub, `${path}.${key}`, errors);
    }
  }
}

// Returns a list of problems; empty means valid.
export function validate(result) {
  const errors = [];
  check(result, SCHEMA, 'result', errors);
  if (Array.isArray(result?.checks)) {
    const seen = new Set();
    for (const c of result.checks) {
      if (!c?.id) continue;
      // The skill counts a check once however many pages it affects; two
      // entries for one id would charge it twice.
      if (seen.has(c.id)) errors.push(`result.checks has ${c.id} twice: merge them, worst status wins`);
      seen.add(c.id);
    }
  }
  return errors;
}
