import styles from "./page.module.css";

const backendUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export default function Home() {
  return (
    <div className={styles.page}>
      <main className={styles.shell}>
        <section className={styles.hero} aria-labelledby="page-title">
          <p className={styles.kicker}>Money Copy Bot</p>
          <h1 id="page-title">MCBot trading workspace is ready.</h1>
          <p>
            A starter workspace for brokerage integration, stock research organization,
            strategy testing, and automated trading workflows.
          </p>
          <div className={styles.actions}>
            <a className={styles.primary} href={`${backendUrl}/docs`}>
              Open API docs
            </a>
            <a className={styles.secondary} href={`${backendUrl}/health`}>
              Check health
            </a>
          </div>
        </section>

        <section className={styles.statusGrid} aria-label="Environment status">
          <article className={styles.statusCard}>
            <span>Frontend</span>
            <strong>Next.js + TypeScript</strong>
            <p>App Router foundation for the stock automation dashboard.</p>
          </article>
          <article className={styles.statusCard}>
            <span>Backend</span>
            <strong>FastAPI</strong>
            <p>
              API foundation for accounts, market data, and trading workflows.
            </p>
          </article>
          <article className={styles.statusCard}>
            <span>API Base URL</span>
            <strong>{backendUrl}</strong>
            <p>
              Override it with <code>NEXT_PUBLIC_API_BASE_URL</code>.
            </p>
          </article>
        </section>

        <section className={styles.commands} aria-label="Run commands">
          <h2>Run commands</h2>
          <div className={styles.commandList}>
            <div>
              <span>Backend</span>
              <code>python -m uvicorn app.main:app --reload --port 8000</code>
            </div>
            <div>
              <span>Frontend</span>
              <code>npm run dev</code>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
