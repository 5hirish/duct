"use client";

// Project collaboration API (members + invitations).
//
// Unlike lib/projects.js there is no localStorage mirror here: a member list is
// shared state that only the server can be right about, and showing a stale
// roster is worse than showing a spinner. Every call goes to the backend and
// throws a plain Error with the server's message so callers can surface it
// verbatim.

import { BASE } from "./api";

const TOKEN_KEY = "duct_auth_token";

function authToken() {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

function headers(extra = {}) {
  const out = { ...extra };
  const apiKey = process.env.NEXT_PUBLIC_DUCT_API_KEY;
  if (apiKey) out["X-API-Key"] = apiKey;
  const token = authToken();
  if (token) out["Authorization"] = `Bearer ${token}`;
  return out;
}

/** Pull the human-readable reason out of a FastAPI error body. */
async function errorMessage(res, fallback) {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    // 422 from a field validator: [{ loc, msg, ... }]
    if (Array.isArray(body?.detail) && body.detail[0]?.msg) {
      return String(body.detail[0].msg).replace(/^Value error,\s*/, "");
    }
  } catch {
    // fall through to the generic message
  }
  return fallback;
}

async function request(path, { method = "GET", body, fallbackError } = {}) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? headers({ "Content-Type": "application/json" }) : headers(),
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    throw new Error(await errorMessage(res, fallbackError || "Something went wrong."));
  }
  if (res.status === 204) return null;
  return res.json();
}

// --- Member list ---------------------------------------------------------

/**
 * Members and pending invitations for a project.
 * Returns { project_id, project_name, viewer_role, members, invitations, email_delivery }.
 */
export function fetchMembers(projectId) {
  return request(`/api/user/projects/${encodeURIComponent(projectId)}/members`, {
    fallbackError: "Could not load the member list.",
  });
}

// --- Invitations ---------------------------------------------------------

export function inviteMember(projectId, email) {
  return request(`/api/user/projects/${encodeURIComponent(projectId)}/invitations`, {
    method: "POST",
    body: { email },
    fallbackError: "Could not send the invitation.",
  });
}

export function resendInvitation(projectId, invitationId) {
  return request(
    `/api/user/projects/${encodeURIComponent(projectId)}/invitations/${encodeURIComponent(
      invitationId
    )}/resend`,
    { method: "POST", fallbackError: "Could not resend the invitation." }
  );
}

export function revokeInvitation(projectId, invitationId) {
  return request(
    `/api/user/projects/${encodeURIComponent(projectId)}/invitations/${encodeURIComponent(
      invitationId
    )}`,
    { method: "DELETE", fallbackError: "Could not revoke the invitation." }
  );
}

// --- Membership ----------------------------------------------------------

/** Remove a collaborator. Pass "me" to leave a project you were invited to. */
export function removeMember(projectId, memberUserId) {
  return request(
    `/api/user/projects/${encodeURIComponent(projectId)}/members/${encodeURIComponent(
      memberUserId
    )}`,
    { method: "DELETE", fallbackError: "Could not remove this member." }
  );
}

// --- Redeeming an invitation --------------------------------------------

/** Public preview of an invite link — works before the recipient signs in. */
export function fetchInvitation(token) {
  return request(`/api/invitations/${encodeURIComponent(token)}`, {
    fallbackError: "This invitation link is invalid or has expired.",
  });
}

export function acceptInvitation(token) {
  return request(`/api/invitations/${encodeURIComponent(token)}/accept`, {
    method: "POST",
    fallbackError: "Could not accept this invitation.",
  });
}
