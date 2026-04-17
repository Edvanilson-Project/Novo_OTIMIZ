'use client'
import Card from '@mui/material/Card'
import { CustomizerContext } from '@/app/context/customizerContext';
import { useContext } from 'react';

type Props = {
  children: React.ReactNode;
};

const AppCard = ({ children }: Props) => {
  const { isCardShadow } = useContext(CustomizerContext);

  return (
    <Card
      sx={{ display: 'flex', p: 0 }}
      elevation={isCardShadow ? 9 : 0}
      variant={!isCardShadow ? 'outlined' : undefined}
    >
      {children}
    </Card>
  );
};

export default AppCard;
