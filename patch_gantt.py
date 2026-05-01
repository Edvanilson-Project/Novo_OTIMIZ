import re

with open("frontend/src/app/(DashboardLayout)/operations/planner/_components/TabGantt.tsx", "r") as f:
    code = f.read()

# 1. Update EventKind enum
code = code.replace(
    "export type EventKind = 'soltura' | 'viagem' | 'recolhimento' | 'descanso';",
    "export type EventKind = 'inicio_jornada' | 'fim_jornada' | 'soltura' | 'viagem' | 'recolhimento' | 'descanso' | 'deslocamento_operacional' | 'troca_motorista';"
)

# 2. Update EVENT_CONFIG
old_config = """const EVENT_CONFIG: Record<EventKind, { label: string; color: 'success' | 'primary' | 'error' | 'warning'; icon: React.ReactNode }> = {
  soltura:       { label: 'Soltura',         color: 'success', icon: <IconMapPin size={14} /> },
  viagem:        { label: 'Viagem',          color: 'primary', icon: <IconBus size={14} /> },
  recolhimento:  { label: 'Recolhimento',    color: 'error',   icon: <IconFlag size={14} /> },
  descanso:      { label: 'Descanso/Refeição', color: 'warning', icon: <IconCoffee size={14} /> },
};"""

new_config = """const EVENT_CONFIG: Record<EventKind, { label: string; color: 'success' | 'primary' | 'error' | 'warning' | 'default' | 'info' | 'secondary'; icon: React.ReactNode }> = {
  inicio_jornada:  { label: 'Início de jornada', color: 'info', icon: <IconCoffee size={14} /> },
  fim_jornada:     { label: 'Fim de jornada', color: 'info', icon: <IconCoffee size={14} /> },
  soltura:         { label: 'Soltura',         color: 'success', icon: <IconMapPin size={14} /> },
  viagem:          { label: 'Viagem',          color: 'primary', icon: <IconBus size={14} /> },
  recolhimento:    { label: 'Recolhimento',    color: 'error',   icon: <IconFlag size={14} /> },
  descanso:        { label: 'Descanso/Refeição', color: 'warning', icon: <IconCoffee size={14} /> },
  deslocamento_operacional: { label: 'Deslocamento oper.', color: 'default', icon: <IconBus size={14} /> },
  troca_motorista: { label: 'Troca motorista', color: 'default', icon: <IconUsers size={14} /> },
};"""
code = code.replace(old_config, new_config)


# 3. Insert `buildEventsFromSegments` after `buildEvents` ends
build_events_from_segments = """
// ─── Helper: build PlanEvent[] correctly directly from duty_time_segments ───
function buildEventsFromSegments(
  dutySegments: any[],
  dutyId: number | undefined,
  terminalMap: Map<number, Terminal>,
  tripById: Map<number, any>,
  blockId?: number
): PlanEvent[] {
  const events: PlanEvent[] = [];

  for (const seg of dutySegments) {
    const type = seg.type ?? seg.event_type;
    const start = Number(seg.start ?? 0);
    const end = Number(seg.end ?? start);
    const dur = end - start;

    let kind: EventKind | null = null;
    let intervalKind: IntervalKind | undefined;

    if (type === 'commercial_trip') kind = 'viagem';
    else if (type === 'pullout' || type === 'vehicle_pullout') kind = 'soltura';
    else if (type === 'pullback' || type === 'vehicle_pullback') kind = 'recolhimento';
    else if (type === 'idle' || type === 'driver_idle') { kind = 'descanso'; intervalKind = 'espera'; }
    else if (type === 'normal_break') { kind = 'descanso'; intervalKind = 'refeicao'; }
    else if (type === 'mandatory_rest') { kind = 'descanso'; intervalKind = 'descanso'; }
    else if (type === 'duty_start') kind = 'inicio_jornada';
    else if (type === 'duty_end') kind = 'fim_jornada';
    else if (type === 'deadhead') kind = 'deslocamento_operacional';
    else if (type === 'driver_change') kind = 'troca_motorista';

    if (!kind) continue;

    // Fetch trip if possible to get line names
    let trip = null;
    let tid = null;
    if (Array.isArray(seg.trip_ids) && seg.trip_ids.length > 0) {
      tid = Number(seg.trip_ids[0]);
      trip = tripById.get(tid);
    } else if (seg.tripId || seg.trip_id) {
      tid = Number(seg.tripId ?? seg.trip_id);
      trip = tripById.get(tid);
    }

    const tName = (id?: number | string) =>
      id != null ? (terminalMap.get(Number(id))?.shortName ?? terminalMap.get(Number(id))?.name ?? `T${id}`) : '—';

    let color = trip?.color;
    if (kind === 'descanso') {
      color = intervalKind === 'refeicao' ? '#2e7d32' : intervalKind === 'descanso' ? '#ffc107' : '#90a4ae';
    }

    events.push({
      kind,
      tripId: tid ?? undefined,
      linha: trip?.lineCode ?? String(trip?.lineId ?? '—'),
      sentido: trip?.direction ?? trip?.sentido ?? '—',
      inicio: start,
      chegada: end,
      origemName: tName(seg.location_start ?? seg.location ?? trip?.origin_id),
      destinoName: tName(seg.location_end ?? seg.location ?? trip?.destination_id),
      km: Number(seg.distance_km ?? trip?.distance_km ?? 0),
      duracao: dur,
      gapMinutes: kind === 'descanso' ? dur : undefined,
      intervalKind,
      vehicleId: blockId ?? seg.block_id,
      dutyId,
      color,
    });
  }

  return events;
}
"""

if "buildEventsFromSegments" not in code:
    findStr = "  return events;\n}"
    idx = code.find(findStr)
    if idx != -1:
        code = code[:idx + len(findStr)] + "\n" + build_events_from_segments + code[idx + len(findStr):]
    else:
        print("Could not find insertion point for buildEventsFromSegments")


# 4. Patch `dutyGroups` calculation line ~900 to use `buildEventsFromSegments` if available
duty_groups_old = """      const events = buildEvents(dutyTrips, terminalMap, lineByCode, intervalPolicy, undefined, dutyId, includeSoltura, includeRecolhimento);"""
duty_groups_new = """
      let events: PlanEvent[] = [];
      const segments = duty.duty_time_segments;
      if (segments && segments.length > 0) {
        events = buildEventsFromSegments(segments, dutyId, terminalMap, tripById);
      } else {
        events = buildEvents(dutyTrips, terminalMap, lineByCode, intervalPolicy, undefined, dutyId, includeSoltura, includeRecolhimento);
      }
"""
code = code.replace(duty_groups_old, duty_groups_new)

# 5. Fix EventKindChip gap resolution logic: we don't need gap>=60 locally, we respect the segment type (intervalKind provides the exact type)
old_chip = """function EventKindChip({ kind, gap, intervalKind }: { kind: EventKind; gap?: number; intervalKind?: IntervalKind }) {
  const cfg = EVENT_CONFIG[kind];
  if (kind === 'descanso' && gap != null) {
    const resolvedKind: IntervalKind = intervalKind ?? (gap >= 60 ? 'refeicao' : 'espera');
    return (
      <Chip
        size="small"
        icon={resolvedKind === 'espera' ? undefined : <IconCoffee size={12} />}
        label={eventDisplayLabel({ kind, gapMinutes: gap, intervalKind: resolvedKind })}
        color={resolvedKind === 'refeicao' ? 'success' : resolvedKind === 'descanso' ? 'warning' : 'default'}
        variant="outlined"
        sx={{ fontWeight: 700 }}
      />
    );
  }"""
new_chip = """function EventKindChip({ kind, gap, intervalKind }: { kind: EventKind; gap?: number; intervalKind?: IntervalKind }) {
  const cfg = EVENT_CONFIG[kind];
  if (kind === 'descanso' && gap != null) {
    const resolvedKind: IntervalKind = intervalKind ?? 'espera';
    return (
      <Chip
        size="small"
        icon={resolvedKind === 'espera' ? undefined : <IconCoffee size={12} />}
        label={eventDisplayLabel({ kind, gapMinutes: gap, intervalKind: resolvedKind })}
        color={resolvedKind === 'refeicao' ? 'success' : resolvedKind === 'descanso' ? 'warning' : 'default'}
        variant="outlined"
        sx={{ fontWeight: 700 }}
      />
    );
  }"""
if old_chip in code:
    code = code.replace(old_chip, new_chip)
else:
    # Just in case, let's use regex
    code = re.sub(
        r"const resolvedKind: IntervalKind = intervalKind \?\? \(gap >= 60 \? 'refeicao' : 'espera'\);",
        "const resolvedKind: IntervalKind = intervalKind ?? 'espera';",
        code
    )

with open("frontend/src/app/(DashboardLayout)/operations/planner/_components/TabGantt.tsx", "w") as f:
    f.write(code)

print("Gantt logic locally patched.")
