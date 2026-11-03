import type { ReactNode } from "react";

type Props = {
  title: string;
  /** The API's error message, shown as it came. */
  message: string;
  label?: string;
  hint?: string;
  action?: ReactNode;
};

/** The state shown when an API call fails. */
export function ApiError({ title, message, label, hint, action }: Props) {
  return (
    <div className="state" role="alert">
      {label && <div className="micro">{label}</div>}
      <h2>{title}</h2>
      <p>
        The API answered: {message}.{hint && ` ${hint}`}
      </p>
      {action && <div className="state-actions">{action}</div>}
    </div>
  );
}
