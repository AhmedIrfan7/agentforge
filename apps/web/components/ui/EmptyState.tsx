import type { ReactNode } from "react";
import styles from "./EmptyState.module.css";

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className={styles.wrapper}>
      <p className={styles.title}>{title}</p>
      {hint && <p className={styles.hint}>{hint}</p>}
      {action && <div className={styles.action}>{action}</div>}
    </div>
  );
}
