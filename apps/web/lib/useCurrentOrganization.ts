"use client";

// Resolves "the caller's organization" (roadmap step 235) -- extracted
// once a genuine SECOND dashboard page needed it (settings/234 was
// the first, doing this fetch inline); same "share once a real second
// consumer exists" bar this codebase applies everywhere else (e.g.
// packages/shared's own promotion history).
//
// Now backs a real org switcher (components/organizations/OrgSwitcher):
// exposes the full `organizations` list (not just the first), and
// persists the chosen id to localStorage so a page refresh doesn't
// silently snap back to orgs[0].

import { useEffect, useState } from "react";
import { listOrganizations, type Organization } from "./organizations";

export type CurrentOrganizationStatus = "loading" | "ready" | "error";

const CURRENT_ORG_ID_KEY = "agentforge:current_org_id";

export interface CurrentOrganization {
  status: CurrentOrganizationStatus;
  organization: Organization | null;
  organizations: Organization[];
  error: string | null;
  setOrganization: (organization: Organization) => void;
}

function readStoredOrgId(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(CURRENT_ORG_ID_KEY);
}

export function useCurrentOrganization(): CurrentOrganization {
  const [status, setStatus] = useState<CurrentOrganizationStatus>("loading");
  const [organization, setOrganizationState] = useState<Organization | null>(null);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listOrganizations()
      .then((orgs) => {
        if (cancelled) {
          return;
        }
        setOrganizations(orgs);
        // Prefer whichever org the user last picked via the switcher, as
        // long as it's still in the real list the API just returned --
        // without this, a page refresh would always silently snap back
        // to orgs[0] no matter what the user had switched to.
        const storedId = readStoredOrgId();
        const stored = storedId ? orgs.find((org) => org.id === storedId) : undefined;
        setOrganizationState(stored ?? orgs[0] ?? null);
        setStatus("ready");
      })
      .catch((err: Error) => {
        if (cancelled) {
          return;
        }
        setError(err.message);
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function setOrganization(org: Organization): void {
    setOrganizationState(org);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(CURRENT_ORG_ID_KEY, org.id);
    }
  }

  return { status, organization, organizations, error, setOrganization };
}
