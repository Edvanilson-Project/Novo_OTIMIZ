import {
  IconAperture,
  IconSettings,
  IconRoute,
  IconUsers,
  IconAdjustmentsHorizontal,
  IconUpload,
  IconBuilding,
  IconHelp,
} from "@tabler/icons-react";
import { uniqueId } from "lodash";

interface MenuitemsType {
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
    href: "/",
  },
  {
    id: uniqueId(),
    title: "Ingestão de Dados",
    icon: IconUpload,
    href: "/operations/data",
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
  },
  {
    id: uniqueId(),
    title: "Usuários",
    icon: IconUsers,
    href: "/settings/users",
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
