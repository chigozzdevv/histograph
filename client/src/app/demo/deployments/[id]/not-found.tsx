import Link from "next/link";

export default function DeploymentNotFound() {
  return (
    <div className="mx-auto w-full max-w-400 px-5 py-14 sm:px-7 lg:px-9">
      <p className="text-sm text-white/42">Deployment not found.</p>
      <Link
        className="mt-5 inline-flex text-sm text-white/72 transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        href="/demo/deployments"
      >
        ← Deployments
      </Link>
    </div>
  );
}
