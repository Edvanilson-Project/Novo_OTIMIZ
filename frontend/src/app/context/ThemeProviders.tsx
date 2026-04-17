"use client";
import React from "react";
import { ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import { CustomizerContextProvider } from "./customizerContext";
import { ThemeSettings } from "@/utils/theme/Theme";

export default function ThemeProviders({ children }: { children: React.ReactNode }) {
  return (
    <CustomizerContextProvider>
      <ThemeSettingsWrapper>{children}</ThemeSettingsWrapper>
    </CustomizerContextProvider>
  );
}

function ThemeSettingsWrapper({ children }: { children: React.ReactNode }) {
  const theme = ThemeSettings();

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      {children}
    </ThemeProvider>
  );
}
