"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { login } from "@/lib/auth";
import { useAuth } from "@/lib/AuthContext";
import styles from "./page.module.css";

const ERROR_MESSAGES: Record<string, string> = {
  invalid_credentials: "Incorrect email or password.",
  mfa_required:
    "This account has two-factor authentication enabled. MFA verification isn't supported in this dashboard yet.",
  unknown: "Something went wrong. Please try again.",
};

export default function LoginPage() {
  const router = useRouter();
  const { status, refreshUser } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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
    setError(ERROR_MESSAGES[result.reason]);
    setSubmitting(false);
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
      </form>
    </main>
  );
}
