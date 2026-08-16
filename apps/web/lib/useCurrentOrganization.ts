"use client";

// Resolves "the caller's organization" (roadmap step 235) -- extracted
// once a genuine SECOND dashboard page needed it (settings/234 was
// the first, doing this fetch inline); same "share once a real second
// consumer exists" bar this codebase applies everywhere else (e.g.
// packages/shared's own promotion history). No org-switcher exists
// yet, so this stays honestly scoped to the FIRST organization
// GET /organizations returns, same limitation settings/page.tsx's own
// original version already had.

import { useEffect, useState } from "react";
import { listOrganizations, type Organization } from "./organizations";

export type CurrentOrganizationStatus = "loading" | "ready" | "error";

export interface CurrentOrganization {
  status: CurrentOrganizationStatus;
  organization: Organization | null;
  error: string | null;
  setOrganization: (organization: Organization) => void;
}

export function useCurrentOrganization(): CurrentOrganization {
  const [status, setStatus] = useState<CurrentOrganizationStatus>("loading");
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listOrganizations()
      .then((orgs) => {
        if (cancelled) {
          return;
        }
        setOrganization(orgs[0] ?? null);
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

  return { status, organization, error, setOrganization };
}
