"use client";

import { useParams } from "next/navigation";
import Workflows from "../../../../../components/workflows";

export default function WorkflowPage() {
  const { org, workflowId } = useParams<{ org: string; workflowId: string }>();
  return <Workflows key={`${org}:${workflowId}`} orgId={org} workflowId={workflowId} />;
}
