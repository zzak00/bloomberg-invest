import { Link } from "react-router";

type Props = { label: string; title: string; body: string };

export function EmptyPage({ label, title, body }: Props) {
  return (
    <section className="state" aria-labelledby="empty-title">
      <div className="micro">{label}</div>
      <h2 id="empty-title">{title}</h2>
      <p>{body}</p>
      <div className="state-actions">
        <Link className="button" to="/index">
          OPEN THE INDEX
        </Link>
      </div>
    </section>
  );
}
