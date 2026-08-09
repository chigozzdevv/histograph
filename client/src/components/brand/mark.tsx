type MarkProps = {
  className?: string;
};

export function Mark({ className }: MarkProps) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      viewBox="0 0 32 32"
    >
      <path
        d="M7 8.5 16 4l9 4.5v15L16 28l-9-4.5v-15Z"
        stroke="currentColor"
        strokeWidth="1.75"
      />
      <path
        d="M10.5 21.5v-9l5.5 3 5.5-3v9"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.75"
      />
      <circle cx="10.5" cy="12.5" r="2" fill="currentColor" />
      <circle cx="16" cy="15.5" r="2" fill="currentColor" />
      <circle cx="21.5" cy="12.5" r="2" fill="currentColor" />
    </svg>
  );
}
