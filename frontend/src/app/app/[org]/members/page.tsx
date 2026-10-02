"use client";

import { useParams } from "next/navigation";
import Organizations from "../../../../components/organizations";

export default function MembersPage() {
  const { org } = useParams<{ org: string }>();
  return <Organizations key={org} orgId={org} />;
}
