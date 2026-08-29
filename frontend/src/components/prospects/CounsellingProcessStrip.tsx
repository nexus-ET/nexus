import PipelineProcessStrip from './PipelineProcessStrip';
import {
  pipelineProcessConfig,
  usePipelineProcessNodes,
  type PipelineProcessNode,
} from '../../utils/studentPipelineProcess';

export type CounsellingProcessNode = PipelineProcessNode;

const counsellingConfig = pipelineProcessConfig('/students/counselling')!;

export function useCounsellingProcessNodes(): CounsellingProcessNode[] {
  return usePipelineProcessNodes(counsellingConfig);
}

export default function CounsellingProcessStrip({
  activeCode,
}: {
  activeCode?: string;
}) {
  return <PipelineProcessStrip config={counsellingConfig} activeCode={activeCode} />;
}
