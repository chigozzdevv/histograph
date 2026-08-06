"use client";

import { useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { useState } from "react";

import { mutate } from "@/lib/browser-api-client";
import type { Organization, Project } from "@/lib/types";

function slugify(value: FormDataEntryValue | null) {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

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
      const organizationName = form.get("organization-name");
      const projectName = form.get("project-name");
      const organization = await mutate<Organization>("/organizations", {
        name: organizationName,
        slug: slugify(organizationName),
        owner_email: form.get("owner-email"),
        owner_display_name: form.get("owner-name"),
      });
      const project = await mutate<Project>("/projects", {
        organization_id: organization.id,
        name: projectName,
        slug: slugify(projectName),
        environment: form.get("environment"),
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
        retention_days: 90,
        max_concurrent_runs: 4,
      });
      router.push(`/projects/${project.id}`);
      router.refresh();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Histograph could not be configured",
      );
      setSubmitting(false);
    }
  }

  return (
    <form className="form-card" onSubmit={submit}>
      <div className="form-heading">
        <span>1</span>
        <div>
          <h2>Project details</h2>
          <p>You can connect DataHub and your analytics agent next.</p>
        </div>
      </div>
      <div className="form-grid">
        <label>
          Company
          <input name="organization-name" required />
        </label>
        <label>
          Your name
          <input name="owner-name" required />
        </label>
        <label>
          Work email
          <input name="owner-email" type="email" required />
        </label>
        <label>
          Project name
          <input
            name="project-name"
            placeholder="Revenue analytics agent"
            required
          />
        </label>
        <label>
          Environment
          <select name="environment" defaultValue="production">
            <option value="development">Development</option>
            <option value="staging">Staging</option>
            <option value="production">Production</option>
          </select>
        </label>
      </div>
      {error ? <p className="form-error">{error}</p> : null}
      <button className="primary-button" disabled={submitting} type="submit">
        {submitting ? "Creating project…" : "Create project"}
      </button>
    </form>
  );
}
