"use client";

// Dashboard home (dashboard UX pass) -- replaces the stale placeholder
// that used to say organization/workspace/knowledge-base management was
// "coming soon" even though every one of those pages already existed
// and just wasn't linked from here. Zero-org state reuses the shared
// CreateOrganizationForm (previously inline-only in Settings); has-org
// state gives a real, honest getting-started path instead of a dead
// end -- a static ordered list of links, not live per-step completion
// tracking (that would need new read calls with no strong payoff over
// just linking the next real page).

import Link from "next/link";
import { CreateOrganizationForm } from "@/components/organizations/CreateOrganizationForm";
import { useAuth } from "@/lib/AuthContext";
import { useCurrentOrganization } from "@/lib/useCurrentOrganization";
import { Card, CardHeading, CardSubtext } from "@/components/ui";
import styles from "./page.module.css";

export default function DashboardHomePage() {
  const { user } = useAuth();
  const { status, organization, error, setOrganization } = useCurrentOrganization();

  if (status === "loading") {
    return <p className={styles.subtext}>Loading…</p>;
  }

  if (status === "error") {
    return <p className={styles.subtext}>{error}</p>;
  }

  if (!organization) {
    return (
      <CreateOrganizationForm
        onCreated={setOrganization}
        subtext="You don't belong to an organization yet -- create one to get started."
      />
    );
  }

  return (
    <div className={styles.wrapper}>
      <h1 className={styles.heading}>Welcome back{user ? `, ${user.full_name}` : ""}.</h1>
      <p className={styles.subtext}>{organization.name}</p>

      <Card>
        <CardHeading>Getting started</CardHeading>
        <CardSubtext>The real path from nothing to a working, embeddable assistant.</CardSubtext>
        <ol className={styles.checklist}>
          <li>
            Create a <Link href="/dashboard/workspaces">workspace</Link>
          </li>
          <li>
            Inside it, create a <Link href="/dashboard/workspaces">knowledge base</Link>
          </li>
          <li>Upload a document to it</li>
          <li>Create an assistant on that knowledge base</li>
          <li>Test the assistant and copy its embed code, right from its own page</li>
        </ol>
      </Card>
    </div>
  );
}
