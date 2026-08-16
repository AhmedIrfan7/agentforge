"use client";

// Document upload/list/status (roadmap step 236, the other half of
// "knowledge-base management UI"). Deliberately covers only upload,
// list, and status -- not chunking-strategy override, reindex, or
// version history, which are real apps/api capabilities (steps
// 103/114/115) with no roadmap step through 250 asking for a UI yet.

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { getDocumentStatus, listDocuments, uploadDocument, type Document } from "@/lib/documents";
import { useCurrentOrganization } from "@/lib/useCurrentOrganization";
import styles from "./page.module.css";

// The real, exhaustive set of terminal statuses the ingestion pipeline
// ever sets (extraction.py/embeddings_pipeline.py) -- "pending",
// "processing", "extracted" (transient, auto-chains into embedding),
// and "embedding" are all still-in-progress and worth polling. Only
// "embedded" is a real success; the other three are real failures
// (or an honest "this file type has no extraction handler" outcome)
// and must not be styled the same as success.
const FAILURE_STATUSES = new Set([
  "extraction_unsupported",
  "extraction_failed",
  "embedding_failed",
]);
const SUCCESS_STATUSES = new Set(["embedded"]);
const TERMINAL_STATUSES = new Set([...FAILURE_STATUSES, ...SUCCESS_STATUSES]);

function statusBadgeClass(documentStatus: string): string {
  if (SUCCESS_STATUSES.has(documentStatus)) {
    return styles.statusSuccess;
  }
  if (FAILURE_STATUSES.has(documentStatus)) {
    return styles.statusFailure;
  }
  return styles.statusInProgress;
}

const POLL_INTERVAL_MS = 2000;

export default function DocumentsPage() {
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
    <DocumentList
      organizationId={organization.id}
      workspaceId={workspaceId}
      knowledgeBaseId={knowledgeBaseId}
    />
  );
}

function DocumentList({
  organizationId,
  workspaceId,
  knowledgeBaseId,
}: {
  organizationId: string;
  workspaceId: string;
  knowledgeBaseId: string;
}) {
  const [documents, setDocuments] = useState<Document[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Cancellation-guarded, matching the real fix workspaces/page.tsx's
  // own mount effect needed (found live via Playwright): without it,
  // Strict Mode's dev-only double-invoke can let a stale duplicate GET
  // resolve after an upload's own optimistic update and silently
  // overwrite it.
  useEffect(() => {
    let cancelled = false;
    listDocuments(organizationId, workspaceId, knowledgeBaseId)
      .then((items) => {
        if (!cancelled) {
          setDocuments(items);
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

  // Polls each still-in-progress document's own status endpoint
  // (step 088) rather than re-listing every document -- a cheap,
  // targeted poll per real in-flight row, matching that endpoint's own
  // documented reason for being smaller than the full document read.
  useEffect(() => {
    const inProgress = (documents ?? []).filter((doc) => !TERMINAL_STATUSES.has(doc.status));
    if (inProgress.length === 0) {
      return;
    }
    const timer = setTimeout(() => {
      Promise.all(
        inProgress.map((doc) =>
          getDocumentStatus(organizationId, workspaceId, knowledgeBaseId, doc.id),
        ),
      ).then((updates) => {
        setDocuments((prev) =>
          (prev ?? []).map((doc) => {
            const update = updates.find((u) => u.id === doc.id);
            return update ? { ...doc, status: update.status, updated_at: update.updated_at } : doc;
          }),
        );
      });
    }, POLL_INTERVAL_MS);
    return () => clearTimeout(timer);
  }, [documents, organizationId, workspaceId, knowledgeBaseId]);

  async function handleUpload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const file = fileInputRef.current?.files?.[0];
    if (!file) {
      return;
    }
    setUploading(true);
    setUploadError(null);
    try {
      const uploaded = await uploadDocument(organizationId, workspaceId, knowledgeBaseId, file);
      setDocuments((prev) => [...(prev ?? []), uploaded]);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className={styles.wrapper}>
      <h1 className={styles.heading}>Documents</h1>
      <Link
        href={`/dashboard/workspaces/${workspaceId}/knowledge-bases/${knowledgeBaseId}/assistants`}
        className={styles.manageLink}
      >
        Manage assistants
      </Link>

      <form className={styles.card} onSubmit={handleUpload}>
        <h2 className={styles.sectionHeading}>Upload a document</h2>
        <input ref={fileInputRef} type="file" required />
        {uploadError && <p className={styles.error}>{uploadError}</p>}
        <button type="submit" className={styles.submit} disabled={uploading}>
          {uploading ? "Uploading…" : "Upload"}
        </button>
      </form>

      {listError && <p className={styles.error}>{listError}</p>}

      {documents === null && !listError && <p className={styles.status}>Loading…</p>}

      {documents !== null && documents.length === 0 && (
        <p className={styles.subtext}>No documents yet.</p>
      )}

      {documents !== null && documents.length > 0 && (
        <ul className={styles.list}>
          {documents.map((doc) => (
            <li key={doc.id} className={styles.listItem}>
              <Link
                href={`/dashboard/workspaces/${workspaceId}/knowledge-bases/${knowledgeBaseId}/${doc.id}`}
                className={styles.itemLink}
              >
                <div className={styles.itemName}>{doc.title}</div>
                <div className={styles.itemSlug}>
                  {(doc.size_bytes / 1024).toFixed(1)} KB · {doc.content_type}
                </div>
              </Link>
              <span className={`${styles.statusBadge} ${statusBadgeClass(doc.status)}`}>
                {doc.status}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
