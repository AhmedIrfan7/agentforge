"use client";

import { useRouter } from "next/navigation";
import type { Organization } from "@/lib/organizations";
import styles from "./OrgSwitcher.module.css";

const CREATE_NEW_VALUE = "__create__";

export function OrgSwitcher({
  organizations,
  currentOrganizationId,
  onSelect,
}: {
  organizations: Organization[];
  currentOrganizationId: string | undefined;
  onSelect: (organization: Organization) => void;
}) {
  const router = useRouter();

  if (organizations.length === 0) {
    return null;
  }

  return (
    <div className={styles.wrapper}>
      <select
        className={styles.select}
        value={currentOrganizationId ?? ""}
        onChange={(event) => {
          const value = event.target.value;
          if (value === CREATE_NEW_VALUE) {
            router.push("/dashboard/organizations/new");
            return;
          }
          const org = organizations.find((candidate) => candidate.id === value);
          if (org) {
            onSelect(org);
          }
        }}
      >
        {organizations.map((org) => (
          <option key={org.id} value={org.id}>
            {org.name}
          </option>
        ))}
        <option value={CREATE_NEW_VALUE}>+ Create organization</option>
      </select>
    </div>
  );
}
