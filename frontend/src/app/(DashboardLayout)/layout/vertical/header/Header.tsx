import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import IconButton from "@mui/material/IconButton";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { styled, type Theme } from "@mui/material/styles";
import { IconMenu2, IconChevronRight } from "@tabler/icons-react";
import { usePathname } from "next/navigation";
import Profile from "./Profile";
import { CustomizerContext } from '@/app/context/customizerContext';
import config from '@/app/context/config'
import { useContext } from "react";

const ROUTE_LABELS: Record<string, string> = {
  dashboard: "Dashboard",
  operations: "Operações",
  data: "Importar Viagens",
  lines: "Cadastro de Linhas",
  terminals: "Cadastro de Terminais",
  planner: "Planejador (Gantt)",
  rostering: "Escala Semanal",
  "advanced-optimization": "Análises What-If",
  map: "Mapa Operacional",
  reporting: "Analytics & Relatórios",
  custom: "Relatórios Customizados",
  settings: "Configurações",
  parameters: "Parâmetros CCT",
  fleet: "Frota & Manutenção",
  companies: "Empresas",
  users: "Usuários",
  access: "Controle de Acesso",
  general: "Configurações Gerais",
  help: "Ajuda",
};

const AppBarStyled = styled(AppBar)(({ theme }) => {
  const TopbarHeight = config.topbarHeight;
  return {
    boxShadow: "none",
    background: theme.palette.background.paper,
    justifyContent: "center",
    backdropFilter: "blur(4px)",
    [theme.breakpoints.up("lg")]: {
      minHeight: TopbarHeight,
    },
  };
});

const ToolbarStyled = styled(Toolbar)(({ theme }) => ({
  width: "100%",
  color: theme.palette.text.secondary,
}));

const Header = () => {
  const lgUp = useMediaQuery((theme: Theme) => theme.breakpoints.up("lg"));
  const pathname = usePathname();

  const {
    setIsCollapse,
    isCollapse,
    isMobileSidebar,
    setIsMobileSidebar
  } = useContext(CustomizerContext);

  const handleToggleSidebar = () => {
    if (lgUp) {
      if (isCollapse === "full-sidebar") {
        setIsCollapse("mini-sidebar");
      } else {
        setIsCollapse("full-sidebar");
      }
    } else {
      setIsMobileSidebar(!isMobileSidebar);
    }
  };

  // Build breadcrumb segments from path, skipping (DashboardLayout) wrapper
  const segments = pathname.split("/").filter(Boolean);
  const crumbs = segments.map((seg, i) => ({
    label: ROUTE_LABELS[seg] ?? seg,
    href: "/" + segments.slice(0, i + 1).join("/"),
    isLast: i === segments.length - 1,
  }));

  return (
    <AppBarStyled position="sticky" color="default">
      <ToolbarStyled>
        <IconButton
          color="inherit"
          aria-label="menu"
          onClick={handleToggleSidebar}
        >
          <IconMenu2 size="20" />
        </IconButton>

        {crumbs.length > 0 && (
          <Breadcrumbs
            separator={<IconChevronRight size={14} />}
            sx={{ ml: 2, "& .MuiBreadcrumbs-separator": { mx: 0.5 } }}
          >
            {crumbs.map((c) =>
              c.isLast ? (
                <Typography key={c.href} variant="body2" color="text.primary" sx={{ fontWeight: 600 }}>
                  {c.label}
                </Typography>
              ) : (
                <Link key={c.href} href={c.href} underline="hover" color="text.secondary" variant="body2">
                  {c.label}
                </Link>
              )
            )}
          </Breadcrumbs>
        )}

        <Box sx={{ flexGrow: 1 }} />

        <Stack spacing={1} direction="row" sx={{ alignItems: "center" }}>
          <Profile />
        </Stack>
      </ToolbarStyled>
    </AppBarStyled>
  );
};

export default Header;
