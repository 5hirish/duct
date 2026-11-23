// Which accounts a project's switched-on channels link to without being asked.
//
// A channel switched on is "post here". When the primary scheduler holds
// exactly one account for it, that account is the only one it can mean, so it
// is linked. Switching on used to save only the switch: LinkedIn read as on,
// nothing could post through it, and Analytics and the Plans checklist (which
// read links, not switches) said no account was linked. Two or more accounts
// is a real choice and stays the person's.

/** The key a linked account is stored under in the Accounts tab. */
export const accountKey = (a) => `${a.publisher || ""}:${a.id ?? a.account_id}`;

/** The one account `channelId` can mean at `primary`, or null. */
export function soleAccount(accounts, channelId, primary) {
  const candidates = accounts.filter((a) => a.platform === channelId && a.publisher === primary);
  return candidates.length === 1 ? candidates[0] : null;
}

/**
 * Accounts to link for channels that are on with nothing linked at the
 * primary scheduler and exactly one account there.
 *
 * @param profiles  { [channelId]: { enabled } }
 * @param accounts  every account the connected schedulers list
 * @param primary   the primary scheduler's id
 * @param linked    Set of accountKey()s already linked
 */
export function accountsToAutoLink({ profiles, accounts, primary, linked }) {
  if (!primary) return [];
  const out = [];
  for (const [channelId, profile] of Object.entries(profiles || {})) {
    if (!profile?.enabled) continue;
    const hasLink = accounts.some((a) => a.platform === channelId && a.publisher === primary && linked.has(accountKey(a)));
    const sole = soleAccount(accounts, channelId, primary);
    if (!hasLink && sole) out.push(sole);
  }
  return out;
}
