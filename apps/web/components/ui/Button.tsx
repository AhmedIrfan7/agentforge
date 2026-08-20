import Link from "next/link";
import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from "react";
import styles from "./Button.module.css";

export type ButtonVariant = "primary" | "destructive" | "secondary";

interface CommonProps {
  children: ReactNode;
  variant?: ButtonVariant;
  className?: string;
}

// `href` present -> renders as a real Next.js Link styled like a button
// (the assistant builder's "Test this assistant" opens a new tab, the
// org switcher's "Create organization" navigates) -- everything else
// renders a plain <button>, so this one component covers both cases
// every page in this pass actually needs instead of two near-identical
// primitives.
type ButtonAsButton = CommonProps &
  Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className"> & { href?: undefined };
type ButtonAsLink = CommonProps &
  Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "className"> & { href: string };

export function Button(props: ButtonAsButton | ButtonAsLink) {
  const { children, variant = "primary", className, ...rest } = props;
  const variantClass = styles[variant];
  const classes = [styles.button, variantClass, className].filter(Boolean).join(" ");

  if ("href" in rest && rest.href !== undefined) {
    const { href, ...anchorRest } = rest as ButtonAsLink;
    return (
      <Link href={href} className={classes} {...anchorRest}>
        {children}
      </Link>
    );
  }

  return (
    <button type="button" className={classes} {...(rest as ButtonAsButton)}>
      {children}
    </button>
  );
}
