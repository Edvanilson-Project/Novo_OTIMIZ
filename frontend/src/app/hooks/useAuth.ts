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
    const u = getSessionUser();
    const token = typeof window !== 'undefined' ? localStorage.getItem('otimiz_token') : null;

    if (!u || !token) {
      router.replace('/auth/login');
      return;
    }

    if (requiredRole && ROLE_RANK[u.role as AppRole] < ROLE_RANK[requiredRole]) {
      router.replace('/dashboard');
      return;
    }

    setUser(u);
    setChecked(true);
  }, [router, requiredRole]);

  const hasRole = (min: AppRole) =>
    user ? ROLE_RANK[user.role as AppRole] >= ROLE_RANK[min] : false;

  return { user, checked, hasRole };
}
