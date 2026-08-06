import type { Metadata } from "next";
import type { ReactNode } from "react";

import "@/app/globals.css";

export const metadata: Metadata = {
  title: "Histograph",
  description: "Continuous assurance for DataHub-powered agents",
};

type RootLayoutProps = {
  children: ReactNode;
};

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="en">
      <body>
        <header className="site-header">
          <a className="wordmark" href="/">
            <span className="wordmark-mark">H</span>
            Histograph
          </a>
        </header>
        {children}
      </body>
    </html>
  );
}
