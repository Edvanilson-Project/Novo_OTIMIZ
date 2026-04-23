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
} from "@tabler/icons-react";
import { uniqueId } from "lodash";

export interface MenuitemsType {
  [x: string]: any;
  id?: string;
  navlabel?: boolean;
  subheader?: string;
  title?: string;
  icon?: any;
  href?: string;
  children?: MenuitemsType[];
  chip?: string;
  chipColor?: string;
  variant?: string;
  external?: boolean;
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
    title: "Ingestão de Dados",
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
    title: "Gantt Planner",
    icon: IconRoute,
    href: "/operations/planner",
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
