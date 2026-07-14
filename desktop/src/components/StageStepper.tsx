import { Check } from 'lucide-react';

type StageStepperProps = {
  stages: string[];
  activeStage: number;
  completedStages?: number[];
  onStageChange?: (index: number) => void;
};

export function StageStepper({ stages, activeStage, completedStages = [], onStageChange }: StageStepperProps) {
  return (
    <div className="flex w-full items-center gap-2 overflow-x-auto rounded-2xl border border-white/10 bg-white/[0.04] p-3">
      {stages.map((stage, index) => {
        const completed = completedStages.includes(index);
        const active = index === activeStage;
        return (
          <div className="flex min-w-fit flex-1 items-center gap-2" key={stage}>
            <button
              aria-current={active ? 'step' : undefined}
              className={[
                'flex min-w-fit cursor-pointer items-center gap-2 rounded-xl border px-3 py-2 text-xs font-semibold transition',
                active
                  ? 'border-sky-300/60 bg-sky-300/15 text-white'
                  : completed
                    ? 'border-emerald-300/30 bg-emerald-400/20 text-emerald-100'
                    : 'border-transparent bg-transparent text-[var(--text-muted)] hover:border-white/10 hover:bg-white/5 hover:text-white',
              ].join(' ')}
              onClick={() => onStageChange?.(index)}
              type="button"
            >
              <span className="flex h-5 w-5 items-center justify-center rounded-full border border-current/25 text-[10px]">
                {completed && !active ? <Check size={12} /> : index + 1}
              </span>
              {stage}
            </button>
            {index < stages.length - 1 && <div className="mx-2 h-px flex-1 bg-white/10" />}
          </div>
        );
      })}
    </div>
  );
}
