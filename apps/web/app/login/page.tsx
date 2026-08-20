"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { login, verifyMfa } from "@/lib/auth";
import { useAuth } from "@/lib/AuthContext";
import styles from "./page.module.css";

const ERROR_MESSAGES: Record<string, string> = {
  invalid_credentials: "Incorrect email or password.",
  invalid_code: "Invalid or expired code. Please try again.",
  unknown: "Something went wrong. Please try again.",
};

export default function LoginPage() {
  const router = useRouter();
  const { status, refreshUser } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaTicket, setMfaTicket] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (status === "authenticated") {
      router.replace("/dashboard");
    }
  }, [status, router]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    const result = await login(email, password);
    if (result.ok) {
      await refreshUser();
      router.push("/dashboard");
      return;
    }
    if (result.reason === "mfa_required") {
      setMfaTicket(result.mfaTicket);
      setSubmitting(false);
      return;
    }
    setError(ERROR_MESSAGES[result.reason]);
    setSubmitting(false);
  }

  async function handleVerifyMfa(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!mfaTicket) {
      return;
    }
    setSubmitting(true);
    setError(null);

    const result = await verifyMfa(mfaTicket, code);
    if (result.ok) {
      await refreshUser();
      router.push("/dashboard");
      return;
    }
    setError(ERROR_MESSAGES[result.reason]);
    setSubmitting(false);
  }

  if (mfaTicket) {
    return (
      <main className={styles.main}>
        <form className={styles.card} onSubmit={handleVerifyMfa}>
          <h1 className={styles.title}>Enter your verification code</h1>
          <label className={styles.field}>
            <span>Authenticator code or backup code</span>
            <input
              value={code}
              onChange={(event) => setCode(event.target.value)}
              required
              autoComplete="one-time-code"
              autoFocus
            />
          </label>
          {error && <p className={styles.error}>{error}</p>}
          <button type="submit" className={styles.submit} disabled={submitting}>
            {submitting ? "Verifying…" : "Verify"}
          </button>
          <button
            type="button"
            className={styles.backButton}
            onClick={() => {
              setMfaTicket(null);
              setCode("");
              setError(null);
            }}
          >
            Back to sign in
          </button>
        </form>
      </main>
    );
  }

  return (
    <main className={styles.main}>
      <form className={styles.card} onSubmit={handleSubmit}>
        <h1 className={styles.title}>Sign in to AgentForge</h1>
        <label className={styles.field}>
          <span>Email</span>
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
            autoComplete="email"
          />
        </label>
        <label className={styles.field}>
          <span>Password</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            autoComplete="current-password"
          />
        </label>
        {error && <p className={styles.error}>{error}</p>}
        <button type="submit" className={styles.submit} disabled={submitting}>
          {submitting ? "Signing in…" : "Sign in"}
        </button>
        <p className={styles.altAction}>
          Don&apos;t have an account? <Link href="/signup">Sign up</Link>
        </p>
      </form>
    </main>
  );
}
