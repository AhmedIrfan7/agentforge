"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { acceptInvitation } from "@/lib/invitations";
import { useAuth } from "@/lib/AuthContext";
import styles from "./page.module.css";

type AcceptState = "accepting" | "accepted" | "error";

export function AcceptInvitationClient({ token }: { token: string }) {
  const { status } = useAuth();
  const [acceptState, setAcceptState] = useState<AcceptState>("accepting");
  const [error, setError] = useState<string | null>(null);

  // Only fires once real authentication is confirmed -- an invitation
  // is accepted by a specific account (routers/invitation.py checks
  // the caller's own email against the invitation's), so there's
  // nothing honest to attempt before that's known. Cancellation-
  // guarded against Strict Mode's dev-only double-invoke, same as
  // every other mount-effect fetch in this dashboard.
  useEffect(() => {
    if (status !== "authenticated") {
      return;
    }
    let cancelled = false;
    acceptInvitation(token)
      .then(() => {
        if (!cancelled) {
          setAcceptState("accepted");
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setError(err.message);
          setAcceptState("error");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [status, token]);

  if (status === "loading") {
    return <p className={styles.status}>Loading…</p>;
  }

  if (status === "unauthenticated") {
    return (
      <div className={styles.card}>
        <h1 className={styles.title}>Join an organization on AgentForge</h1>
        <p>
          Log in or sign up with the email this invitation was sent to, then use this same link
          again to accept it.
        </p>
        <Link href="/login" className={styles.link}>
          Go to login
        </Link>
      </div>
    );
  }

  if (acceptState === "accepting") {
    return <p className={styles.status}>Joining…</p>;
  }

  if (acceptState === "accepted") {
    return (
      <div className={styles.card}>
        <h1 className={styles.title}>You&apos;re in.</h1>
        <p>You&apos;ve joined the organization.</p>
        <Link href="/dashboard" className={styles.link}>
          Go to dashboard
        </Link>
      </div>
    );
  }

  return (
    <div className={styles.card}>
      <h1 className={styles.title}>Couldn&apos;t accept this invitation</h1>
      <p className={styles.error}>{error}</p>
    </div>
  );
}
