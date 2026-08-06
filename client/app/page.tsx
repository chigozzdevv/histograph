import Link from "next/link";

import { SetupForm } from "@/components/setup-form";
import { getOrganizations, getProjects } from "@/lib/api-client";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  let organizations: Awaited<ReturnType<typeof getOrganizations>> = [];
  let unavailable = false;
  try {
    organizations = await getOrganizations();
  } catch {
    unavailable = true;
  }
  const projectGroups = await Promise.all(
    organizations.map(async (organization) => ({
      organization,
      projects: await getProjects(organization.id),
    })),
  );

  return (
    <main className="home-page">
      {unavailable ? (
        <section className="empty-state">
          The Histograph control plane is unavailable.
        </section>
      ) : projectGroups.length ? (
        <section className="page-section">
          <div className="page-title">
            <div>
              <h1>Projects</h1>
              <p>Choose an agent to monitor.</p>
            </div>
          </div>
          <div className="project-grid">
            {projectGroups.flatMap(({ organization, projects }) =>
              projects.map((project) => (
                <Link
                  className="project-card"
                  href={`/projects/${project.id}`}
                  key={project.id}
                >
                  <span>{organization.name}</span>
                  <h3>{project.name}</h3>
                  <p>{project.environment}</p>
                  <strong>Open →</strong>
                </Link>
              )),
            )}
          </div>
        </section>
      ) : (
        <section className="page-section">
          <div className="page-title">
            <div>
              <h1>Create your first project</h1>
              <p>Connect an analytics agent and start checking its answers.</p>
            </div>
          </div>
          <SetupForm />
        </section>
      )}
    </main>
  );
}
