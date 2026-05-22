'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getSessionUser, type SessionUser } from '@/lib/api';

export type AppRole = 'super_admin' | 'company_admin' | 'analyst' | 'operator';

const ROLE_RANK: Record<AppRole, number> = {
  super_admin: 4,
  company_admin: 3,
  analyst: 2,
  operator: 1,
};

export function useAuth(requiredRole?: AppRole) {
  const router = useRouter();
  const [user, setUser] = useState<SessionUser | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    let isMounted = true;

    const checkAuth = async () => {
      const u = getSessionUser();

      if (!u) {
        if (isMounted) router.replace('/auth/login');
        return;
      }

      if (requiredRole && ROLE_RANK[u.role as AppRole] < ROLE_RANK[requiredRole]) {
        if (isMounted) router.replace('/dashboard');
        return;
      }

      if (isMounted) {
        setUser(u);
        setChecked(true);
      }
    };

    checkAuth();

    return () => {
      isMounted = false;
    };
  }, [router, requiredRole]);

  const hasRole = (min: AppRole) =>
    user ? ROLE_RANK[user.role as AppRole] >= ROLE_RANK[min] : false;

  return { user, checked, hasRole };
}
