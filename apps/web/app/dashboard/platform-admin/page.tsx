"use client";

// Platform-admin dashboard (roadmap step 249) -- cross-org super-admin
// views, the first real consumer of GET /platform-admin/organizations
// (routers/platform_admin.py). Not org-scoped, same as system-health --
// no useCurrentOrganization() call, since this describes every
// organization at once, not the caller's own one.
//
// KPI cards are computed client-side by summing each real per-org row
// -- routers/platform_admin.py's own docstring already explains why:
// one real per-org query already carries everything both "view
// organizations" (the table) and "review aggregate metrics" (these
// cards) need, so summing here avoids a second backend endpoint that
// would just repeat the identical per-org RLS loop.
//
// The nav link is visible to every authenticated user, same pattern
// Audit log/System health already established -- the backend enforces
// is_platform_admin, and UserRead doesn't expose that flag to the
// client, so hiding the link would need new plumbing just to duplicate
// a check the backend already makes.

import { useEffect, useState } from "react";
import { getPlatformOrganizations, type OrganizationSummary } from "@/lib/platformAdmin";
import styles from "./page.module.css";

export default function PlatformAdminPage() {
  const [organizations, setOrganizations] = useState<OrganizationSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getPlatformOrganizations()
      .then((data) => {
        if (!cancelled) {
          setOrganizations(data.organizations);
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
  }, []);

  if (error) {
    return (
      <div className={styles.wrapper}>
        <h1 className={styles.heading}>Platform admin</h1>
        <p className={styles.error}>{error}</p>
      </div>
    );
  }

  if (!organizations) {
    return (
      <div className={styles.wrapper}>
        <h1 className={styles.heading}>Platform admin</h1>
        <p className={styles.status}>Loading…</p>
      </div>
    );
  }

  const totals = organizations.reduce(
    (acc, org) => ({
      workspaces: acc.workspaces + org.workspace_count,
      members: acc.members + org.member_count,
      conversations: acc.conversations + org.conversation_count,
      documents: acc.documents + org.document_count,
    }),
    { workspaces: 0, members: 0, conversations: 0, documents: 0 },
  );

  return (
    <div className={styles.wrapper}>
      <h1 className={styles.heading}>Platform admin</h1>

      <div className={styles.cards}>
        <div className={styles.card}>
          <div className={styles.cardValue}>{organizations.length}</div>
          <div className={styles.cardLabel}>Organizations</div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardValue}>{totals.workspaces}</div>
          <div className={styles.cardLabel}>Workspaces</div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardValue}>{totals.members}</div>
          <div className={styles.cardLabel}>Members</div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardValue}>{totals.conversations}</div>
          <div className={styles.cardLabel}>Conversations</div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardValue}>{totals.documents}</div>
          <div className={styles.cardLabel}>Documents</div>
        </div>
      </div>

      <div className={styles.chartCard}>
        <h2 className={styles.sectionHeading}>Organizations</h2>
        {organizations.length === 0 ? (
          <p className={styles.subtext}>No organizations yet.</p>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Name</th>
                <th>Slug</th>
                <th>Workspaces</th>
                <th>Members</th>
                <th>Conversations</th>
                <th>Documents</th>
              </tr>
            </thead>
            <tbody>
              {organizations.map((org) => (
                <tr key={org.id}>
                  <td>{org.name}</td>
                  <td className={styles.slugCell}>{org.slug}</td>
                  <td>{org.workspace_count}</td>
                  <td>{org.member_count}</td>
                  <td>{org.conversation_count}</td>
                  <td>{org.document_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
