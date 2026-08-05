"use client";

import { useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { useState } from "react";

import { mutate } from "@/lib/browser-api-client";
import type { GitHubInstallation, Organization } from "@/lib/types";

type GitHubSetupFormProps = {
  installationId: number;
  organizations: Organization[];
};

export function GitHubSetupForm({ installationId, organizations }: GitHubSetupFormProps) {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const organizationId = String(form.get("organization-id"));
    try {
      await mutate<GitHubInstallation>(`/organizations/${organizationId}/github-installations`, {
        installation_id: installationId,
      });
      router.push("/");
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "GitHub installation could not be connected");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="form-card github-setup-form" onSubmit={connect}>
      <div className="form-heading">
        <span>GH</span>
        <div>
          <h2>Attach installation {installationId}</h2>
          <p>Select the Histograph organization that owns this GitHub installation.</p>
        </div>
      </div>
      <select name="organization-id" required defaultValue="">
        <option value="" disabled>Select organization</option>
        {organizations.map((organization) => (
          <option value={organization.id} key={organization.id}>{organization.name}</option>
        ))}
      </select>
      {error ? <p className="form-error">{error}</p> : null}
      <button className="primary-button" disabled={submitting || !organizations.length}>
        Connect GitHub installation
      </button>
    </form>
  );
}
