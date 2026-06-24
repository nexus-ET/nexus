import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { getStoredToken, isValidTokenFormat, isTokenExpired } from '../utils/api';

interface ProtectedRouteProps {
  children: React.ReactNode;
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
  const location = useLocation();
  const token = getStoredToken();

  if (!isValidTokenFormat(token) || isTokenExpired(token)) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <>{children}</>;
};

export default ProtectedRoute;
