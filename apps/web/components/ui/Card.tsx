import type { ReactNode } from "react";
import styles from "./Card.module.css";

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={className ? `${styles.card} ${className}` : styles.card}>{children}</div>;
}

export function CardHeading({ children }: { children: ReactNode }) {
  return <h2 className={styles.heading}>{children}</h2>;
}

export function CardSubtext({ children }: { children: ReactNode }) {
  return <p className={styles.subtext}>{children}</p>;
}
