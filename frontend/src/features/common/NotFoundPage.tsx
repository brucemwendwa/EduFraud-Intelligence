import { Compass } from 'lucide-react';
import { Link } from 'react-router';
import { EmptyState } from '@/components/ui/States';

export function NotFoundPage() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <EmptyState
        icon={<Compass className="size-5" />}
        title="Page not found"
        description="The page you are looking for does not exist or you do not have access to it."
        action={
          <Link to="/app" className="text-sm font-medium text-brand-blue hover:underline">
            Back to dashboard
          </Link>
        }
      />
    </div>
  );
}
