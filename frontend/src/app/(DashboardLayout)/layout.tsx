"use client";
import React, { useState } from "react";
import {
  Box, styled, Container, Fab, Dialog, DialogTitle,
  DialogContent, DialogActions, Button, Typography, Stack,
  Accordion, AccordionSummary, AccordionDetails, Tooltip,
} from "@mui/material";
import { IconQuestionMark, IconChevronDown, IconExternalLink } from "@tabler/icons-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import Header from "./layout/vertical/header/Header";

const Sidebar = dynamic(() => import("./layout/vertical/sidebar/Sidebar"), {
  ssr: false,
});

const MainWrapper = styled("div")(() => ({
  display: "flex",
  minHeight: "100vh",
  width: "100%",
}));

const PageWrapper = styled("div")(() => ({
  display: "flex",
  flexGrow: 1,
  paddingBottom: "60px",
  flexDirection: "column",
  zIndex: 1,
  backgroundColor: "transparent",
}));

// Resumo rápido dos parâmetros mais importantes exibido no FAB
const QUICK_HELP = [
  { term: "Gap", def: "Tempo ocioso entre o fim de uma viagem e o início da próxima." },
  { term: "+1 (Avanço de Dia)", def: "Viagem que cruza a meia-noite e termina no dia seguinte." },
  { term: "Pull-out / Pull-in", def: "Deslocamento vazio da garagem até a 1ª viagem e de volta." },
  { term: "Custo Fixo por Veículo", def: "Valor diário para disponibilizar um veículo, mesmo sem rodar." },
  { term: "Jornada Máxima", def: "Limite de horas contínuas de um motorista conforme a CCT." },
  { term: "What-If", def: "Arraste uma viagem no Gantt para simular o impacto no custo." },
];

interface Props {
  children: React.ReactNode;
}

export default function DashboardLayout({ children }: Props) {
  const [helpOpen, setHelpOpen] = useState(false);

  return (
    <MainWrapper className="mainwrapper">
      <Sidebar />
      <PageWrapper className="page-wrapper">
        <Header />
        <Container
          sx={{
            paddingTop: "20px",
            maxWidth: "1200px !important",
          }}
        >
          <Box sx={{ minHeight: "calc(100vh - 170px)" }}>{children}</Box>
        </Container>
      </PageWrapper>

      {/* ── FAB de Ajuda Rápida ── */}
      <Tooltip title="Ajuda Rápida" placement="left" arrow>
        <Fab
          color="primary"
          size="medium"
          onClick={() => setHelpOpen(true)}
          sx={{ position: "fixed", bottom: 32, right: 32, zIndex: 1300 }}
          aria-label="Abrir ajuda rápida"
        >
          <IconQuestionMark size={22} />
        </Fab>
      </Tooltip>

      {/* ── Modal de Ajuda Rápida ── */}
      <Dialog open={helpOpen} onClose={() => setHelpOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>
          <Stack direction="row" sx={{ alignItems: 'center' }} spacing={1}>
            <IconQuestionMark size={20} />
            <Typography sx={{ fontWeight: 700 }}>Referência Rápida</Typography>
          </Stack>
        </DialogTitle>
        <DialogContent dividers sx={{ p: 0 }}>
          {QUICK_HELP.map((item, i) => (
            <Accordion key={i} disableGutters elevation={0} sx={{ '&:before': { display: 'none' }, borderBottom: '1px solid', borderColor: 'divider' }}>
              <AccordionSummary expandIcon={<IconChevronDown size={16} />}>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>{item.term}</Typography>
              </AccordionSummary>
              <AccordionDetails sx={{ pt: 0 }}>
                <Typography variant="caption" color="text.secondary">{item.def}</Typography>
              </AccordionDetails>
            </Accordion>
          ))}
        </DialogContent>
        <DialogActions sx={{ justifyContent: "space-between", px: 2 }}>
          <Button component={Link} href="/help" size="small" endIcon={<IconExternalLink size={14} />} onClick={() => setHelpOpen(false)}>
            Ver Central de Ajuda
          </Button>
          <Button onClick={() => setHelpOpen(false)} variant="contained" size="small">Fechar</Button>
        </DialogActions>
      </Dialog>
    </MainWrapper>
  );
}
