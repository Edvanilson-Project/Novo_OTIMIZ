import React, { useContext } from "react";
import Link from "next/link";

// mui imports
import Chip from "@mui/material/Chip";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import { Theme } from "@mui/material/styles";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { CustomizerContext } from "@/app/context/customizerContext";
import { useTranslation } from "react-i18next";

export default function NavItem({
  item,
  level,
  pathDirect,
  hideMenu,
  onClick,
}: any) {
  const lgDown = useMediaQuery((theme: Theme) => theme.breakpoints.down("lg"));
  const { isBorderRadius } = useContext(CustomizerContext) as any;
  const Icon = item?.icon;
  const theme = useTheme();
  const { t } = useTranslation();

  const itemIcon = Icon ? (
    (level ?? 1) > 1 ? (
      <Icon stroke={1.5} size="1rem" />
    ) : (
      <Icon stroke={1.5} size="1.3rem" />
    )
  ) : null;

  const isSelected = pathDirect === item?.href;
  const lvl = level ?? 1;

  return (
    <List component="li" disablePadding key={item?.id && item.title}>
      <Link href={item.href || ""} passHref legacyBehavior>
        <ListItemButton
          component="a"
          disabled={item?.disabled}
          selected={isSelected}
          onClick={lgDown ? onClick : undefined}
          sx={{
            whiteSpace: "nowrap",
            marginBottom: "2px",
            padding: "8px 10px",
            borderRadius: `${isBorderRadius}px`,
            backgroundColor:
              lvl > 1 ? "transparent !important" : "inherit",
            color:
              lvl > 1 && isSelected
                ? `${theme.palette.primary.main}!important`
                : theme.palette.text.secondary,
            "&:hover": {
              backgroundColor: theme.palette.primary.light,
              color: theme.palette.primary.main,
            },
            "&.Mui-selected": {
              color: "white",
              backgroundColor: theme.palette.primary.main,
              "&:hover": {
                backgroundColor: theme.palette.primary.main,
                color: "white",
              },
            },
          }}
        >
          <ListItemIcon
            sx={{
              minWidth: "36px",
              p: "3px 0",
              color:
                lvl > 1 && isSelected
                  ? `${theme.palette.primary.main}!important`
                  : "inherit",
            }}
          >
            {itemIcon}
          </ListItemIcon>
          <ListItemText>
            {hideMenu ? "" : <>{t(`${item?.title}`)}</>}
            <br />
            {item?.subtitle ? (
              <Typography variant="caption">
                {hideMenu ? "" : item?.subtitle}
              </Typography>
            ) : (
              ""
            )}
          </ListItemText>

          {!item?.chip || hideMenu ? null : (
            <Chip
              color={
                (item?.chipColor as
                  | "default"
                  | "error"
                  | "primary"
                  | "secondary"
                  | "info"
                  | "success"
                  | "warning") || "default"
              }
              variant={
                (item?.variant as "filled" | "outlined") || "filled"
              }
              size="small"
              label={item?.chip}
            />
          )}
        </ListItemButton>
      </Link>
    </List>
  );
}
