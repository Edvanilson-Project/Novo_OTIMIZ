// Profile dropdown
interface ProfileType {
  href: string;
  title: string;
  subtitle: string;
  icon: string;
}

const profile: ProfileType[] = [
  {
    href: "/apps/user-profile/profile",
    title: "Meu Perfil",
    subtitle: "Configurações de Conta",
    icon: "/images/svgs/icon-account.svg",
  },
  {
    href: "/apps/email",
    title: "Minha Caixa",
    subtitle: "Mensagens & Emails",
    icon: "/images/svgs/icon-inbox.svg",
  },
  {
    href: "/apps/kanban",
    title: "Minhas Tarefas",
    subtitle: "To-do e Tarefas Diárias",
    icon: "/images/svgs/icon-tasks.svg",
  },
];

export { profile };
