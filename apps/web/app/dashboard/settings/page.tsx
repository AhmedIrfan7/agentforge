"use client";

// Org-settings page (roadmap step 234): branding + security settings
// for the caller's own organization. No org-switcher exists in this
// dashboard yet (no roadmap step asks for one through 250) -- most
// accounts at this stage have exactly one organization, so this
// honestly operates on the FIRST one GET /organizations returns, same
// "single org for now, real future work" scope this codebase already
// applies elsewhere (e.g. the widget's own single-assistant-per-embed
// design). A user with no organization yet gets a real, minimal
// create-organization form instead of a dead end -- POST /organizations
// has existed since Milestone 1 but no earlier dashboard step ever gave
// it a UI entry point.

import { useEffect, useState } from "react";
import {
  createOrganization,
  getSecuritySettings,
  updateOrganization,
  updateSecuritySettings,
  type Organization,
  type SecuritySettings,
} from "@/lib/organizations";
import { slugify } from "@/lib/slugify";
import { useCurrentOrganization } from "@/lib/useCurrentOrganization";
import styles from "./page.module.css";

export default function SettingsPage() {
  const { status, organization, error, setOrganization } = useCurrentOrganization();
  const [securitySettings, setSecuritySettings] = useState<SecuritySettings | null>(null);
  const [securitySettingsError, setSecuritySettingsError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);

  // Deliberately independent of useCurrentOrganization's own request --
  // security settings failing to load (a real, observed transient 403
  // immediately after creating a brand-new organization, most likely
  // the same class of pooled-connection read-your-own-write timing
  // this codebase has hit before elsewhere) must never be mistaken for
  // organization loading itself having failed; the branding form is
  // still fully usable either way.
  const organizationId = organization?.id;
  useEffect(() => {
    if (!organizationId) {
      return;
    }
    let cancelled = false;
    getSecuritySettings(organizationId)
      .then((settings) => {
        if (!cancelled) {
          setSecuritySettings(settings);
          setSecuritySettingsError(null);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setSecuritySettingsError(err.message);
        }
      });
    return () => {
      cancelled = true;
    };
    // organizationId (not the whole `organization` object) on purpose --
    // saving branding produces a new Organization object with the same
    // id, which would otherwise needlessly refetch security settings.
  }, [organizationId, retryToken]);

  if (status === "loading") {
    return <p className={styles.status}>Loading…</p>;
  }

  if (status === "error") {
    return <p className={styles.error}>{error}</p>;
  }

  if (!organization) {
    return <CreateOrganizationForm onCreated={setOrganization} />;
  }

  return (
    <div className={styles.wrapper}>
      <h1 className={styles.heading}>Organization settings</h1>
      <BrandingForm organization={organization} onSaved={setOrganization} />
      {securitySettings && (
        <SecurityForm
          organizationId={organization.id}
          settings={securitySettings}
          onSaved={setSecuritySettings}
        />
      )}
      {securitySettingsError && (
        <div className={styles.card}>
          <p className={styles.error}>
            Couldn&apos;t load security settings: {securitySettingsError}
          </p>
          <button
            type="button"
            className={styles.submit}
            onClick={() => setRetryToken((token) => token + 1)}
          >
            Retry
          </button>
        </div>
      )}
    </div>
  );
}

function CreateOrganizationForm({ onCreated }: { onCreated: (org: Organization) => void }) {
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
      // Only organization CREATION marks this form as failed --
      // onCreated's own follow-up (loading security settings) is
      // independently handled by the parent, so a failure there can
      // never be mistaken for "the organization wasn't created" and
      // risk a confusing duplicate submit.
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
      <h1 className={styles.heading}>Create your organization</h1>
      <p className={styles.subtext}>You don&apos;t belong to an organization yet.</p>
      <form className={styles.card} onSubmit={handleSubmit}>
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
        <button type="submit" className={styles.submit} disabled={submitting}>
          {submitting ? "Creating…" : "Create organization"}
        </button>
      </form>
    </div>
  );
}

function BrandingForm({
  organization,
  onSaved,
}: {
  organization: Organization;
  onSaved: (org: Organization) => void;
}) {
  const [name, setName] = useState(organization.name);
  const [logoUrl, setLogoUrl] = useState(organization.logo_url ?? "");
  const [primaryColor, setPrimaryColor] = useState(organization.primary_color ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const updated = await updateOrganization(organization.id, {
        name,
        logo_url: logoUrl || null,
        primary_color: primaryColor || null,
      });
      onSaved(updated);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className={styles.card} onSubmit={handleSubmit}>
      <h2 className={styles.sectionHeading}>Branding</h2>
      <label className={styles.field}>
        <span>Name</span>
        <input value={name} onChange={(event) => setName(event.target.value)} required />
      </label>
      <label className={styles.field}>
        <span>Logo URL</span>
        <input
          value={logoUrl}
          onChange={(event) => setLogoUrl(event.target.value)}
          placeholder="https://…"
        />
      </label>
      <label className={styles.field}>
        <span>Primary color</span>
        <input
          value={primaryColor}
          onChange={(event) => setPrimaryColor(event.target.value)}
          placeholder="#4f46e5"
        />
      </label>
      {error && <p className={styles.error}>{error}</p>}
      {saved && !error && <p className={styles.savedNote}>Saved.</p>}
      <button type="submit" className={styles.submit} disabled={saving}>
        {saving ? "Saving…" : "Save branding"}
      </button>
    </form>
  );
}

function SecurityForm({
  organizationId,
  settings,
  onSaved,
}: {
  organizationId: string;
  settings: SecuritySettings;
  onSaved: (settings: SecuritySettings) => void;
}) {
  const [mfaRequired, setMfaRequired] = useState(settings.mfa_required);
  const [allowedDomains, setAllowedDomains] = useState(settings.allowed_domains.join(", "));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const updated = await updateSecuritySettings(organizationId, {
        mfa_required: mfaRequired,
        allowed_domains: allowedDomains
          .split(",")
          .map((domain) => domain.trim())
          .filter((domain) => domain.length > 0),
      });
      onSaved(updated);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className={styles.card} onSubmit={handleSubmit}>
      <h2 className={styles.sectionHeading}>Security settings</h2>
      <label className={styles.checkboxField}>
        <input
          type="checkbox"
          checked={mfaRequired}
          onChange={(event) => setMfaRequired(event.target.checked)}
        />
        <span>Require MFA for all members</span>
      </label>
      <label className={styles.field}>
        <span>Allowed embed domains (comma-separated; empty means no restriction)</span>
        <input
          value={allowedDomains}
          onChange={(event) => setAllowedDomains(event.target.value)}
          placeholder="example.com, app.example.com"
        />
      </label>
      <p className={styles.hint}>
        Session timeout and password policy fields exist on this organization but aren&apos;t
        enforced anywhere yet.
      </p>
      {error && <p className={styles.error}>{error}</p>}
      {saved && !error && <p className={styles.savedNote}>Saved.</p>}
      <button type="submit" className={styles.submit} disabled={saving}>
        {saving ? "Saving…" : "Save security settings"}
      </button>
    </form>
  );
}
