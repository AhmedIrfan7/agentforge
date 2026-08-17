"use client";

// Auth-gated dashboard shell (roadmap step 233). A Client Component,
// not middleware/proxy.ts-based gating -- this app's session lives in
// localStorage (lib/auth.ts), which a Next.js proxy/edge function can
// never read (it isn't sent to the server at all), so the gate has to
// run in the browser, the same reasoning lib/AuthContext.tsx's own
// docstring already gives for why this can't be a Server Component.
//
// Real nav links only ever appear here once their own real page lands
// -- Settings (234), Workspaces (235), Members (239), Invitations
// (240), API keys (241), Analytics (243), Audit log (247), System
// health (248), Platform admin (249) so far; knowledge-bases/etc. each
// add their own entry as their own step lands, matching how this
// codebase everywhere else avoids wiring a UI affordance to a route
// that doesn't exist yet.
//
// System health and Platform admin are both visible to every
// authenticated user, same as Audit log -- their own GET endpoints
// enforce User.is_platform_admin server-side (a global flag, not a
// per-org role UserRead doesn't even expose to the client), so hiding
// either link client-side would need a new field just to duplicate a
// check the backend already makes.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/lib/AuthContext";
import styles from "./layout.module.css";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { status, user, logout } = useAuth();

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
        <Link href="/dashboard/workspaces" className={styles.navLink}>
          Workspaces
        </Link>
        <Link href="/dashboard/members" className={styles.navLink}>
          Members
        </Link>
        <Link href="/dashboard/invitations" className={styles.navLink}>
          Invitations
        </Link>
        <Link href="/dashboard/api-keys" className={styles.navLink}>
          API keys
        </Link>
        <Link href="/dashboard/analytics" className={styles.navLink}>
          Analytics
        </Link>
        <Link href="/dashboard/audit-log" className={styles.navLink}>
          Audit log
        </Link>
        <Link href="/dashboard/system-health" className={styles.navLink}>
          System health
        </Link>
        <Link href="/dashboard/platform-admin" className={styles.navLink}>
          Platform admin
        </Link>
        <Link href="/dashboard/settings" className={styles.navLink}>
          Settings
        </Link>
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
