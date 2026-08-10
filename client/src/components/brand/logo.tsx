import Image from "next/image";

type LogoProps = {
  className?: string;
  priority?: boolean;
};

export function Logo({ className = "", priority = false }: LogoProps) {
  return (
    <span className={`relative block h-8 w-40 overflow-hidden ${className}`}>
      <Image
        alt=""
        className="absolute top-[-37px] left-[-84px] h-auto w-[334px] max-w-none"
        height={720}
        priority={priority}
        sizes="334px"
        src="/histograph_logo.png"
        width={2400}
      />
      <span className="sr-only">Histograph</span>
    </span>
  );
}
