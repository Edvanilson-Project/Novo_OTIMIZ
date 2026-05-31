// Profile dropdown
interface ProfileType {
  href: string;
  title: string;
  subtitle: string;
  icon: string;
}

// Atalhos reais da conta no dropdown de perfil. As rotas de template
// (/apps/email, /apps/kanban, /apps/user-profile) foram removidas por não
// existirem neste produto (geravam link morto/404).
const profile: ProfileType[] = [
  {
    href: "/settings/general",
    title: "Ajustes",
    subtitle: "Preferências da conta",
    icon: "/images/svgs/icon-account.svg",
  },
];

export { profile };
