"use client";

// Knowledge-base list/create/delete within a workspace (part of
// roadmap step 236, "knowledge-base management UI"). No update
// endpoint exists in apps/api (create/read/delete only, mirroring
// Workspace's own scope), so no rename UI here either -- same
// reasoning workspaces/page.tsx already documents.

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  listKnowledgeBases,
  type KnowledgeBase,
} from "@/lib/knowledgeBases";
import { slugify } from "@/lib/slugify";
import { useCurrentOrganization } from "@/lib/useCurrentOrganization";
import styles from "./page.module.css";

export default function KnowledgeBasesPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const { status, organization, error } = useCurrentOrganization();

  if (status === "loading") {
    return <p className={styles.status}>Loading…</p>;
  }

  if (status === "error" || !organization) {
    return <p className={styles.error}>{error ?? "No organization found."}</p>;
  }

  return <KnowledgeBaseList organizationId={organization.id} workspaceId={workspaceId} />;
}

function KnowledgeBaseList({
  organizationId,
  workspaceId,
}: {
  organizationId: string;
  workspaceId: string;
}) {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Cancellation-guarded, matching the real fix workspaces/page.tsx's
  // own effect needed (found live via Playwright): without it,
  // Strict Mode's dev-only double-invoke can let a stale duplicate GET
  // resolve after a create/delete's own optimistic update and silently
  // overwrite it.
  useEffect(() => {
    let cancelled = false;
    listKnowledgeBases(organizationId, workspaceId)
      .then((items) => {
        if (!cancelled) {
          setKnowledgeBases(items);
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
  }, [organizationId, workspaceId]);

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreating(true);
    setCreateError(null);
    try {
      // Trusts the POST response directly rather than reloading the
      // list afterward -- the same real, live-confirmed fix
      // workspaces/page.tsx already applies for this backend's own
      // transient read-your-own-write timing.
      const created = await createKnowledgeBase(organizationId, workspaceId, name, slug);
      setKnowledgeBases((prev) => [...(prev ?? []), created]);
      setName("");
      setSlug("");
      setSlugEdited(false);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(knowledgeBase: KnowledgeBase) {
    if (
      !window.confirm(
        `Delete knowledge base "${knowledgeBase.name}"? This deletes every document in it and cannot be undone.`,
      )
    ) {
      return;
    }
    setDeletingId(knowledgeBase.id);
    try {
      await deleteKnowledgeBase(organizationId, workspaceId, knowledgeBase.id);
      setKnowledgeBases((prev) => (prev ?? []).filter((kb) => kb.id !== knowledgeBase.id));
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className={styles.wrapper}>
      <h1 className={styles.heading}>Knowledge bases</h1>

      <form className={styles.card} onSubmit={handleCreate}>
        <h2 className={styles.sectionHeading}>New knowledge base</h2>
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
          {creating ? "Creating…" : "Create knowledge base"}
        </button>
      </form>

      {listError && <p className={styles.error}>{listError}</p>}

      {knowledgeBases === null && !listError && <p className={styles.status}>Loading…</p>}

      {knowledgeBases !== null && knowledgeBases.length === 0 && (
        <p className={styles.subtext}>No knowledge bases yet.</p>
      )}

      {knowledgeBases !== null && knowledgeBases.length > 0 && (
        <ul className={styles.list}>
          {knowledgeBases.map((kb) => (
            <li key={kb.id} className={styles.listItem}>
              <div>
                <div className={styles.itemName}>{kb.name}</div>
                <div className={styles.itemSlug}>{kb.slug}</div>
              </div>
              <div className={styles.listItemActions}>
                <Link
                  href={`/dashboard/workspaces/${workspaceId}/knowledge-bases/${kb.id}`}
                  className={styles.manageLink}
                >
                  Documents
                </Link>
                <button
                  type="button"
                  className={styles.deleteButton}
                  onClick={() => handleDelete(kb)}
                  disabled={deletingId === kb.id}
                >
                  {deletingId === kb.id ? "Deleting…" : "Delete"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
