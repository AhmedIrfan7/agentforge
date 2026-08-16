"use client";

// Document detail view (roadmap step 237): chunking decision + quality
// warnings. Read-only -- chunking-strategy OVERRIDE (step 103) and
// reindex (114) are real apps/api capabilities, but no roadmap step
// through 250 asks for a UI to change either, so this page only shows
// the current decision, not a form to change it.
//
// "Quality warnings" has no dedicated backend field anywhere in this
// codebase -- deliberately not inventing one. AGENTS.md never names
// this term either. The honest, correct scope: derive real warnings
// client-side from data pipeline_status.py (step 111) already computes
// honestly per-document (a failed/skipped stage) -- step 244's own
// future "knowledge-health dashboard (duplicates, low-confidence,
// unused docs)" is the real, separate, KB-wide/cross-document concept;
// this stays scoped to what this ONE document's own real pipeline
// state already proves.

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  getDocument,
  getDocumentPipelineStatus,
  type Document,
  type DocumentPipelineStatus,
} from "@/lib/documents";
import { useCurrentOrganization } from "@/lib/useCurrentOrganization";
import styles from "./page.module.css";

const STAGE_LABELS: Record<string, string> = {
  extraction: "Extraction",
  chunk_generation: "Chunk generation",
  embedding_generation: "Embedding generation",
};

function deriveWarnings(pipeline: DocumentPipelineStatus): string[] {
  // Deliberately just failed/skipped stages -- a separate "extraction
  // completed but zero chunks exist" check was considered and dropped:
  // per pipeline_status.py's own real state machine, chunk_generation
  // can only ever report "completed" when chunk_count > 0, so that
  // condition either duplicates a failed-stage warning already covered
  // here, or (for a document still legitimately mid-pipeline, status
  // "extracted" with chunk_generation "pending") would misleadingly
  // warn about normal in-progress state as if something were wrong.
  const warnings: string[] = [];
  for (const stage of pipeline.stages) {
    const label = STAGE_LABELS[stage.stage] ?? stage.stage;
    if (stage.status === "failed") {
      warnings.push(`${label} failed.`);
    } else if (stage.status === "skipped") {
      warnings.push(`${label} was skipped -- this file type has no extraction handler.`);
    }
  }
  return warnings;
}

export default function DocumentDetailPage() {
  const { workspaceId, knowledgeBaseId, documentId } = useParams<{
    workspaceId: string;
    knowledgeBaseId: string;
    documentId: string;
  }>();
  const { status, organization, error } = useCurrentOrganization();

  if (status === "loading") {
    return <p className={styles.status}>Loading…</p>;
  }

  if (status === "error" || !organization) {
    return <p className={styles.error}>{error ?? "No organization found."}</p>;
  }

  return (
    <DocumentDetail
      organizationId={organization.id}
      workspaceId={workspaceId}
      knowledgeBaseId={knowledgeBaseId}
      documentId={documentId}
    />
  );
}

function DocumentDetail({
  organizationId,
  workspaceId,
  knowledgeBaseId,
  documentId,
}: {
  organizationId: string;
  workspaceId: string;
  knowledgeBaseId: string;
  documentId: string;
}) {
  const [document, setDocument] = useState<Document | null>(null);
  const [pipeline, setPipeline] = useState<DocumentPipelineStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      getDocument(organizationId, workspaceId, knowledgeBaseId, documentId),
      getDocumentPipelineStatus(organizationId, workspaceId, knowledgeBaseId, documentId),
    ])
      .then(([doc, pipelineStatus]) => {
        if (!cancelled) {
          setDocument(doc);
          setPipeline(pipelineStatus);
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
  }, [organizationId, workspaceId, knowledgeBaseId, documentId]);

  if (error) {
    return <p className={styles.error}>{error}</p>;
  }

  if (!document || !pipeline) {
    return <p className={styles.status}>Loading…</p>;
  }

  const warnings = deriveWarnings(pipeline);

  return (
    <div className={styles.wrapper}>
      <h1 className={styles.heading}>{document.title}</h1>
      <p className={styles.subtext}>
        {(document.size_bytes / 1024).toFixed(1)} KB · {document.content_type} · {document.status}
      </p>

      {warnings.length > 0 && (
        <div className={styles.warningsCard}>
          <h2 className={styles.sectionHeading}>Quality warnings</h2>
          <ul className={styles.warningsList}>
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      <div className={styles.card}>
        <h2 className={styles.sectionHeading}>Chunking decision</h2>
        {document.chunking_strategy ? (
          <dl className={styles.definitionList}>
            <dt>Strategy</dt>
            <dd>{document.chunking_strategy}</dd>
            <dt>Source</dt>
            <dd>{document.chunking_strategy_source}</dd>
            {document.chunking_strategy_reasoning && (
              <>
                <dt>Reasoning</dt>
                <dd>{document.chunking_strategy_reasoning}</dd>
              </>
            )}
          </dl>
        ) : (
          <p className={styles.subtext}>
            No chunking strategy has been decided yet -- this document hasn&apos;t finished
            extraction.
          </p>
        )}
      </div>

      <div className={styles.card}>
        <h2 className={styles.sectionHeading}>Pipeline stages</h2>
        <ul className={styles.stageList}>
          {pipeline.stages.map((stage) => (
            <li key={stage.stage} className={styles.stageItem}>
              <span>{STAGE_LABELS[stage.stage] ?? stage.stage}</span>
              <span className={styles.stageStatus}>{stage.status}</span>
            </li>
          ))}
        </ul>
        <p className={styles.subtext}>
          {pipeline.chunk_count} chunk{pipeline.chunk_count === 1 ? "" : "s"},{" "}
          {pipeline.embedded_chunk_count} embedded
        </p>
      </div>
    </div>
  );
}
