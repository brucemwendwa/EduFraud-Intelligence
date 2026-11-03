import { Lock, MapPin } from 'lucide-react';
import { Tooltip } from './Menu';

/** Coarse location (city, country). Hidden unless the viewer holds `location:read`. */
export function LocationText({ location, restricted }: { location: string | null | undefined; restricted: boolean }) {
  if (restricted) {
    return (
      <Tooltip content="Location is restricted to roles with location access. It is recorded only from authorised transaction and sign-in events.">
        <span className="inline-flex items-center gap-1 text-xs text-slate-400" tabIndex={0}>
          <Lock className="size-3" aria-hidden /> Restricted
        </span>
      </Tooltip>
    );
  }
  if (!location) return <span className="text-xs text-slate-400">—</span>;
  return (
    <span className="inline-flex items-center gap-1 whitespace-nowrap">
      <MapPin className="size-3 text-slate-400" aria-hidden />
      {location}
    </span>
  );
}
