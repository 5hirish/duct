// Read once from package.json so the User-Agent, --version and the result's
// `tool` field can never name a different release from the one installed.
import { readFileSync } from 'node:fs';

export const VERSION = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8')).version;
export const REPO_URL = 'https://github.com/5hirish/duct';
export const USER_AGENT = `getduct/${VERSION} (+${REPO_URL})`;
