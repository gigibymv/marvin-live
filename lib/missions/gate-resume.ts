export type GateResumeResult = { status?: string | null };

export function shouldAttachResumeStream(result: GateResumeResult | null | undefined): boolean {
  return (
    result?.status === "resumed" ||
    result?.status === "resumed_detached" ||
    result?.status === "resume_pending"
  );
}
