import type { CSSProperties } from "react";

type RotatingTermsProps = {
  terms: readonly [string, string, string];
};

export function RotatingTerms({ terms }: RotatingTermsProps) {
  return (
    <span className="hero-term-rotator">
      {terms.map((term, index) => (
        <span
          aria-hidden="true"
          className="hero-term-rotator__item"
          key={term}
          style={
            {
              "--term-delay": `${index * 3 - 0.35}s`,
              "--term-duration": "9s",
            } as CSSProperties
          }
        >
          <span className="hero-term-rotator__text">{term}</span>
          <span className="hero-term-rotator__cursor" />
        </span>
      ))}
      <span className="sr-only">{terms[0]}</span>
    </span>
  );
}
