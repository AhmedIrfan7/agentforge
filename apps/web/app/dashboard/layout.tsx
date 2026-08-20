"use client";

// Auth-gated dashboard shell (roadmap step 233). A Client Component,
// not middleware/proxy.ts-based gating -- this app's session lives in
// localStorage (lib/auth.ts), which a Next.js proxy/edge function can
// never read (it isn't sent to the server at all), so the gate has to
// run in the browser, the same reasoning lib/AuthContext.tsx's own
// docstring already gives for why this can't be a Server Component.
//
// Nav is grouped into logical sections (dashboard UX pass) instead of
// one flat row of 9 links -- Workspace / Organization / Insights /
// Platform. "Platform" (System health, Platform admin) now only
// renders when `user.is_platform_admin` is true -- that field didn't
// exist on UserRead until this same pass added it; before, these links
// were shown to every authenticated user and relied entirely on the
// backend's own 403 for a non-admin who clicked them.
//
// Renders OrgSwitcher next to the brand -- its own
// useCurrentOrganization() call is independent of whatever the page
// below it also calls (no shared OrganizationContext exists yet, a
// known, accepted minor inefficiency, not a correctness bug: both
// instances resolve to the same organization via the same
// localStorage-persisted id).

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/lib/AuthContext";
import { useCurrentOrganization } from "@/lib/useCurrentOrganization";
import { OrgSwitcher } from "@/components/organizations/OrgSwitcher";
import styles from "./layout.module.css";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { status, user, logout } = useAuth();
  const { organization, organizations, setOrganization } = useCurrentOrganization();

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/login");
    }
  }, [status, router]);

  if (status !== "authenticated" || !user) {
    return <div className={styles.loading}>Loading…</div>;
  }

  return (
    <div className={styles.shell}>
      <nav className={styles.nav}>
        <span className={styles.brand}>AgentForge</span>
        <OrgSwitcher
          organizations={organizations}
          currentOrganizationId={organization?.id}
          onSelect={setOrganization}
        />

        <div className={styles.navGroup}>
          <span className={styles.navGroupLabel}>Workspace</span>
          <Link href="/dashboard/workspaces" className={styles.navLink}>
            Workspaces
          </Link>
        </div>

        <div className={styles.navGroup}>
          <span className={styles.navGroupLabel}>Organization</span>
          <Link href="/dashboard/members" className={styles.navLink}>
            Members
          </Link>
          <Link href="/dashboard/invitations" className={styles.navLink}>
            Invitations
          </Link>
          <Link href="/dashboard/api-keys" className={styles.navLink}>
            API keys
          </Link>
          <Link href="/dashboard/settings" className={styles.navLink}>
            Settings
          </Link>
        </div>

        <div className={styles.navGroup}>
          <span className={styles.navGroupLabel}>Insights</span>
          <Link href="/dashboard/analytics" className={styles.navLink}>
            Analytics
          </Link>
          <Link href="/dashboard/audit-log" className={styles.navLink}>
            Audit log
          </Link>
        </div>

        {user.is_platform_admin && (
          <div className={styles.navGroup}>
            <span className={styles.navGroupLabel}>Platform</span>
            <Link href="/dashboard/system-health" className={styles.navLink}>
              System health
            </Link>
            <Link href="/dashboard/platform-admin" className={styles.navLink}>
              Platform admin
            </Link>
          </div>
        )}

        <div className={styles.navSpacer} />
        <span className={styles.userEmail}>{user.email}</span>
        <button
          type="button"
          className={styles.logoutButton}
          onClick={() => {
            void logout().then(() => router.push("/login"));
          }}
        >
          Log out
        </button>
      </nav>
      <main className={styles.content}>{children}</main>
    </div>
  );
}
