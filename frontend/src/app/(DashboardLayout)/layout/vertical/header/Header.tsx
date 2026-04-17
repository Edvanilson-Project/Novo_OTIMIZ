import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Toolbar from "@mui/material/Toolbar";
import useMediaQuery from "@mui/material/useMediaQuery";
import { styled } from "@mui/material/styles";
import { IconMenu2 } from "@tabler/icons-react";
import Profile from "./Profile";
import { CustomizerContext } from '@/app/context/customizerContext';
import config from '@/app/context/config'
import { useContext } from "react";

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
  const lgUp = useMediaQuery((theme: any) => theme.breakpoints.up("lg"));
  
  // drawer
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

  return (
    <AppBarStyled position="sticky" color="default">
      <ToolbarStyled>
        {/* Toggle Button Sidebar */}
        <IconButton
          color="inherit"
          aria-label="menu"
          onClick={handleToggleSidebar}
        >
          <IconMenu2 size="20" />
        </IconButton>

        <Box sx={{ flexGrow: 1 }} />

        <Stack spacing={1} direction="row" sx={{ alignItems: "center" }}>
          <Profile />
        </Stack>
      </ToolbarStyled>
    </AppBarStyled>
  );
};

export default Header;
