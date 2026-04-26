import MissionControl from "@/components/marvin/MissionControl";

export default function MissionPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <ResolvedMissionPage params={params} />;
}

async function ResolvedMissionPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <MissionControl missionId={id} />;
}
