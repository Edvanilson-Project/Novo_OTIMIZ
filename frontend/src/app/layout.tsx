import type { Metadata } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";
import ThemeProviders from "./context/ThemeProviders";
import EmotionRegistry from "./context/EmotionRegistry";

const plusJakartaSans = Plus_Jakarta_Sans({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-plus-jakarta",
});

export const metadata: Metadata = {
  title: "OTIMIZ - SaaS de Otimização de Transportes",
  description: "Plataforma avançada de otimização de frota e tripulação",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-br" suppressHydrationWarning>
      <body className={plusJakartaSans.variable}>
        <EmotionRegistry>
          <ThemeProviders>
            {children}
          </ThemeProviders>
        </EmotionRegistry>
      </body>
    </html>
  );
}
