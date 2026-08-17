"use client";

// System-health dashboard (roadmap step 248) -- queue depth, worker
// status, provider status, the first real consumer of GET
// /system-health (routers/system_health.py). Not org-scoped, unlike
// every other dashboard page in this app -- this describes shared
// infrastructure, not any one organization's own data, so there's no
// useCurrentOrganization() call here at all.
//
// The nav link is visible to every authenticated user, the same
// "no client-side role check duplicating what the backend already
// enforces" pattern the audit-log page already established -- a
// non-platform-admin visiting this page sees the real 403 message
// from the API, not a hidden or dead link.

import { useEffect, useState } from "react";
import { getSystemHealth, type SystemHealth } from "@/lib/systemHealth";
import styles from "./page.module.css";

export default function SystemHealthPage() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSystemHealth()
      .then((data) => {
        if (!cancelled) {
          setHealth(data);
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
        <h1 className={styles.heading}>System health</h1>
        <p className={styles.error}>{error}</p>
      </div>
    );
  }

  if (!health) {
    return (
      <div className={styles.wrapper}>
        <h1 className={styles.heading}>System health</h1>
        <p className={styles.status}>Loading…</p>
      </div>
    );
  }

  return (
    <div className={styles.wrapper}>
      <h1 className={styles.heading}>System health</h1>

      <div className={styles.cards}>
        <div className={styles.card}>
          <div className={styles.cardValue}>{health.queue_depth}</div>
          <div className={styles.cardLabel}>Queue depth</div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardValue}>{health.worker_count}</div>
          <div className={styles.cardLabel}>Workers online</div>
        </div>
      </div>

      <div className={styles.chartCard}>
        <h2 className={styles.sectionHeading}>Workers</h2>
        {health.workers.length === 0 ? (
          <p className={styles.subtext}>No workers responding.</p>
        ) : (
          <ul className={styles.workerList}>
            {health.workers.map((name) => (
              <li key={name} className={styles.workerItem}>
                <span className={styles.statusDot} data-status="online" />
                {name}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className={styles.chartCard}>
        <h2 className={styles.sectionHeading}>Providers</h2>
        <ul className={styles.workerList}>
          {health.providers.map((provider) => (
            <li key={provider.name} className={styles.workerItem}>
              <span
                className={styles.statusDot}
                data-status={provider.configured ? "online" : "offline"}
              />
              {provider.name}
              <span className={styles.providerState}>
                {provider.configured ? "Configured" : "Not configured"}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
