import Menuitems, { type MenuitemsType } from './MenuItems';
import { usePathname } from "next/navigation";
import Box from '@mui/material/Box';
import List from '@mui/material/List';
import useMediaQuery from '@mui/material/useMediaQuery';
import { CustomizerContext } from '@/app/context/customizerContext';
import NavItem from './NavItem';
import NavCollapse from './NavCollapse';
import NavGroup from './NavGroup/NavGroup';
import { useContext, useEffect, useState } from 'react';
import { getSessionUser } from '@/lib/api';

const ROLE_RANK: Record<string, number> = {
  super_admin: 4,
  company_admin: 3,
  analyst: 2,
  operator: 1,
};

function isAllowed(item: MenuitemsType, userRole: string): boolean {
  if (!item.allowedRoles || item.allowedRoles.length === 0) return true;
  const rank = ROLE_RANK[userRole] ?? 0;
  return item.allowedRoles.some((r) => ROLE_RANK[r] <= rank + 0 && userRole === r || item.allowedRoles!.includes(userRole));
}

const SidebarItems = () => {
  const pathname = usePathname();
  const pathDirect = pathname;
  const pathWithoutLastPart = pathname.slice(0, pathname.lastIndexOf('/'));
  const { isSidebarHover, isCollapse, isMobileSidebar, setIsMobileSidebar } = useContext(CustomizerContext);
  const [userRole, setUserRole] = useState<string>('operator');

  useEffect(() => {
    const u = getSessionUser();
    if (u?.role) setUserRole(u.role);
  }, []);

  const lgUp = useMediaQuery((theme) => theme.breakpoints.up('lg'));
  const hideMenu = lgUp ? isCollapse == "mini-sidebar" && !isSidebarHover : '';

  // Filtra itens pela role do usuário, removendo navlabels órfãos
  const visibleItems = (() => {
    const filtered: MenuitemsType[] = [];
    let pendingLabel: MenuitemsType | null = null;

    for (const item of Menuitems) {
      if (item.navlabel) {
        pendingLabel = item;
        continue;
      }
      if (!isAllowed(item, userRole)) continue;
      if (pendingLabel) {
        filtered.push(pendingLabel);
        pendingLabel = null;
      }
      filtered.push(item);
    }
    return filtered;
  })();

  return (
    <Box sx={{ px: 3 }}>
      <List sx={{ pt: 0 }} className="sidebarNav">
        {visibleItems.map((item) => {
          if (item.subheader) {
            return <NavGroup item={item} hideMenu={hideMenu} key={item.subheader} />;
          } else if (item.children) {
            return (
              <NavCollapse
                menu={item}
                pathDirect={pathDirect}
                hideMenu={hideMenu}
                pathWithoutLastPart={pathWithoutLastPart}
                level={1}
                key={item.id}
                onClick={() => setIsMobileSidebar(!isMobileSidebar)}
              />
            );
          } else {
            return (
              <NavItem item={item} key={item.id} pathDirect={pathDirect} hideMenu={hideMenu} onClick={() => setIsMobileSidebar(!isMobileSidebar)} />
            );
          }
        })}
      </List>
    </Box>
  );
};
export default SidebarItems;
