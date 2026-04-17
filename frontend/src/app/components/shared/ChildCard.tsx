

"use client";
import React from "react";

import { Card, CardHeader, CardContent, Divider, Box } from "@mui/material";

type Props = {
  title?: string;
  children: React.ReactNode;
  codeModel?: React.ReactNode;
  code?: string;
  footer?: string | React.ReactNode;
};

const ChildCard = ({ title, children, codeModel, footer }: Props) => (
  <Card
    sx={{ padding: 0, borderColor: (theme) => theme.palette.divider }}
    variant="outlined"
  >
    {title ? (
      <>
        <CardHeader title={title} />
        <Divider />{" "}
      </>
    ) : (
      ""
    )}

    <CardContent>{children}</CardContent>

    {footer ? (
      <>
        <Divider />
        <Box sx={{ p: 3 }}>{footer}</Box>
      </>
    ) : (
      ""
    )}
    {codeModel && <Box>{codeModel}</Box>}
  </Card>
);

export default ChildCard;
