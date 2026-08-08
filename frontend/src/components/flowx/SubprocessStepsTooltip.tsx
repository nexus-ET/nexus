import type { ReactNode } from 'react';
import { subprocessSteps } from '../../utils/flowxSubprocessSteps';
import FlowxStepsTooltip from './FlowxStepsTooltip';

type SubprocessStepsTooltipProps = {
  title: string;
  children: ReactNode;
  disabled?: boolean;
  code?: string;
  /** Saved steps from the country workflow brick (one action per item). */
  actionSteps?: string[] | null;
};

/** Click-to-open panel listing short action steps for a sub-process. */
export default function SubprocessStepsTooltip({
  title,
  children,
  disabled,
  code,
  actionSteps,
}: SubprocessStepsTooltipProps) {
  return (
    <FlowxStepsTooltip
      steps={subprocessSteps(title, actionSteps)}
      disabled={disabled}
      code={code}
      name={title}
      kind="Sub-process"
    >
      {children}
    </FlowxStepsTooltip>
  );
}
