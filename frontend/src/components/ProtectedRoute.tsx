import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import {
  getStoredToken,
  isValidTokenFormat,
  isTokenExpired,
  rememberPostLoginRedirect,
} from '../utils/api';

interface ProtectedRouteProps {
  children: React.ReactNode;
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
  const location = useLocation();
  const token = getStoredToken();

  if (!isValidTokenFormat(token) || isTokenExpired(token)) {
    const from = `${location.pathname}${location.search}${location.hash}`;
    rememberPostLoginRedirect(from);
    return <Navigate to="/login" replace state={{ from }} />;
  }

  return <>{children}</>;
};

export default ProtectedRoute;
