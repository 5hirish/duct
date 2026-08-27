"use client";

// Per-project connector→account mappings.
//
// A user can save several accounts per connector (two Stripe accounts, an
// MCC's sub-accounts, …). This panel decides which one each PROJECT uses:
// pick a project, then map any connector type you have saved accounts for.
// Agents, executions, and reports scoped to that project resolve credentials
// through the mapping first; unmapped connectors fall back to the
// account-level default. Mappings live server-side (project_connectors) so
// server-side agent runs honor them too.

import { useEffect, useState } from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  bindProjectConnector,
  listProjectConnectors,
  unbindProjectConnector,
} from "../../lib/connectorsApi";
import { fetchProjectsRemote } from "../../lib/projectsApi";
import { getActiveProjectId } from "../../lib/projects";

const CONNECTOR_LABELS = {
  google_ads: "Google Ads",
  ga4: "Google Analytics",
  gsc: "Search Console",
  gtm: "Tag Manager",
  meta_ads: "Meta Ads",
  stripe: "Stripe",
  apple_ads: "Apple Search Ads",
  revenuecat: "RevenueCat",
  openai_ads: "OpenAI Ads",
};

// Radix SelectItem values must be non-empty — sentinel for "no mapping".
const DEFAULT_VALUE = "__default__";

function accountLabel(row) {
  return row.account_name || row.account_id || "Unnamed account";
}

export default function ProjectConnectorMappings({ signedIn, serverRowsAll }) {
  const [projects, setProjects] = useState(null); // null = loading
  const [projectId, setProjectId] = useState("");
  const [bindings, setBindings] = useState({}); // connector_type -> binding row
  const [busyType, setBusyType] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!signedIn) return;
    let alive = true;
    fetchProjectsRemote().then((rows) => {
      if (!alive) return;
      setProjects(rows);
      const active = getActiveProjectId();
      setProjectId(rows.some((p) => p.id === active) ? active : rows[0]?.id || "");
    });
    return () => {
      alive = false;
    };
  }, [signedIn]);

  useEffect(() => {
    if (!projectId) return;
    let alive = true;
    setError("");
    listProjectConnectors(projectId)
      .then((rows) => {
        if (!alive) return;
        const byType = {};
        for (const row of rows) byType[row.connector_type] = row;
        setBindings(byType);
      })
      .catch((err) => alive && setError(err.message || String(err)));
    return () => {
      alive = false;
    };
  }, [projectId]);

  async function changeMapping(connectorType, value) {
    setBusyType(connectorType);
    setError("");
    try {
      if (value === DEFAULT_VALUE) {
        if (bindings[connectorType]) {
          await unbindProjectConnector(projectId, connectorType);
          setBindings((prev) => {
            const next = { ...prev };
            delete next[connectorType];
            return next;
          });
        }
      } else {
        const row = await bindProjectConnector(projectId, connectorType, value);
        setBindings((prev) => ({ ...prev, [connectorType]: row }));
      }
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusyType("");
    }
  }

  if (!signedIn) {
    return (
      <p className="app-subtle" style={{ marginTop: 0 }}>
        Sign in to map connectors to projects — mappings are stored on your
        account so agents and scheduled runs honor them.
      </p>
    );
  }

  const mappableTypes = Object.keys(CONNECTOR_LABELS).filter(
    (type) => (serverRowsAll[type] || []).length > 0
  );

  return (
    <div style={{ display: "grid", gap: 16, maxWidth: 640 }}>
      <p className="app-subtle" style={{ margin: 0 }}>
        Each project can use a different account per connector — e.g. one
        Stripe account per client. Agents, executions, and reports for the
        project resolve through its mapping first; &ldquo;Account
        default&rdquo; falls back to your saved connector.
      </p>

      {projects !== null && projects.length === 0 && (
        <p className="app-subtle" style={{ margin: 0 }}>
          No synced projects yet — create a project first.
        </p>
      )}

      {projects !== null && projects.length > 0 && (
        <div style={{ display: "grid", gap: 6, maxWidth: 360 }}>
          <span className="app-subtle" style={{ fontSize: 13 }}>Project</span>
          <Select value={projectId} onValueChange={setProjectId}>
            <SelectTrigger>
              <SelectValue placeholder="Pick a project" />
            </SelectTrigger>
            <SelectContent>
              {projects.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name || "Untitled project"}
                  {p.role === "collaborator" ? " (shared)" : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {projectId && mappableTypes.length === 0 && (
        <p className="app-subtle" style={{ margin: 0 }}>
          No saved connector accounts yet — connect a data source first.
        </p>
      )}

      {projectId &&
        mappableTypes.map((type) => {
          const rows = serverRowsAll[type] || [];
          const bound = bindings[type];
          // A binding may reference another member's credential row — one we
          // can't offer in the options list. Surface it read-only instead.
          const foreignBinding =
            bound && !rows.some((r) => r.id === bound.connector_credential_id);
          return (
            <div
              key={type}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
                flexWrap: "wrap",
              }}
            >
              <div>
                <div style={{ fontSize: 14, fontWeight: 500 }}>
                  {CONNECTOR_LABELS[type]}
                </div>
                {foreignBinding && (
                  <div className="app-subtle" style={{ fontSize: 12 }}>
                    Mapped to {bound.account_name || bound.account_id || "a teammate's account"}{" "}
                    (a teammate&rsquo;s connector)
                  </div>
                )}
              </div>
              <div style={{ minWidth: 240 }}>
                <Select
                  value={
                    bound && !foreignBinding
                      ? bound.connector_credential_id
                      : DEFAULT_VALUE
                  }
                  onValueChange={(value) => changeMapping(type, value)}
                  disabled={busyType === type}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={DEFAULT_VALUE}>Account default</SelectItem>
                    {rows.map((row) => (
                      <SelectItem key={row.id} value={row.id}>
                        {accountLabel(row)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          );
        })}

      {error && (
        <p style={{ margin: 0, fontSize: 13, color: "var(--destructive, #e5484d)" }}>
          {error}
        </p>
      )}
    </div>
  );
}
