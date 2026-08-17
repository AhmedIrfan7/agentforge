"use client";

// Conversation-analytics dashboard (roadmap step 243) -- the first
// real UI consumer of analytics/agent.py:AnalyticsAgent.conversation_
// metrics (242). No charting library exists in this app yet (apps/
// widget's own "minimal deps" constraint applies equally here) --
// the one real chart this step's data supports honestly is a plain
// CSS bar showing what share of all-time conversations happened in
// the last 7 days, not a fabricated multi-series graph the backend
// doesn't actually have data for.

import { useEffect, useState } from "react";
import Link from "next/link";
import { getConversationMetrics, type ConversationMetrics } from "@/lib/analytics";
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

  return <ConversationAnalytics organizationId={organization.id} />;
}

function ConversationAnalytics({ organizationId }: { organizationId: string }) {
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
    return (
      <div className={styles.wrapper}>
        <h1 className={styles.heading}>Analytics</h1>
        <p className={styles.error}>{error}</p>
      </div>
    );
  }

  if (!metrics) {
    return (
      <div className={styles.wrapper}>
        <h1 className={styles.heading}>Analytics</h1>
        <p className={styles.status}>Loading…</p>
      </div>
    );
  }

  const recentShare =
    metrics.total_conversations > 0
      ? Math.round((metrics.conversations_last_7_days / metrics.total_conversations) * 100)
      : 0;

  return (
    <div className={styles.wrapper}>
      <h1 className={styles.heading}>Analytics</h1>

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
    </div>
  );
}
