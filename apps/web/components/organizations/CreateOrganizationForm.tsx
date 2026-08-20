"use client";

// Extracted from app/dashboard/settings/page.tsx, which previously
// defined this form inline and was its only real consumer. Now shared
// with the rebuilt dashboard home page (zero-org state) and the new
// "add another organization" page -- same "share once a real second
// consumer exists" bar this codebase already applies elsewhere.

import { useState } from "react";
import { createOrganization, type Organization } from "@/lib/organizations";
import { slugify } from "@/lib/slugify";
import { Button, Card } from "@/components/ui";
import styles from "./CreateOrganizationForm.module.css";

export function CreateOrganizationForm({
  onCreated,
  heading = "Create your organization",
  subtext,
}: {
  onCreated: (org: Organization) => void;
  heading?: string;
  subtext?: string;
}) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const org = await createOrganization(name, slug);
      onCreated(org);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className={styles.wrapper}>
      <h1 className={styles.heading}>{heading}</h1>
      {subtext && <p className={styles.subtext}>{subtext}</p>}
      <Card>
        <form className={styles.form} onSubmit={handleSubmit}>
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
          {error && <p className={styles.error}>{error}</p>}
          <Button type="submit" disabled={submitting}>
            {submitting ? "Creating…" : "Create organization"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
