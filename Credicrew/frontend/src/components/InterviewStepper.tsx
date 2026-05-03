'use client';
import {
  STAGES,
  STAGE_LABEL,
  STAGE_TONE,
  type InterviewRecord,
  type InterviewStage,
} from '@/lib/interview';

const TONE_BG: Record<string, string> = {
  sky: 'bg-sky-400',
  indigo: 'bg-indigo-400',
  violet: 'bg-violet-400',
  amber: 'bg-amber-400',
  emerald: 'bg-emerald-400',
};

const TONE_TEXT: Record<string, string> = {
  sky: 'text-sky-200 border-sky-400/40 bg-sky-400/10',
  indigo: 'text-indigo-200 border-indigo-400/40 bg-indigo-400/10',
  violet: 'text-violet-200 border-violet-400/40 bg-violet-400/10',
  amber: 'text-amber-200 border-amber-400/40 bg-amber-400/10',
  emerald: 'text-emerald-200 border-emerald-400/40 bg-emerald-400/10',
};

const STATUS_LABEL = {
  planned: 'planned',
  in_progress: 'in progress',
  done: 'done',
} as const;

export default function InterviewStepper({
  record,
  active,
  onPick,
}: {
  record: InterviewRecord;
  active: InterviewStage;
  onPick: (s: InterviewStage) => void;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-[11px] uppercase tracking-wider text-white/50">
          Stages
        </div>
        <div className="text-[11px] text-white/40">
          {record.questions.length} prompts · {record.rubric.length} rubric dims
        </div>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {STAGES.map((s, i) => {
          const isActive = s === active;
          const stage = record.stages.find(x => x.stage === s)!;
          const tone = STAGE_TONE[s];
          const ratedHere = stage.scores.filter(sc => sc.rating !== null).length;
          const totalHere = stage.scores.length;
          const qCount = record.questions.filter(q => q.stage === s).length;
          return (
            <button
              key={s}
              onClick={() => onPick(s)}
              className={`group relative w-full overflow-hidden rounded-xl border px-3 py-3 text-left transition ${
                isActive
                  ? 'border-white/20 bg-white/[0.06]'
                  : 'border-white/10 bg-white/[0.02] hover:bg-white/[0.04]'
              }`}
            >
              <div className="flex items-center gap-2">
                <span
                  className={`grid h-5 w-5 place-items-center rounded-full text-[10px] font-semibold text-black ${TONE_BG[tone]}`}
                >
                  {i + 1}
                </span>
                <span className="text-sm font-medium text-white">
                  {STAGE_LABEL[s]}
                </span>
              </div>
              <div className="mt-2 flex items-center gap-2 text-[11px] text-white/55">
                <span className={`rounded-full border px-1.5 py-0.5 ${TONE_TEXT[tone]}`}>
                  {STATUS_LABEL[stage.status]}
                </span>
                <span>{qCount} q</span>
                <span>·</span>
                <span>{ratedHere}/{totalHere} rated</span>
              </div>
              {isActive && (
                <span
                  className={`absolute inset-x-0 bottom-0 h-[2px] ${TONE_BG[tone]}`}
                />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
