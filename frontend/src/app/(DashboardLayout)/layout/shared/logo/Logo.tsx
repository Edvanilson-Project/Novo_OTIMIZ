'use client'
import { CustomizerContext } from "@/app/context/customizerContext";
import Link from "next/link";
import { styled } from "@mui/material/styles";
import config from '@/app/context/config'
import Image from "next/image";
import { useContext } from "react";

interface LinkStyledProps {
  $isCollapse: string;
  $isSidebarHover: boolean;
  $topbarHeight: number;
}

const LinkStyled = styled(Link)<LinkStyledProps>(({ $isCollapse, $isSidebarHover, $topbarHeight }) => ({
  height: $topbarHeight,
  width: $isCollapse == "mini-sidebar" && !$isSidebarHover ? '40px' : '180px',
  overflow: "hidden",
  display: "block",
}));

const Logo = () => {
  const { isCollapse, isSidebarHover, activeDir, activeMode } = useContext(CustomizerContext);
  const TopbarHeight = config.topbarHeight;

  if (activeDir === "ltr") {
    return (
      <LinkStyled href="/" $isCollapse={isCollapse} $isSidebarHover={isSidebarHover} $topbarHeight={TopbarHeight}>
        {activeMode === "dark" ? (
          <Image
            src="/images/logos/light-logo.svg"
            alt="logo"
            height={TopbarHeight}
            width={174}
            priority
          />
        ) : (
          <Image
            src={"/images/logos/dark-logo.svg"}
            alt="logo"
            height={TopbarHeight}
            width={174}
            priority
          />
        )}
      </LinkStyled>
    );
  }

  return (
    <LinkStyled href="/" $isCollapse={isCollapse} $isSidebarHover={isSidebarHover} $topbarHeight={TopbarHeight}>
      {activeMode === "dark" ? (
        <Image
          src="/images/logos/dark-rtl-logo.svg"
          alt="logo"
          height={TopbarHeight}
          width={174}
          priority
        />
      ) : (
        <Image
          src="/images/logos/light-logo-rtl.svg"
          alt="logo"
          height={TopbarHeight}
          width={174}
          priority
        />
      )}
    </LinkStyled>
  );
};

export default Logo;
