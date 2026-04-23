"use client";
import { FC, useState, useContext } from "react";
import {
  Divider, Drawer, Fab, IconButton, Slider, Stack,
  Tooltip, Typography, Box,
} from "@mui/material";
import { styled } from "@mui/material/styles";
import { CustomizerContext } from "@/app/context/customizerContext";
import { IconX, IconSettings, IconCheck } from "@tabler/icons-react";
import Scrollbar from "@/app/components/custom-scroll/Scrollbar";

const SidebarWidth = "320px";

const StyledBox = styled(Box)(({ theme }) => ({
  boxShadow: theme.shadows[8],
  padding: "16px",
  cursor: "pointer",
  justifyContent: "center",
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  gap: "6px",
  flex: 1,
  transition: "0.1s ease-in",
  border: "1px solid rgba(145, 158, 171, 0.12)",
  borderRadius: theme.shape.borderRadius,
  "&:hover": { transform: "scale(1.03)" },
}));

const thColors = [
  { id: 1, bgColor: "#5D87FF", disp: "BLUE_THEME", label: "Azul" },
  { id: 2, bgColor: "#0074BA", disp: "AQUA_THEME", label: "Aqua" },
  { id: 3, bgColor: "#763EBD", disp: "PURPLE_THEME", label: "Roxo" },
  { id: 4, bgColor: "#0A7EA4", disp: "GREEN_THEME", label: "Verde" },
  { id: 5, bgColor: "#FA896B", disp: "ORANGE_THEME", label: "Laranja" },
];

const Row = ({ children }: { children: React.ReactNode }) => (
  <Stack direction="row" sx={{ gap: 2, my: 2 }}>{children}</Stack>
);

const Customizer: FC = () => {
  const [showDrawer, setShowDrawer] = useState(false);
  const {
    activeMode, setActiveMode,
    isCollapse, setIsCollapse,
    activeTheme, setActiveTheme,
    isLayout, setIsLayout,
    isCardShadow, setIsCardShadow,
    isBorderRadius, setIsBorderRadius,
  } = useContext(CustomizerContext);

  return (
    <>
      <Tooltip title="Configurações de Tema">
        <Fab
          color="secondary"
          aria-label="settings"
          sx={{ position: "fixed", right: "25px", bottom: "15px", zIndex: 1200 }}
          onClick={() => setShowDrawer(true)}
        >
          <IconSettings stroke={1.5} size={20} />
        </Fab>
      </Tooltip>

      <Drawer
        anchor="right"
        open={showDrawer}
        onClose={() => setShowDrawer(false)}
        slotProps={{ paper: { sx: { width: SidebarWidth } } }}
      >
        <Scrollbar sx={{ height: "calc(100vh - 5px)" }}>
          <Box sx={{ p: 2, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <Typography variant="h4">Configurações</Typography>
            <IconButton color="inherit" onClick={() => setShowDrawer(false)}>
              <IconX size="1rem" />
            </IconButton>
          </Box>
          <Divider />

          <Box sx={{ p: 3 }}>
            {/* ── Modo Claro / Escuro ── */}
            <Typography variant="h6" gutterBottom>Modo de Cor</Typography>
            <Row>
              <StyledBox onClick={() => setActiveMode("light")}>
                <Typography variant="caption">☀️ Claro</Typography>
                {activeMode === "light" && <IconCheck size={14} color="#5D87FF" />}
              </StyledBox>
              <StyledBox onClick={() => setActiveMode("dark")}>
                <Typography variant="caption">🌙 Escuro</Typography>
                {activeMode === "dark" && <IconCheck size={14} color="#5D87FF" />}
              </StyledBox>
            </Row>

            <Box sx={{ pt: 2 }} />

            {/* ── Cores do Tema ── */}
            <Typography variant="h6" gutterBottom>Cor do Tema</Typography>
            <Stack direction="row" sx={{ gap: 1.5, my: 2, flexWrap: "wrap" }}>
              {thColors.map((c) => (
                <Tooltip key={c.id} title={c.label} placement="top">
                  <Box
                    onClick={() => setActiveTheme(c.disp)}
                    sx={{
                      width: 36, height: 36, borderRadius: "50%",
                      backgroundColor: c.bgColor, cursor: "pointer",
                      border: activeTheme === c.disp ? "3px solid #fff" : "3px solid transparent",
                      boxShadow: activeTheme === c.disp ? `0 0 0 3px ${c.bgColor}` : "none",
                      transition: "all 0.2s",
                      "&:hover": { transform: "scale(1.15)" },
                      display: "flex", alignItems: "center", justifyContent: "center",
                    }}
                  >
                    {activeTheme === c.disp && <IconCheck size={14} color="#fff" />}
                  </Box>
                </Tooltip>
              ))}
            </Stack>

            <Box sx={{ pt: 3 }} />

            {/* ── Container: Boxed / Full ── */}
            <Typography variant="h6" gutterBottom>Container</Typography>
            <Row>
              <StyledBox onClick={() => setIsLayout("boxed")}>
                <Typography variant="caption" color={isLayout === "boxed" ? "primary" : "text.secondary"}>
                  ▣ Boxed
                </Typography>
                {isLayout === "boxed" && <IconCheck size={14} color="#5D87FF" />}
              </StyledBox>
              <StyledBox onClick={() => setIsLayout("full")}>
                <Typography variant="caption" color={isLayout === "full" ? "primary" : "text.secondary"}>
                  ⬜ Full Width
                </Typography>
                {isLayout === "full" && <IconCheck size={14} color="#5D87FF" />}
              </StyledBox>
            </Row>

            <Box sx={{ pt: 3 }} />

            {/* ── Sidebar: Full / Mini ── */}
            <Typography variant="h6" gutterBottom>Sidebar</Typography>
            <Row>
              <StyledBox onClick={() => setIsCollapse("full-sidebar")}>
                <Typography variant="caption" color={isCollapse === "full-sidebar" ? "primary" : "text.secondary"}>
                  ▦ Full
                </Typography>
                {isCollapse === "full-sidebar" && <IconCheck size={14} color="#5D87FF" />}
              </StyledBox>
              <StyledBox onClick={() => setIsCollapse("mini-sidebar")}>
                <Typography variant="caption" color={isCollapse === "mini-sidebar" ? "primary" : "text.secondary"}>
                  ◫ Mini
                </Typography>
                {isCollapse === "mini-sidebar" && <IconCheck size={14} color="#5D87FF" />}
              </StyledBox>
            </Row>

            <Box sx={{ pt: 3 }} />

            {/* ── Sombra nos Cards ── */}
            <Typography variant="h6" gutterBottom>Sombra nos Cards</Typography>
            <Row>
              <StyledBox onClick={() => setIsCardShadow(true)}>
                <Typography variant="caption" color={isCardShadow ? "primary" : "text.secondary"}>
                  Ativada
                </Typography>
                {isCardShadow && <IconCheck size={14} color="#5D87FF" />}
              </StyledBox>
              <StyledBox onClick={() => setIsCardShadow(false)}>
                <Typography variant="caption" color={!isCardShadow ? "primary" : "text.secondary"}>
                  Desativada
                </Typography>
                {!isCardShadow && <IconCheck size={14} color="#5D87FF" />}
              </StyledBox>
            </Row>

            <Box sx={{ pt: 3 }} />

            {/* ── Raio de Borda ── */}
            <Typography variant="h6" gutterBottom>
              Raio de Borda: <strong>{isBorderRadius}px</strong>
            </Typography>
            <Slider
              size="small"
              value={isBorderRadius}
              aria-label="Border radius"
              min={4}
              max={24}
              onChange={(_, v) => setIsBorderRadius(v as number)}
              sx={{ mt: 2 }}
            />
          </Box>
        </Scrollbar>
      </Drawer>
    </>
  );
};

export default Customizer;
