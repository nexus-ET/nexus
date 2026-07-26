import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Lock, Mail, Loader2, Eye, EyeOff } from 'lucide-react';
import { isValidTokenFormat, resolveBaseUrl, setSessionToken } from '../utils/api';

const Login: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);

    try {
      // FastAPI OAuth2 expects form data (x-www-form-urlencoded)
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
      
      // Redirect to the core dashboard framework loop
      navigate('/');
    } catch (err: any) {
      setError(err.message || 'An error occurred during login authentication.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-bg px-4 transition-colors duration-300">
      <div className="max-w-md w-full space-y-8 bg-card p-10 rounded-2xl shadow-xl border border-border-subtle/50">
        <div className="text-center">
          <div className="mx-auto h-12 w-12 bg-accent rounded-xl flex items-center justify-center mb-4 shadow-md shadow-accent/20">
            <span className="text-text-dark-bg font-bold text-2xl italic tracking-tighter">N</span>
          </div>
          <h2 className="text-3xl font-black text-text-main tracking-tight">NEXUS Login</h2>
          <p className="mt-2 text-xs font-semibold text-text-muted uppercase tracking-wider">
            AI-Powered Education Intelligence
          </p>
        </div>

        <form className="mt-8 space-y-6" onSubmit={handleLogin}>
          {error && (
            <div className="bg-alert/10 border-l-4 border-alert p-4 text-alert text-xs font-bold rounded-lg animate-in fade-in duration-200">
              {error}
            </div>
          )}
          
          <div className="space-y-4">
            <div className="relative group">
              <Mail className="absolute left-3 top-3.5 h-5 w-5 text-text-muted/60 group-focus-within:text-accent transition-colors" />
              <input
                type="email"
                name="username"
                autoComplete="username"
                required
                className="appearance-none block w-full pl-10 pr-3 py-3.5 bg-surface-bg border border-border-subtle rounded-xl text-text-main placeholder:text-text-muted/50 focus:outline-none focus:bg-card focus:border-accent focus:ring-4 focus:ring-accent/10 sm:text-sm transition-all"
                placeholder="Email address"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            
            <div className="relative group">
              <Lock className="absolute left-3 top-3.5 h-5 w-5 text-text-muted/60 group-focus-within:text-accent transition-colors" />
              <input
                type={showPassword ? 'text' : 'password'}
                name="password"
                autoComplete="current-password"
                required
                className="appearance-none block w-full pl-10 pr-11 py-3.5 bg-surface-bg border border-border-subtle rounded-xl text-text-main placeholder:text-text-muted/50 focus:outline-none focus:bg-card focus:border-accent focus:ring-4 focus:ring-accent/10 sm:text-sm transition-all"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                onClick={() => setShowPassword(prev => !prev)}
                className="absolute right-3 top-3.5 text-text-muted/60 hover:text-text-main focus:outline-none focus:text-accent transition-colors"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
              </button>
            </div>
          </div>

          <div>
            <button
              type="submit"
              disabled={isLoading}
              className="group relative w-full flex justify-center py-3.5 px-4 border border-transparent text-sm font-bold rounded-xl text-text-dark-bg bg-accent hover:opacity-90 active:scale-[0.99] focus:outline-none focus:ring-4 focus:ring-accent/20 transition-all disabled:opacity-40 disabled:pointer-events-none shadow-md shadow-accent/10"
            >
              {isLoading ? (
                <Loader2 className="animate-spin h-5 w-5" />
              ) : (
                'Sign in to Nexus'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default Login;