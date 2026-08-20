"use client";

// The real "add a second organization" entry point that didn't exist
// before this pass -- Settings' own CreateOrganizationForm only ever
// rendered as a fallback for a user with ZERO organizations, so there
// was no way to create a second one once you already had one.

import { CreateOrganizationForm } from "@/components/organizations/CreateOrganizationForm";
import { useCurrentOrganization } from "@/lib/useCurrentOrganization";
import type { Organization } from "@/lib/organizations";
import styles from "./page.module.css";

export default function NewOrganizationPage() {
  const { setOrganization } = useCurrentOrganization();

  function handleCreated(org: Organization): void {
    // setOrganization persists the choice to localStorage, but this
    // page's useCurrentOrganization() instance is independent of
    // layout.tsx's own (no shared OrganizationContext exists yet --
    // a real, accepted limitation, see useCurrentOrganization.ts) --
    // a soft router.push wouldn't make the nav's OrgSwitcher re-fetch
    // and pick up the brand-new org. A full navigation forces every
    // instance to freshly mount and read the just-stored id.
    setOrganization(org);
    window.location.href = "/dashboard";
  }

  return (
    <div className={styles.wrapper}>
      <CreateOrganizationForm
        onCreated={handleCreated}
        heading="Create a new organization"
        subtext="Set up a separate organization -- its own workspaces, members, and knowledge bases."
      />
    </div>
  );
}
