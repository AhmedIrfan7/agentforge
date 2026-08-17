"use client";

// API-key management UI (roadmap step 241) -- no backend existed for
// this resource at all before this step (unlike 239/240, which only
// needed a UI for already-existing endpoints). Create/list/revoke,
// org-level only, matching the same scope discipline Members/
// Invitations already settled on.
//
// Deliberately does NOT let a caller use a generated key against this
// API anywhere yet -- see models/api_key.py's own docstring for why
// that's real, separate, future work. This page is honest about that:
// a created key is real, hashed-at-rest, and revocable, it just has
// nothing to authenticate against yet.

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  createApiKey,
  listApiKeys,
  revokeApiKey,
  type ApiKey,
  type ApiKeyCreated,
} from "@/lib/apiKeys";
import { useCurrentOrganization } from "@/lib/useCurrentOrganization";
import styles from "./page.module.css";

export default function ApiKeysPage() {
  const { status, organization, error } = useCurrentOrganization();

  if (status === "loading") {
    return <p className={styles.status}>Loading…</p>;
  }

  if (status === "error") {
    return <p className={styles.error}>{error}</p>;
  }

  if (!organization) {
    return (
      <div className={styles.wrapper}>
        <h1 className={styles.heading}>API keys</h1>
        <p className={styles.subtext}>
          You don&apos;t belong to an organization yet.{" "}
          <Link href="/dashboard/settings">Create one in Settings</Link> first.
        </p>
      </div>
    );
  }

  return <ApiKeyList organizationId={organization.id} />;
}

function ApiKeyList({ organizationId }: { organizationId: string }) {
  const [apiKeys, setApiKeys] = useState<ApiKey[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [revealedKey, setRevealedKey] = useState<ApiKeyCreated | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  // Cancellation-guarded mount effect -- same Strict Mode double-invoke
  // fix every other list page in this dashboard already needed.
  useEffect(() => {
    let cancelled = false;
    listApiKeys(organizationId)
      .then((items) => {
        if (!cancelled) {
          setApiKeys(items);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setListError(err.message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [organizationId]);

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreating(true);
    setCreateError(null);
    try {
      const created = await createApiKey(organizationId, name);
      setApiKeys((prev) => [created, ...(prev ?? [])]);
      setRevealedKey(created);
      setName("");
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setCreating(false);
    }
  }

  async function handleRevoke(apiKey: ApiKey) {
    if (!window.confirm(`Revoke "${apiKey.name}"? Anything using it will stop working.`)) {
      return;
    }
    setRevokingId(apiKey.id);
    try {
      await revokeApiKey(organizationId, apiKey.id);
      setApiKeys((prev) =>
        (prev ?? []).map((k) =>
          k.id === apiKey.id ? { ...k, revoked_at: new Date().toISOString() } : k,
        ),
      );
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setRevokingId(null);
    }
  }

  return (
    <div className={styles.wrapper}>
      <h1 className={styles.heading}>API keys</h1>

      {revealedKey && (
        <div className={styles.revealCard}>
          <h2 className={styles.sectionHeading}>&quot;{revealedKey.name}&quot; created</h2>
          <p className={styles.revealWarning}>
            Copy this key now — you won&apos;t be able to see it again.
          </p>
          <code className={styles.revealKey}>{revealedKey.key}</code>
          <button
            type="button"
            className={styles.submit}
            onClick={() => {
              void navigator.clipboard?.writeText(revealedKey.key);
              setRevealedKey(null);
            }}
          >
            I&apos;ve copied it
          </button>
        </div>
      )}

      <form className={styles.card} onSubmit={handleCreate}>
        <h2 className={styles.sectionHeading}>New API key</h2>
        <label className={styles.field}>
          <span>Name</span>
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. Production integration"
            required
          />
        </label>
        {createError && <p className={styles.error}>{createError}</p>}
        <button type="submit" className={styles.submit} disabled={creating}>
          {creating ? "Creating…" : "Create key"}
        </button>
      </form>

      {listError && <p className={styles.error}>{listError}</p>}

      {apiKeys === null && !listError && <p className={styles.status}>Loading…</p>}

      {apiKeys !== null && apiKeys.length === 0 && (
        <p className={styles.subtext}>No API keys yet.</p>
      )}

      {apiKeys !== null && apiKeys.length > 0 && (
        <ul className={styles.list}>
          {apiKeys.map((apiKey) => (
            <li key={apiKey.id} className={styles.listItem}>
              <div className={styles.keyInfo}>
                <div className={styles.keyName}>{apiKey.name}</div>
                <div className={styles.keyMeta}>
                  {apiKey.key_prefix}… · {apiKey.revoked_at ? "Revoked" : "Active"}
                </div>
              </div>
              {!apiKey.revoked_at && (
                <button
                  type="button"
                  className={styles.revokeButton}
                  onClick={() => handleRevoke(apiKey)}
                  disabled={revokingId === apiKey.id}
                >
                  {revokingId === apiKey.id ? "Revoking…" : "Revoke"}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
