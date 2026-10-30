import { Search } from 'lucide-react';
import { useEffect, useEffectEvent, useState } from 'react';
import { Input } from './Field';

/** Text search that reports changes after the user pauses typing (avoids a request per keystroke). */
export function SearchInput({
  value,
  onChange,
  placeholder,
  label,
  delay = 300,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  label: string;
  delay?: number;
}) {
  const [draft, setDraft] = useState(value);
  const [synced, setSynced] = useState(value);
  // External resets (e.g. "Clear filters") replace the draft.
  if (value !== synced) {
    setSynced(value);
    setDraft(value);
  }

  const commit = useEffectEvent((next: string) => onChange(next));
  useEffect(() => {
    if (draft === synced) return;
    const t = window.setTimeout(() => commit(draft), delay);
    return () => window.clearTimeout(t);
  }, [draft, synced, delay]);

  return (
    <Input
      type="search"
      icon={<Search className="size-4" />}
      placeholder={placeholder}
      aria-label={label}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
    />
  );
}
