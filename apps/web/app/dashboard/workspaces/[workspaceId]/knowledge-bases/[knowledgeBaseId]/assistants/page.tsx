"use client";

// Assistant list/create/delete within a knowledge base (part of
// roadmap step 238, "assistant-builder UI"). Create here is
// deliberately minimal (name + slug, matching every other create form
// in this dashboard) -- instructions/knowledge access/agent config are
// the builder page's own job (.../assistants/[assistantId]), reached
// immediately after creation, not crammed into this form too.

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { createAssistant, deleteAssistant, listAssistants, type Assistant } from "@/lib/assistants";
import { slugify } from "@/lib/slugify";
import { useCurrentOrganization } from "@/lib/useCurrentOrganization";
import styles from "./page.module.css";

export default function AssistantsPage() {
  const { workspaceId, knowledgeBaseId } = useParams<{
    workspaceId: string;
    knowledgeBaseId: string;
  }>();
  const { status, organization, error } = useCurrentOrganization();

  if (status === "loading") {
    return <p className={styles.status}>Loading…</p>;
  }

  if (status === "error" || !organization) {
    return <p className={styles.error}>{error ?? "No organization found."}</p>;
  }

  return (
    <AssistantList
      organizationId={organization.id}
      workspaceId={workspaceId}
      knowledgeBaseId={knowledgeBaseId}
    />
  );
}

function AssistantList({
  organizationId,
  workspaceId,
  knowledgeBaseId,
}: {
  organizationId: string;
  workspaceId: string;
  knowledgeBaseId: string;
}) {
  const [assistants, setAssistants] = useState<Assistant[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Cancellation-guarded mount effect -- the real fix workspaces/
  // page.tsx's own effect needed at step 236 (Strict Mode's dev-only
  // double-invoke can let a stale duplicate GET resolve after a
  // create/delete's own optimistic update and silently overwrite it).
  useEffect(() => {
    let cancelled = false;
    listAssistants(organizationId, workspaceId, knowledgeBaseId)
      .then((items) => {
        if (!cancelled) {
          setAssistants(items);
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
  }, [organizationId, workspaceId, knowledgeBaseId]);

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreating(true);
    setCreateError(null);
    try {
      // Trusts the POST response directly rather than reloading the
      // list -- the same real, live-confirmed fix already applied to
      // every other create/delete flow in this dashboard.
      const created = await createAssistant(
        organizationId,
        workspaceId,
        knowledgeBaseId,
        name,
        slug,
      );
      setAssistants((prev) => [...(prev ?? []), created]);
      setName("");
      setSlug("");
      setSlugEdited(false);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(assistant: Assistant) {
    if (!window.confirm(`Delete assistant "${assistant.name}"? This cannot be undone.`)) {
      return;
    }
    setDeletingId(assistant.id);
    try {
      await deleteAssistant(organizationId, workspaceId, knowledgeBaseId, assistant.id);
      setAssistants((prev) => (prev ?? []).filter((a) => a.id !== assistant.id));
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className={styles.wrapper}>
      <h1 className={styles.heading}>Assistants</h1>

      <form className={styles.card} onSubmit={handleCreate}>
        <h2 className={styles.sectionHeading}>New assistant</h2>
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
          {creating ? "Creating…" : "Create assistant"}
        </button>
      </form>

      {listError && <p className={styles.error}>{listError}</p>}

      {assistants === null && !listError && <p className={styles.status}>Loading…</p>}

      {assistants !== null && assistants.length === 0 && (
        <p className={styles.subtext}>No assistants yet.</p>
      )}

      {assistants !== null && assistants.length > 0 && (
        <ul className={styles.list}>
          {assistants.map((assistant) => (
            <li key={assistant.id} className={styles.listItem}>
              <Link
                href={`/dashboard/workspaces/${workspaceId}/knowledge-bases/${knowledgeBaseId}/assistants/${assistant.id}`}
                className={styles.itemLink}
              >
                <div className={styles.itemName}>{assistant.name}</div>
                <div className={styles.itemSlug}>
                  {assistant.slug}
                  {assistant.is_public ? " · public" : ""}
                </div>
              </Link>
              <button
                type="button"
                className={styles.deleteButton}
                onClick={() => handleDelete(assistant)}
                disabled={deletingId === assistant.id}
              >
                {deletingId === assistant.id ? "Deleting…" : "Delete"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
