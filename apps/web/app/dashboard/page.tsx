"use client";

import { useAuth } from "@/lib/AuthContext";
import styles from "./page.module.css";

export default function DashboardHomePage() {
  const { user } = useAuth();

  return (
    <div className={styles.wrapper}>
      <h1 className={styles.heading}>Welcome back{user ? `, ${user.full_name}` : ""}.</h1>
      <p className={styles.subtext}>
        Organization, workspace, and knowledge base management are coming to this dashboard soon.
      </p>
    </div>
  );
}
