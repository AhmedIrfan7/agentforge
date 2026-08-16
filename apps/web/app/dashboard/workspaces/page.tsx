"use client";

// Workspace-management UI (roadmap step 235): list/create/delete
// workspaces within the caller's organization. No workspace:update
// permission or PATCH endpoint exists in apps/api (only create/read/
// delete were ever seeded, step 072) -- unlike organization branding
// (234), there is no real backend rename capability to give this page
// a UI for, so this stays honestly scoped to what the API actually
// supports rather than building a form for an endpoint that doesn't
// exist.
//
// Organization resolution is shared with settings/page.tsx via
// lib/useCurrentOrganization.ts -- if there isn't one yet, this page
// points the caller at Settings (the one real place org creation
// lives) rather than duplicating that form here too.

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { slugify } from "@/lib/slugify";
import { useCurrentOrganization } from "@/lib/useCurrentOrganization";
import { createWorkspace, deleteWorkspace, listWorkspaces, type Workspace } from "@/lib/workspaces";
import styles from "./page.module.css";

export default function WorkspacesPage() {
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
        <h1 className={styles.heading}>Workspaces</h1>
        <p className={styles.subtext}>
          You don&apos;t belong to an organization yet.{" "}
          <Link href="/dashboard/settings">Create one in Settings</Link> first.
        </p>
      </div>
    );
  }

  return <WorkspaceList organizationId={organization.id} />;
}

function WorkspaceList({ organizationId }: { organizationId: string }) {
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const reload = useCallback(() => {
    listWorkspaces(organizationId)
      .then(setWorkspaces)
      .catch((err: Error) => setListError(err.message));
  }, [organizationId]);

  useEffect(() => {
    reload();
  }, [reload]);

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreating(true);
    setCreateError(null);
    try {
      // Applies the real created row straight from the POST response
      // rather than re-fetching the list -- a moment-later GET can
      // transiently miss a just-written row under this backend's real
      // pooled connections (confirmed live: the identical class of
      // read-your-own-write race step 234 already found for a freshly
      // created organization's security settings), so trusting the
      // mutation's own response is both simpler and genuinely more
      // correct here, not just an optimization.
      const created = await createWorkspace(organizationId, name, slug);
      setWorkspaces((prev) => [...(prev ?? []), created]);
      setName("");
      setSlug("");
      setSlugEdited(false);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(workspace: Workspace) {
    if (!window.confirm(`Delete workspace "${workspace.name}"? This cannot be undone.`)) {
      return;
    }
    setDeletingId(workspace.id);
    try {
      // Same reasoning as handleCreate above -- confirmed live that an
      // immediate reload() here can transiently show the just-deleted
      // workspace again (server genuinely still had zero rows on direct
      // query moments later). A 204 is itself authoritative proof of
      // deletion; removing it from local state directly needs no
      // re-fetch and can't be racy against it.
      await deleteWorkspace(organizationId, workspace.id);
      setWorkspaces((prev) => (prev ?? []).filter((w) => w.id !== workspace.id));
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className={styles.wrapper}>
      <h1 className={styles.heading}>Workspaces</h1>

      <form className={styles.card} onSubmit={handleCreate}>
        <h2 className={styles.sectionHeading}>New workspace</h2>
        <label className={styles.field}>
          <span>Name</span>
          <input
            value={name}
            onChange={(event) => {
              const value = event.target.value;
              setName(value);
              if (!slugEdited) {
                setSlug(slugify(value));
              }
            }}
            required
          />
        </label>
        <label className={styles.field}>
          <span>Slug</span>
          <input
            value={slug}
            onChange={(event) => {
              setSlugEdited(true);
              setSlug(event.target.value);
            }}
            pattern="[a-z0-9]+(-[a-z0-9]+)*"
            required
          />
        </label>
        {createError && <p className={styles.error}>{createError}</p>}
        <button type="submit" className={styles.submit} disabled={creating}>
          {creating ? "Creating…" : "Create workspace"}
        </button>
      </form>

      {listError && <p className={styles.error}>{listError}</p>}

      {workspaces === null && !listError && <p className={styles.status}>Loading…</p>}

      {workspaces !== null && workspaces.length === 0 && (
        <p className={styles.subtext}>No workspaces yet.</p>
      )}

      {workspaces !== null && workspaces.length > 0 && (
        <ul className={styles.list}>
          {workspaces.map((workspace) => (
            <li key={workspace.id} className={styles.listItem}>
              <div>
                <div className={styles.workspaceName}>{workspace.name}</div>
                <div className={styles.workspaceSlug}>{workspace.slug}</div>
              </div>
              <button
                type="button"
                className={styles.deleteButton}
                onClick={() => handleDelete(workspace)}
                disabled={deletingId === workspace.id}
              >
                {deletingId === workspace.id ? "Deleting…" : "Delete"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
