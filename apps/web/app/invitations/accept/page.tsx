import { AcceptInvitationClient } from "./AcceptInvitationClient";
import styles from "./page.module.css";

// Invitation-accept landing page (roadmap step 240), reached via the
// real emailed link routers/invitation.py's own create_invitation
// already builds (`{app_base_url}/invitations/accept?token=...`).
// Reads the token via a Server Component searchParams prop, the same
// "async page component reads the query string" pattern app/chat's
// own page.tsx already established for this Next.js version -- avoids
// the client-side useSearchParams()/Suspense-boundary requirement for
// a value that's known at request time either way.
export default async function AcceptInvitationPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;

  if (!token) {
    return (
      <main className={styles.main}>
        <p className={styles.error}>
          This link is missing its invitation token. Use the link from your invitation email.
        </p>
      </main>
    );
  }

  return (
    <main className={styles.main}>
      <AcceptInvitationClient token={token} />
    </main>
  );
}
