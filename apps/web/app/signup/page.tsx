"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { signup } from "@/lib/auth";
import { useAuth } from "@/lib/AuthContext";
import { Button, Card } from "@/components/ui";
import styles from "./page.module.css";

const ERROR_MESSAGES: Record<string, string> = {
  email_taken: "An account with that email already exists.",
  invalid: "Password must be at least 8 characters.",
  unknown: "Something went wrong. Please try again.",
};

export default function SignupPage() {
  const router = useRouter();
  const { status, refreshUser } = useAuth();
  const [fullName, setFullName] = useState("");
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

    const result = await signup(email, password, fullName);
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
      <Card className={styles.card}>
        <form onSubmit={handleSubmit} className={styles.form}>
          <h1 className={styles.title}>Create your AgentForge account</h1>
          <label className={styles.field}>
            <span>Full name</span>
            <input
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              required
              autoComplete="name"
            />
          </label>
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
              autoComplete="new-password"
              minLength={8}
            />
            <span className={styles.hint}>At least 8 characters.</span>
          </label>
          {error && <p className={styles.error}>{error}</p>}
          <Button type="submit" disabled={submitting}>
            {submitting ? "Creating account…" : "Create account"}
          </Button>
          <p className={styles.altAction}>
            Already have an account? <Link href="/login">Sign in</Link>
          </p>
        </form>
      </Card>
    </main>
  );
}
