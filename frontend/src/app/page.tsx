import React from "react";
import { Box, Typography, Container, Button } from "@mui/material";
import Link from "next/link";

export default function Home() {
  return (
    <Container maxWidth="lg">
      <Box
        sx={{
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          gap: 3,
          textAlign: "center",
        }}
      >
        <Typography variant="h1" sx={{ fontWeight: 700 }}>
          OTIMIZ
        </Typography>
        <Typography variant="h4" sx={{ color: "textSecondary" }}>
          SaaS de Otimização de Transportes do Zero
        </Typography>
        <Typography variant="body1">
          Fundação visual (Módulo 2) concluída com Modo Escuro forçado.
        </Typography>
        <Box sx={{ display: "flex", gap: 2 }}>
          <Button variant="contained" color="primary" component={Link} href="/operations/planner">
            Iniciar Operação
          </Button>
          <Button variant="outlined" component={Link} href="/settings/parameters">
            Configurações
          </Button>
        </Box>
        <Typography variant="caption" sx={{ mt: 5 }}>
          Data do Sistema: 16 04 2026
        </Typography>
      </Box>
    </Container>
  );
}
