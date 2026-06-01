"use client";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../ui/table";

function shouldHighlight(row, threshold) {
  if (!threshold?.field) return false;
  const value = Number(row?.[threshold.field]);
  if (!Number.isFinite(value)) return false;
  if (threshold.below !== undefined && threshold.below !== null) return value < Number(threshold.below);
  if (threshold.above !== undefined && threshold.above !== null) return value > Number(threshold.above);
  return false;
}

export default function TableBlock({ title, rows, xField, yField, groupBy, highlightThreshold, insightNote = "" }) {
  if (!rows?.length) return null;
  const fields = [xField, groupBy, yField].filter(Boolean);
  const columnSet = fields.length ? fields : Object.keys(rows[0] || {}).slice(0, 6);

  return (
    <section>
      <p className="rpt-section-label">{title || "Table"}</p>
      <div className="rounded-xl border border-border bg-card">
        <Table className="camp-table">
          <TableHeader>
            <TableRow>
              {columnSet.map((key) => (
                <TableHead key={key}>{key.replace(/_/g, " ")}</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row, index) => (
              <TableRow
                key={`${index}-${row?.[xField] ?? "row"}`}
                className={index % 2 ? "camp-row camp-row--alt" : "camp-row"}
              >
                {columnSet.map((key) => (
                  <TableCell
                    key={key}
                    className={shouldHighlight(row, highlightThreshold) ? "text-destructive" : ""}
                  >
                    {String(row?.[key] ?? "-")}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {insightNote ? <p className="rpt-meta">{insightNote}</p> : null}
    </section>
  );
}
