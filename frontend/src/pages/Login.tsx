import React, { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Lock, Mail, Loader2, Eye, EyeOff, ShieldCheck } from 'lucide-react';
import NexusLogo from '../components/NexusLogo';
import {
  consumePostLoginRedirect,
  isSafeInternalPath,
  isValidTokenFormat,
  resolveBaseUrl,
  setSessionToken,
} from '../utils/api';

const Login: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);

    try {
      const formData = new URLSearchParams();
      formData.append('username', email);
      formData.append('password', password);

      const finalUrl = `${resolveBaseUrl()}/login`;

      const response = await fetch(finalUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'ngrok-skip-browser-warning': 'true',
        },
        body: formData,
      });

      if (!response.ok) {
        throw new Error('Invalid email or password');
      }

      const data = await response.json();
      const accessToken = data.access_token;

      if (!isValidTokenFormat(accessToken)) {
        throw new Error('Login succeeded but no valid session token was returned.');
      }

      setSessionToken(accessToken);
      const fromState =
        location.state &&
        typeof location.state === 'object' &&
        'from' in location.state &&
        typeof (location.state as { from?: unknown }).from === 'string'
          ? (location.state as { from: string }).from
          : '';
      const returnTo = consumePostLoginRedirect() || fromState;
      navigate(isSafeInternalPath(returnTo) ? returnTo : '/', { replace: true });
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'An error occurred during login authentication.';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen w-full flex-col bg-surface-bg text-text-main lg:flex-row">
      {/* Left — brand & context (Nexus palette) */}
      <aside
        className="relative flex w-full flex-col justify-between overflow-hidden border-b border-border-subtle/40 px-8 py-8 font-inter text-text-dark-bg sm:px-12 sm:py-10 lg:w-[48%] lg:border-b-0 lg:border-r lg:px-12 lg:py-12 xl:w-1/2"
        style={{
          background:
            'linear-gradient(145deg, #322f86 0%, #2a2770 42%, #386fa4 100%)',
        }}
      >
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.12]"
          style={{
            backgroundImage:
              'radial-gradient(circle at 18% 22%, #84d2f6 0%, transparent 42%), radial-gradient(circle at 88% 78%, #59a5d8 0%, transparent 36%)',
          }}
          aria-hidden
        />

        <div className="relative z-10 space-y-1.5">
          <h1 className="flex items-center gap-3 font-inter text-3xl font-extrabold tracking-tight text-text-dark-bg lg:text-4xl">
            <NexusLogo size={48} className="lg:hidden" />
            <NexusLogo size={56} className="hidden lg:block" />
            <span className="drop-shadow-sm">Nexus Intel</span>
          </h1>
          <p className="pl-[3.75rem] font-inter text-xs font-medium uppercase tracking-wider text-[#84d2f6] lg:pl-[4.25rem] lg:text-sm">
            FlowX Operational Core
          </p>
        </div>

        <div className="relative z-10 my-10 max-w-xl space-y-4 lg:my-auto lg:space-y-5">
          <h2 className="font-inter text-4xl font-extrabold leading-[1.15] tracking-tight text-text-dark-bg lg:text-5xl">
            Empowering Global Education Consultancies
          </h2>
          <p className="font-inter text-sm font-medium leading-relaxed text-white/85 lg:text-base">
            Manage cross-regional student journeys, SLA workflows, and universal applications with
            total precision.
          </p>
          <p className="font-inter text-xs font-normal leading-relaxed text-white/70 lg:text-sm">
            Nexus Intel is the operational core built specifically for modern education
            consultancies. Powered by the FlowX engine, it unifies cross-regional student
            recruitment, strict SLA-governed milestone tracking, and multi-pathway global
            applications into a single, intelligent workspace. Scale your operations, eliminate
            administrative bottlenecks, and deliver flawless guidance from inquiry to enrollment.
          </p>
        </div>

        <div className="relative z-10 flex items-center gap-3 font-inter text-xs font-medium text-[#b8e0f5] lg:text-sm">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#59a5d8] opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-[#59a5d8]" />
          </span>
          <span>All Systems Operational · FlowX Core v2.4</span>
        </div>
      </aside>

      {/* Right — authentication */}
      <div className="flex w-full flex-1 flex-col justify-between bg-surface-bg px-6 py-10 sm:px-10 lg:w-[52%] lg:px-12 lg:py-12 xl:w-1/2 xl:px-16">
        <div className="mx-auto my-auto w-full max-w-xl space-y-8">
          <div>
            <h2 className="text-3xl font-bold tracking-tight text-text-main sm:text-4xl">
              Sign in to Nexus Intel
            </h2>
            <p className="mt-2 text-base text-text-muted sm:text-lg">
              Enter your credentials to manage your student pipelines.
            </p>
          </div>

          <div className="rounded-2xl border border-border-subtle/60 bg-card p-8 shadow-sm sm:p-10 lg:p-12">
            <form className="space-y-6" onSubmit={e => void handleLogin(e)}>
              {error ? (
                <div className="animate-in fade-in rounded-lg border-l-4 border-alert bg-alert/10 p-3.5 text-sm font-bold text-alert duration-200">
                  {error}
                </div>
              ) : null}

              <div className="space-y-2.5">
                <label className="block text-sm font-semibold uppercase tracking-wide text-text-muted">
                  Login ID / Email
                </label>
                <div className="relative group">
                  <Mail className="absolute left-3.5 top-4 h-5 w-5 text-text-muted/60 transition-colors group-focus-within:text-accent" />
                  <input
                    type="email"
                    name="username"
                    autoComplete="username"
                    required
                    className="block w-full appearance-none rounded-xl border border-border-subtle bg-surface-bg py-4 pl-12 pr-3 text-base text-text-main placeholder:text-text-muted/50 transition-all focus:border-accent focus:bg-card focus:outline-none focus:ring-4 focus:ring-accent/10"
                    placeholder="you@consultancy.com"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                  />
                </div>
              </div>

              <div className="space-y-2.5">
                <div className="flex items-center justify-between gap-2">
                  <label className="block text-sm font-semibold uppercase tracking-wide text-text-muted">
                    Password
                  </label>
                  <a
                    href="mailto:admin@edutrust.in?subject=Nexus%20password%20reset"
                    className="text-sm font-semibold text-text-muted hover:text-accent"
                  >
                    Forgot Password?
                  </a>
                </div>
                <div className="relative group">
                  <Lock className="absolute left-3.5 top-4 h-5 w-5 text-text-muted/60 transition-colors group-focus-within:text-accent" />
                  <input
                    type={showPassword ? 'text' : 'password'}
                    name="password"
                    autoComplete="current-password"
                    required
                    className="block w-full appearance-none rounded-xl border border-border-subtle bg-surface-bg py-4 pl-12 pr-12 text-base text-text-main placeholder:text-text-muted/50 transition-all focus:border-accent focus:bg-card focus:outline-none focus:ring-4 focus:ring-accent/10"
                    placeholder="Password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(prev => !prev)}
                    className="absolute right-3.5 top-4 text-text-muted/60 transition-colors hover:text-text-main focus:text-accent focus:outline-none"
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={isLoading}
                className="group relative flex w-full items-center justify-center rounded-xl border border-transparent bg-accent px-4 py-4 text-base font-bold text-text-dark-bg shadow-md shadow-accent/10 transition-all hover:opacity-90 focus:outline-none focus:ring-4 focus:ring-accent/20 active:scale-[0.99] disabled:pointer-events-none disabled:opacity-40"
              >
                {isLoading ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                  'Sign In'
                )}
              </button>
            </form>
          </div>

          <p className="text-center text-sm text-text-muted sm:text-base">
            Need access?{' '}
            <a
              href="mailto:admin@edutrust.in?subject=Nexus%20access%20request"
              className="font-semibold text-accent hover:underline"
            >
              Contact Admin
            </a>
          </p>
        </div>

        <div className="mx-auto mt-10 flex max-w-xl flex-col items-center gap-2 text-center text-sm text-text-muted sm:mt-8">
          <div className="inline-flex items-center gap-1.5 font-medium">
            <ShieldCheck className="h-4 w-4 text-accent" />
            <span>Secure sign-in · TLS-protected connection · Role-based access</span>
          </div>
          <p className="text-xs text-text-muted/80">Enterprise workspace authentication</p>
          <p className="text-xs text-text-muted/70">
            © {new Date().getFullYear()} Nexus Intel. All rights reserved.
          </p>
        </div>
      </div>
    </div>
  );
};

export default Login;
