export function Skeleton({ className = "" }: { className?: string }) {
  return <span className={`ui-skeleton ${className}`.trim()} aria-hidden="true" />;
}

export function SkeletonRows({ count = 3 }: { count?: number }) {
  return (
    <div className="ui-skeleton-list" aria-label="Loading content" aria-busy="true">
      {Array.from({ length: count }, (_, index) => (
        <div className="ui-skeleton-row" key={index}>
          <Skeleton className="ui-skeleton-badge" />
          <span className="ui-skeleton-copy">
            <Skeleton className="ui-skeleton-title" />
            <Skeleton className="ui-skeleton-line" />
          </span>
        </div>
      ))}
    </div>
  );
}
