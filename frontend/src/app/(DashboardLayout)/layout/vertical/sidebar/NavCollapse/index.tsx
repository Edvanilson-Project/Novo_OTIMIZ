import React, { useContext, useState } from "react";


import { CustomizerContext } from "@/app/context/customizerContext";

import { usePathname } from "next/navigation";

// mui imports
import Collapse from '@mui/material/Collapse';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import { Theme } from '@mui/material/styles';
import useMediaQuery from '@mui/material/useMediaQuery';
import { styled, useTheme } from '@mui/material/styles';

// custom imports
import NavItem from "../NavItem";
import { isNull } from "lodash";

// plugins
import { IconChevronDown, IconChevronUp } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";



interface ListItemStyledProps {
  $level: number;
  $open: boolean;
  $isBorderRadius: number;
  $hideMenu: boolean;
}

const ListItemStyled = styled(ListItemButton)<ListItemStyledProps>(({ theme, $level, $open, $isBorderRadius, $hideMenu }) => ({
  marginBottom: "2px",
  padding: "8px 10px",
  paddingLeft: $hideMenu ? "10px" : $level > 2 ? `${$level * 15}px` : "10px",
  backgroundColor: $open && $level < 2 ? theme.palette.primary.main : "",
  whiteSpace: "nowrap",
  "&:hover": {
    backgroundColor: $open
      ? theme.palette.primary.main
      : theme.palette.primary.light,
    color: $open
      ? "white"
      : theme.palette.primary.main,
  },
  color:
    $open && $level < 2
      ? "white"
      : $level > 1 && $open
        ? theme.palette.primary.main
        : theme.palette.text.secondary,
  borderRadius: `${$isBorderRadius}px`,
}));

// FC Component For Dropdown Menu
export default function NavCollapse({
  menu,
  level,
  pathWithoutLastPart,
  pathDirect,
  hideMenu,
  onClick,
}: any) {
  const lgDown = useMediaQuery((theme: Theme) => theme.breakpoints.down("lg"));

  const { isBorderRadius } = useContext(CustomizerContext);
  const Icon = menu?.icon;
  const theme = useTheme();
  const pathname = usePathname();
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);



  const menuIcon = Icon ? (
    level > 1 ? <Icon stroke={1.5} size="1rem" /> : <Icon stroke={1.5} size="1.3rem" />
  ) : null;



  const handleClick = () => {
    setOpen(!open);
  };

  // menu collapse for sub-levels
  React.useEffect(() => {
    setOpen(false);
    menu?.children?.forEach((item: any) => {
      if (item?.href === pathname) {
        setOpen(true);
      }
    });
  }, [pathname, menu.children]);

  // If Menu has Children
  const submenus = menu.children?.map((item: any) => {
    if (item.children) {
      return (
        <NavCollapse
          key={item?.id}
          menu={item}
          level={level + 1}
          pathWithoutLastPart={pathWithoutLastPart}
          pathDirect={pathDirect}
          hideMenu={hideMenu}
          onClick={onClick}
        />
      );
    } else {
      return (
        <NavItem
          key={item.id}
          item={item}
          level={level + 1}
          pathDirect={pathDirect}
          hideMenu={hideMenu}
          onClick={lgDown ? onClick : isNull}
        />
      );
    }
  });

  return (
    <>
      <ListItemStyled
        onClick={handleClick}
        selected={pathWithoutLastPart === menu.href}
        key={menu?.id}
        $level={level}
        $open={open}
        $isBorderRadius={isBorderRadius}
        $hideMenu={!!hideMenu}
      >
        <ListItemIcon
          sx={{
            minWidth: "36px",
            p: "3px 0",
            color: "inherit",
          }}
        >
          {menuIcon}
        </ListItemIcon>
        <ListItemText color="inherit">
          {hideMenu ? "" : <>{t(`${menu.title}`)}</>}
        </ListItemText>
        {!open ? (
          <IconChevronDown size="1rem" />
        ) : (
          <IconChevronUp size="1rem" />
        )}
      </ListItemStyled>
      <Collapse in={open} timeout="auto">
        {submenus}
      </Collapse>
    </>
  );
}
