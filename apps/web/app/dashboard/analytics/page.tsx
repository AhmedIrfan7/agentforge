"use client";

// Analytics dashboard. Conversation metrics (roadmap step 243) was
// this page's first section -- the first real UI consumer of
// analytics/agent.py:AnalyticsAgent.conversation_metrics (242).
// Knowledge health (244) and agent performance (245, this page's
// third section) are further independent sections on the SAME page
// rather than new nav entries each -- all are "analytics" concerns a
// user expects to find together, and the nav is already six entries
// deep. No charting library exists in this app yet (apps/widget's own
// "minimal deps" constraint applies equally here) -- the one real
// chart each section's data supports honestly is a plain CSS bar, not
// a fabricated multi-series graph the backend has no data for; agent
// performance instead lists per-agent rows, since its own real shape
// (one row per distinct agent_name) is a table, not a single bar.

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  getAgentPerformanceMetrics,
  getConversationMetrics,
  getKnowledgeMetrics,
  type AgentPerformanceMetrics,
  type ConversationMetrics,
  type KnowledgeMetrics,
} from "@/lib/analytics";
import { useCurrentOrganization } from "@/lib/useCurrentOrganization";
import styles from "./page.module.css";

export default function AnalyticsPage() {
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
        <h1 className={styles.heading}>Analytics</h1>
        <p className={styles.subtext}>
          You don&apos;t belong to an organization yet.{" "}
          <Link href="/dashboard/settings">Create one in Settings</Link> first.
        </p>
      </div>
    );
  }

  return (
    <div className={styles.wrapper}>
      <h1 className={styles.heading}>Analytics</h1>
      <ConversationSection organizationId={organization.id} />
      <KnowledgeHealthSection organizationId={organization.id} />
      <AgentPerformanceSection organizationId={organization.id} />
    </div>
  );
}

function ConversationSection({ organizationId }: { organizationId: string }) {
  const [metrics, setMetrics] = useState<ConversationMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getConversationMetrics(organizationId)
      .then((data) => {
        if (!cancelled) {
          setMetrics(data);
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
  }, [organizationId]);

  if (error) {
    return <p className={styles.error}>{error}</p>;
  }

  if (!metrics) {
    return <p className={styles.status}>Loading…</p>;
  }

  const recentShare =
    metrics.total_conversations > 0
      ? Math.round((metrics.conversations_last_7_days / metrics.total_conversations) * 100)
      : 0;

  return (
    <>
      <div className={styles.cards}>
        <div className={styles.card}>
          <div className={styles.cardValue}>{metrics.total_conversations}</div>
          <div className={styles.cardLabel}>Conversations</div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardValue}>{metrics.total_messages}</div>
          <div className={styles.cardLabel}>Messages</div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardValue}>
            {metrics.average_messages_per_conversation.toFixed(1)}
          </div>
          <div className={styles.cardLabel}>Avg messages / conversation</div>
        </div>
      </div>

      <div className={styles.chartCard}>
        <h2 className={styles.sectionHeading}>Conversations in the last 7 days</h2>
        <div className={styles.barTrack}>
          <div className={styles.barFill} style={{ width: `${recentShare}%` }} />
        </div>
        <p className={styles.chartCaption}>
          {metrics.conversations_last_7_days} of {metrics.total_conversations} conversations (
          {recentShare}%)
        </p>
      </div>
    </>
  );
}

function KnowledgeHealthSection({ organizationId }: { organizationId: string }) {
  const [metrics, setMetrics] = useState<KnowledgeMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getKnowledgeMetrics(organizationId)
      .then((data) => {
        if (!cancelled) {
          setMetrics(data);
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
  }, [organizationId]);

  if (error) {
    return <p className={styles.error}>{error}</p>;
  }

  if (!metrics) {
    return <p className={styles.status}>Loading…</p>;
  }

  return (
    <div className={styles.chartCard}>
      <h2 className={styles.sectionHeading}>Knowledge health</h2>
      {metrics.total_documents === 0 ? (
        <p className={styles.subtext}>No documents yet.</p>
      ) : (
        <ul className={styles.healthList}>
          <li className={styles.healthItem}>
            <span className={styles.healthLabel}>Duplicates</span>
            <span className={styles.healthValue}>
              {metrics.duplicate_document_count} / {metrics.total_documents}
            </span>
          </li>
          <li className={styles.healthItem}>
            <span className={styles.healthLabel}>Low-confidence chunking</span>
            <span className={styles.healthValue}>
              {metrics.low_confidence_document_count} / {metrics.total_documents}
            </span>
          </li>
          <li className={styles.healthItem}>
            <span className={styles.healthLabel}>Never cited</span>
            <span className={styles.healthValue}>
              {metrics.unused_document_count} / {metrics.total_documents}
            </span>
          </li>
        </ul>
      )}
    </div>
  );
}

function AgentPerformanceSection({ organizationId }: { organizationId: string }) {
  const [metrics, setMetrics] = useState<AgentPerformanceMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getAgentPerformanceMetrics(organizationId)
      .then((data) => {
        if (!cancelled) {
          setMetrics(data);
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
  }, [organizationId]);

  if (error) {
    return <p className={styles.error}>{error}</p>;
  }

  if (!metrics) {
    return <p className={styles.status}>Loading…</p>;
  }

  return (
    <div className={styles.chartCard}>
      <h2 className={styles.sectionHeading}>Agent performance</h2>
      {metrics.per_agent.length === 0 ? (
        <p className={styles.subtext}>No agent executions yet.</p>
      ) : (
        <table className={styles.perfTable}>
          <thead>
            <tr>
              <th>Agent</th>
              <th>Runs</th>
              <th>Success rate</th>
              <th>Avg latency</th>
            </tr>
          </thead>
          <tbody>
            {metrics.per_agent.map((entry) => (
              <tr key={entry.agent_name}>
                <td>{entry.agent_name}</td>
                <td>{entry.execution_count}</td>
                <td>{Math.round(entry.success_rate * 100)}%</td>
                <td>{entry.average_latency_ms.toFixed(0)}ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
