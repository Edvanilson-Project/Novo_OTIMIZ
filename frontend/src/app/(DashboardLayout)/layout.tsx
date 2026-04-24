"use client";
import React, { useContext, useEffect, useState } from "react";
import { Box, Container, styled, useTheme } from "@mui/material";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import Header from "./layout/vertical/header/Header";
import Customizer from "./layout/shared/customizer/Customizer";
import { CustomizerContext } from "@/app/context/customizerContext";
import { getSessionUser } from "@/lib/api";

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
  minWidth: 0,
  backgroundColor: "transparent",
}));

interface Props {
  children: React.ReactNode;
}

export default function DashboardLayout({ children }: Props) {
  const { isLayout, isCollapse } = useContext(CustomizerContext);
  const theme = useTheme();
  const router = useRouter();
  const [authorized, setAuthorized] = useState(false);

  useEffect(() => {
    let isMounted = true;

    const checkAuth = () => {
      const user = getSessionUser();
      const token = localStorage.getItem('otimiz_token');
      if (!user || !token) {
        if (isMounted) router.replace('/auth/login');
      } else {
        if (isMounted) setAuthorized(true);
      }
    };

    checkAuth();

    return () => {
      isMounted = false;
    };
  }, [router]);

  if (!authorized) return null;

  return (
    <MainWrapper className="mainwrapper">
      <Sidebar />
      <PageWrapper
        className="page-wrapper"
        sx={{
          ...(isCollapse === "mini-sidebar" && {
            [theme.breakpoints.up("lg")]: { ml: "87px" },
          }),
        }}
      >
        <Header />
        <Container
          sx={{
            pt: "30px",
            maxWidth: isLayout === "boxed" ? "lg" : "100%!important",
          }}
        >
          <Box sx={{ minHeight: "calc(100vh - 170px)" }}>{children}</Box>
        </Container>
        <Customizer />
      </PageWrapper>
    </MainWrapper>
  );
}
