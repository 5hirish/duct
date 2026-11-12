// robots.txt as crawlers read it (RFC 9309): a crawler obeys the group that
// names it, else the `*` group; the longest matching rule wins and Allow wins
// a tie.

export const AI_CRAWLERS = ['GPTBot', 'OAI-SearchBot', 'ChatGPT-User', 'ClaudeBot', 'Claude-SearchBot', 'PerplexityBot', 'Google-Extended'];
export const SEARCH_CRAWLERS = ['Googlebot', 'Bingbot'];

export function parseRobots(text) {
  const groups = [];
  const sitemaps = [];
  let current = null, lastWasAgent = false;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.replace(/#.*/, '').trim();
    const m = /^([a-z-]+)\s*:\s*(.*)$/i.exec(line);
    if (!m) continue;
    const key = m[1].toLowerCase(), value = m[2].trim();
    if (key === 'user-agent') {
      if (!lastWasAgent) { current = { agents: [], rules: [] }; groups.push(current); }
      current.agents.push(value.toLowerCase());
      lastWasAgent = true;
      continue;
    }
    lastWasAgent = false;
    if (key === 'sitemap') { if (value) sitemaps.push(value); continue; }
    if ((key === 'allow' || key === 'disallow') && current) current.rules.push({ allow: key === 'allow', path: value });
  }
  return { groups, sitemaps };
}

function groupFor(robots, agent) {
  const a = agent.toLowerCase();
  const named = robots.groups.filter((g) => g.agents.some((x) => x !== '*' && a.startsWith(x)));
  if (named.length) return { rules: named.flatMap((g) => g.rules), named: true };
  const star = robots.groups.filter((g) => g.agents.includes('*'));
  return { rules: star.flatMap((g) => g.rules), named: false };
}

function matches(pattern, path) {
  const anchored = pattern.endsWith('$');
  const body = (anchored ? pattern.slice(0, -1) : pattern).split('*').map((s) => s.replace(/[.+?^${}()|[\]\\]/g, '\\$&')).join('.*');
  return new RegExp(`^${body}${anchored ? '$' : ''}`).test(path);
}

export function isAllowed(robots, agent, path = '/') {
  const { rules } = groupFor(robots, agent);
  let best = null;
  for (const r of rules) {
    // An empty Disallow allows everything; it is not a rule about "/".
    if (!r.path) continue;
    if (!matches(r.path, path)) continue;
    if (!best || r.path.length > best.path.length || (r.path.length === best.path.length && r.allow)) best = r;
  }
  return !best || best.allow;
}

// Which named group decided, for the evidence line.
export function decidingGroup(robots, agent) {
  return groupFor(robots, agent).named ? agent : '*';
}
