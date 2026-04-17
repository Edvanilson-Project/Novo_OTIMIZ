import ListSubheader from '@mui/material/ListSubheader';
import { Theme } from '@mui/material/styles';
import { styled } from '@mui/material/styles';
import { IconDots } from '@tabler/icons-react';
import React from 'react';

type NavGroup = {
  navlabel?: boolean;
  subheader?: string;
};

interface ItemType {
  item: NavGroup;
  hideMenu: string | boolean;
}

const ListSubheaderStyle = styled((props: any) => (
  <ListSubheader disableSticky {...props} />
))(({ theme, $hideMenu }: { theme: Theme, $hideMenu: boolean }) => ({
  ...theme.typography.overline,
  fontWeight: '700',
  marginTop: theme.spacing(3),
  marginBottom: theme.spacing(0),
  color: theme.palette.text.primary,
  lineHeight: '26px',
  padding: '3px 12px',
  marginLeft: $hideMenu ? '' : '-10px',
}));

const NavGroup = ({ item, hideMenu }: ItemType) => {

  return (
    <ListSubheaderStyle $hideMenu={!!hideMenu}>{hideMenu ? <IconDots size="14" /> : item?.subheader}</ListSubheaderStyle>
  );
};

export default NavGroup;
