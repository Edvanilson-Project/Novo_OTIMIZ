'use client'
import { useEffect, ReactElement } from 'react';
import { usePathname } from 'next/navigation';

export default function ScrollToTop({ children }: { children: ReactElement | null }) {
  const pathname = usePathname();

  useEffect(() => {
    window.scrollTo({
      top: 0,
      left: 0,
      behavior: 'smooth',
    });
  }, [pathname]);

  return children || null;
}
