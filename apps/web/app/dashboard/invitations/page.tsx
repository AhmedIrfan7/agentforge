"use client";

// Invitation-management UI (roadmap step 240): invite someone by
// email/role, see pending/accepted/revoked/expired status, revoke a
// pending one. The backend endpoints (create/list/revoke) already
// existed (steps 073/075) -- this is that capability's first UI.
// Org-level only (no workspace_id in the create form), same scope
// Members (239) already settled on for the identical reason.

import { useEffect, useState } from "react";
import Link from "next/link";
import { ROLE_NAMES } from "@/lib/members";
import {
  createInvitation,
  listInvitations,
  revokeInvitation,
  type Invitation,
} from "@/lib/invitations";
import { useCurrentOrganization } from "@/lib/useCurrentOrganization";
import styles from "./page.module.css";

export default function InvitationsPage() {
  const { status, organization, error } = useCurrentOrganization();

  if (status === "loading") {
    return <p className={styles.status}>Loading…</p>;
  }

  if (status === "error") {
    return <p className={styles.error}>{error}</p>;
  }

  if (!organization) {
    return (
      <div className={styles.wrapper}>
        <h1 className={styles.heading}>Invitations</h1>
        <p className={styles.subtext}>
          You don&apos;t belong to an organization yet.{" "}
          <Link href="/dashboard/settings">Create one in Settings</Link> first.
        </p>
      </div>
    );
  }

  return <InvitationList organizationId={organization.id} />;
}

const STATUS_LABELS: Record<Invitation["status"], string> = {
  pending: "Pending",
  accepted: "Accepted",
  revoked: "Revoked",
  expired: "Expired",
};

function InvitationList({ organizationId }: { organizationId: string }) {
  const [invitations, setInvitations] = useState<Invitation[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [roleName, setRoleName] = useState<string>("viewer");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  // Cancellation-guarded mount effect -- same Strict Mode double-invoke
  // fix every other list page in this dashboard already needed.
  useEffect(() => {
    let cancelled = false;
    listInvitations(organizationId)
      .then((items) => {
        if (!cancelled) {
          setInvitations(items);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setListError(err.message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [organizationId]);

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreating(true);
    setCreateError(null);
    try {
      // Trusts the POST response directly rather than reloading the
      // list -- the same real, live-confirmed fix every other create
      // flow in this dashboard already applies.
      const created = await createInvitation(organizationId, email, roleName);
      setInvitations((prev) => [created, ...(prev ?? [])]);
      setEmail("");
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setCreating(false);
    }
  }

  async function handleRevoke(invitation: Invitation) {
    setRevokingId(invitation.id);
    try {
      await revokeInvitation(organizationId, invitation.id);
      // status, not just revoked_at -- the list renders STATUS_LABELS
      // keyed off status, which the backend derives server-side and
      // never gets recomputed client-side from a raw timestamp.
      setInvitations((prev) =>
        (prev ?? []).map((i) =>
          i.id === invitation.id
            ? { ...i, status: "revoked" as const, revoked_at: new Date().toISOString() }
            : i,
        ),
      );
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setRevokingId(null);
    }
  }

  return (
    <div className={styles.wrapper}>
      <h1 className={styles.heading}>Invitations</h1>

      <form className={styles.card} onSubmit={handleCreate}>
        <h2 className={styles.sectionHeading}>Invite someone</h2>
        <label className={styles.field}>
          <span>Email</span>
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </label>
        <label className={styles.field}>
          <span>Role</span>
          <select value={roleName} onChange={(event) => setRoleName(event.target.value)}>
            {ROLE_NAMES.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        {createError && <p className={styles.error}>{createError}</p>}
        <button type="submit" className={styles.submit} disabled={creating}>
          {creating ? "Sending…" : "Send invitation"}
        </button>
      </form>

      {listError && <p className={styles.error}>{listError}</p>}

      {invitations === null && !listError && <p className={styles.status}>Loading…</p>}

      {invitations !== null && invitations.length === 0 && (
        <p className={styles.subtext}>No invitations yet.</p>
      )}

      {invitations !== null && invitations.length > 0 && (
        <ul className={styles.list}>
          {invitations.map((invitation) => (
            <li key={invitation.id} className={styles.listItem}>
              <div className={styles.invitationInfo}>
                <div className={styles.invitationEmail}>{invitation.email}</div>
                <div className={styles.invitationMeta}>
                  {invitation.role_name} · {STATUS_LABELS[invitation.status]}
                </div>
              </div>
              {invitation.status === "pending" && (
                <button
                  type="button"
                  className={styles.revokeButton}
                  onClick={() => handleRevoke(invitation)}
                  disabled={revokingId === invitation.id}
                >
                  {revokingId === invitation.id ? "Revoking…" : "Revoke"}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
