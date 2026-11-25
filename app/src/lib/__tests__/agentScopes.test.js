import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  DEFAULT_WORK_SCOPES,
  SCOPE_PROJECTS,
  WORK_SCOPES,
  askedExtras,
  grantBody,
  grantFacts,
  grantProblem,
  initialGrant,
  toggleScope,
} from "../agentScopes";

describe("the grant a person gives an agent", () => {
  it("opens closed when the agent asked for setup alone, and sends setup on every project", () => {
    const grant = initialGrant(["projects"]);
    expect(grant.work).toBe(false);
    expect(grantBody(grant)).toEqual({ scopes: [SCOPE_PROJECTS], project_ids: null });
  });

  it("opens on the safe defaults when the agent asked for more, never on a deliberate one", () => {
    const grant = initialGrant(["projects", "data", "changes", "media"]);
    expect(grant.work).toBe(true);
    expect(grant.scopes).toEqual(DEFAULT_WORK_SCOPES);
  });

  it("keeps the table order whatever order the ticks came in", () => {
    let scopes = toggleScope([], "media", true);
    scopes = toggleScope(scopes, "data", true);
    expect(scopes).toEqual(["data", "media"]);
    expect(toggleScope(scopes, "media", false)).toEqual(["data"]);
  });

  it("refuses only some projects with none picked, and sends the picked ones", () => {
    const grant = { work: true, scopes: ["data"], projectIds: [] };
    expect(grantProblem(grant)).toBe("no_projects");
    expect(grantProblem({ ...grant, projectIds: ["p1"] })).toBeNull();
    expect(grantBody({ ...grant, projectIds: ["p1"] })).toEqual({ scopes: ["projects", "data"], project_ids: ["p1"] });
  });

  it("keeps the project choice for setup alone too", () => {
    const grant = { work: false, scopes: ["data"], projectIds: ["p1"] };
    expect(grantBody(grant)).toEqual({ scopes: ["projects"], project_ids: ["p1"] });
    expect(grantProblem({ ...grant, projectIds: [] })).toBe("no_projects");
  });

  it("names the extras the agent asked for, in table order, and nothing else", () => {
    expect(askedExtras(["media", "data", "changes"])).toEqual(["changes", "media"]);
    expect(askedExtras(undefined)).toEqual([]);
  });

  it("reads a row from before tiers as setup on every project", () => {
    expect(grantFacts({})).toEqual({ scopes: [], projects: null });
    expect(grantFacts({ scopes: ["projects", "data"], project_ids: ["a", "b"] })).toEqual({
      scopes: ["data"],
      projects: 2,
    });
  });

  it("names the same scopes the backend does", () => {
    const backend = readFileSync(new URL("../../../../backend/service/mcp_server/scopes.py", import.meta.url), "utf8");
    const named = [...backend.matchAll(/^([A-Z]+) = "([a-z]+)"$/gm)].map((m) => m[2]);
    expect(new Set(named)).toEqual(new Set([SCOPE_PROJECTS, ...WORK_SCOPES]));
  });
});
