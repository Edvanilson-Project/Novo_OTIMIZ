import type React from "react";
import {
  IconAperture,
  IconSettings,
  IconRoute,
  IconUsers,
  IconAdjustmentsHorizontal,
  IconUpload,
  IconBuilding,
  IconHelp,
  IconMapPin,
  IconShieldCheck,
  IconChartBar,
  IconWand,
  IconTruck,
  IconCalendarTime,
  IconReportAnalytics,
  IconCalendarStats,
} from "@tabler/icons-react";
import { uniqueId } from "lodash";

export interface MenuitemsType {
  [x: string]: unknown;
  id?: string;
  navlabel?: boolean;
  subheader?: string;
  title?: string;
  icon?: React.ElementType;
  href?: string;
  children?: MenuitemsType[];
  chip?: string;
  chipColor?: string;
  variant?: string;
  external?: boolean;
  disabled?: boolean;
  subtitle?: string;
  /** Roles mínimas para ver este item. Undefined = todos os usuários autenticados. */
  allowedRoles?: string[];
}

const Menuitems: MenuitemsType[] = [
  {
    navlabel: true,
    subheader: "Operação",
  },
  {
    id: uniqueId(),
    title: "Dashboard",
    icon: IconAperture,
    href: "/dashboard",
  },
  {
    id: uniqueId(),
    title: "Importar Viagens (CSV)",
    icon: IconUpload,
    href: "/operations/data",
  },
  {
    id: uniqueId(),
    title: "Cadastro de Linhas",
    icon: IconRoute,
    href: "/operations/lines",
  },
  {
    id: uniqueId(),
    title: "Cadastro de Terminais",
    icon: IconMapPin,
    href: "/operations/terminals",
  },
  {
    id: uniqueId(),
    title: "Planejador (Gantt)",
    icon: IconCalendarTime,
    href: "/operations/planner",
  },
  {
    id: uniqueId(),
    title: "Escala Semanal",
    icon: IconCalendarStats,
    href: "/operations/rostering",
  },
  {
    id: uniqueId(),
    title: "Análises What-If",
    icon: IconWand,
    href: "/operations/advanced-optimization",
  },
  {
    id: uniqueId(),
    title: "Mapa Operacional",
    icon: IconMapPin,
    href: "/operations/map",
  },
  {
    id: uniqueId(),
    title: "Analytics & Relatórios",
    icon: IconChartBar,
    href: "/operations/reporting",
  },
  {
    id: uniqueId(),
    title: "Relatórios Customizados",
    icon: IconReportAnalytics,
    href: "/operations/reporting/custom",
  },
  {
    navlabel: true,
    subheader: "Configurações",
  },
  {
    id: uniqueId(),
    title: "Parâmetros CCT",
    icon: IconAdjustmentsHorizontal,
    href: "/settings/parameters",
    allowedRoles: ["super_admin", "company_admin", "analyst"],
  },
  {
    id: uniqueId(),
    title: "Frota & Manutenção",
    icon: IconTruck,
    href: "/settings/fleet",
  },
  {
    id: uniqueId(),
    title: "Empresas",
    icon: IconBuilding,
    href: "/settings/companies",
    allowedRoles: ["super_admin"],
  },
  {
    id: uniqueId(),
    title: "Usuários",
    icon: IconUsers,
    href: "/settings/users",
    allowedRoles: ["super_admin", "company_admin"],
  },
  {
    id: uniqueId(),
    title: "Controle de Acesso",
    icon: IconShieldCheck,
    href: "/settings/access",
    allowedRoles: ["super_admin", "company_admin"],
  },
  {
    id: uniqueId(),
    title: "Ajustes",
    icon: IconSettings,
    href: "/settings/general",
  },
  {
    navlabel: true,
    subheader: "Suporte",
  },
  {
    id: uniqueId(),
    title: "Central de Ajuda",
    icon: IconHelp,
    href: "/help",
  },
];

export default Menuitems;
