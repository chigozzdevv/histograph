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
    <main>
      <section className="hero compact-hero">
        <p className="eyebrow">Continuous assurance for data agents</p>
        <h1>Know when context changes the answer.</h1>
        <p className="hero-copy">
          Histograph uses DataHub lineage to select affected business questions, rerun the real
          analytics agent, and publish deterministic evidence before people trust a wrong answer.
        </p>
        <div className="flow-strip">
          <span>Metadata or code changes</span><i /><span>Lineage impact plan</span><i />
          <span>Agent behavior rerun</span><i /><span>Auditable gate</span>
        </div>
      </section>

      {unavailable ? (
        <section className="empty-state">The Histograph control plane is unavailable.</section>
      ) : projectGroups.length ? (
        <section className="content-section">
          <div className="section-title">
            <div><p className="eyebrow">Control plane</p><h2>Assurance projects</h2></div>
            <p>Each project connects one DataHub environment to the agents and questions it protects.</p>
          </div>
          <div className="project-grid">
            {projectGroups.flatMap(({ organization, projects }) =>
              projects.map((project) => (
                <Link className="project-card" href={`/projects/${project.id}`} key={project.id}>
                  <span>{organization.name}</span>
                  <h3>{project.name}</h3>
                  <p>{project.environment} · {project.timezone}</p>
                  <strong>Open project →</strong>
                </Link>
              )),
            )}
          </div>
        </section>
      ) : (
        <section className="content-section">
          <div className="section-title">
            <div><p className="eyebrow">Set up Histograph</p><h2>Start with the tenant boundary</h2></div>
          </div>
          <SetupForm />
        </section>
      )}
    </main>
  );
}
