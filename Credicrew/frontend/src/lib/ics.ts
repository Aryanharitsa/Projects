// Minimal RFC 5545 iCalendar generator.
//
// Closes the long-standing roadmap item: "iCal export for an Interview
// status with proposed slots." Used by the Decision Studio's slot-proposer
// to hand recruiters a `.ics` they can drop into Gmail / Outlook / Apple
// Calendar without leaving Credicrew.
//
// We intentionally do not pull a 200 kB iCal lib for what's a few lines
// of text — but we *do* respect the bits that actually matter (CRLF, UTC
// Z-suffixed DTSTART/DTEND, line-folding at 75 octets, `\` and `,` and
// `;` and newline escaping in TEXT properties, stable UIDs).
//
// Pure functions. Mirrored on the backend in `app/services/ics.py`.

export type SlotInput = {
  uid?: string;
  startUtcMs: number;
  durationMin: number;
  summary: string;
  description?: string;
  location?: string;
  organizer?: { name?: string; email?: string };
  attendees?: { name?: string; email: string }[];
};

const PRODID = '-//Credicrew//Decision Studio 0.5//EN';

function pad(n: number, w = 2): string {
  return String(n).padStart(w, '0');
}

/** RFC 5545 UTC date-time form: 19970714T170000Z */
export function formatIcsUtc(epochMs: number): string {
  const d = new Date(epochMs);
  return (
    `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}` +
    `T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}Z`
  );
}

/** Escape the four reserved chars in TEXT-typed properties. */
function escapeText(value: string): string {
  return value
    .replace(/\\/g, '\\\\')
    .replace(/\n/g, '\\n')
    .replace(/,/g, '\\,')
    .replace(/;/g, '\\;');
}

/** Fold a content line at 75 octets per RFC 5545 §3.1.
 *  Continuation lines start with a single space.
 *  Most modern parsers tolerate longer lines, but Outlook still respects
 *  the wrap, so we do it. */
function fold(line: string): string {
  if (line.length <= 75) return line;
  const out: string[] = [];
  let i = 0;
  while (i < line.length) {
    const chunk = i === 0 ? line.slice(i, i + 75) : ' ' + line.slice(i, i + 74);
    out.push(chunk);
    i += i === 0 ? 75 : 74;
  }
  return out.join('\r\n');
}

function defaultUid(slot: SlotInput): string {
  // Stable per-slot — derived from start time + summary hash so re-exports
  // overwrite calendar entries cleanly.
  let h = 0;
  for (const c of slot.summary) h = ((h << 5) - h + c.charCodeAt(0)) | 0;
  return `credicrew-${slot.startUtcMs}-${(h >>> 0).toString(36)}@credicrew.local`;
}

function buildEvent(slot: SlotInput, dtStamp: string): string[] {
  const dtStart = formatIcsUtc(slot.startUtcMs);
  const dtEnd = formatIcsUtc(slot.startUtcMs + slot.durationMin * 60_000);
  const uid = slot.uid ?? defaultUid(slot);

  const lines: string[] = ['BEGIN:VEVENT'];
  lines.push(`UID:${escapeText(uid)}`);
  lines.push(`DTSTAMP:${dtStamp}`);
  lines.push(`DTSTART:${dtStart}`);
  lines.push(`DTEND:${dtEnd}`);
  lines.push(`SUMMARY:${escapeText(slot.summary)}`);
  if (slot.description) lines.push(`DESCRIPTION:${escapeText(slot.description)}`);
  if (slot.location) lines.push(`LOCATION:${escapeText(slot.location)}`);
  if (slot.organizer) {
    const cn = slot.organizer.name ? `;CN=${escapeText(slot.organizer.name)}` : '';
    if (slot.organizer.email) lines.push(`ORGANIZER${cn}:mailto:${slot.organizer.email}`);
  }
  for (const a of slot.attendees ?? []) {
    const cn = a.name ? `;CN=${escapeText(a.name)}` : '';
    lines.push(`ATTENDEE${cn};ROLE=REQ-PARTICIPANT;RSVP=TRUE:mailto:${a.email}`);
  }
  lines.push('STATUS:CONFIRMED');
  lines.push('END:VEVENT');
  return lines;
}

/** Build a single VCALENDAR with N VEVENTs. CRLF-terminated. */
export function buildCalendar(slots: SlotInput[]): string {
  const dtStamp = formatIcsUtc(Date.now());
  const lines: string[] = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    `PRODID:${PRODID}`,
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
  ];
  for (const slot of slots) lines.push(...buildEvent(slot, dtStamp));
  lines.push('END:VCALENDAR');
  return lines.map(fold).join('\r\n') + '\r\n';
}

/** Trigger a download of the .ics blob. Caller picks the filename. */
export function downloadIcs(filename: string, ics: string): void {
  if (typeof window === 'undefined') return;
  const blob = new Blob([ics], { type: 'text/calendar;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(url);
    a.remove();
  }, 0);
}

// ---------- slot proposer ----------

export type ProposalOptions = {
  /** First slot at or after this epoch ms. Defaults to next workday 10:00 local. */
  earliestMs?: number;
  /** Number of business days to scan. Default 7. */
  daysAhead?: number;
  /** Slots per business day. Default 2 (10:00 + 14:00 local). */
  slotsPerDay?: number;
  /** Hours of day to propose (24h, local). Default [10, 14, 16]. */
  hours?: number[];
  /** Minutes per slot. Default 60. */
  durationMin?: number;
  /** Hard cap on number of slots returned. Default 5. */
  maxSlots?: number;
};

/** Propose interview slots, skipping weekends and avoiding the past.
 *  All times are computed in the *local* tz of the running browser, then
 *  serialised in UTC at .ics build time so attendees in any zone see the
 *  same wall clock as the recruiter intended. */
export function proposeSlots(opts: ProposalOptions = {}): number[] {
  const {
    daysAhead = 7,
    hours = [10, 14, 16],
    slotsPerDay = 2,
    maxSlots = 5,
  } = opts;
  const now = new Date();

  const start = opts.earliestMs ? new Date(opts.earliestMs) : (() => {
    // Default earliest = today's first hour-of-day if still in future, else tomorrow
    const d = new Date(now);
    const earliestHour = hours[0] ?? 10;
    d.setHours(earliestHour, 0, 0, 0);
    if (d.getTime() <= now.getTime() + 30 * 60_000) {
      d.setDate(d.getDate() + 1);
    }
    return d;
  })();

  const out: number[] = [];
  const cursor = new Date(start);
  cursor.setHours(0, 0, 0, 0);

  for (let d = 0; d < daysAhead && out.length < maxSlots; d += 1) {
    const day = new Date(cursor);
    day.setDate(day.getDate() + d);
    const wd = day.getDay();
    if (wd === 0 || wd === 6) continue; // skip weekends

    let placedToday = 0;
    for (const h of hours) {
      if (placedToday >= slotsPerDay || out.length >= maxSlots) break;
      const slot = new Date(day);
      slot.setHours(h, 0, 0, 0);
      if (slot.getTime() < now.getTime() + 30 * 60_000) continue;
      out.push(slot.getTime());
      placedToday += 1;
    }
  }
  return out;
}

/** Friendly "Wed Sep 4 · 10:00" formatter for the UI. */
export function formatSlotLabel(epochMs: number): string {
  const d = new Date(epochMs);
  const wk = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][d.getDay()];
  const mo = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getMonth()];
  return `${wk} ${mo} ${d.getDate()} · ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
