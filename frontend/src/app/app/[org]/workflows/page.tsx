"use client";

import { useParams } from "next/navigation";
import Workflows from "../../../../components/workflows";

export default function WorkflowsPage() {
  const { org } = useParams<{ org: string }>();
  return <Workflows key={org} orgId={org} />;
}
