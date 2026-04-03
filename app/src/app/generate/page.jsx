import Link from "next/link";

export default function GeneratePage() {
  return (
    <section>
      <h1 style={{ marginTop: 0 }}>Generate</h1>
      <p className="app-subtle" style={{ marginTop: 0, marginBottom: 18 }}>
        Generate flow placeholder. This is where report generation steps will live.
      </p>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <Link className="btn btn-ghost" href="/connections">
          Go to Connections
        </Link>
        <Link className="btn btn-ghost" href="/reports">
          Back to Reports
        </Link>
      </div>
    </section>
  );
}
