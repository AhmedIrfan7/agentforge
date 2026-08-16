"use client";

// User/role-management UI (roadmap step 239): list an organization's
// members and manage their role or remove them. Adding a NEW member
// happens through the invitation flow (step 073's own real endpoint,
// this dashboard's own UI for it is step 240, still ahead) -- this
// page is honestly scoped to managing people already IN the org, not
// a second way to add them.
//
// Backend gap this step needed first: no membership-listing/role-
// update/removal endpoint existed anywhere (routers/membership.py,
// new). Two real backend business rules this page has to respect,
// not just RBAC: only an org_owner can touch another org_owner's
// membership, and the last remaining org_owner can't be demoted or
// removed -- both surfaced here as plain error messages from the API
// rather than re-implemented client-side, so the backend stays the
// single source of truth for them.

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/AuthContext";
import {
  listMembers,
  removeMember,
  updateMemberRole,
  ROLE_NAMES,
  type Member,
} from "@/lib/members";
import { useCurrentOrganization } from "@/lib/useCurrentOrganization";
import styles from "./page.module.css";

export default function MembersPage() {
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
        <h1 className={styles.heading}>Members</h1>
        <p className={styles.subtext}>
          You don&apos;t belong to an organization yet.{" "}
          <Link href="/dashboard/settings">Create one in Settings</Link> first.
        </p>
      </div>
    );
  }

  return <MemberList organizationId={organization.id} />;
}

function MemberList({ organizationId }: { organizationId: string }) {
  const { user } = useAuth();
  const [members, setMembers] = useState<Member[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);

  // Cancellation-guarded mount effect -- same Strict Mode double-invoke
  // fix every other list page in this dashboard already needed (step
  // 236's own real, live-reproduced finding).
  useEffect(() => {
    let cancelled = false;
    listMembers(organizationId)
      .then((items) => {
        if (!cancelled) {
          setMembers(items);
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

  async function handleRoleChange(member: Member, roleName: string) {
    setBusyId(member.id);
    setRowErrors((prev) => ({ ...prev, [member.id]: "" }));
    try {
      // Trusts the PATCH response directly rather than re-fetching the
      // list -- the same read-your-own-write race this codebase has
      // already found and fixed for every other mutate-then-list flow.
      const updated = await updateMemberRole(organizationId, member.id, roleName);
      setMembers((prev) => (prev ?? []).map((m) => (m.id === member.id ? updated : m)));
    } catch (err) {
      setRowErrors((prev) => ({
        ...prev,
        [member.id]: err instanceof Error ? err.message : "Something went wrong.",
      }));
    } finally {
      setBusyId(null);
    }
  }

  async function handleRemove(member: Member) {
    if (!window.confirm(`Remove ${member.email} from this organization?`)) {
      return;
    }
    setBusyId(member.id);
    setRowErrors((prev) => ({ ...prev, [member.id]: "" }));
    try {
      await removeMember(organizationId, member.id);
      setMembers((prev) => (prev ?? []).filter((m) => m.id !== member.id));
    } catch (err) {
      setRowErrors((prev) => ({
        ...prev,
        [member.id]: err instanceof Error ? err.message : "Something went wrong.",
      }));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className={styles.wrapper}>
      <h1 className={styles.heading}>Members</h1>

      {listError && <p className={styles.error}>{listError}</p>}

      {members === null && !listError && <p className={styles.status}>Loading…</p>}

      {/* No empty state -- organization creation always seeds the
          owner's own membership, so this list can never actually be
          empty for an org that exists. */}
      {members !== null && members.length > 0 && (
        <ul className={styles.list}>
          {members.map((member) => {
            const isSelf = member.user_id === user?.id;
            const busy = busyId === member.id;
            return (
              <li key={member.id} className={styles.listItem}>
                <div className={styles.memberInfo}>
                  <div className={styles.memberName}>
                    {member.full_name}
                    {isSelf ? " (you)" : ""}
                  </div>
                  <div className={styles.memberEmail}>{member.email}</div>
                  {rowErrors[member.id] && <p className={styles.error}>{rowErrors[member.id]}</p>}
                </div>
                <div className={styles.listItemActions}>
                  <select
                    className={styles.roleSelect}
                    value={member.role_name}
                    disabled={isSelf || busy}
                    onChange={(event) => handleRoleChange(member, event.target.value)}
                    aria-label={`Role for ${member.email}`}
                  >
                    {ROLE_NAMES.map((roleName) => (
                      <option key={roleName} value={roleName}>
                        {roleName}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className={styles.deleteButton}
                    onClick={() => handleRemove(member)}
                    disabled={isSelf || busy}
                  >
                    {busy ? "…" : "Remove"}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
