"use client";

import React from "react";
import FullCalendar from "@fullcalendar/react";
import resourceTimelinePlugin from "@fullcalendar/resource-timeline";
import interactionPlugin from "@fullcalendar/interaction";
import { Box, useTheme, styled } from "@mui/material";

// A Âncora Temporal CRÍTICA sugerida pelo Arquiteto
const ANCHOR_DATE = "2000-01-01";

const CalendarWrapper = styled(Box)(({ theme }) => ({
  "& .fc": {
    fontFamily: theme.typography.fontFamily,
    backgroundColor: theme.palette.background.paper,
    color: theme.palette.text.primary,
    border: "none",
    borderRadius: theme.shape.borderRadius,
  },
  "& .fc-theme-standard td, & .fc-theme-standard th": {
    borderColor: theme.palette.divider,
  },
  "& .fc-timeline-slot-label": {
    backgroundColor: theme.palette.action.hover,
    fontSize: "0.8rem",
  },
  "& .fc-resource-timeline-divider": {
    backgroundColor: theme.palette.divider,
  },
  "& .fc-timeline-event": {
    border: "none",
    borderRadius: "4px",
    padding: "2px",
    boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
  },
  "& .fc-timeline-lane-frame": {
    backgroundColor: "transparent",
  },
}));

interface GanttChartProps {
  resources: { id: string; title: string }[];
  events: {
    id: string;
    resourceId: string;
    start: string;
    end: string;
    title: string;
    color?: string;
    extendedProps?: any;
  }[];
  onEventDrop?: (tripId: number, targetBlockId: number) => void;
}

const GanttChart: React.FC<GanttChartProps> = ({ resources, events, onEventDrop }) => {
  const theme = useTheme();

  return (
    <CalendarWrapper>
      <FullCalendar
        plugins={[resourceTimelinePlugin, interactionPlugin]}
        initialView="resourceTimelineDay"
        headerToolbar={{
          left: "prev,next today",
          center: "title",
          right: "resourceTimelineDay,resourceTimelineWeek",
        }}
        resources={resources}
        events={events}
        resourceAreaHeaderContent="Recurso (Bloco/Escala)"
        resourceAreaWidth="20%"
        slotMinTime="00:00:00"
        slotMaxTime="30:00:00" // Jornada estendida (Módulo 7)
        height="auto"
        aspectRatio={1.8}
        nowIndicator={true}
        editable={true}
        eventResourceEditable={true}
        eventStartEditable={false} // Mantemos o horário original por enquanto
        eventDurationEditable={false}
        selectable={true}
        eventDrop={(info) => {
          const tripId = parseInt(info.event.id.split("-")[1]);
          const targetBlockId = parseInt(info.newResource?.id || "0");
          if (onEventDrop) onEventDrop(tripId, targetBlockId);
        }}
        eventBackgroundColor={theme.palette.primary.main}
        eventBorderColor={theme.palette.primary.dark}
        locale="pt-br"
        buttonText={{
          today: "Hoje",
          day: "Dia",
          week: "Semana",
        }}
        initialDate={ANCHOR_DATE} // Forçar a data âncora
      />
    </CalendarWrapper>
  );
};

export default GanttChart;
