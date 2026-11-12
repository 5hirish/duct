"use client";

// Scheduled runs (#562), from the app's side: /api/user/schedules. No
// localStorage mirror: a schedule's state is the loop's, and only the server
// can be right about whether it is running.

import { authedRequest } from "./authFetch";

const PATH = "/api/user/schedules";

export function listSchedules(projectId) {
  const q = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return authedRequest(`${PATH}${q}`);
}

export function createSchedule(body) {
  return authedRequest(PATH, { method: "POST", body });
}

export function updateSchedule(id, changes) {
  return authedRequest(`${PATH}/${id}`, { method: "PATCH", body: changes });
}

export function runScheduleNow(id) {
  return authedRequest(`${PATH}/${id}/run`, { method: "POST" });
}

export function deleteSchedule(id) {
  return authedRequest(`${PATH}/${id}`, { method: "DELETE" });
}

export function scheduleHistory(id) {
  return authedRequest(`${PATH}/${id}/history`);
}
