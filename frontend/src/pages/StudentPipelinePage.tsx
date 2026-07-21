import { Navigate, useParams } from 'react-router-dom';
import ProspectsPage from './ProspectsPage';
import { studentPipelineBySlug } from '../config/studentPipelineNav';

export default function StudentPipelinePage() {
  const { pipelineSlug } = useParams<{ pipelineSlug: string }>();
  const config = pipelineSlug ? studentPipelineBySlug(pipelineSlug) : undefined;

  if (!config) {
    return <Navigate to="/students/counselling" replace />;
  }

  return (
    <ProspectsPage
      pageTitle={config.label}
      statusCategory={config.category}
      basePath={config.path}
    />
  );
}
