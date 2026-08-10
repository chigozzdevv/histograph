import { Footer } from "@/components/layout/footer";
import { Header } from "@/components/layout/header";
import { Cta } from "@/components/sections/cta";
import { Hero } from "@/components/sections/hero";
import { Integrations } from "@/components/sections/integrations";
import { Investigation } from "@/components/sections/investigation";
import { Monitoring } from "@/components/sections/monitoring";
import { Product } from "@/components/sections/product";
import { Recovery } from "@/components/sections/recovery";
import { Response } from "@/components/sections/response";

export default function Home() {
  return (
    <main className="min-h-screen bg-midnight text-white">
      <Header />
      <Hero />
      <Product />
      <Monitoring />
      <Investigation />
      <Response />
      <Recovery />
      <Integrations />
      <Cta />
      <Footer />
    </main>
  );
}
