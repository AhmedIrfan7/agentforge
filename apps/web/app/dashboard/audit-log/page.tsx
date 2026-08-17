"use client";

// Audit-log viewer (roadmap step 247) -- the first real reader of the
// AuditLog rows every mutating router in this app has been writing
// since step 072 (routers/audit_log.py's own docstring). Its own nav
// entry, not folded into Settings alongside branding/security forms
// like SecuritySettings is: this is a searchable list view (filters +
// pagination + a table), a genuinely different shape of page, the same
// reasoning Analytics already got its own entry despite the same "nav
// is getting deep" tension.
//
// org_owner/admin only (audit_log:read, migration f2a7c9d13e58) -- a
// manager/analyst/end_user visiting this page sees the real 403
// message from the API, the same pattern every other permission-gated
// page in this app already uses (no client-side role check duplicating
// what the backend already enforces).

import { useEffect, useState } from "react";
import Link from "next/link";
import { getAuditLogs, type AuditLogEntry } from "@/lib/auditLog";
import { useCurrentOrganization } from "@/lib/useCurrentOrganization";
import styles from "./page.module.css";

const PAGE_SIZE = 25;

interface FilterState {
  action: string;
  resourceType: string;
  since: string;
  until: string;
}

const EMPTY_FILTERS: FilterState = { action: "", resourceType: "", since: "", until: "" };

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString();
}

export default function AuditLogPage() {
  const { status, organization, error: orgError } = useCurrentOrganization();

  if (status === "loading") {
    return <p className={styles.status}>Loading…</p>;
  }

  if (status === "error") {
    return <p className={styles.error}>{orgError}</p>;
  }

  if (!organization) {
    return (
      <div className={styles.wrapper}>
        <h1 className={styles.heading}>Audit log</h1>
        <p className={styles.subtext}>
          You don&apos;t belong to an organization yet.{" "}
          <Link href="/dashboard/settings">Create one in Settings</Link> first.
        </p>
      </div>
    );
  }

  return <AuditLogView organizationId={organization.id} />;
}

function AuditLogView({ organizationId }: { organizationId: string }) {
  const [appliedFilters, setAppliedFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [draftFilters, setDraftFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<AuditLogEntry[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getAuditLogs(organizationId, {
      action: appliedFilters.action || undefined,
      resource_type: appliedFilters.resourceType || undefined,
      since: appliedFilters.since ? new Date(appliedFilters.since).toISOString() : undefined,
      until: appliedFilters.until ? new Date(appliedFilters.until).toISOString() : undefined,
      limit: PAGE_SIZE,
      offset,
    })
      .then((page) => {
        if (!cancelled) {
          setItems(page.items);
          setTotal(page.total);
          setError(null);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setError(err.message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [organizationId, appliedFilters, offset]);

  const rangeStart = total === 0 ? 0 : offset + 1;
  const rangeEnd = Math.min(offset + PAGE_SIZE, total);

  return (
    <div className={styles.wrapper}>
      <h1 className={styles.heading}>Audit log</h1>

      <form
        className={styles.filters}
        onSubmit={(e) => {
          e.preventDefault();
          setOffset(0);
          setAppliedFilters(draftFilters);
        }}
      >
        <label className={styles.field}>
          Action
          <input
            type="text"
            placeholder="e.g. workspace.create"
            value={draftFilters.action}
            onChange={(e) => setDraftFilters({ ...draftFilters, action: e.target.value })}
          />
        </label>
        <label className={styles.field}>
          Resource type
          <input
            type="text"
            placeholder="e.g. workspace"
            value={draftFilters.resourceType}
            onChange={(e) => setDraftFilters({ ...draftFilters, resourceType: e.target.value })}
          />
        </label>
        <label className={styles.field}>
          Since
          <input
            type="datetime-local"
            value={draftFilters.since}
            onChange={(e) => setDraftFilters({ ...draftFilters, since: e.target.value })}
          />
        </label>
        <label className={styles.field}>
          Until
          <input
            type="datetime-local"
            value={draftFilters.until}
            onChange={(e) => setDraftFilters({ ...draftFilters, until: e.target.value })}
          />
        </label>
        <button type="submit" className={styles.submit}>
          Apply filters
        </button>
        {(draftFilters.action ||
          draftFilters.resourceType ||
          draftFilters.since ||
          draftFilters.until) && (
          <button
            type="button"
            className={styles.clearButton}
            onClick={() => {
              setDraftFilters(EMPTY_FILTERS);
              setOffset(0);
              setAppliedFilters(EMPTY_FILTERS);
            }}
          >
            Clear
          </button>
        )}
      </form>

      {error && <p className={styles.error}>{error}</p>}

      {!error && !items && <p className={styles.status}>Loading…</p>}

      {!error && items && items.length === 0 && (
        <p className={styles.subtext}>No audit log entries match these filters.</p>
      )}

      {!error && items && items.length > 0 && (
        <>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Time</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Resource</th>
              </tr>
            </thead>
            <tbody>
              {items.map((entry) => (
                <tr key={entry.id}>
                  <td>{formatTimestamp(entry.created_at)}</td>
                  <td>{entry.actor_email ?? "—"}</td>
                  <td className={styles.actionCell}>{entry.action}</td>
                  <td>
                    {entry.resource_type}{" "}
                    <span className={styles.resourceId}>{entry.resource_id}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className={styles.pagination}>
            <span className={styles.subtext}>
              {rangeStart}–{rangeEnd} of {total}
            </span>
            <div className={styles.paginationButtons}>
              <button
                type="button"
                className={styles.pageButton}
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                Previous
              </button>
              <button
                type="button"
                className={styles.pageButton}
                disabled={rangeEnd >= total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
