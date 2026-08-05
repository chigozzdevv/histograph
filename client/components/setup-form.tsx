"use client";

import { useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { useState } from "react";

import { mutate } from "@/lib/browser-api-client";
import type { Organization, Project } from "@/lib/types";

export function SetupForm() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    try {
      const organization = await mutate<Organization>("/organizations", {
        name: form.get("organization-name"),
        slug: form.get("organization-slug"),
        owner_email: form.get("owner-email"),
        owner_display_name: form.get("owner-name"),
      });
      const project = await mutate<Project>("/projects", {
        organization_id: organization.id,
        name: form.get("project-name"),
        slug: form.get("project-slug"),
        environment: form.get("environment"),
        timezone: form.get("timezone"),
        retention_days: 90,
        max_concurrent_runs: 4,
      });
      router.push(`/projects/${project.id}`);
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Histograph could not be configured");
      setSubmitting(false);
    }
  }

  return (
    <form className="form-card" onSubmit={submit}>
      <div className="form-heading">
        <span>01</span>
        <div>
          <h2>Create the assurance boundary</h2>
          <p>An organization is the tenant boundary. A project owns one agent assurance program.</p>
        </div>
      </div>
      <div className="form-grid">
        <label>
          Organization name
          <input name="organization-name" required />
        </label>
        <label>
          Organization slug
          <input name="organization-slug" pattern="[a-z0-9][a-z0-9-]+[a-z0-9]" required />
        </label>
        <label>
          Owner name
          <input name="owner-name" required />
        </label>
        <label>
          Owner email
          <input name="owner-email" type="email" required />
        </label>
        <label>
          Project name
          <input name="project-name" placeholder="Revenue analytics agent" required />
        </label>
        <label>
          Project slug
          <input name="project-slug" pattern="[a-z0-9][a-z0-9-]+[a-z0-9]" required />
        </label>
        <label>
          Environment
          <select name="environment" defaultValue="production">
            <option value="development">Development</option>
            <option value="staging">Staging</option>
            <option value="production">Production</option>
          </select>
        </label>
        <label>
          Timezone
          <input name="timezone" defaultValue="UTC" required />
        </label>
      </div>
      {error ? <p className="form-error">{error}</p> : null}
      <button className="primary-button" disabled={submitting} type="submit">
        {submitting ? "Creating organization…" : "Create organization and project"}
      </button>
    </form>
  );
}
