import { Check } from 'lucide-react';

type StageStepperProps = {
  stages: string[];
  activeStage: number;
  completedStages?: number[];
};

export function StageStepper({ stages, activeStage, completedStages = [] }: StageStepperProps) {
  return (
    <div className="flex w-full items-center gap-2 overflow-x-auto rounded-2xl border border-white/10 bg-white/[0.04] p-3">
      {stages.map((stage, index) => {
        const completed = completedStages.includes(index);
        const active = index === activeStage;
        return (
          <div className="flex min-w-fit flex-1 items-center gap-2" key={stage}>
            <div
              className={[
                'flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-xs font-bold',
                completed
                  ? 'border-emerald-300/30 bg-emerald-400/20 text-emerald-100'
                  : active
                    ? 'border-white/70 bg-white/10 text-white'
                    : 'border-white/10 bg-white/5 text-[var(--text-soft)]',
              ].join(' ')}
            >
              {completed ? <Check size={15} /> : index + 1}
            </div>
            <span className={active ? 'text-sm font-semibold text-white' : 'text-sm text-[var(--text-muted)]'}>{stage}</span>
            {index < stages.length - 1 && <div className="mx-2 h-px flex-1 bg-white/10" />}
          </div>
        );
      })}
    </div>
  );
}
