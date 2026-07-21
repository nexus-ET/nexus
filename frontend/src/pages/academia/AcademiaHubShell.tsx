import { Navigate, useOutletContext } from 'react-router-dom';
import { canAccessAcademiaHub } from '../../utils/academiaAccess';
import { isAllowedRoute } from '../../utils/routeAccess';
import AcademiaHubLayout from '../../components/academia/AcademiaHubLayout';

interface AcademiaHubShellContext {
  currentUser?: {
    role?: string | null;
    admin_role?: { name?: string | null } | null;
    is_superuser?: boolean;
  } | null;
  allowedRoutes?: string[] | null;
  /** False until users/me + permissions have resolved — avoid bouncing deep links to `/`. */
  sessionReady?: boolean;
  onOpenAcademiaCommandPalette?: () => void;
}

const AcademiaHubShell: React.FC = () => {
  const context = useOutletContext<AcademiaHubShellContext>();

  if (context?.sessionReady === false) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-text-muted">Loading…</div>
    );
  }

  if (!canAccessAcademiaHub(context?.currentUser)) {
    return <Navigate to="/" replace />;
  }

  if (context?.allowedRoutes && !isAllowedRoute('/academia', context.allowedRoutes)) {
    return <Navigate to="/" replace />;
  }

  return <AcademiaHubLayout onOpenCommandPalette={context?.onOpenAcademiaCommandPalette} />;
};

export default AcademiaHubShell;
