import clsx from "clsx";

interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className }: SkeletonProps): JSX.Element {
  return (
    <div
      aria-hidden="true"
      className={clsx(
        "animate-shimmer rounded-md bg-gradient-to-r from-raised via-line to-raised bg-[length:200%_100%] motion-reduce:animate-none",
        className,
      )}
    />
  );
}
