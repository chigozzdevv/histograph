import Link from "next/link";

import { GitHubSetupForm } from "@/components/github-setup-form";
import { getOrganizations } from "@/lib/api-client";

type GitHubSetupPageProps = {
  searchParams: Promise<{ installation_id?: string; setup_action?: string }>;
};

export const dynamic = "force-dynamic";

export default async function GitHubSetupPage({ searchParams }: GitHubSetupPageProps) {
  const query = await searchParams;
  const installationId = Number(query.installation_id);
  const organizations = await getOrganizations();

  return (
    <main className="project-page">
      <Link className="back-link" href="/">← Histograph</Link>
      <section className="project-heading">
        <div>
          <p className="eyebrow">GitHub App setup</p>
          <h1>Connect repository access.</h1>
          <p>Histograph stores the installation identifier, not a permanent GitHub token.</p>
        </div>
      </section>
      {Number.isSafeInteger(installationId) && installationId > 0 ? (
        <GitHubSetupForm installationId={installationId} organizations={organizations} />
      ) : (
        <section className="error-panel">
          GitHub did not provide a valid installation identifier. Reopen the App installation flow.
        </section>
      )}
    </main>
  );
}
